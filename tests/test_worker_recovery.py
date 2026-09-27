from unittest.mock import patch

from barq_support.worker import process_incident


class FakeServiceNow:
    def __init__(self, settings):
        self.settings = settings

    def get_incident(self, sys_id):
        print(f"GET incident: {sys_id}")

        return {
            "result": {
                "number": "INC00" + sys_id[-1],
                "sys_id": sys_id,
                "short_description": "Test incident",
                "description": "Test description",
                "category": "software",
            }
        }

    def mark_processing_failure(self, sys_id, error_type):
        print("\nFAILURE RECOVERY PATCH")
        print("PATCH /api/now/table/incident/" + sys_id)
        print({
            "ai_status": "in_progress",
            "ai_processed": False,
            "work_notes": (
                "AI processing failed. "
                f"Incident remains recoverable. Error: {error_type}"
            ),
        })

        return {"status": "recovered"}


class FakeQdrantClient:
    def __init__(self, url, api_key, timeout):
        print("QDRANT CLIENT CREATED")


class FakeSettings:
    qdrant_url = "fake-qdrant"
    qdrant_api_key = "fake-key"
    agent_max_iterations = 5


job_count = 0


def fake_get_settings():
    return FakeSettings()


def fake_run_agent(
    settings,
    incident,
    servicenow,
    qdrant_client,
):
    global job_count

    job_count += 1

    print(f"\n=== WORKER JOB {job_count} ===")

    if job_count == 1:
        print("BROKEN DEPENDENCY: Qdrant unavailable")
        raise RuntimeError("Qdrant dependency unavailable")

    print("SECOND JOB PROCESSED SUCCESSFULLY")

    return {
        "s3_terminal_called": True,
        "status": "suggested",
    }


with patch(
    "barq_support.worker.get_settings",
    side_effect=fake_get_settings,
), patch(
    "barq_support.worker.ServiceNowClient",
    side_effect=lambda settings: FakeServiceNow(settings),
), patch(
    "barq_support.worker.QdrantClient",
    side_effect=FakeQdrantClient,
), patch(
    "barq_support.worker.run_agent",
    side_effect=fake_run_agent,
):

    print("========== JOB 1: BROKEN DEPENDENCY ==========")

    result_1 = process_incident(
        {
            "sys_id": "test-sys-1",
        }
    )

    print("\nJOB 1 RESULT:")
    print(result_1)

    print("\n========== JOB 2: SUBSEQUENT JOB ==========")

    result_2 = process_incident(
        {
            "sys_id": "test-sys-2",
        }
    )

    print("\nJOB 2 RESULT:")
    print(result_2)