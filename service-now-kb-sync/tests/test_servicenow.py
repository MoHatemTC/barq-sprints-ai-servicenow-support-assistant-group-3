from datetime import UTC, datetime

import httpx
import pytest

from app.exceptions import (
    ServiceNowAuthError,
    ServiceNowError,
    ServiceNowNotFoundError,
    ServiceNowResponseError,
)
from app.services.servicenow import FetchFailure, ServiceNowClient

RECORD = {
    "sys_id": "abc123",
    "number": "KB001500",
    "short_description": "VPN Authentication Issue",
    "text": "<p>Reset your password.</p>",
    "workflow_state": "published",
    "active": "true",
    "sys_updated_on": "2026-10-01 12:30:00",
    "kb_knowledge_base": {"value": "kbid1", "display_value": "IT"},
}


def _client(handler, **kw) -> ServiceNowClient:
    kw.setdefault("backoff_base", 0)
    return ServiceNowClient(
        "https://example.service-now.com",
        "user",
        "pass",
        transport=httpx.MockTransport(handler),
        **kw,
    )


def _json(result, status=200):
    return httpx.Response(status, json={"result": result})


# ---------------------------------------------------------------- parsing
def test_parse_record_into_normalized_article():
    article = _client(lambda r: _json(RECORD)).parse_article(RECORD)
    assert article.sys_id == "abc123"
    assert article.number == "KB001500"
    assert article.title == "VPN Authentication Issue"
    assert article.text == "<p>Reset your password.</p>"
    assert article.workflow_state == "published"
    assert article.published is True
    assert article.updated_on == datetime(2026, 10, 1, 12, 30, tzinfo=UTC)
    assert article.knowledge_base == "kbid1"


def test_parse_handles_reference_dicts_and_alternate_field_names():
    record = {
        "sys_id": {"value": "x1"},
        "title": "Alt title",
        "article_content": "body",
        "workflow_state": {"value": "Published", "display_value": "Published"},
    }
    article = _client(lambda r: _json(record)).parse_article(record)
    assert (article.sys_id, article.title, article.text) == ("x1", "Alt title", "body")
    assert article.published is True  # state comparison is case-insensitive


def test_wiki_is_used_when_text_is_empty():
    record = {**RECORD, "text": "", "wiki": "wiki body"}
    assert _client(lambda r: _json(record)).parse_article(record).text == "wiki body"


@pytest.mark.parametrize(
    "overrides",
    [{"workflow_state": "draft"}, {"workflow_state": "retired"}, {"active": "false"}],
)
def test_unpublished_states_are_not_published(overrides):
    record = {**RECORD, **overrides}
    assert _client(lambda r: _json(record)).parse_article(record).published is False


def test_published_states_are_configurable():
    client = _client(lambda r: _json(RECORD), published_states=["published", "review"])
    assert client.parse_article({**RECORD, "workflow_state": "review"}).published is True


def test_record_without_sys_id_is_rejected():
    with pytest.raises(ServiceNowResponseError):
        _client(lambda r: _json({})).parse_article({"number": "KB1"})


# ---------------------------------------------------------------- get_article
def test_get_article_ok_and_request_shape():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization", "")
        return _json(RECORD)

    article = _client(handler).get_article("abc123")
    assert article.number == "KB001500"
    assert "/api/now/table/kb_knowledge/abc123" in seen["url"]
    assert seen["auth"].startswith("Basic ")


def test_get_article_not_found():
    with pytest.raises(ServiceNowNotFoundError):
        _client(
            lambda r: httpx.Response(404, json={"error": {"message": "No Record found"}})
        ).get_article("nope")


@pytest.mark.parametrize("status", [401, 403])
def test_auth_errors_are_not_retried(status):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(status)

    with pytest.raises(ServiceNowAuthError):
        _client(handler).get_article("abc123")
    assert len(calls) == 1


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b""),
        httpx.Response(200, content=b"<html>login</html>"),
        httpx.Response(200, json=["not", "an", "object"]),
        httpx.Response(200, json={"nothing": 1}),
        httpx.Response(200, json={"result": {}}),
    ],
)
def test_empty_or_malformed_responses(response):
    with pytest.raises(ServiceNowResponseError):
        _client(lambda r: response).get_article("abc123")


def test_error_payload_is_surfaced():
    with pytest.raises(ServiceNowError, match="boom"):
        _client(lambda r: httpx.Response(200, json={"error": {"message": "boom"}})).get_article(
            "abc123"
        )


def test_timeouts_are_retried_then_raise():
    calls = []

    def handler(request):
        calls.append(1)
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ServiceNowError, match="timed out"):
        _client(handler, max_retries=2).get_article("abc123")
    assert len(calls) == 3


def test_server_errors_retry_then_succeed():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(503) if len(calls) < 2 else _json(RECORD)

    assert _client(handler).get_article("abc123").sys_id == "abc123"


def test_invalid_sys_id_never_reaches_the_network():
    with pytest.raises(ValueError):
        _client(lambda r: pytest.fail("no request")).get_article("../etc/passwd")


# ---------------------------------------------------------------- listing
def test_modified_since_builds_query_and_paginates():
    queries, offsets = [], []

    def handler(request):
        params = request.url.params
        queries.append(params["sysparm_query"])
        offsets.append(int(params["sysparm_offset"]))
        page = {0: [RECORD, {**RECORD, "sys_id": "b"}], 2: [{**RECORD, "sys_id": "c"}]}
        return _json(page[int(params["sysparm_offset"])])

    client = _client(handler, page_size=2, kb_sys_ids=["kb1", "kb2"])
    articles = client.get_articles_modified_since(datetime(2026, 10, 1, 8, 5, 3, tzinfo=UTC))
    assert [a.sys_id for a in articles] == ["abc123", "b", "c"]
    assert offsets == [0, 2]
    assert "sys_updated_on>=javascript:gs.dateGenerate('2026-10-01','08:05:03')" in queries[0]
    assert "kb_knowledge_baseINkb1,kb2" in queries[0]
    assert "workflow_state" not in queries[0]  # all states, so unpublished ones are removed


def test_published_query_filters_state_and_active():
    seen = []

    def handler(request):
        seen.append(request.url.params["sysparm_query"])
        return _json([])

    assert _client(handler).get_published_articles() == []
    assert seen[0].startswith("workflow_stateINpublished^active=true")


def test_empty_list_is_valid():
    assert _client(lambda r: _json([])).get_articles_modified_since(None) == []


def test_malformed_record_is_reported_not_fatal():
    handler = lambda r: _json([RECORD, {"number": "KB9"}, "garbage"])  # noqa: E731
    errors: list[FetchFailure] = []
    articles = _client(handler).get_articles_modified_since(None, errors=errors)
    assert len(articles) == 1
    assert len(errors) == 2


def test_list_result_must_be_a_list():
    with pytest.raises(ServiceNowResponseError):
        _client(lambda r: _json(RECORD)).get_articles_modified_since(None)


def test_unsafe_query_values_rejected():
    with pytest.raises(ValueError):
        ServiceNowClient("https://x.service-now.com", "u", "p", published_states=["a^ORb"])
