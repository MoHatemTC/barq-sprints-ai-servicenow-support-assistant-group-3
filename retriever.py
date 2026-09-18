import os
from typing import Optional, Dict, Any
from qdrant_client import QdrantClient
from qdrant_client.http import models

DEFAULT_THRESHOLD = 0.65


def get_qdrant_client(url: Optional[str] = None, api_key: Optional[str] = None) -> QdrantClient:
    qdrant_url = url or os.getenv("QDRANT_URL")
    qdrant_api_key = api_key or os.getenv("QDRANT_API_KEY")

    if not qdrant_url:
        raise ValueError("QDRANT_URL is not set. Please define it in your environment or .env file.")

    return QdrantClient(
        url=qdrant_url,
        api_key=qdrant_api_key
    )


def retrieve_relevant_chunks(
    query_vector: list,
    query_text: str,
    collection_name: str = "kb_articles",
    top_k: int = 3,
    category: Optional[str] = None,
    threshold: float = DEFAULT_THRESHOLD,
    client: Optional[QdrantClient] = None
) -> Dict[str, Any]:
    """
    Performs vector retrieval from Qdrant with optional category filtering 
    and applies a score threshold gate.
    """
    if client is None:
        client = get_qdrant_client()

    query_filter = None
    if category:
        query_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="category",
                    match=models.MatchValue(value=category)
                )
            ]
        )

    try:
        response = client.query_points(
            collection_name=collection_name,
            query=query_vector,
            query_filter=query_filter,
            limit=top_k,
            with_payload=True
        )
        search_results = response.points
    except Exception:
        response = client.query_points(
            collection_name=collection_name,
            query=query_vector,
            limit=top_k * 5,
            with_payload=True
        )
        all_points = response.points
        if category:
            search_results = [
                p for p in all_points 
                if (p.payload or {}).get("category") == category
            ][:top_k]
        else:
            search_results = all_points[:top_k]

    if not search_results:
        return {
            "status": "refused",
            "message": "No relevant knowledge articles found matching the criteria.",
            "searched_query": query_text,
            "top_score": 0.0,
            "threshold": threshold,
            "results": []
        }

    top_score = search_results[0].score

    if top_score < threshold:
        return {
            "status": "refused",
            "message": "Top similarity score is below the relevance threshold.",
            "searched_query": query_text,
            "top_score": top_score,
            "threshold": threshold,
            "results": []
        }

    ranked_chunks = []
    for hit in search_results:
        payload = hit.payload or {}
        ranked_chunks.append({
            "score": hit.score,
            "article_id": payload.get("article_id", "Unknown"),
            "text": payload.get("text", ""),
            "category": payload.get("category", ""),
            "metadata": payload
        })

    return {
        "status": "success",
        "message": "Relevant chunks retrieved successfully.",
        "searched_query": query_text,
        "top_score": top_score,
        "threshold": threshold,
        "results": ranked_chunks
    }