"""Dependency container: builds and owns the service objects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from app.config import Settings
from app.services.chunker import Chunker
from app.services.embedder import EmbeddingService, OpenAICompatibleEmbeddingService
from app.services.ingestion import IngestionService
from app.services.qdrant import QdrantRepository
from app.services.servicenow import ServiceNowClient
from app.services.state import SyncStateStore


@dataclass
class Container:
    settings: Settings
    servicenow: ServiceNowClient
    embedder: EmbeddingService
    repository: QdrantRepository
    ingestion: IngestionService

    def close(self) -> None:
        for resource in (self.servicenow, self.embedder, self.repository):
            close = getattr(resource, "close", None)
            if callable(close):
                close()


def build_container(settings: Settings) -> Container:
    servicenow = ServiceNowClient.from_settings(settings)
    embedder = OpenAICompatibleEmbeddingService.from_settings(settings)
    repository = QdrantRepository.from_settings(settings)
    ingestion = IngestionService(
        servicenow=servicenow,
        embedder=embedder,
        repository=repository,
        chunker=Chunker(settings.chunk_size, settings.chunk_overlap),
        state_store=SyncStateStore(settings.sync_state_path),
        include_title=settings.embedding_include_title,
        initial_lookback=timedelta(hours=settings.sync_initial_lookback_hours),
    )
    return Container(settings, servicenow, embedder, repository, ingestion)
