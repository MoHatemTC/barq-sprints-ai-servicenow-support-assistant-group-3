"""Pydantic models: normalized article, chunk, and API/result schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class KnowledgeArticle(BaseModel):
    """A normalized ServiceNow knowledge article.

    ServiceNow-specific field names/shapes are resolved by the ServiceNow client; the rest of
    the service only ever sees this model.
    """

    sys_id: str
    number: str | None = None
    title: str = ""
    text: str = ""  # raw article body as returned by ServiceNow (usually HTML)
    workflow_state: str | None = None
    active: bool = True
    # Derived by the client: workflow_state is one of the configured "published" states AND active.
    published: bool = False
    updated_on: datetime | None = None
    knowledge_base: str | None = None

    @property
    def label(self) -> str:
        """Human friendly identifier for logs."""
        return self.number or self.sys_id


class Chunk(BaseModel):
    index: int
    text: str
    start: int  # character offsets into the text of the chunk's section
    end: int
    metadata: dict[str, Any] = Field(default_factory=dict)


# ----------------------------------------------------------------------------- results

SyncAction = Literal["created", "updated", "deleted", "skipped", "failed"]


class ArticleSyncResult(BaseModel):
    sys_id: str
    number: str | None = None
    action: SyncAction
    chunks: int = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.action != "failed"


class SyncSummary(BaseModel):
    status: Literal["completed", "completed_with_errors"]
    processed: int
    created: int
    updated: int
    deleted: int
    skipped: int
    failed: int
    since: datetime | None = None
    failures: list[ArticleSyncResult] = Field(default_factory=list)

    @classmethod
    def from_results(
        cls, results: list[ArticleSyncResult], since: datetime | None = None
    ) -> SyncSummary:
        def count(action: str) -> int:
            return sum(1 for r in results if r.action == action)

        failed = count("failed")
        return cls(
            status="completed" if failed == 0 else "completed_with_errors",
            processed=len(results),
            created=count("created"),
            updated=count("updated"),
            deleted=count("deleted"),
            skipped=count("skipped"),
            failed=failed,
            since=since,
            failures=[r for r in results if r.action == "failed"],
        )


# ----------------------------------------------------------------------------- API schemas


class SyncRequest(BaseModel):
    since: datetime | None = Field(
        default=None,
        description="Only sync articles updated at/after this time (UTC if no offset). "
        "Defaults to the last successful sync.",
    )
    full: bool = Field(default=False, description="Ignore timestamps and sync every article.")


class SingleSyncResponse(BaseModel):
    status: Literal["success", "failed"]
    sys_id: str
    number: str | None = None
    action: SyncAction
    chunks: int = 0
    error: str | None = None


class WebhookEvent(BaseModel):
    sys_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")
    event: str | None = None
