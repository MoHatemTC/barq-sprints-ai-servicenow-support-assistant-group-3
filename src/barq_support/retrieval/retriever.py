from typing import Any, Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models

from .embedder import embed_text

COLLECTION_NAME = "kb_articles"
DEFAULT_TOP_K = 5


def get_qdrant_client(
    url: str,
    api_key: str,
) -> QdrantClient:
    if not url:
        raise ValueError("QDRANT_URL is not configured")

    return QdrantClient(
        url=url,
        api_key=api_key,
        timeout=120,
    )


def search_kb(
    query: str,
    client: QdrantClient,
    top_k: int = DEFAULT_TOP_K,
    category: Optional[str] = None,
) -> list[dict[str, Any]]:
    """
    Dense vector search against the ServiceNow KB collection.

    The function returns scored chunks to the agent.
    It does not make a final relevance/refusal decision.
    """

    if not query.strip():
        raise ValueError("query must not be empty")

    query_vector = embed_text(query)

    query_filter = None

    if category:
        query_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="category",
                    match=models.MatchValue(value=category),
                )
            ]
        )

    response = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        query_filter=query_filter,
        limit=top_k,
        with_payload=True,
    )

    results: list[dict[str, Any]] = []

    for point in response.points:
        payload = point.payload or {}

        results.append(
            {
                "score": float(point.score),
                "article_id": payload.get("article_id"),
                "section": payload.get("section"),
                "chunk_index": payload.get("chunk_index"),
                "text": payload.get("text", ""),
                "category": payload.get("category"),
                "metadata": payload,
            }
        )

    return results