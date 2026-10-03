"""Shared fakes. No test touches the network or needs real credentials."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest
from qdrant_client import QdrantClient

from app.config import Settings
from app.container import Container
from app.exceptions import ServiceNowNotFoundError
from app.models.knowledge import KnowledgeArticle
from app.services.chunker import Chunker
from app.services.embedder import EmbeddingService
from app.services.ingestion import IngestionService
from app.services.qdrant import QdrantRepository

DIM = 8


def make_settings(**overrides) -> Settings:
    values = dict(
        service_now_url="https://example.service-now.com",
        service_now_username="svc-user",
        service_now_password="not-a-real-password",
        qdrant_url="http://localhost:6333",
        qdrant_collection="test_kb",
        embedding_api_key="not-a-real-key",
        embedding_model="test-model",
        embedding_dimension=DIM,
    )
    values.update(overrides)
    return Settings(_env_file=None, **values)


def make_article(sys_id="a1", number="KB001500", text=None, **kw) -> KnowledgeArticle:
    if text is None:
        text = (
            "<p>" + " ".join(f"VPN step {i} explains authentication." for i in range(60)) + "</p>"
        )
    defaults = dict(
        sys_id=sys_id,
        number=number,
        title="VPN Authentication Issue",
        text=text,
        workflow_state="published",
        active=True,
        published=True,
        updated_on=datetime(2026, 10, 1, tzinfo=UTC),
    )
    defaults.update(kw)
    return KnowledgeArticle(**defaults)


class FakeEmbedder(EmbeddingService):
    """Deterministic vectors; can be told to fail or to return the wrong dimension."""

    def __init__(self, dimension=DIM, fail_on: str | None = None, wrong_dim: bool = False):
        super().__init__(dimension)
        self.fail_on = fail_on
        self.wrong_dim = wrong_dim
        self.calls = 0

    def _embed(self, texts):
        self.calls += 1
        if self.fail_on and any(self.fail_on in t for t in texts):
            from app.exceptions import EmbeddingError

            raise EmbeddingError("embedding failed (simulated)")
        size = self.dimension + 1 if self.wrong_dim else self.dimension
        out = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            out.append([b / 255 + 0.01 for b in digest[:size]])
        return out


class FakeServiceNow:
    def __init__(self, articles=()):
        self.articles = {a.sys_id: a for a in articles}
        self.parse_failures = []

    def get_article(self, sys_id):
        if sys_id not in self.articles:
            raise ServiceNowNotFoundError(sys_id)
        return self.articles[sys_id]

    def get_articles_modified_since(self, since, errors=None):
        if errors is not None:
            errors.extend(self.parse_failures)
        return list(self.articles.values())

    def ping(self):
        return None


class RecordingRepository(QdrantRepository):
    """Records the order of mutating calls."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.log: list[str] = []

    def delete_article(self, sys_id):
        self.log.append("delete")
        return super().delete_article(sys_id)

    def upsert_chunks(self, article, chunks, vectors):
        self.log.append("upsert")
        return super().upsert_chunks(article, chunks, vectors)


@pytest.fixture
def repo() -> RecordingRepository:
    return RecordingRepository(QdrantClient(":memory:"), "test_kb", DIM)


@pytest.fixture
def make_service(repo):
    def _make(articles=(), embedder=None, **kw):
        sn = FakeServiceNow(articles)
        service = IngestionService(
            servicenow=sn,
            embedder=embedder or FakeEmbedder(),
            repository=repo,
            chunker=Chunker(200, 20),
            **kw,
        )
        return service, sn

    return _make


def make_container(service, sn, repo, **settings_overrides) -> Container:
    return Container(
        settings=make_settings(**settings_overrides),
        servicenow=sn,  # type: ignore[arg-type]
        embedder=FakeEmbedder(),
        repository=repo,
        ingestion=service,
    )
