import httpx
from typing import List, Dict

from chunker import chunk_article
from embedder import embed_texts, EMBEDDING_BATCH_SIZE
from qdrant_store import get_client, ensure_collection, upsert_chunks
from config import settings
from embedding_cache import load_cache, save_embedding, get_embedding


ARTICLES_ENDPOINT = "http://localhost:8000/kb-articles"
BATCH_SIZE = 50


def load_articles() -> List[Dict]:
    """Fetches KB articles directly from the Task 1 FastAPI service."""
    response = httpx.get(ARTICLES_ENDPOINT, timeout=30)
    response.raise_for_status()

    data = response.json()

    return data["articles"]



FIELDS_USED_SEPARATELY = {"number", "text"}

def build_all_chunks(articles: List[Dict]) -> List[Dict]:
    all_chunks: List[Dict] = []

    for article in articles:
        article_id = article["number"]
        text = article.get("text", "")

        metadata = {
            k: v for k, v in article.items()
            if k not in FIELDS_USED_SEPARATELY
        }

        chunks = chunk_article(
            article_id, text, metadata=metadata,
            chunk_size=settings.chunk_size,
            overlap=settings.chunk_overlap,
        )
        all_chunks.extend(chunks)

    return all_chunks


def generate_embeddings(chunks: List[Dict]) -> List[List[float]]:
    """
    Generates embeddings while reusing previously cached embeddings.

    If the process stops because of quota/rate limits, already completed
    embeddings remain saved and will be skipped on the next run.
    """

    cache = load_cache()

    vectors: List[List[float] | None] = [None] * len(chunks)

    pending_chunks: List[tuple[int, Dict]] = []

    for index, chunk in enumerate(chunks):
        cached_vector = get_embedding(cache, chunk)

        if cached_vector is not None:
            vectors[index] = cached_vector
        else:
            pending_chunks.append((index, chunk))

    cached_count = len(chunks) - len(pending_chunks)

    print(
        f"Embedding cache: {cached_count} cached, "
        f"{len(pending_chunks)} remaining."
    )

    total_batches = (
        len(pending_chunks) + EMBEDDING_BATCH_SIZE - 1
    ) // EMBEDDING_BATCH_SIZE

    for i in range(0, len(pending_chunks), EMBEDDING_BATCH_SIZE):
        batch = pending_chunks[i:i + EMBEDDING_BATCH_SIZE]

        batch_number = (i // EMBEDDING_BATCH_SIZE) + 1

        print(
            f"Embedding batch {batch_number}/{total_batches} "
            f"({len(batch)} chunks) ..."
        )

        texts = [chunk["text"] for _, chunk in batch]

        batch_vectors = embed_texts(texts)

        if len(batch_vectors) != len(batch):
            raise RuntimeError(
                f"Expected {len(batch)} embeddings, "
                f"but received {len(batch_vectors)}."
            )

        for (index, chunk), vector in zip(batch, batch_vectors):
            vectors[index] = vector
            save_embedding(cache, chunk, vector)

        print(
            f"Saved batch {batch_number} to embedding cache."
        )

    if any(vector is None for vector in vectors):
        raise RuntimeError(
            "Some embeddings are missing. "
            "The ingestion cannot continue."
        )

    return [vector for vector in vectors if vector is not None]



def main():
    print(f"Fetching articles from {ARTICLES_ENDPOINT} ...")

    articles = load_articles()

    print(f"Loaded {len(articles)} articles.")

    print(
        f"Chunking articles "
        f"(chunk_size={settings.chunk_size}, "
        f"overlap={settings.chunk_overlap}) ..."
    )

    chunks = build_all_chunks(articles)

    print(f"Produced {len(chunks)} chunks.")

    print("Generating embeddings ...")

    vectors = generate_embeddings(chunks)

    print("Connecting to Qdrant and ensuring collection exists ...")

    client = get_client()

    ensure_collection(client)

    print(
        f"Upserting {len(chunks)} points "
        f"in batches of {BATCH_SIZE} ..."
    )

    upsert_chunks(
        client,
        chunks,
        vectors,
        batch_size=BATCH_SIZE,
    )

    info = client.get_collection("kb_articles")

    print(
        f"Done. Collection now has "
        f"{info.points_count} points."
    )


if __name__ == "__main__":
    main()