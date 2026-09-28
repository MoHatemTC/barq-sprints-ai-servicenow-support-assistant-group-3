import json
import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status

from ..dedup import check_and_set_dedup, extract_event_id, get_redis_client
from ..security import verify_hmac_signature
from ..settings import get_settings
from ..tasks import process_servicenow_event, sync_kb_article

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/events", tags=["events"])


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
        task = process_servicenow_event.delay(payload)
        logger.info("Dispatched incident event %s to Celery task %s", event_id, task.id)

    return {
        "status": "accepted",
        "event_id": event_id,
        "task_id": task.id,
        "deduplicated": False,
    }
