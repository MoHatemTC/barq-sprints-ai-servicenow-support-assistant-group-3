import hashlib
import uuid
from typing import List, Dict

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from config import settings

COLLECTION_NAME = "kb_articles"
VECTOR_SIZE = 384  # must match the embedding model's output dimension


def get_client() -> QdrantClient:
    """Creates a Qdrant client connected to the cloud cluster from .env."""
    return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)


def ensure_collection(client: QdrantClient, vector_size: int = VECTOR_SIZE) -> None:
    """Creates the collection if it doesn't already exist."""
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME in existing:
        return

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )


def generate_point_id(article_id: str, section: str, chunk_index: int) -> str:
    """
    Deterministically derives a point ID from the chunk's source
    (article id + section + chunk index), so re-running ingestion over
    unchanged chunks always produces the same ID instead of creating
    duplicates. Qdrant point IDs must be an unsigned int or a UUID, so we
    hash the inputs into a UUID (uuid5) rather than using a random UUID.
    """
    raw_key = f"{article_id}::{section}::{chunk_index}"
    digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    return str(uuid.uuid5(uuid.NAMESPACE_URL, digest))


def build_point(chunk: Dict, vector: List[float]) -> PointStruct:
    """Builds a single Qdrant point from a chunk dict and its embedding vector."""
    point_id = generate_point_id(chunk["article_id"], chunk["section"], chunk["chunk_index"])

    payload = {
        "text": chunk["text"],
        "article_id": chunk["article_id"],
        "section": chunk["section"],
        "chunk_index": chunk["chunk_index"],
        **chunk.get("metadata", {}),
    }

    return PointStruct(id=point_id, vector=vector, payload=payload)

def upsert_chunks(client: QdrantClient, chunks: List[Dict], vectors: List[List[float]], batch_size: int = 100) -> None:
    """
    Upserts chunks (with their pre-computed vectors) into the collection
    in batches. Since point IDs are deterministic, re-running this over
    the same chunks overwrites the same points instead of duplicating them.
    """
    points = [build_point(chunk, vector) for chunk, vector in zip(chunks, vectors)]

    for i in range(0, len(points), batch_size):
        batch = points[i:i + batch_size]
        client.upsert(collection_name=COLLECTION_NAME, points=batch)


if __name__ == "__main__":
    from embedder import embed_text

    sample_chunks = [
        {
            "text": "A machine learning validation workflow fails with a runtime shape error.",
            "article_id": "KB0010035",
            "section": "Problem",
            "chunk_index": 0,
            "metadata": {"workflow_state": "published", "category": ""},
        }
    ]

    client = get_client()
    ensure_collection(client)

    vectors = [embed_text(c["text"]) for c in sample_chunks]
    upsert_chunks(client, sample_chunks, vectors)

    print("Upserted 1 test point successfully.")
    print(f"Collection info: {client.get_collection(COLLECTION_NAME)}")