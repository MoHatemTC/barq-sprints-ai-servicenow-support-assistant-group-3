from copy import deepcopy
from unittest.mock import Mock, patch

import pytest

from barq_support.ingestion import ingest
from barq_support.password_protection import (
    classify_password_presence,
    sanitize_chunk_fields,
    sanitize_text_fields,
)
from barq_support.retrieval import retriever
from barq_support.worker import process_incident
from scripts.ingest_pdf import sanitize_pdf_chunks


def test_classifier_calls_ollama_chat_endpoint():
    settings = Mock(
        password_classifier_base_url="http://ollama:11434",
        password_classifier_model="qwen2.5:1.5b",
        password_classifier_timeout_seconds=120.0,
    )
    response = Mock()
    response.json.return_value = {
        "message": {"content": '{"contains_secret": true}'}
    }
    with patch(
        "barq_support.password_protection.httpx.post",
        return_value=response,
    ) as post:
        assert classify_password_presence("Password: hunter2", settings) is True

    response.raise_for_status.assert_called_once_with()
    post.assert_called_once()
    args, kwargs = post.call_args
    assert args == ("http://ollama:11434/api/chat",)
    assert kwargs["json"]["model"] == "qwen2.5:1.5b"
    assert kwargs["json"]["messages"][-1] == {
        "role": "user",
        "content": "Password: hunter2",
    }
    assert kwargs["json"]["format"]["required"] == ["contains_secret"]
    assert kwargs["json"]["stream"] is False
    assert kwargs["timeout"] == 120.0


def test_classifier_returns_false_for_safe_text():
    settings = Mock(
        password_classifier_base_url="http://ollama:11434",
        password_classifier_model="qwen2.5:1.5b",
        password_classifier_timeout_seconds=120.0,
    )
    response = Mock()
    response.json.return_value = {
        "message": {"content": '{"contains_secret": false}'}
    }
    with patch(
        "barq_support.password_protection.httpx.post",
        return_value=response,
    ):
        assert classify_password_presence("Login fails.", settings) is False


@pytest.mark.parametrize(
    "content",
    [
        "not-json",
        "null",
        "[]",
        '{"contains_secret": "false"}',
        '{"contains_secret": false, "extra": true}',
    ],
)
def test_classifier_fails_closed_on_invalid_response(content):
    settings = Mock(
        password_classifier_base_url="http://ollama:11434",
        password_classifier_model="qwen2.5:1.5b",
        password_classifier_timeout_seconds=120.0,
    )
    response = Mock()
    response.json.return_value = {"message": {"content": content}}
    with (
        patch(
            "barq_support.password_protection.httpx.post",
            return_value=response,
        ),
        pytest.raises(RuntimeError),
    ):
        classify_password_presence("Password: value", settings)


def test_sanitize_text_fields_redacts_known_credentials_before_classifying():
    fields = {
        "short_description": "Unable to log in",
        "description": (
            "I tried to change my password from OLD-TEST-ONLY to "
            "NEW-TEST-ONLY but it keeps raising an error."
        ),
    }
    settings = Mock()
    with patch(
        "barq_support.password_protection.classify_password_presence",
        return_value=False,
    ) as classify:
        result = sanitize_text_fields(fields, settings)

    assert result == {
        "short_description": "Unable to log in",
        "description": (
            "I tried to change my password from [REDACTED] to "
            "[REDACTED] but it keeps raising an error."
        ),
    }
    classifier_input = classify.call_args.args[0]
    assert "OLD-TEST-ONLY" in classifier_input
    assert "NEW-TEST-ONLY" in classifier_input


def test_sanitize_text_fields_fails_closed_when_secret_cannot_be_located():
    fields = {
        "short_description": "Unable to log in",
        "description": "The credential appeared somewhere in the request.",
    }
    settings = Mock()
    with (
        patch(
            "barq_support.password_protection.classify_password_presence",
            return_value=True,
        ),
        pytest.raises(RuntimeError, match="patterns could not locate"),
    ):
        sanitize_text_fields(fields, settings)


