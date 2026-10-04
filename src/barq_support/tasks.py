import logging
from typing import Any

from .celery_app import celery_app
from .servicenow import ServiceNowClient
from .settings import get_settings
from .worker import process_incident
from .ingestion.ingest import ingest_article, delete_article
from .ingestion.runbook_pdf import ingest_runbook_pdf

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


@celery_app.task(
    name="barq_support.tasks.ingest_servicenow_attachment",
    bind=True,
    # Must stay below broker_transport_options["visibility_timeout"] (3600 s),
    # otherwise Redis re-delivers the task while it is still running.
    soft_time_limit=1800,
    time_limit=2400,
)
def ingest_servicenow_attachment(
    self,
    event_payload: dict[str, Any],
) -> dict[str, Any]:
    """Download and index a PDF runbook linked to a ServiceNow attachment."""
    attachment_sys_id = event_payload.get("attachment_sys_id")
    file_name = event_payload.get("file_name")
    runbook_sys_id = event_payload.get("table_sys_id")
    title = event_payload.get("title", "")
    category = event_payload.get("category", "")
    runbook_notes = event_payload.get("runbook_notes", "")
    if (
        not isinstance(attachment_sys_id, str)
        or not isinstance(file_name, str)
        or not isinstance(runbook_sys_id, str)
    ):
        raise ValueError(
            "Attachment event requires attachment_sys_id, file_name, and table_sys_id"
        )
    if not isinstance(title, str):
        raise ValueError("Attachment event title must be a string")
    if not isinstance(category, str):
        raise ValueError("Attachment event category must be a string")
    if not isinstance(runbook_notes, str):
        raise ValueError("Attachment event runbook_notes must be a string")

    settings = get_settings()
    servicenow = ServiceNowClient(settings)
    try:
        servicenow.update_runbook_upload(
            runbook_sys_id,
            status_value="Processing",
            notes="Downloading and indexing PDF runbook.",
        )
        pdf_bytes = servicenow.download_attachment(
            attachment_sys_id,
            max_bytes=settings.servicenow_attachment_max_bytes,
        )
        result = ingest_runbook_pdf(
            attachment_sys_id=attachment_sys_id,
            file_name=file_name,
            pdf_bytes=pdf_bytes,
            title=title,
            category=category,
            runbook_notes=runbook_notes,
        )
    except Exception as exc:
        try:
            servicenow.update_runbook_upload(
                runbook_sys_id,
                status_value="Failed",
                notes=f"Ingestion failed ({type(exc).__name__}). Check backend worker logs.",
            )
        except Exception:
            logger.exception(
                "Could not mark runbook record %s as Failed",
                runbook_sys_id,
            )
        raise

    servicenow.update_runbook_upload(
        runbook_sys_id,
        status_value="Ingested",
        notes=f"Indexed {result['chunks']} chunks from {result['pages']} PDF pages.",
    )
    logger.info("Runbook attachment %s ingested: %s", attachment_sys_id, result)
    return {
        "status": "success",
        "ingestion_status": result["status"],
        **{key: value for key, value in result.items() if key != "status"},
    }
