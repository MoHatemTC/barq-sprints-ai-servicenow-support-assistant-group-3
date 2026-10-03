"""Orchestrates: fetch -> normalize -> chunk -> embed -> (delete old) -> upsert.

Failure isolation: every article is processed independently; one failure never aborts a batch.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime, timedelta

from app.exceptions import KBSyncError, ServiceNowNotFoundError
from app.models.knowledge import ArticleSyncResult, KnowledgeArticle, SyncSummary
from app.services.chunker import Chunker
from app.services.embedder import EmbeddingService
from app.services.qdrant import QdrantRepository
from app.services.sections import extract_sections
from app.services.servicenow import FetchFailure, ServiceNowClient
from app.services.state import SyncStateStore

logger = logging.getLogger(__name__)


class IngestionService:
    def __init__(
        self,
        *,
        servicenow: ServiceNowClient,
        embedder: EmbeddingService,
        repository: QdrantRepository,
        chunker: Chunker,
        state_store: SyncStateStore | None = None,
        include_title: bool = True,
        initial_lookback: timedelta = timedelta(hours=24),
        state_safety_margin: timedelta = timedelta(seconds=60),
    ) -> None:
        self._servicenow = servicenow
        self._embedder = embedder
        self._repository = repository
        self._chunker = chunker
        self._state = state_store
        self._include_title = include_title
        self._initial_lookback = initial_lookback
        self._margin = state_safety_margin
        # Serializes delete+upsert so concurrent syncs (API + webhook) cannot interleave.
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ single article
    def sync_article(self, sys_id: str) -> ArticleSyncResult:
        """Fetch one article from ServiceNow and synchronize it. Never raises."""
        logger.info("Synchronizing article sys_id=%s", sys_id)
        try:
            try:
                article = self._servicenow.get_article(sys_id)
            except ServiceNowNotFoundError:
                logger.warning(
                    "Article sys_id=%s not found in ServiceNow; removing any indexed chunks", sys_id
                )
                with self._lock:
                    removed = self._repository.delete_article(sys_id)
                return ArticleSyncResult(
                    sys_id=sys_id, action="deleted" if removed else "skipped", chunks=0
                )
            logger.info("Fetched article %s", article.label)
            return self.process_article(article)
        except Exception as exc:  # noqa: BLE001 - converted to a failed result, never swallowed
            return self._failure(sys_id, None, exc)

    def process_article(self, article: KnowledgeArticle) -> ArticleSyncResult:
        """Synchronize an already-fetched article. Raises on failure (callers isolate it)."""
        with self._lock:
            return self._process_locked(article)

    def _process_locked(self, article: KnowledgeArticle) -> ArticleSyncResult:
        label = article.label

        if not article.published:
            logger.info(
                "Article %s is not published (state=%s, active=%s); removing vectors",
                label, article.workflow_state, article.active,
            )  # fmt: skip
            return self._remove(article)

        sections = extract_sections(article.text)
        chunks = self._chunker.chunk_sections(article, sections)
        if not chunks:
            logger.warning("Article %s has no indexable content; removing any vectors", label)
            return self._remove(article)
        logger.info("Article %s contains %d chunks", label, len(chunks))

        # Embed BEFORE touching Qdrant: the most failure-prone step must not leave the article
        # half-deleted.
        texts = [
            f"{article.title}\n\n{c.text}" if self._include_title and article.title else c.text
            for c in chunks
        ]
        vectors = self._embedder.embed_documents(texts)
        logger.info("Generated %d embeddings for %s", len(vectors), label)

        existed = self._repository.article_exists(article.sys_id)
        if existed:
            # Never append: remove every old chunk so stale content cannot be retrieved.
            deleted = self._repository.delete_article(article.sys_id)
            logger.info("Deleted %d old chunk(s) for %s", deleted, label)
        self._repository.upsert_chunks(article, chunks, vectors)
        logger.info("Successfully synchronized %s", label)
        return ArticleSyncResult(
            sys_id=article.sys_id,
            number=article.number,
            action="updated" if existed else "created",
            chunks=len(chunks),
        )

    def _remove(self, article: KnowledgeArticle) -> ArticleSyncResult:
        removed = self._repository.delete_article(article.sys_id)
        return ArticleSyncResult(
            sys_id=article.sys_id,
            number=article.number,
            action="deleted" if removed else "skipped",
            chunks=0,
        )

    # ------------------------------------------------------------------ batch
    def run_sync(self, since: datetime | None = None, full: bool = False) -> SyncSummary:
        """Synchronize every article changed since `since`.

        - full=True: every article; advances the stored watermark on success.
        - since given: just that window; the stored watermark is left untouched.
        - neither: since the last successful sync (or the initial lookback window).
        """
        started = datetime.now(UTC)
        manages_state = True
        if full:
            effective: datetime | None = None
        elif since is not None:
            effective = since if since.tzinfo else since.replace(tzinfo=UTC)
            manages_state = False
        else:
            saved = self._state.load() if self._state else None
            effective = saved or (started - self._initial_lookback)

        logger.info("Starting KB synchronization (since=%s)", effective or "beginning of time")
        fetch_failures: list[FetchFailure] = []
        articles = self._servicenow.get_articles_modified_since(effective, errors=fetch_failures)

        results: list[ArticleSyncResult] = []
        for article in articles:
            try:
                results.append(self.process_article(article))
            except Exception as exc:  # noqa: BLE001
                results.append(self._failure(article.sys_id, article.number, exc))
        for failure in fetch_failures:
            results.append(
                ArticleSyncResult(
                    sys_id=failure.sys_id or "unknown", action="failed", error=failure.error
                )
            )

        summary = SyncSummary.from_results(results, since=effective)
        if self._state and manages_state and summary.failed == 0:
            self._state.save(started - self._margin)
        logger.info(
            "KB synchronization finished: processed=%d created=%d updated=%d deleted=%d "
            "skipped=%d failed=%d",
            summary.processed, summary.created, summary.updated, summary.deleted,
            summary.skipped, summary.failed,
        )  # fmt: skip
        return summary

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _failure(sys_id: str, number: str | None, exc: Exception) -> ArticleSyncResult:
        label = number or sys_id
        if isinstance(exc, KBSyncError):
            logger.error("Failed to synchronize %s: %s", label, exc)
            message = str(exc)
        else:
            logger.exception("Unexpected error synchronizing %s", label)
            message = f"Unexpected error: {type(exc).__name__}"
        return ArticleSyncResult(sys_id=sys_id, number=number, action="failed", error=message)