def test_sanitize_text_fields_redacts_labeled_secret_locally():
    fields = {
        "short_description": "Password reset",
        "description": 'The password is "hunter2".',
    }
    settings = Mock()
    with patch(
        "barq_support.password_protection.classify_password_presence",
        return_value=True,
    ) as classify:
        result = sanitize_text_fields(fields, settings)

    assert result == {
        "short_description": "Password reset",
        "description": "The password is [REDACTED].",
    }
    classify.assert_called_once()
    assert "hunter2" in classify.call_args.args[0]


def test_sanitize_single_field_does_not_add_classifier_label():
    settings = Mock()
    with patch(
        "barq_support.password_protection.classify_password_presence",
        return_value=False,
    ) as classify:
        result = sanitize_text_fields(
            {"text": "VPN profile reset procedure."},
            settings,
        )

    assert result == {"text": "VPN profile reset procedure."}
    classify.assert_called_once_with("VPN profile reset procedure.", settings)


def test_sanitize_chunk_fields_redacts_text_and_string_metadata():
    chunk = {
        "text": "Password: hunter2",
        "section": "Resolution",
        "metadata": {
            "short_description": "Use password hunter2",
            "attachment_sys_id": "a1b2c3d4e5f60718293a4b5c6d7e8f90",
            "page_number": 2,
        },
    }
    settings = Mock()

    with patch(
        "barq_support.password_protection.sanitize_text_fields",
        side_effect=[
            {"text": "Password: [REDACTED]"},
            {"metadata.short_description": "Use password [REDACTED]"},
        ],
    ) as sanitize:
        sanitize_chunk_fields(chunk, settings)

    assert sanitize.call_args_list[0].args == (
        {"text": "Password: hunter2"},
        settings,
    )
    assert sanitize.call_args_list[1].args == (
        {"metadata.short_description": "Use password hunter2"},
        settings,
    )
    assert chunk == {
        "text": "Password: [REDACTED]",
        "section": "Resolution",
        "metadata": {
            "short_description": "Use password [REDACTED]",
            "attachment_sys_id": "a1b2c3d4e5f60718293a4b5c6d7e8f90",
            "page_number": 2,
        },
    }


def test_pdf_chunks_are_sanitized_with_the_shared_chunk_guard():
    chunks = [
        {
            "text": "Password: secret",
            "section": "page_1_text",
            "metadata": {"source_type": "pdf"},
        }
    ]
    settings = Mock()

    def redact_pdf_chunk(chunk, passed_settings):
        assert passed_settings is settings
        chunk["text"] = "Password: [REDACTED]"

    with patch(
        "scripts.ingest_pdf.sanitize_chunk_fields",
        side_effect=redact_pdf_chunk,
    ) as sanitize:
        result = sanitize_pdf_chunks(chunks, settings)

    assert result is chunks
    assert chunks[0]["text"] == "Password: [REDACTED]"
    sanitize.assert_called_once_with(chunks[0], settings)


def test_process_incident_masks_and_persists_before_running_agent():
    service_now = Mock()
    service_now.get_incident.return_value = {
        "result": {
            "number": "INC0012345",
            "sys_id": "incident-id",
            "short_description": "Unable to log in",
            "description": "My secret is hunter2.",
            "category": "software",
        }
    }
    settings = Mock()
    qdrant = Mock()
    agent_result = {"status": "suggested"}
    redacted_fields = {
        "short_description": "Unable to log in",
        "description": "My secret is [REDACTED].",
    }

    def run_agent(**kwargs):
        service_now.redact_incident_fields.assert_called_once_with(
            sys_id="incident-id",
            fields=redacted_fields,
        )
        assert kwargs["incident"]["description"] == redacted_fields["description"]
        return agent_result

    with (
        patch("barq_support.worker.get_settings", return_value=settings),
        patch("barq_support.worker.ServiceNowClient", return_value=service_now),
        patch("barq_support.worker.QdrantClient", return_value=qdrant),
        patch(
            "barq_support.worker.sanitize_text_fields",
            return_value=redacted_fields,
        ) as sanitize,
        patch("barq_support.worker.run_agent", side_effect=run_agent),
    ):
        result = process_incident({"sys_id": "incident-id"})

    assert result is agent_result
    sanitize.assert_called_once_with(
        {
            "short_description": "Unable to log in",
            "description": "My secret is hunter2.",
        },
        settings,
    )


