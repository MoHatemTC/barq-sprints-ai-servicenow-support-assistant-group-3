from unittest.mock import Mock, patch

import pytest

from barq_support.password_protection import (
    _label_token_ids,
    classify_password_presence,
    sanitize_text_fields,
)
from barq_support.ingestion import ingest
from barq_support.retrieval import retriever
from barq_support.worker import process_incident


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_classifier_compares_true_and_false_label_logits():
    settings = Mock(
        password_classifier_base_url="http://vllm:8000/v1",
        password_classifier_api_key="test-key",
        password_classifier_model="Qwen/Qwen2.5-1.5B-Instruct",
        password_classifier_timeout_seconds=5.0,
    )
    _label_token_ids.cache_clear()
    tokenize_responses = [
        {"tokens": [1, 2]},
        {"tokens": [1, 2, 31]},
        {"tokens": [1, 2, 46]},
    ]
    score_response = {
        "choices": [
            {
                "logprobs": {
                    "content": [
                        {
                            "top_logprobs": [
                                {"token": "token_id:31", "logprob": -0.2},
                                {"token": "token_id:46", "logprob": -1.6},
                            ]
                        }
                    ]
                }
            }
        ]
    }

    with patch(
        "barq_support.password_protection.httpx.post",
        side_effect=[
            *(FakeResponse(payload) for payload in tokenize_responses),
            FakeResponse(score_response),
        ],
    ) as post:
        found = classify_password_presence("Password: hunter2", settings)

    assert found is True
    assert post.call_count == 4
    score_call = post.call_args
    assert score_call.args[0] == "http://vllm:8000/v1/chat/completions"
    assert score_call.kwargs["json"]["logprob_token_ids"] == [31, 46]
    assert score_call.kwargs["json"]["max_tokens"] == 1
    assert score_call.kwargs["headers"]["Authorization"] == "Bearer test-key"


def test_classifier_returns_false_when_false_label_has_higher_logit():
    settings = Mock(
        password_classifier_base_url="http://vllm:8000",
        password_classifier_api_key="",
        password_classifier_model="Qwen/Qwen2.5-1.5B-Instruct",
        password_classifier_timeout_seconds=5.0,
    )
    _label_token_ids.cache_clear()
    responses = [
        FakeResponse({"tokens": [1, 2]}),
        FakeResponse({"tokens": [1, 2, 31]}),
        FakeResponse({"tokens": [1, 2, 46]}),
        FakeResponse(
            {
                "choices": [
                    {
                        "logprobs": {
                            "content": [
                                {
                                    "top_logprobs": [
                                        {"token": "token_id:31", "logprob": -1.6},
                                        {"token": "token_id:46", "logprob": -0.2},
                                    ]
                                }
                            ]
                        }
                    }
                ]
            }
        ),
    ]

    with patch(
        "barq_support.password_protection.httpx.post",
        side_effect=responses,
    ):
        assert classify_password_presence("Login fails.", settings) is False


def test_classifier_requires_single_token_labels():
    settings = Mock(
        password_classifier_base_url="http://vllm:8000",
        password_classifier_api_key="",
        password_classifier_model="Qwen/Qwen2.5-1.5B-Instruct",
        password_classifier_timeout_seconds=5.0,
    )
    _label_token_ids.cache_clear()

    with (
        patch(
            "barq_support.password_protection.httpx.post",
            side_effect=[
                FakeResponse({"tokens": [1, 2]}),
                FakeResponse({"tokens": [1, 2, 3, 4]}),
            ],
        ),
        pytest.raises(RuntimeError, match="exactly one model token"),
    ):
        classify_password_presence("Password: value", settings)


def test_sanitize_text_fields_masks_and_verifies_with_classifier():
    fields = {
        "short_description": "Unable to log in",
        "description": "The password is hunter2.",
    }
    masked_fields = {
        "short_description": "Unable to log in",
        "description": "The password is [REDACTED].",
    }
    settings = Mock()
    llm = Mock()
    structured_llm = Mock()
    structured_llm.invoke.return_value.model_dump.return_value = {
        "field_0": masked_fields["short_description"],
        "field_1": masked_fields["description"],
    }
    llm.with_structured_output.return_value = structured_llm

    with (
        patch(
            "barq_support.password_protection.classify_password_presence",
            side_effect=[True, False],
        ) as classify,
        patch(
            "barq_support.password_protection.build_llm",
            return_value=llm,
        ),
    ):
        result = sanitize_text_fields(fields, settings)

    assert result == masked_fields
    assert classify.call_count == 2
    schema = llm.with_structured_output.call_args.args[0]
    assert set(schema.model_fields) == {"field_0", "field_1"}
    human_message = structured_llm.invoke.call_args.args[0][1]
    assert "hunter2" in human_message.content


def test_sanitize_text_fields_rejects_unchanged_mask_result():
    fields = {
        "short_description": "Unable to log in",
        "description": "The password is hunter2.",
    }
    llm = Mock()
    structured_llm = Mock()
    structured_llm.invoke.return_value.model_dump.return_value = {
        "field_0": fields["short_description"],
        "field_1": fields["description"],
    }
    llm.with_structured_output.return_value = structured_llm

    with (
        patch("barq_support.password_protection.build_llm", return_value=llm),
        patch(
            "barq_support.password_protection.classify_password_presence",
            return_value=True,
        ),
        pytest.raises(RuntimeError, match="original text unchanged"),
    ):
        sanitize_text_fields(fields, Mock())


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
    sanitized_fields = {
        "text": "Password: [REDACTED]",
        "section": "Resolution",
        "metadata.short_description": "Password reset guide",
    }
    expected_sanitized_fields = sanitized_fields.copy()

    with (
        patch("barq_support.ingestion.ingest.get_settings", return_value=settings),
        patch(
            "barq_support.ingestion.ingest.chunk_article",
            return_value=[raw_chunk.copy()],
        ) as chunk_article,
        patch(
            "barq_support.ingestion.ingest.sanitize_text_fields",
            return_value=sanitized_fields,
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
    sanitize.assert_called_once_with(
        {
            "text": "Password: secret",
            "section": "Resolution",
            "metadata.short_description": "Password reset guide",
        },
        settings,
    )
    assert chunks[0]["text"] == expected_sanitized_fields["text"]
    assert chunks[0]["metadata"]["short_description"] == (
        expected_sanitized_fields["metadata.short_description"]
    )


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
