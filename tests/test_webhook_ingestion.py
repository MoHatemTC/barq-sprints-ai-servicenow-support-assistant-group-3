import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from barq_support.dedup import check_and_set_dedup, extract_event_id
from barq_support.main import app
from barq_support.security import compute_hmac_signature, verify_hmac_signature
from barq_support.settings import get_settings


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def secret():
    return get_settings().servicenow_webhook_secret or "sample_secret_key_123"


# ==============================================================================
# 1. HMAC Verification Unit Tests
# ==============================================================================

def test_compute_and_verify_hmac_signature_valid(secret):
    body = b'{"incident_sys_id": "test_sys_123", "number": "INC001"}'
    sig = compute_hmac_signature(body, secret)
    # Plain hex
    verify_hmac_signature(body, sig, secret)
    # With sha256= prefix
    verify_hmac_signature(body, f"sha256={sig}", secret)


def test_verify_hmac_signature_tampered_body(secret):
    body = b'{"incident_sys_id": "test_sys_123"}'
    tampered = b'{"incident_sys_id": "test_sys_999"}'
    sig = compute_hmac_signature(body, secret)

    with pytest.raises(Exception) as exc_info:
        verify_hmac_signature(tampered, sig, secret)
    assert exc_info.value.status_code == 401
    assert "Invalid signature" in exc_info.value.detail


def test_verify_hmac_signature_missing_header(secret):
    body = b'{"incident_sys_id": "test_sys_123"}'
    with pytest.raises(Exception) as exc_info:
        verify_hmac_signature(body, None, secret)
    assert exc_info.value.status_code == 401
    assert "Missing X-Signature" in exc_info.value.detail


def test_verify_hmac_signature_missing_secret():
    body = b'{"incident_sys_id": "test_sys_123"}'
    with pytest.raises(Exception) as exc_info:
        verify_hmac_signature(body, "dummy_sig", "")
    assert exc_info.value.status_code == 401
    assert "secret not configured" in exc_info.value.detail


# ==============================================================================
# 2. Redis Dedup Gate Unit Tests
# ==============================================================================

def test_extract_event_id():
    assert extract_event_id({"incident_sys_id": "sys_abc"}) == "sys_abc"
    assert extract_event_id({"sys_id": "sys_def"}) == "sys_def"
    assert extract_event_id({"event_id": "evt_ghi"}) == "evt_ghi"
    # Precedence: event_id -> incident_sys_id -> sys_id
    assert extract_event_id({"event_id": "e1", "incident_sys_id": "s1"}) == "e1"
    assert extract_event_id({}) is None


def test_dedup_gate_atomic_setnx():
    mock_redis = MagicMock()
    # First time: setnx succeeds (returns True)
    mock_redis.set.return_value = True

    is_new = check_and_set_dedup("event_123", redis_client=mock_redis, ttl_seconds=86400)
    assert is_new is True
    mock_redis.set.assert_called_once_with("evt:event_123", "1", nx=True, ex=86400)

    # Second time (replay): setnx fails (returns False/None)
    mock_redis.set.reset_mock()
    mock_redis.set.return_value = False

    is_replay = check_and_set_dedup("event_123", redis_client=mock_redis, ttl_seconds=86400)
    assert is_replay is False
    mock_redis.set.assert_called_once_with("evt:event_123", "1", nx=True, ex=86400)


# ==============================================================================
# 3. Endpoint Integration Tests (POST /api/v1/events/servicenow)
# ==============================================================================

@patch("barq_support.api.events.ServiceNowClient")
@patch("barq_support.api.events.process_servicenow_event.delay")
@patch("barq_support.api.events.check_and_set_dedup")
def test_endpoint_valid_signed_request(mock_dedup, mock_delay, mock_sn_cls, client, secret):
    mock_dedup.return_value = True
    mock_task = MagicMock()
    mock_task.id = "celery-task-uuid-1234"
    mock_delay.return_value = mock_task
    mock_sn = MagicMock()
    mock_sn_cls.return_value = mock_sn

    payload = {
        "incident_sys_id": "47138238a9fe1981016e3762d1fd26d4",
        "number": "INC0000035",
        "short_description": "Network outage in HQ",
    }
    raw_bytes = json.dumps(payload).encode("utf-8")
    sig = compute_hmac_signature(raw_bytes, secret)

    response = client.post(
        "/api/v1/events/servicenow",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "X-Signature": sig},
    )

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "accepted"
    assert data["event_id"] == "47138238a9fe1981016e3762d1fd26d4"
    assert data["task_id"] == "celery-task-uuid-1234"
    assert data["deduplicated"] is False
    mock_sn.claim_incident.assert_called_once_with("47138238a9fe1981016e3762d1fd26d4")
    mock_delay.assert_called_once_with(payload)


@patch("barq_support.api.events.ServiceNowClient")
@patch("barq_support.api.events.process_servicenow_event.delay")
@patch("barq_support.api.events.check_and_set_dedup")
def test_endpoint_claims_incident_before_queueing_celery_task(mock_dedup, mock_delay, mock_sn_cls, client, secret):
    mock_dedup.return_value = True
    call_order = []
    mock_sn = MagicMock()
    mock_sn.claim_incident.side_effect = lambda sys_id: call_order.append("claim")
    mock_sn_cls.return_value = mock_sn
    mock_delay.side_effect = lambda p: (
        call_order.append("enqueue"),
        MagicMock(id="celery-task-seq-1"),
    )[1]

    payload = {
        "incident_sys_id": "sys_ordering_check",
        "number": "INC0009999",
    }
    raw_bytes = json.dumps(payload).encode("utf-8")
    sig = compute_hmac_signature(raw_bytes, secret)

    response = client.post(
        "/api/v1/events/servicenow",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "X-Signature": sig},
    )

    assert response.status_code == 202
    assert call_order == ["claim", "enqueue"]
    mock_sn.claim_incident.assert_called_once_with("sys_ordering_check")


