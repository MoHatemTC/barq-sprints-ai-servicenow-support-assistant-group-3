import hashlib
import uuid
from typing import List, Dict

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FilterSelector, FieldCondition, MatchValue

from barq_support.settings import get_settings
from barq_support.retrieval.embedder import EMBEDDING_DIMENSION

VECTOR_SIZE = EMBEDDING_DIMENSION  # 3072 for Gemini Embedding 2


def _collection_name() -> str:
    return get_settings().qdrant_collection


def get_client() -> QdrantClient:
    settings = get_settings()
    return QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        timeout=120,
    )


def ensure_collection(
    client: QdrantClient,
    vector_size: int = VECTOR_SIZE,
) -> None:
    name = _collection_name()
    existing = [c.name for c in client.get_collections().collections]
    if name in existing:
        return
    client.create_collection(
        collection_name=name,
        vectors_config=VectorParams(
            size=vector_size,
            distance=Distance.COSINE,
        ),
    )


def generate_point_id(
    article_id: str,
    section: str,
    chunk_index: int,
    chunk_text: str,
) -> str:
    raw_key = f"{article_id}::{section}::{chunk_index}::{chunk_text}"
    digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    return str(uuid.uuid5(uuid.NAMESPACE_URL, digest))


def build_point(chunk: Dict, vector: List[float]) -> PointStruct:
    point_id = generate_point_id(
        chunk["article_id"],
        chunk["section"],
        chunk["chunk_index"],
        chunk["text"],
    )
    payload = {
        "text": chunk["text"],
        "article_id": chunk["article_id"],
        "section": chunk["section"],
        "chunk_index": chunk["chunk_index"],
        **chunk.get("metadata", {}),
    }
    return PointStruct(id=point_id, vector=vector, payload=payload)


def upsert_chunks(
    client: QdrantClient,
    chunks: List[Dict],
    vectors: List[List[float]],
    batch_size: int = 100,
) -> None:
    name = _collection_name()
    points = [build_point(c, v) for c, v in zip(chunks, vectors)]
    for i in range(0, len(points), batch_size):
        client.upsert(collection_name=name, points=points[i : i + batch_size])


def delete_article_chunks(client: QdrantClient, article_id: str) -> int:
    """Delete all Qdrant vectors whose payload article_id matches.
    Returns the number of points deleted (approximate — Qdrant reports
    operation info, not exact count, so we return 0 on delete-by-filter).
    """
    name = _collection_name()
    client.delete(
        collection_name=name,
        points_selector=FilterSelector(
            filter=Filter(
                must=[
                    FieldCondition(
                        key="article_id",
                        match=MatchValue(value=article_id),
                    )
                ]
            )
        ),
    )
    return 0  # Qdrant delete-by-filter does not return exact count
