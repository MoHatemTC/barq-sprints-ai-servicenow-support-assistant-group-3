import httpx
from typing import List, Dict

from chunker import chunk_article
from embedder import embed_text
from qdrant_store import get_client, ensure_collection, upsert_chunks
from config import settings

ARTICLES_ENDPOINT = "http://localhost:8000/kb-articles"
BATCH_SIZE = 50


def load_articles() -> List[Dict]:
    """Fetches KB articles directly from the Task 1 FastAPI service."""
    response = httpx.get(ARTICLES_ENDPOINT, timeout=30)
    response.raise_for_status()
    data = response.json()
    return data["articles"]


def build_all_chunks(articles: List[Dict]) -> List[Dict]:
    """Runs chunking over every article and collects the resulting chunks."""
    all_chunks: List[Dict] = []

    for article in articles:
        article_id = article["number"]
        text = article.get("text", "")

        metadata = {
            "workflow_state": article.get("workflow_state"),
            "category": article.get("category"),
            "kb_knowledge_base": article.get("kb_knowledge_base"),
            "short_description": article.get("short_description"),
        }

        chunks = chunk_article(
            article_id,
            text,
            metadata=metadata,
            chunk_size=settings.chunk_size,
            overlap=settings.chunk_overlap,
        )
        all_chunks.extend(chunks)

    return all_chunks


def main():
    print(f"Fetching articles from {ARTICLES_ENDPOINT} ...")
    articles = load_articles()
    print(f"Loaded {len(articles)} articles.")

    print(f"Chunking articles (chunk_size={settings.chunk_size}, overlap={settings.chunk_overlap}) ...")
    chunks = build_all_chunks(articles)
    print(f"Produced {len(chunks)} chunks.")

    print("Generating embeddings ...")
    vectors = [embed_text(c["text"]) for c in chunks]

    print("Connecting to Qdrant and ensuring collection exists ...")
    client = get_client()
    ensure_collection(client)

    print(f"Upserting {len(chunks)} points in batches of {BATCH_SIZE} ...")
    upsert_chunks(client, chunks, vectors, batch_size=BATCH_SIZE)

    info = client.get_collection("kb_articles")
    print(f"Done. Collection now has {info.points_count} points.")


if __name__ == "__main__":
    main()