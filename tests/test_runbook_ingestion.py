import json
from unittest.mock import MagicMock, patch

import pymupdf
import pytest
from fastapi.testclient import TestClient

from barq_support.ingestion.runbook_pdf import ingest_runbook_pdf
from barq_support.main import app
from barq_support.security import compute_hmac_signature
from barq_support.servicenow import ServiceNowClient
from barq_support.settings import get_settings
from barq_support.tasks import ingest_servicenow_attachment


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def secret():
    return get_settings().servicenow_webhook_secret or "sample_secret_key_123"


def signed_request(client, payload, secret):
    body = json.dumps(payload).encode("utf-8")
    signature = compute_hmac_signature(body, secret)
    return client.post(
        "/api/v1/documents/servicenow-attachment",
        content=body,
        headers={"Content-Type": "application/json", "X-Signature": signature},
    )


@patch("barq_support.api.events.ingest_servicenow_attachment.delay")
@patch("barq_support.api.events.check_and_set_dedup", return_value=True)
@patch("barq_support.api.events.get_redis_client")
def test_signed_pdf_attachment_is_queued(
    mock_redis, mock_dedup, mock_delay, client, secret
):
    mock_delay.return_value = MagicMock(id="runbook-task-123")
    payload = {
        "attachment_sys_id": "a" * 32,
        "file_name": "network-runbook.pdf",
        "table_sys_id": "1" * 32,
        "title": "Network recovery",
        "category": "network",
        "runbook_notes": "Restart the gateway after recovery.",
    }

    response = signed_request(client, payload, secret)

    assert response.status_code == 202
    assert response.json()["task_id"] == "runbook-task-123"
    mock_delay.assert_called_once_with(payload)
    assert mock_dedup.call_args.kwargs["event_id"] == f"runbook:{'a' * 32}"
    mock_redis.assert_called_once()


@patch("barq_support.api.events.ingest_servicenow_attachment.delay")
@patch("barq_support.api.events.check_and_set_dedup", return_value=False)
@patch("barq_support.api.events.get_redis_client")
def test_duplicate_attachment_event_is_not_queued(
    mock_redis, mock_dedup, mock_delay, client, secret
):
    response = signed_request(
        client,
        {
            "attachment_sys_id": "b" * 32,
            "file_name": "guide.pdf",
            "table_sys_id": "2" * 32,
        },
        secret,
    )

    assert response.status_code == 202
    assert response.json()["deduplicated"] is True
    mock_delay.assert_not_called()


def test_non_pdf_attachment_is_rejected(client, secret):
    response = signed_request(
        client,
        {
            "attachment_sys_id": "c" * 32,
            "file_name": "guide.txt",
            "table_sys_id": "3" * 32,
        },
        secret,
    )

    assert response.status_code == 422


@patch("barq_support.ingestion.runbook_pdf.upsert_chunks")
@patch("barq_support.ingestion.runbook_pdf.ensure_collection")
@patch("barq_support.ingestion.runbook_pdf.get_client")
@patch(
    "barq_support.ingestion.runbook_pdf.embed_texts",
    return_value=[[0.1] * 3072, [0.2] * 3072],
)
@patch("barq_support.ingestion.runbook_pdf.sanitize_chunk_fields")
def test_pdf_text_is_extracted_chunked_embedded_and_indexed(
    mock_sanitize, mock_embed, mock_get_client, mock_ensure, mock_upsert
):
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Restart the network gateway after maintenance.")
    second_page = document.new_page()
    second_page.insert_text((72, 72), "Confirm VPN access from a remote network.")
    pdf_bytes = document.tobytes()

    result = ingest_runbook_pdf(
        "d" * 32,
        "gateway.pdf",
        pdf_bytes,
        title="Gateway recovery",
        category="network",
        runbook_notes="Restart the gateway after recovery.",
    )

    assert result["status"] == "upserted"
    assert result["chunks"] == 1
    assert mock_sanitize.call_count == 1
    mock_embed.assert_called_once()
    mock_ensure.assert_called_once_with(mock_get_client.return_value)
    mock_upsert.assert_called_once()
    chunks = mock_upsert.call_args.args[1]
    assert result["pages"] == 2
    assert len(chunks) == 1
    assert all(not chunk["text"].startswith("Page ") for chunk in chunks)
    assert chunks[0]["metadata"]["source_type"] == "pdf"
    assert chunks[0]["metadata"]["title"] == "Gateway recovery"
    assert chunks[0]["metadata"]["category"] == "network"
    assert chunks[0]["metadata"]["runbook_notes"] == (
        "Restart the gateway after recovery."
    )


def test_invalid_pdf_is_rejected_before_indexing():
    with pytest.raises(ValueError, match="not a valid PDF"):
        ingest_runbook_pdf("e" * 32, "bad.pdf", b"not pdf")


@patch("barq_support.servicenow.httpx.stream")
def test_attachment_download_enforces_streamed_size_limit(mock_stream):
    response = MagicMock()
    response.status_code = 200
    response.headers = {}
    response.iter_bytes.return_value = [b"123", b"456"]
    context = MagicMock()
    context.__enter__.return_value = response
    mock_stream.return_value = context
    client = ServiceNowClient(get_settings())

    with pytest.raises(ValueError, match="exceeds the 5-byte limit"):
        client.download_attachment("f" * 32, max_bytes=5)


def test_attachment_download_rejects_malformed_sys_id():
    client = ServiceNowClient(get_settings())

    with pytest.raises(ValueError, match="32-character ServiceNow sys_id"):
        client.download_attachment("../attachment", max_bytes=100)


@patch(
    "barq_support.tasks.ingest_runbook_pdf",
    return_value={"chunks": 4, "pages": 2, "status": "upserted"},
)
@patch("barq_support.tasks.ServiceNowClient")
def test_worker_sets_processing_then_ingested_status(mock_client_class, mock_ingest):
    mock_client = mock_client_class.return_value
    mock_client.download_attachment.return_value = b"%PDF-example"
    event = {
        "attachment_sys_id": "a" * 32,
        "table_sys_id": "b" * 32,
        "file_name": "guide.pdf",
        "title": "Network guide",
        "category": "network",
        "runbook_notes": "Restart the gateway after recovery.",
    }

    result = ingest_servicenow_attachment(event)

    assert result["status"] == "success"
    assert [call.kwargs["status_value"] for call in mock_client.update_runbook_upload.call_args_list] == [
        "Processing",
        "Ingested",
    ]
    mock_ingest.assert_called_once_with(
        attachment_sys_id="a" * 32,
        file_name="guide.pdf",
        pdf_bytes=b"%PDF-example",
        title="Network guide",
        category="network",
        runbook_notes="Restart the gateway after recovery.",
    )


@patch(
    "barq_support.tasks.ingest_runbook_pdf",
    side_effect=ValueError("invalid PDF"),
)
@patch("barq_support.tasks.ServiceNowClient")
def test_worker_marks_runbook_failed_and_reraises(mock_client_class, mock_ingest):
    mock_client = mock_client_class.return_value
    mock_client.download_attachment.return_value = b"%PDF-example"
    event = {
        "attachment_sys_id": "c" * 32,
        "table_sys_id": "d" * 32,
        "file_name": "bad.pdf",
    }

    with pytest.raises(ValueError, match="invalid PDF"):
        ingest_servicenow_attachment(event)

    assert [call.kwargs["status_value"] for call in mock_client.update_runbook_upload.call_args_list] == [
        "Processing",
        "Failed",
    ]
