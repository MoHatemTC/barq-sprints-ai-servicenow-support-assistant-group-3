"""Embedding abstraction + an OpenAI-compatible HTTP implementation.

The ingestion code depends only on `EmbeddingService`. To use another provider, subclass it and
implement `_embed`; dimension validation is inherited.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod

import httpx

from app.config import Settings
from app.exceptions import EmbeddingDimensionError, EmbeddingError

logger = logging.getLogger(__name__)

_RETRY_STATUS = {429, 500, 502, 503, 504}


class EmbeddingService(ABC):
    def __init__(self, dimension: int) -> None:
        if dimension <= 0:
            raise ValueError("dimension must be positive")
        self.dimension = dimension

    @abstractmethod
    def _embed(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text, in order."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._embed(texts)
        if len(vectors) != len(texts):
            raise EmbeddingError(
                f"Embedding provider returned {len(vectors)} vectors for {len(texts)} inputs"
            )
        for i, vector in enumerate(vectors):
            if len(vector) != self.dimension:
                raise EmbeddingDimensionError(
                    f"Embedding dimension mismatch: provider returned {len(vector)} values "
                    f"but EMBEDDING_DIMENSION={self.dimension} (input #{i}). Check EMBEDDING_MODEL "
                    "and EMBEDDING_DIMENSION, and the Qdrant collection's vector size."
                )
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


class OpenAICompatibleEmbeddingService(EmbeddingService):
    """Calls `POST {base_url}/embeddings` (OpenAI schema; also served by many gateways)."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        dimension: int,
        base_url: str = "https://api.openai.com/v1",
        batch_size: int = 64,
        timeout: float = 60.0,
        max_retries: int = 3,
        backoff_base: float = 0.5,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        super().__init__(dimension)
        self.model = model
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=timeout,
            transport=transport,
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> OpenAICompatibleEmbeddingService:
        return cls(
            api_key=settings.embedding_api_key.get_secret_value(),
            model=settings.embedding_model,
            dimension=settings.embedding_dimension,
            base_url=settings.embedding_base_url,
            batch_size=settings.embedding_batch_size,
        )

    def close(self) -> None:
        self._client.close()

    def _embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            vectors.extend(self._embed_batch(texts[i : i + self.batch_size]))
        return vectors

    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        payload = {"model": self.model, "input": batch}
        last_error = "unknown error"
        for attempt in range(self.max_retries + 1):
            try:
                response = self._client.post("/embeddings", json=payload)
            except httpx.TransportError as exc:
                last_error = f"{type(exc).__name__}"
            else:
                if response.status_code in (401, 403):
                    raise EmbeddingError(
                        f"Embedding provider rejected the API key (HTTP {response.status_code})"
                    )
                if response.status_code in _RETRY_STATUS:
                    last_error = f"HTTP {response.status_code}"
                elif response.status_code >= 400:
                    raise EmbeddingError(
                        f"Embedding request failed (HTTP {response.status_code}): "
                        f"{response.text[:200]}"
                    )
                else:
                    return self._parse(response, expected=len(batch))
            if attempt < self.max_retries:
                delay = self.backoff_base * (2**attempt)
                logger.warning(
                    "Embedding request failed (%s); retrying in %.1fs (%d/%d)",
                    last_error, delay, attempt + 1, self.max_retries,
                )  # fmt: skip
                time.sleep(delay)
        raise EmbeddingError(f"Embedding request failed after retries: {last_error}")

    @staticmethod
    def _parse(response: httpx.Response, expected: int) -> list[list[float]]:
        try:
            data = response.json()["data"]
            ordered = sorted(data, key=lambda item: item["index"])
            vectors = [list(map(float, item["embedding"])) for item in ordered]
        except (ValueError, KeyError, TypeError) as exc:
            raise EmbeddingError("Malformed response from embedding provider") from exc
        if len(vectors) != expected:
            raise EmbeddingError(
                f"Embedding provider returned {len(vectors)} vectors for {expected} inputs"
            )
        return vectors