@patch("barq_support.api.events.ServiceNowClient")
@patch("barq_support.api.events.sync_kb_article.delay")
@patch("barq_support.api.events.check_and_set_dedup")
def test_endpoint_kb_article_event_does_not_claim_incident(mock_dedup, mock_kb_delay, mock_sn_cls, client, secret):
    mock_dedup.return_value = True
    mock_kb_task = MagicMock()
    mock_kb_task.id = "kb-task-123"
    mock_kb_delay.return_value = mock_kb_task
    mock_sn = MagicMock()
    mock_sn_cls.return_value = mock_sn

    payload = {
        "article_id": "kb_sys_123",
        "operation": "updated",
    }
    raw_bytes = json.dumps(payload).encode("utf-8")
    sig = compute_hmac_signature(raw_bytes, secret)

    response = client.post(
        "/api/v1/events/servicenow",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "X-Signature": sig},
    )

    assert response.status_code == 202
    mock_kb_delay.assert_called_once_with(payload)
    mock_sn.claim_incident.assert_not_called()


@patch("barq_support.api.events.process_servicenow_event.delay")
@patch("barq_support.api.events.check_and_set_dedup")
def test_endpoint_replay_deduplication(mock_dedup, mock_delay, client, secret):
    mock_dedup.return_value = False  # Simulates existing key in Redis

    payload = {
        "incident_sys_id": "47138238a9fe1981016e3762d1fd26d4",
        "number": "INC0000035",
    }
    raw_bytes = json.dumps(payload).encode("utf-8")
    sig = compute_hmac_signature(raw_bytes, secret)

    response = client.post(
        "/api/v1/events/servicenow",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "X-Signature": sig},
    )

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "accepted"
    assert data["deduplicated"] is True
    # Confirm NO Celery task was enqueued on replay
    mock_delay.assert_not_called()


@patch("barq_support.api.events.process_servicenow_event.delay")
def test_endpoint_missing_signature(mock_delay, client):
    payload = {"incident_sys_id": "123"}
    raw_bytes = json.dumps(payload).encode("utf-8")

    response = client.post(
        "/api/v1/events/servicenow",
        content=raw_bytes,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 401
    assert "Missing X-Signature" in response.json()["detail"]
    mock_delay.assert_not_called()


@patch("barq_support.api.events.process_servicenow_event.delay")
def test_endpoint_tampered_signature(mock_delay, client, secret):
    payload = {"incident_sys_id": "123"}
    raw_bytes = json.dumps(payload).encode("utf-8")

    response = client.post(
        "/api/v1/events/servicenow",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "X-Signature": "invalid_sig_hex_000"},
    )

    assert response.status_code == 401
    assert "Invalid signature" in response.json()["detail"]
    mock_delay.assert_not_called()


@patch("barq_support.api.events.process_servicenow_event.delay")
def test_endpoint_malformed_json_after_valid_signature(mock_delay, client, secret):
    raw_bytes = b"not-a-valid-json{"
    sig = compute_hmac_signature(raw_bytes, secret)

    response = client.post(
        "/api/v1/events/servicenow",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "X-Signature": sig},
    )

    assert response.status_code == 400
    assert "Invalid JSON" in response.json()["detail"]
    mock_delay.assert_not_called()


# ==============================================================================
# 4. Celery Task Unit Tests (Claim First, Then Agent Hand-off)
# ==============================================================================

@patch("barq_support.tasks.process_incident")
@patch("barq_support.tasks.ServiceNowClient")
def test_celery_task_claims_before_agent(mock_sn_cls, mock_process_incident):
    from barq_support.tasks import process_servicenow_event

    mock_sn = MagicMock()
    mock_sn.claim_incident.return_value = {
        "result": {"x_2215697_ai_ser_0_ai_status": "in_progress"}
    }
    mock_sn_cls.return_value = mock_sn

    call_order = []
    mock_sn.claim_incident.side_effect = lambda sys_id: (
        call_order.append("claim"),
        {"result": {"x_2215697_ai_ser_0_ai_status": "in_progress"}},
    )[1]
    mock_process_incident.side_effect = lambda p: (
        call_order.append("agent"),
        {"status": "suggested"},
    )[1]

    payload = {"incident_sys_id": "test_sys_999", "number": "INC999"}
    result = process_servicenow_event.run(payload)

    # Verify claim happened before agent
    assert call_order == ["claim", "agent"]
    mock_sn.claim_incident.assert_called_once_with("test_sys_999")
    mock_process_incident.assert_called_once_with({
        "incident_sys_id": "test_sys_999",
        "number": "INC999",
        "sys_id": "test_sys_999",
    })
    assert result["status"] == "success"
    assert result["claimed"] is True


@patch("barq_support.tasks.process_incident")
@patch("barq_support.tasks.ServiceNowClient")
def test_celery_task_aborts_agent_if_claim_fails(mock_sn_cls, mock_process_incident):
    from barq_support.tasks import process_servicenow_event

    mock_sn = MagicMock()
    mock_sn.claim_incident.side_effect = RuntimeError("ServiceNow Table API failure")
    mock_sn_cls.return_value = mock_sn

    payload = {"sys_id": "test_sys_fail"}

    with pytest.raises(RuntimeError) as exc_info:
        process_servicenow_event.run(payload)

    assert "ServiceNow Table API failure" in str(exc_info.value)
    # The agent MUST NOT be invoked if the claim fails
    mock_process_incident.assert_not_called()
