import logging
import traceback

from .incident import IncidentEvent
from .servicenow import ServiceNowClient
from .settings import get_settings

from qdrant_client import QdrantClient
from .agent.agent import run_agent

logger = logging.getLogger(__name__)

def _mark_processing_failure(servicenow, sys_id, error):
    logger.error(
        "S3.4 agent processing failed for sys_id=%s",
        sys_id,
        exc_info=error,
    )

    servicenow.mark_processing_failure(
        sys_id=sys_id,
        error_type=type(error).__name__,
    )

def _extract_incident(response: dict, fallback_sys_id: str) -> dict[str, str]:
    result = response.get("result", {})

    return {
        "number": str(result.get("number", "")),
        "sys_id": str(result.get("sys_id", fallback_sys_id)),
        "short_description": str(result.get("short_description", "")),
        "description": str(result.get("description", "")),
        "category": str(result.get("category", "")),
    }


def process_incident(event_payload: dict) -> dict:
    """Fetch incident context and run the autonomous support agent."""

    event = None
    servicenow = None

    try:
        settings = get_settings()
        event = IncidentEvent.model_validate(event_payload)

        servicenow = ServiceNowClient(settings)

        incident_response = servicenow.get_incident(event.sys_id)

        incident = _extract_incident(
            response=incident_response,
            fallback_sys_id=event.sys_id,
        )

        logger.info(
            "Incident preloaded: number=%s sys_id=%s",
            incident["number"],
            incident["sys_id"],
        )

        qdrant_client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
            timeout=120,
        )

        result = run_agent(
            settings=settings,
            incident=incident,
            servicenow=servicenow,
            qdrant_client=qdrant_client,
        )

        return result

    except Exception as error:
        logger.error(
            "S3.4 agent processing failed",
            exc_info=error,
        )

        if event is not None and servicenow is not None:
            try:
                _mark_processing_failure(
                    servicenow=servicenow,
                    sys_id=event.sys_id,
                    error=error,
                )
            except Exception:
                logger.error(
                    "Failed to mark incident as recoverable after processing failure",
                    exc_info=True,
                )

        return {
            "status": "failed",
            "sys_id": event.sys_id if event is not None else None,
            "error": type(error).__name__,
        }