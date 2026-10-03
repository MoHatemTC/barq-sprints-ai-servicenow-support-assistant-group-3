import json

import httpx
import pytest

from app.exceptions import EmbeddingDimensionError, EmbeddingError
from app.services.embedder import OpenAICompatibleEmbeddingService
from tests.conftest import DIM, FakeEmbedder

SECRET = "sk-super-secret-key"


def _service(handler, **kw):
    return OpenAICompatibleEmbeddingService(
        api_key=SECRET,
        model="m",
        dimension=DIM,
        backoff_base=0,
        transport=httpx.MockTransport(handler),
        **kw,
    )


def _ok(request: httpx.Request, dim=DIM):
    body = json.loads(request.content)
    # Return out of order to prove we sort by index.
    data = [{"index": i, "embedding": [float(i)] * dim} for i in range(len(body["input"]))]
    return httpx.Response(200, json={"data": list(reversed(data))})


def test_fake_dimension_mismatch_fails_clearly():
    with pytest.raises(EmbeddingDimensionError, match="EMBEDDING_DIMENSION=8"):
        FakeEmbedder(wrong_dim=True).embed_documents(["hello"])


def test_openai_compatible_success_and_ordering():
    vectors = _service(_ok).embed_documents(["a", "b", "c"])
    assert [v[0] for v in vectors] == [0.0, 1.0, 2.0]


def test_provider_dimension_mismatch_is_rejected():
    service = _service(lambda r: _ok(r, dim=DIM + 4))
    with pytest.raises(EmbeddingDimensionError, match="returned 12 values"):
        service.embed_documents(["a"])


def test_batching():
    seen = []

    def handler(request):
        seen.append(len(json.loads(request.content)["input"]))
        return _ok(request)

    _service(handler, batch_size=2).embed_documents(["a", "b", "c", "d", "e"])
    assert seen == [2, 2, 1]


def test_retries_transient_errors_then_succeeds():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] < 3 else _ok(request)

    assert len(_service(handler).embed_documents(["a"])) == 1
    assert calls["n"] == 3


def test_auth_error_not_retried_and_key_not_leaked():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(401, text="bad key")

    with pytest.raises(EmbeddingError) as exc:
        _service(handler).embed_documents(["a"])
    assert calls["n"] == 1
    assert SECRET not in str(exc.value)


def test_malformed_response():
    service = _service(lambda r: httpx.Response(200, json={"unexpected": True}))
    with pytest.raises(EmbeddingError, match="Malformed"):
        service.embed_documents(["a"])


def test_empty_input_makes_no_request():
    service = _service(lambda r: pytest.fail("no request expected"))
    assert service.embed_documents([]) == []
