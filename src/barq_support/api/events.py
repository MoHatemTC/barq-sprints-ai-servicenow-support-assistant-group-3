import json
import logging
import re
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status

from ..dedup import check_and_set_dedup, extract_event_id, get_redis_client
from ..security import verify_hmac_signature
from ..servicenow import ServiceNowClient
from ..settings import get_settings
from ..tasks import ingest_servicenow_attachment, process_servicenow_event, sync_kb_article

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/events", tags=["events"])
documents_router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


@router.post(
    "/servicenow",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Receive and dispatch ServiceNow incident webhooks",
)
async def receive_servicenow_webhook(
    request: Request,
    x_signature: str | None = Header(None, alias="X-Signature"),
) -> dict[str, Any]:
    """
    ServiceNow Webhook Ingestion Door:
    1. HMAC-SHA256 signature verification over raw request body bytes.
    2. JSON parsing & validation after signature passes.
    3. Redis atomic SETNX dedup gate (~24h TTL).
    4. Fast dispatch to Celery worker (returns 202 Accepted immediately).
    """
    settings = get_settings()

    # Step 1: HMAC verification before any JSON parsing
    raw_body = await request.body()
    verify_hmac_signature(
        raw_body=raw_body,
        signature_header=x_signature,
        secret=settings.servicenow_webhook_secret,
    )

    # Step 2: JSON parsing
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as exc:
        logger.warning("Failed to parse JSON body from webhook: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        ) from exc

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payload must be a JSON object",
        )

    # Step 3: Extract unique event identifier
    event_id = extract_event_id(payload)
    if not event_id:
        logger.warning("Missing event identifier in webhook payload: %s", payload)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Missing event identifier (incident_sys_id, sys_id, or event_id)",
        )

    # Step 4: Redis atomic SETNX dedup gate
    redis_client = get_redis_client(settings)
    is_new = check_and_set_dedup(
        event_id=event_id,
        redis_client=redis_client,
        ttl_seconds=settings.webhook_dedup_ttl_seconds,
    )

    if not is_new:
        logger.info(
            "Replay detected for event_id=%s. Returning 202 Accepted without Celery enqueue.",
            event_id,
        )
        return {
            "status": "accepted",
            "event_id": event_id,
            "deduplicated": True,
            "message": "Duplicate event ignored",
        }

    # Step 5: Fast Celery dispatch — branch on event type
    if "article_id" in payload:
        task = sync_kb_article.delay(payload)
        logger.info(
            "Dispatched KB event %s (op=%s) to Celery task %s",
            event_id, payload.get("operation"), task.id,
        )
    else:
        # Step 5a: Claim incident in ServiceNow (ai_status=in_progress) at queue time
        incident_sys_id = (
            payload.get("sys_id")
            or payload.get("incident_sys_id")
            or event_id
        )
        try:
            sn_client = ServiceNowClient(settings)
            sn_client.claim_incident(incident_sys_id)
            logger.info(
                "Claimed incident %s in ServiceNow (ai_status=in_progress) at queue time",
                incident_sys_id,
            )
        except Exception as exc:
            logger.warning(
                "Failed to claim incident %s at queue time (%s). Proceeding with Celery dispatch.",
                incident_sys_id,
                exc,
            )

        task = process_servicenow_event.delay(payload)
        logger.info("Dispatched incident event %s to Celery task %s", event_id, task.id)

    return {
        "status": "accepted",
        "event_id": event_id,
        "task_id": task.id,
        "deduplicated": False,
    }


@documents_router.post(
    "/servicenow-attachment",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue ingestion of a ServiceNow PDF attachment",
)
async def receive_servicenow_attachment(
    request: Request,
    x_signature: str | None = Header(None, alias="X-Signature"),
) -> dict[str, Any]:
    """Verify a signed attachment event, de-duplicate it, and queue ingestion."""
    settings = get_settings()
    raw_body = await request.body()
    verify_hmac_signature(
        raw_body=raw_body,
        signature_header=x_signature,
        secret=settings.servicenow_webhook_secret,
    )

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        ) from exc

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payload must be a JSON object",
        )

    attachment_sys_id = payload.get("attachment_sys_id")
    runbook_sys_id = payload.get("table_sys_id")
    file_name = payload.get("file_name")
    if (
        not isinstance(attachment_sys_id, str)
        or re.fullmatch(r"[0-9a-fA-F]{32}", attachment_sys_id) is None
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="attachment_sys_id must be a 32-character ServiceNow sys_id",
        )
    if (
        not isinstance(runbook_sys_id, str)
        or re.fullmatch(r"[0-9a-fA-F]{32}", runbook_sys_id) is None
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="table_sys_id must be a 32-character Runbook sys_id",
        )
    if not isinstance(file_name, str) or not file_name.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Only PDF attachments are accepted",
        )
    title = payload.get("title")
    if title is not None and (not isinstance(title, str) or len(title) > 120):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="title must be a string of at most 120 characters",
        )
    category = payload.get("category")
    if category is not None and (
        not isinstance(category, str)
        or category not in {"network", "software", "hardware", "vpn"}
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="category must be network, software, hardware, or vpn",
        )
    runbook_notes = payload.get("runbook_notes")
    if runbook_notes is not None and (
        not isinstance(runbook_notes, str) or len(runbook_notes) > 500
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="runbook_notes must be a string of at most 500 characters",
        )

    event_id = f"runbook:{attachment_sys_id}"
    is_new = check_and_set_dedup(
        event_id=event_id,
        redis_client=get_redis_client(settings),
        ttl_seconds=settings.webhook_dedup_ttl_seconds,
    )
    if not is_new:
        return {
            "status": "accepted",
            "event_id": event_id,
            "deduplicated": True,
            "message": "Duplicate attachment event ignored",
        }

    task_payload = {
        "attachment_sys_id": attachment_sys_id,
        "file_name": file_name,
        "table_sys_id": runbook_sys_id,
    }
    if title:
        task_payload["title"] = title
    if category:
        task_payload["category"] = category
    if runbook_notes:
        task_payload["runbook_notes"] = runbook_notes
    task = ingest_servicenow_attachment.delay(task_payload)
    logger.info(
        "Dispatched runbook attachment %s to Celery task %s",
        attachment_sys_id,
        task.id,
    )
    return {
        "status": "accepted",
        "event_id": event_id,
        "task_id": task.id,
        "deduplicated": False,
    }
