"""Retrieval gate tests against the live Qdrant collection.

Skipped automatically when QDRANT_URL is not configured or the cluster is
unreachable, so `uv run pytest` works offline for everyone else.
"""

import os

import pytest
from dotenv import load_dotenv

from barq_support.retrieval.retriever import retrieve_relevant_chunks

load_dotenv()

qdrant_url = os.getenv("QDRANT_URL")
qdrant_api_key = os.getenv("QDRANT_API_KEY")


def _reachable() -> bool:
    if not qdrant_url:
        return False
    try:
        from qdrant_client import QdrantClient

        client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key, timeout=5)
        client.get_collections()
        return True
    except Exception:
        return False


QDRANT_AVAILABLE = _reachable()

pytestmark = pytest.mark.skipif(
    not QDRANT_AVAILABLE,
    reason="live Qdrant not reachable (set QDRANT_URL/QDRANT_API_KEY to run)",
)

COLLECTION = "kb_articles"


@pytest.fixture(scope="module")
def client():
    from qdrant_client import QdrantClient

    return QdrantClient(url=qdrant_url, api_key=qdrant_api_key, timeout=15)


@pytest.fixture(scope="module")
def sample(client):
    points, _ = client.scroll(collection_name=COLLECTION, limit=1, with_payload=True, with_vectors=True)
    if not points:
        pytest.skip("collection kb_articles has no points")
    p = points[0]
    return p.vector, p.payload.get("text", "")[:60]


def test_retrieval_meets_threshold(client, sample):
    vector, text = sample
    result = retrieve_relevant_chunks(
        query_vector=vector,
        query_text=text,
        collection_name=COLLECTION,
        top_k=2,
        threshold=0.70,
        client=client,
    )
    assert result["status"] == "success"
    assert result["results"], "success must include results"
    assert result["top_score"] >= 0.70


def test_refusal_gate_when_below_threshold(client, sample):
    vector, text = sample
    result = retrieve_relevant_chunks(
        query_vector=vector,
        query_text=text,
        collection_name=COLLECTION,
        top_k=2,
        threshold=1.05,  # impossible score -> guaranteed refusal
        client=client,
    )
    assert result["status"] == "refused"
    assert result["results"] == []
    assert result["top_score"] < 1.05


def test_category_filter_returns_no_unknown_articles(client, sample):
    vector, text = sample
    result = retrieve_relevant_chunks(
        query_vector=vector,
        query_text=text,
        collection_name=COLLECTION,
        top_k=2,
        category="NonExistingCategory123",
        threshold=0.50,
        client=client,
    )
    assert result["status"] in ("success", "refused")
    for chunk in result["results"]:
        assert chunk["category"] == "NonExistingCategory123"
