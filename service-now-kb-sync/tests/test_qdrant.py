import pytest
from qdrant_client import QdrantClient, models

from app.exceptions import ConfigurationError, EmbeddingDimensionError
from app.services.chunker import Chunker
from app.services.qdrant import QdrantRepository
from tests.conftest import DIM, make_article


def _chunks(article, text="Alpha beta gamma. " * 30, size=100):
    return Chunker(size, 10).chunk_article(article, text)


def _vectors(n, dim=DIM):
    return [[0.1 * (i + 1)] * dim for i in range(n)]


def test_point_ids_are_deterministic_and_unique():
    a = QdrantRepository.point_id("sys1", 0)
    assert a == QdrantRepository.point_id("sys1", 0)
    assert a != QdrantRepository.point_id("sys1", 1)
    assert a != QdrantRepository.point_id("sys2", 0)


def test_upsert_is_idempotent(repo):
    article = make_article()
    chunks = _chunks(article)
    for _ in range(2):
        repo.upsert_chunks(article, chunks, _vectors(len(chunks)))
    assert repo.count_article_points(article.sys_id) == len(chunks)


def test_payload_contains_metadata_and_text(repo):
    article = make_article(sys_id="abc123", number="KB001500")
    chunks = _chunks(article)
    repo.upsert_chunks(article, chunks, _vectors(len(chunks)))
    point = repo._client.retrieve("test_kb", [QdrantRepository.point_id("abc123", 0)])[0]
    assert point.payload["sys_id"] == "abc123"
    assert point.payload["number"] == "KB001500"
    assert point.payload["chunk_index"] == 0
    assert point.payload["source"] == "servicenow"
    assert point.payload["text"] == chunks[0].text
    assert point.payload["chunk_count"] == len(chunks)


def test_delete_and_exists_only_touch_one_article(repo):
    a, b = make_article("a1", "KB1"), make_article("b2", "KB2")
    for art in (a, b):
        ch = _chunks(art)
        repo.upsert_chunks(art, ch, _vectors(len(ch)))
    assert repo.article_exists("a1") and repo.article_exists("b2")
    removed = repo.delete_article("a1")
    assert removed > 0
    assert not repo.article_exists("a1")
    assert repo.article_exists("b2")
    assert repo.delete_article("a1") == 0  # deleting again is a harmless no-op


def test_text_field_and_vector_name_are_configurable():
    repo = QdrantRepository(
        QdrantClient(":memory:"), "c", DIM, text_field="content", vector_name="dense"
    )
    article = make_article()
    chunks = _chunks(article)
    repo.upsert_chunks(article, chunks, _vectors(len(chunks)))
    point = repo._client.retrieve("c", [repo.point_id(article.sys_id, 0)], with_vectors=True)[0]
    assert "content" in point.payload and "text" not in point.payload
    assert "dense" in point.vector


def test_wrong_vector_dimension_fails_clearly(repo):
    article = make_article()
    chunks = _chunks(article)
    with pytest.raises(EmbeddingDimensionError, match="expects 8"):
        repo.upsert_chunks(article, chunks, _vectors(len(chunks), dim=DIM + 1))
    assert repo.count_article_points(article.sys_id) == 0


def test_existing_collection_with_other_dimension_is_rejected():
    client = QdrantClient(":memory:")
    client.create_collection(
        "c", vectors_config=models.VectorParams(size=DIM * 2, distance=models.Distance.COSINE)
    )
    repo = QdrantRepository(client, "c", DIM)
    with pytest.raises(ConfigurationError, match="vector size 16"):
        repo.ensure_collection()


def test_named_vector_collection_requires_vector_name():
    client = QdrantClient(":memory:")
    client.create_collection(
        "c",
        vectors_config={"dense": models.VectorParams(size=DIM, distance=models.Distance.COSINE)},
    )
    with pytest.raises(ConfigurationError, match="QDRANT_VECTOR_NAME"):
        QdrantRepository(client, "c", DIM).ensure_collection()
    QdrantRepository(client, "c", DIM, vector_name="dense").ensure_collection()


def test_payload_is_compatible_with_agent_search_kb(repo):
    """searchKB reads article_id/section/chunk_index/text/category from the payload."""
    article = make_article(sys_id="abc123", number="KB0000007", knowledge_base="kb-sys-id")
    chunks = _chunks(article)
    repo.upsert_chunks(article, chunks, _vectors(len(chunks)))
    payload = repo._client.retrieve("test_kb", [QdrantRepository.point_id("abc123", 1)])[0].payload
    assert payload["article_id"] == "KB0000007"  # same value the Agent's own KB chunks use
    assert payload["section"] == "Body"
    assert payload["category"] == ""
    assert payload["chunk_index"] == 1
    assert payload["short_description"] == "VPN Authentication Issue"
    assert payload["kb_knowledge_base"] == "kb-sys-id"
    assert payload["sys_updated_on"] == "2026-10-01 00:00:00"
    assert payload["workflow_state"] == "published"
