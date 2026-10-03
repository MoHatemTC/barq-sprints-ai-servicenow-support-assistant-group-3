"""Read-only sanity check: does this service embed text the same way the Agent's ingestion did?

Takes a few existing KB chunks from the live collection, re-embeds their stored text with THIS
service's embedder, and compares with the vector already stored in Qdrant (cosine similarity).

    uv run python -m scripts.check_embedding_compat

~1.00 (>= 0.99)  -> same model and same input: safe to sync.
clearly lower    -> different model/provider or different embedding input (e.g. title prefix);
                    do NOT sync into this collection yet.
Nothing is written to Qdrant.
"""

from __future__ import annotations

import math

from qdrant_client import QdrantClient

from app.config import Settings
from app.services.embedder import OpenAICompatibleEmbeddingService


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def main() -> None:
    settings = Settings()
    client = QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None,
        timeout=60,
    )
    points, _ = client.scroll(
        settings.qdrant_collection, limit=300, with_payload=True, with_vectors=True
    )
    samples = [p for p in points if str((p.payload or {}).get("article_id", "")).startswith("KB")][
        :5
    ]
    if not samples:
        print("No KB chunks (article_id starting with 'KB') found to compare.")
        return

    embedder = OpenAICompatibleEmbeddingService.from_settings(settings)
    scores = []
    for point in samples:
        stored = point.vector
        if isinstance(stored, dict):
            stored = stored[settings.qdrant_vector_name or next(iter(stored))]
        text = point.payload[settings.qdrant_text_field]
        score = cosine(stored, embedder.embed_documents([text])[0])
        scores.append(score)
        label = f"{point.payload.get('article_id')}  {point.payload.get('section')}"
        print(f"{label:<32} cosine={score:.4f}")

    worst = min(scores)
    print()
    print(
        "OK: embeddings match the existing ones."
        if worst >= 0.99
        else f"MISMATCH: lowest cosine is {worst:.4f}. Do not sync yet; send this output."
    )


if __name__ == "__main__":
    main()
