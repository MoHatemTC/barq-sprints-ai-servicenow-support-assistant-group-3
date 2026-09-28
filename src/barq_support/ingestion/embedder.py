from google import genai
from google.genai import types
from typing import List
import os
from dotenv import load_dotenv

load_dotenv()

_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

EMBEDDING_MODEL = "gemini-embedding-2"
EMBEDDING_DIMENSION = 3072
EMBEDDING_BATCH_SIZE = 50


def embed_text(text: str) -> List[float]:
    """
    Takes a single text and returns its Gemini Embedding 2 vector.
    Output dimension: 3072.
    """
    result = _client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
        config=types.EmbedContentConfig(
            output_dimensionality=EMBEDDING_DIMENSION,
        ),
    )

    return result.embeddings[0].values


def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Takes multiple texts and returns one embedding vector per text.
    """

    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(text=text)
            ],
        )
        for text in texts
    ]

    result = _client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=contents,
        config=types.EmbedContentConfig(
            output_dimensionality=EMBEDDING_DIMENSION,
        ),
    )

    return [embedding.values for embedding in result.embeddings]


if __name__ == "__main__":
    sample = "The order service returns HTTP 500 under load."

    vec = embed_text(sample)

    print(f"Vector length: {len(vec)}")
    print(f"First 5 values: {vec[:5]}")