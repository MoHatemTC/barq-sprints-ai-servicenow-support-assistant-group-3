from unittest.mock import MagicMock, Mock, patch

import httpx
import pytest

from barq_support.password_protection import (
    classify_password_presence,
    redact_known_patterns,
    sanitize_text_fields,
)
from barq_support.settings import Settings
from barq_support.worker import process_incident


def test_redact_known_patterns_masks_password_change():
    text = "The user changed password from old_secret123 to new_secret456!"
    result = redact_known_patterns(text)
    assert "old_secret123" not in result
    assert "new_secret456" not in result
    assert "[REDACTED]" in result


def test_redact_known_patterns_masks_credential_assignment():
    text = "Please use password: secretPassword! and token=abc123xyz"
    result = redact_known_patterns(text)
    assert "secretPassword!" not in result
    assert "abc123xyz" not in result
    assert "password: [REDACTED]" in result
    assert "token=[REDACTED]" in result


def test_redact_known_patterns_masks_natural_language_password():
    text = "The temporary password is MySecretPass2026 for login."
    result = redact_known_patterns(text)
    assert "MySecretPass2026" not in result
    assert "password is [REDACTED]" in result


def test_ollama_fallback_to_passthrough_when_unconfigured():
    settings = Settings(password_classifier_base_url="", password_classifier_model="")
    # Must return False and not raise RuntimeError
    assert classify_password_presence("password is test123", settings) is False


def test_ollama_fallback_to_passthrough_when_connection_fails():
    settings = Settings(
        password_classifier_base_url="http://localhost:11434",
        password_classifier_model="qwen2.5:1.5b",
    )
    with patch("httpx.post", side_effect=httpx.ConnectError("Connection refused")):
        assert classify_password_presence("password is test123", settings) is False


def test_ollama_returns_true_when_secret_detected():
    settings = Settings(
        password_classifier_base_url="http://localhost:11434",
        password_classifier_model="qwen2.5:1.5b",
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "message": {"content": '{"contains_secret": true}'}
    }
    with patch("httpx.post", return_value=mock_resp):
        assert classify_password_presence("test text", settings) is True


def test_sanitize_text_fields_redacts_incident_credentials():
    settings = Settings(password_classifier_base_url="")
    fields = {
        "short_description": "Password reset for user",
        "description": "User says password is Secret123! and needs help.",
    }
    sanitized = sanitize_text_fields(fields, settings)
    assert sanitized["short_description"] == "Password reset for user"
    assert "Secret123!" not in sanitized["description"]
    assert "[REDACTED]" in sanitized["description"]


def test_process_incident_masks_and_calls_servicenow_redact():
    mock_sn = Mock()
    mock_sn.get_incident.return_value = {
        "result": {
            "number": "INC009999",
            "sys_id": "incident_sys_id_123",
            "short_description": "VPN login failure",
            "description": "My password is SuperSecretPassword! please reset.",
            "category": "software",
        }
    }
    mock_sn.redact_incident_fields.return_value = {"status": "ok"}

    mock_qdrant = Mock()
    mock_agent_result = {"status": "suggested"}

    settings = Settings(password_classifier_base_url="")

    with (
        patch("barq_support.worker.get_settings", return_value=settings),
        patch("barq_support.worker.ServiceNowClient", return_value=mock_sn),
        patch("barq_support.worker.QdrantClient", return_value=mock_qdrant),
        patch("barq_support.worker.run_agent", return_value=mock_agent_result) as mock_run_agent,
    ):
        result = process_incident({"sys_id": "incident_sys_id_123"})

    assert result == mock_agent_result
    mock_sn.redact_incident_fields.assert_called_once()
    call_args = mock_sn.redact_incident_fields.call_args.kwargs
    assert call_args["sys_id"] == "incident_sys_id_123"
    assert "SuperSecretPassword!" not in call_args["fields"]["description"]
    assert "[REDACTED]" in call_args["fields"]["description"]

    # Verify agent receives the sanitized description
    agent_incident = mock_run_agent.call_args.kwargs["incident"]
    assert "[REDACTED]" in agent_incident["description"]
