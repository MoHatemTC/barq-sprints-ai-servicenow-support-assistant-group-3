"""HTTP API."""

from __future__ import annotations

import hmac
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from fastapi import Path as PathParam
from pydantic import SecretStr

from app.container import Container
from app.exceptions import KBSyncError
from app.models.knowledge import SingleSyncResponse, SyncRequest, SyncSummary, WebhookEvent

logger = logging.getLogger(__name__)
router = APIRouter()


def get_container(request: Request) -> Container:
    return request.app.state.container


def _matches(supplied: str | None, expected: SecretStr) -> bool:
    return hmac.compare_digest((supplied or "").encode(), expected.get_secret_value().encode())


def require_api_token(request: Request, container: Container = Depends(get_container)) -> None:
    """If API_AUTH_TOKEN is configured, require it in the X-API-Key header."""
    token = container.settings.api_auth_token
    if token is not None and not _matches(request.headers.get("x-api-key"), token):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def _check(fn) -> str:
    try:
        fn()
        return "ok"
    except Exception as exc:  # noqa: BLE001 - reported, not hidden
        return f"error: {type(exc).__name__}: {exc}"


@router.get("/health")
def health(response: Response, deep: bool = False, container: Container = Depends(get_container)):
    """Liveness. Add `?deep=true` to also probe Qdrant and ServiceNow (503 if either is down)."""
    body: dict = {"status": "ok"}
    if deep:
        deps = {
            "qdrant": _check(container.repository.ping),
            "servicenow": _check(container.servicenow.ping),
        }
        body["dependencies"] = deps
        if any(v != "ok" for v in deps.values()):
            body["status"] = "degraded"
            response.status_code = 503
    return body


@router.post("/kb/sync", response_model=SyncSummary, dependencies=[Depends(require_api_token)])
def sync_changed(body: SyncRequest | None = None, container: Container = Depends(get_container)):
    """Synchronize all articles changed since `since` / the last successful sync."""
    body = body or SyncRequest()
    try:
        return container.ingestion.run_sync(since=body.since, full=body.full)
    except KBSyncError as exc:
        logger.error("KB synchronization aborted: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post(
    "/kb/sync/{sys_id}",
    response_model=SingleSyncResponse,
    dependencies=[Depends(require_api_token)],
)
def sync_one(
    response: Response,
    sys_id: str = PathParam(pattern=r"^[A-Za-z0-9_\-]{1,64}$"),
    container: Container = Depends(get_container),
):
    """Synchronize a single article by sys_id."""
    result = container.ingestion.sync_article(sys_id)
    if not result.ok:
        response.status_code = 502
    return SingleSyncResponse(
        status="success" if result.ok else "failed",
        sys_id=result.sys_id,
        number=result.number,
        action=result.action,
        chunks=result.chunks,
        error=result.error,
    )


@router.post("/kb/events", status_code=202)
def kb_event(
    event: WebhookEvent,
    request: Request,
    background: BackgroundTasks,
    container: Container = Depends(get_container),
):
    """Optional ServiceNow webhook. Disabled unless WEBHOOK_SECRET is set.

    Authenticated with the X-Webhook-Secret header; the sync runs in the background so the
    ServiceNow business rule / REST message is not kept waiting.
    """
    secret = container.settings.webhook_secret
    if secret is None:
        raise HTTPException(status_code=503, detail="Webhook support is disabled")
    if not _matches(request.headers.get("x-webhook-secret"), secret):
        raise HTTPException(status_code=401, detail="Invalid or missing webhook secret")
    logger.info("Received KB event %s for sys_id=%s", event.event or "update", event.sys_id)
    background.add_task(container.ingestion.sync_article, event.sys_id)
    return {"status": "accepted", "sys_id": event.sys_id}
