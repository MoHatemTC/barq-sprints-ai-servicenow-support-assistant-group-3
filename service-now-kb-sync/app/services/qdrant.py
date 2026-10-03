"""Qdrant repository: deterministic point IDs, per-article delete, idempotent upserts."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from typing import Any

from qdrant_client import QdrantClient, models

from app.config import Settings
from app.exceptions import ConfigurationError, EmbeddingDimensionError, QdrantError
from app.models.knowledge import Chunk, KnowledgeArticle

logger = logging.getLogger(__name__)

# Fixed namespace => the same (sys_id, chunk_index) always yields the same point ID.
_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "barq/servicenow-kb-sync")
_UPSERT_BATCH = 100
_DISTANCES = {
    "Cosine": models.Distance.COSINE,
    "Dot": models.Distance.DOT,
    "Euclid": models.Distance.EUCLID,
}


class QdrantRepository:
    def __init__(
        self,
        client: QdrantClient,
        collection: str,
        dimension: int,
        *,
        text_field: str = "text",
        vector_name: str | None = None,
        distance: str = "Cosine",
    ) -> None:
        self._client = client
        self.collection = collection
        self.dimension = dimension
        self.text_field = text_field
        self.vector_name = vector_name
        self.distance = distance
        self._ready = False

    @classmethod
    def from_settings(cls, settings: Settings) -> QdrantRepository:
        client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None,
            timeout=30,
        )
        return cls(
            client,
            settings.qdrant_collection,
            settings.embedding_dimension,
            text_field=settings.qdrant_text_field,
            vector_name=settings.qdrant_vector_name,
            distance=settings.qdrant_distance,
        )

    def close(self) -> None:
        self._client.close()

    # ------------------------------------------------------------------ IDs / filters
    @staticmethod
    def point_id(sys_id: str, chunk_index: int) -> str:
        """Deterministic UUIDv5 of `{sys_id}:{chunk_index}`."""
        return str(uuid.uuid5(_NAMESPACE, f"{sys_id}:{chunk_index}"))

    @staticmethod
    def _article_filter(sys_id: str) -> models.Filter:
        return models.Filter(
            must=[models.FieldCondition(key="sys_id", match=models.MatchValue(value=sys_id))]
        )

    # ------------------------------------------------------------------ collection
    def ensure_collection(self) -> None:
        """Create the collection if missing; otherwise verify its vector size. Idempotent."""
        if self._ready:
            return
        if self._call("check collection", self._client.collection_exists, self.collection):
            info = self._call("read collection", self._client.get_collection, self.collection)
            size = self._existing_vector_size(info)
            if size != self.dimension:
                raise ConfigurationError(
                    f"Qdrant collection '{self.collection}' has vector size {size} but "
                    f"EMBEDDING_DIMENSION={self.dimension}. Fix the configuration or use a "
                    "different collection."
                )
        else:
            logger.info(
                "Creating Qdrant collection '%s' (dimension=%d, distance=%s)",
                self.collection, self.dimension, self.distance,
            )  # fmt: skip
            params = models.VectorParams(size=self.dimension, distance=_DISTANCES[self.distance])
            self._call(
                "create collection",
                self._client.create_collection,
                collection_name=self.collection,
                vectors_config={self.vector_name: params} if self.vector_name else params,
            )
        try:  # speeds up / enables filtered deletes on remote Qdrant; harmless if it exists
            self._client.create_payload_index(
                self.collection, "sys_id", models.PayloadSchemaType.KEYWORD
            )
        except Exception as exc:  # noqa: BLE001 - best effort, deletes still work unindexed
            logger.warning("Could not create payload index on 'sys_id': %s", type(exc).__name__)
        self._ready = True

    def _existing_vector_size(self, info: Any) -> int:
        vectors = info.config.params.vectors
        if isinstance(vectors, dict):
            if not self.vector_name:
                raise ConfigurationError(
                    f"Collection '{self.collection}' uses named vectors "
                    f"({', '.join(vectors)}); set QDRANT_VECTOR_NAME."
                )
            if self.vector_name not in vectors:
                raise ConfigurationError(
                    f"Collection '{self.collection}' has no vector named '{self.vector_name}' "
                    f"(available: {', '.join(vectors)})."
                )
            return vectors[self.vector_name].size
        if self.vector_name:
            raise ConfigurationError(
                f"QDRANT_VECTOR_NAME is set but collection '{self.collection}' "
                "uses an unnamed vector."
            )
        return vectors.size

    # ------------------------------------------------------------------ operations
    def upsert_chunks(
        self, article: KnowledgeArticle, chunks: list[Chunk], vectors: list[list[float]]
    ) -> int:
        """Upsert chunks with deterministic IDs. Re-running with the same input is a no-op."""
        if len(chunks) != len(vectors):
            raise ValueError(f"{len(chunks)} chunks but {len(vectors)} vectors")
        if not chunks:
            return 0
        for vector in vectors:
            if len(vector) != self.dimension:
                raise EmbeddingDimensionError(
                    f"Vector has {len(vector)} values but the Qdrant collection "
                    f"'{self.collection}' expects {self.dimension}"
                )
        self.ensure_collection()
        points = [
            models.PointStruct(
                id=self.point_id(article.sys_id, chunk.index),
                vector={self.vector_name: vector} if self.vector_name else vector,
                payload={
                    **chunk.metadata,
                    self.text_field: chunk.text,
                    "chunk_count": len(chunks),
                    "workflow_state": article.workflow_state,
                    "updated_on": article.updated_on.isoformat() if article.updated_on else None,
                    # Compatibility with the BARQ Agent's existing KB payload. Its searchKB reads
                    # article_id / section / category and uses article_id to build citations.
                    "article_id": article.number or article.sys_id,
                    "section": chunk.metadata.get("section", "Body"),
                    "category": "",
                    "short_description": article.title,
                    "kb_knowledge_base": article.knowledge_base,
                    "sys_updated_on": (
                        article.updated_on.strftime("%Y-%m-%d %H:%M:%S")
                        if article.updated_on
                        else None
                    ),
                },
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        for i in range(0, len(points), _UPSERT_BATCH):
            self._call(
                "upsert points",
                self._client.upsert,
                collection_name=self.collection,
                points=points[i : i + _UPSERT_BATCH],
                wait=True,
            )
        logger.info("Upserted %d chunks into Qdrant for %s", len(points), article.label)
        return len(points)

    def delete_article(self, sys_id: str) -> int:
        """Delete every chunk of an article. Returns how many points were removed."""
        self.ensure_collection()
        existing = self._count(sys_id)
        if existing:
            self._call(
                "delete points",
                self._client.delete,
                collection_name=self.collection,
                points_selector=models.FilterSelector(filter=self._article_filter(sys_id)),
                wait=True,
            )
            logger.info("Deleted %d chunk(s) for sys_id=%s", existing, sys_id)
        return existing

    def article_exists(self, sys_id: str) -> bool:
        self.ensure_collection()
        return self._count(sys_id) > 0

    def count_article_points(self, sys_id: str) -> int:
        self.ensure_collection()
        return self._count(sys_id)

    def ping(self) -> None:
        self._call("ping", self._client.get_collections)

    # ------------------------------------------------------------------ internals
    def _count(self, sys_id: str) -> int:
        result = self._call(
            "count points",
            self._client.count,
            collection_name=self.collection,
            count_filter=self._article_filter(sys_id),
            exact=True,
        )
        return result.count

    @staticmethod
    def _call(operation: str, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - re-raised as a typed domain error
            raise QdrantError(f"Qdrant operation '{operation}' failed: {exc}") from exc
