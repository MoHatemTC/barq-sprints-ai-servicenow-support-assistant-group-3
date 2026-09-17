from sentence_transformers import SentenceTransformer
from typing import List

# Model is loaded once when this module is imported, not on every call
_model = SentenceTransformer("all-MiniLM-L6-v2")

EMBEDDING_DIMENSION = 384  # fixed for the all-MiniLM-L6-v2 model


def embed_text(text: str) -> List[float]:
    """
    Takes a chunk's text and returns its embedding vector (384 dimensions).
    """
    vector = _model.encode(text, normalize_embeddings=True)
    return vector.tolist()


if __name__ == "__main__":
    sample = "The order service returns HTTP 500 under load."
    vec = embed_text(sample)
    print(f"Vector length: {len(vec)}")
    print(f"First 5 values: {vec[:5]}")