def test_process_incident_does_not_run_agent_if_password_remains():
    service_now = Mock()
    service_now.get_incident.return_value = {
        "result": {
            "number": "INC0012345",
            "sys_id": "incident-id",
            "short_description": "Login failure",
            "description": "Password: hunter2",
            "category": "software",
        }
    }
    settings = Mock()
    run_agent = Mock()

    with (
        patch("barq_support.worker.get_settings", return_value=settings),
        patch("barq_support.worker.ServiceNowClient", return_value=service_now),
        patch(
            "barq_support.worker.sanitize_text_fields",
            side_effect=RuntimeError("Password classifier still detects a secret"),
        ),
        patch("barq_support.worker.run_agent", run_agent),
    ):
        result = process_incident({"sys_id": "incident-id"})

    assert result == {
        "status": "failed",
        "sys_id": "incident-id",
        "error": "RuntimeError",
    }
    run_agent.assert_not_called()
    service_now.redact_incident_fields.assert_not_called()
    service_now.mark_processing_failure.assert_called_once_with(
        sys_id="incident-id",
        error_type="RuntimeError",
    )


def test_kb_chunks_are_sanitized_before_embedding_or_upsert():
    settings = Mock(chunk_size=500, chunk_overlap=50)
    raw_chunk = {
        "text": "Password: secret",
        "section": "Resolution",
        "article_id": "article-id",
        "chunk_index": 0,
        "metadata": {"short_description": "Password reset guide"},
    }
    observed_fields = {}

    def redact_chunk(chunk, passed_settings):
        assert passed_settings is settings
        observed_fields.update(
            text=chunk["text"],
            section=chunk["section"],
            metadata=chunk["metadata"].copy(),
        )
        chunk["text"] = "Password: [REDACTED]"

    with (
        patch("barq_support.ingestion.ingest.get_settings", return_value=settings),
        patch(
            "barq_support.ingestion.ingest.chunk_article",
            return_value=[deepcopy(raw_chunk)],
        ) as chunk_article,
        patch(
            "barq_support.ingestion.ingest.sanitize_chunk_fields",
            side_effect=redact_chunk,
        ) as sanitize,
    ):
        chunks = ingest._article_to_chunks(
            {
                "sys_id": "article-id",
                "text": "<p>Password: secret</p>",
                "short_description": "Password reset guide",
            }
        )

    chunk_article.assert_called_once()
    sanitize.assert_called_once()
    assert observed_fields == {
        "text": raw_chunk["text"],
        "section": raw_chunk["section"],
        "metadata": raw_chunk["metadata"],
    }
    assert chunks[0]["text"] == "Password: [REDACTED]"


def test_search_query_is_sanitized_before_embedding():
    settings = Mock()
    qdrant = Mock()
    qdrant.query_points.return_value.points = []

    with (
        patch("barq_support.retrieval.retriever.get_settings", return_value=settings),
        patch(
            "barq_support.retrieval.retriever.sanitize_text_fields",
            return_value={"query": "safe query"},
        ) as sanitize,
        patch(
            "barq_support.retrieval.retriever.embed_text",
            return_value=[0.1, 0.2],
        ) as embed,
    ):
        results = retriever.search_kb("Password: secret", qdrant)

    assert results == []
    sanitize.assert_called_once_with({"query": "Password: secret"}, settings)
    embed.assert_called_once_with("safe query")
    assert qdrant.query_points.call_args.kwargs["query"] == [0.1, 0.2]
