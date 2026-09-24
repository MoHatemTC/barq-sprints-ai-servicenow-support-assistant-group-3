import logging
import time

from qdrant_client import QdrantClient

from .agent.agent import run_agent
from .incident import IncidentEvent
from .servicenow import ServiceNowClient
from .settings import get_settings

logger = logging.getLogger(__name__)

RECOVERY_WRITE_RETRIES = 2
RECOVERY_RETRY_DELAY_SECONDS = 1


def _mark_processing_failure(servicenow, sys_id, error):
    logger.error(
        "S3.4 agent processing failed for sys_id=%s",
        sys_id,
        exc_info=error,
    )

    last_error = None

    for attempt in range(1, RECOVERY_WRITE_RETRIES + 1):
        try:
            servicenow.mark_processing_failure(
                sys_id=sys_id,
                error_type=type(error).__name__,
            )

            logger.info(
                "Incident recovery state written successfully "
                "for sys_id=%s on attempt %s",
                sys_id,
                attempt,
            )
            return

        except Exception as recovery_error:
            last_error = recovery_error

            logger.error(
                "Failed to write recoverable state for sys_id=%s "
                "(attempt %s/%s)",
                sys_id,
                attempt,
                RECOVERY_WRITE_RETRIES,
                exc_info=True,
            )

            if attempt < RECOVERY_WRITE_RETRIES:
                time.sleep(RECOVERY_RETRY_DELAY_SECONDS)

    raise RuntimeError(
        "Unable to persist recoverable incident state after retries"
    ) from last_error


def _extract_incident(
    response: dict,
    fallback_sys_id: str,
) -> dict[str, str]:
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

        # Preload trusted incident context before starting the agent.
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

        # Explicitly pass the preloaded incident context to the agent.
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
            exc_info=True,
        )

        if event is not None and servicenow is not None:
            try:
                _mark_processing_failure(
                    servicenow=servicenow,
                    sys_id=event.sys_id,
                    error=error,
                )

            except Exception:
                # The worker must remain alive even if the recovery write
                # itself fails after all retry attempts.
                logger.error(
                    "Failed to mark incident as recoverable after "
                    "all recovery attempts",
                    exc_info=True,
                )

        return {
            "status": "failed",
            "sys_id": event.sys_id if event is not None else None,
            "error": type(error).__name__,
        }
