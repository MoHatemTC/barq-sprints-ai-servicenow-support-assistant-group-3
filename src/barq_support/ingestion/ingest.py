"""
ingestion/ingest.py
Batch and incremental KB article ingestion pipeline.

Batch (run as script):
    uv run python -m barq_support.ingestion.ingest
    -> Fetches all published KB articles from ServiceNow and upserts into Qdrant.

Incremental (called by Celery sync_kb_article task):
    ingest_article(sys_id)  - upsert one article (created / updated)
    delete_article(sys_id)  - remove all vectors for one article (deleted / unpublished)
"""

import logging
from typing import Any

from barq_support.ingestion.chunker import chunk_article
from barq_support.ingestion.embedding_cache import load_cache, save_embedding, get_embedding
from barq_support.ingestion.qdrant_store import (
    get_client,
    ensure_collection,
    upsert_chunks,
    delete_article_chunks,
)
from barq_support.password_protection import sanitize_text_fields
from barq_support.retrieval.embedder import embed_texts, EMBEDDING_BATCH_SIZE
from barq_support.servicenow import ServiceNowClient
from barq_support.settings import get_settings

logger = logging.getLogger(__name__)

BATCH_SIZE = 50


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _sn_client() -> ServiceNowClient:
    return ServiceNowClient(get_settings())


def _article_to_chunks(article: dict[str, Any]) -> list[dict[str, Any]]:
    settings = get_settings()
    article_id = article.get("sys_id") or article.get("number", "unknown")
    text = article.get("text", "")
    metadata = {k: v for k, v in article.items() if k not in {"sys_id", "text"}}
    chunks = chunk_article(
        article_id,
        text,
        metadata=metadata,
        chunk_size=settings.chunk_size,
        overlap=settings.chunk_overlap,
    )
    for chunk in chunks:
        text_fields = {
            "text": chunk["text"],
            "section": chunk["section"],
        }
        text_fields.update(
            {
                f"metadata.{key}": value
                for key, value in chunk["metadata"].items()
                if isinstance(value, str)
            }
        )
        sanitized_fields = sanitize_text_fields(text_fields, settings)
        chunk["text"] = sanitized_fields.pop("text")
        chunk["section"] = sanitized_fields.pop("section")
        sanitized_metadata = {}
        for key, value in chunk["metadata"].items():
            if isinstance(value, str):
                value = sanitized_fields[f"metadata.{key}"]
            sanitized_metadata[key] = value
        chunk["metadata"] = sanitized_metadata
    return chunks


def _embed_with_cache(chunks: list[dict[str, Any]]) -> list[list[float]]:
    cache = load_cache()
    vectors: list[list[float] | None] = [None] * len(chunks)
    pending: list[tuple[int, dict]] = []

    for i, chunk in enumerate(chunks):
        cached = get_embedding(cache, chunk)
        if cached is not None:
            vectors[i] = cached
        else:
            pending.append((i, chunk))

    logger.info(
        "Embedding cache: %d cached, %d pending.",
        len(chunks) - len(pending),
        len(pending),
    )

    for b in range(0, len(pending), EMBEDDING_BATCH_SIZE):
        batch = pending[b : b + EMBEDDING_BATCH_SIZE]
        texts = [chunk["text"] for _, chunk in batch]
        batch_vectors = embed_texts(texts)
        for (i, chunk), vector in zip(batch, batch_vectors):
            vectors[i] = vector
            save_embedding(cache, chunk, vector)

    return [v for v in vectors if v is not None]  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Public API (used by Celery task + batch __main__)
# ---------------------------------------------------------------------------

def ingest_article(sys_id: str) -> dict[str, Any]:
    """Fetch one KB article from ServiceNow and upsert its chunks into Qdrant."""
    resp = _sn_client().get_kb_article(sys_id)
    article: dict[str, Any] = resp.get("result", {})
    if not article:
        raise ValueError(f"KB article {sys_id!r} not found in ServiceNow")

    article["sys_id"] = sys_id  # ensure key is present for chunker
    chunks = _article_to_chunks(article)

    if not chunks:
        logger.warning("KB article %s produced zero chunks — skipping.", sys_id)
        return {"sys_id": sys_id, "chunks": 0, "status": "no_content"}

    vectors = _embed_with_cache(chunks)
    qdrant = get_client()
    ensure_collection(qdrant)
    upsert_chunks(qdrant, chunks, vectors)

    logger.info("Upserted %d chunks for KB article %s.", len(chunks), sys_id)
    return {"sys_id": sys_id, "chunks": len(chunks), "status": "upserted"}


def delete_article(sys_id: str) -> dict[str, Any]:
    """Remove all Qdrant vectors for an article (deleted or unpublished in ServiceNow)."""
    qdrant = get_client()
    delete_article_chunks(qdrant, sys_id)
    logger.info("Deleted Qdrant vectors for KB article %s.", sys_id)
    return {"sys_id": sys_id, "status": "deleted"}


def load_all_articles() -> list[dict[str, Any]]:
    """Fetch every published KB article from ServiceNow (batch ingest helper)."""
    return _sn_client().list_kb_articles()


# ---------------------------------------------------------------------------
# Batch ingest entry-point
# ---------------------------------------------------------------------------

def main() -> None:
    import sys

    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    logger.info("Fetching published KB articles from ServiceNow ...")

    articles = load_all_articles()
    logger.info("Loaded %d articles.", len(articles))

    all_chunks: list[dict[str, Any]] = []
    for article in articles:
        article.setdefault("sys_id", article.get("number", "unknown"))
        all_chunks.extend(_article_to_chunks(article))

    logger.info("Produced %d chunks.", len(all_chunks))
    vectors = _embed_with_cache(all_chunks)

    qdrant = get_client()
    ensure_collection(qdrant)
    upsert_chunks(qdrant, all_chunks, vectors, batch_size=BATCH_SIZE)

    info = qdrant.get_collection(get_settings().qdrant_collection)
    logger.info("Done. Collection now has %s points.", info.points_count)


if __name__ == "__main__":
    main()
