import json
from pathlib import Path
from typing import Dict, List

CACHE_FILE = Path("embeddings_cache.json")


def _chunk_key(chunk: Dict) -> str:
    """
    Creates a stable key for a chunk.
    The text is included so that changed content gets a new embedding.
    """
    return (
        f"{chunk['article_id']}::"
        f"{chunk['section']}::"
        f"{chunk['chunk_index']}::"
        f"{chunk['text']}"
    )


def load_cache() -> Dict[str, List[float]]:
    """Loads previously generated embeddings from disk."""

    if not CACHE_FILE.exists():
        return {}

    with CACHE_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_embedding(
    cache: Dict[str, List[float]],
    chunk: Dict,
    vector: List[float],
) -> None:
    """Saves one embedding immediately."""

    cache[_chunk_key(chunk)] = vector

    with CACHE_FILE.open("w", encoding="utf-8") as file:
        json.dump(cache, file)


def get_embedding(
    cache: Dict[str, List[float]],
    chunk: Dict,
) -> List[float] | None:
    """Returns a cached embedding if available."""

    return cache.get(_chunk_key(chunk))

