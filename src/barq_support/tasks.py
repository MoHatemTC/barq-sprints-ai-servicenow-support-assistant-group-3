import logging
from typing import Any

from .celery_app import celery_app
from .servicenow import ServiceNowClient
from .settings import get_settings
from .worker import process_incident
from .ingestion.ingest import ingest_article, delete_article

logger = logging.getLogger(__name__)


def _sanitize_for_json(data: Any) -> Any:
    """Ensure complex data structures (e.g. LangChain messages) serialize cleanly to JSON."""
    if isinstance(data, (str, int, float, bool, type(None))):
        return data
    if isinstance(data, dict):
        return {str(k): _sanitize_for_json(v) for k, v in data.items()}
    if isinstance(data, (list, tuple, set)):
        return [_sanitize_for_json(item) for item in data]
    if hasattr(data, "model_dump"):
        return _sanitize_for_json(data.model_dump())
    if hasattr(data, "dict"):
        return _sanitize_for_json(data.dict())
    if hasattr(data, "content"):
        return {
            "type": getattr(data, "type", data.__class__.__name__),
            "content": str(getattr(data, "content", "")),
        }
    return str(data)


@celery_app.task(name="barq_support.tasks.process_servicenow_event", bind=True)
def process_servicenow_event(self, event_payload: dict[str, Any]) -> dict[str, Any]:
    """
    Celery task that receives ServiceNow incident webhook events:
    1. Table API PATCH claim: sets ai_status = in_progress on the incident record.
    2. Only after claim PATCH succeeds: invokes the real S3.4 agent entry point.
    """
    sys_id = (
        event_payload.get("sys_id")
        or event_payload.get("incident_sys_id")
        or event_payload.get("event_id")
    )

    if not sys_id:
        err = f"No sys_id found in event payload: {event_payload}"
        logger.error(err)
        raise ValueError(err)

    logger.info("Executing Celery task for incident sys_id=%s", sys_id)

    settings = get_settings()
    servicenow = ServiceNowClient(settings)

    # 1. Mandatory First Action: Claim the incident in ServiceNow via Table API PATCH
    logger.info(
        "Claiming incident in ServiceNow Table API (ai_status=in_progress): sys_id=%s",
        sys_id,
    )
    claim_response = servicenow.claim_incident(sys_id)
    logger.info(
        "ServiceNow incident claimed successfully: sys_id=%s, result=%s",
        sys_id,
        claim_response.get("result", {}).get("x_2215697_ai_ser_0_ai_status", "ok"),
    )

    # 2. Only after claim succeeds: Hand off to real S3.4 agent entry point
    normalized_payload = dict(event_payload)
    normalized_payload["sys_id"] = sys_id

    logger.info("Invoking real S3.4 agent entry point (process_incident) for sys_id=%s", sys_id)
    agent_result = process_incident(normalized_payload)
    logger.info(
        "S3.4 agent processing finished for sys_id=%s with status=%s",
        sys_id,
        agent_result.get("status", "completed"),
    )

    safe_agent_result = _sanitize_for_json(agent_result)

    return {
        "status": "success",
        "sys_id": sys_id,
        "claimed": True,
        "agent_result": safe_agent_result,
    }


@celery_app.task(name="barq_support.tasks.sync_kb_article", bind=True)
def sync_kb_article(self, event_payload: dict[str, Any]) -> dict[str, Any]:
    """
    Celery task for KB article webhook events (created / updated / deleted).

    - created / updated: fetch article from ServiceNow, re-chunk, re-embed, upsert Qdrant.
    - deleted:           remove all Qdrant vectors for that article.
    """
    article_id = event_payload.get("article_id")
    operation = event_payload.get("operation", "updated")

    if not article_id:
        err = f"No article_id in KB event payload: {event_payload}"
        logger.error(err)
        raise ValueError(err)

    logger.info(
        "Executing KB sync task: article_id=%s operation=%s", article_id, operation
    )

    if operation == "deleted":
        result = delete_article(article_id)
    else:
        result = ingest_article(article_id)

    safe_result = _sanitize_for_json(result)
    logger.info("KB sync finished: %s", safe_result)
    return {"status": "success", "operation": operation, **safe_result}
