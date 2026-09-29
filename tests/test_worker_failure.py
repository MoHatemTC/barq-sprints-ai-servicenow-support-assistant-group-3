from unittest.mock import patch

from barq_support.worker import process_incident


class FakeServiceNow:
    def get_incident(self, sys_id):
        return {
            "result": {
                "number": "INC0012345",
                "sys_id": sys_id,
                "short_description": "Test incident",
                "description": "Test failure path",
                "category": "software",
            }
        }

    def _request(self, method, endpoint, **kwargs):
        print("FAILURE PATCH CALLED")
        print(method, endpoint)
        print(kwargs["json"])
        return {"result": "updated"}


with patch(
    "barq_support.worker.ServiceNowClient",
    return_value=FakeServiceNow(),
):
    with patch(
        "barq_support.worker.run_agent",
        side_effect=RuntimeError("simulated agent failure"),
    ):
        result = process_incident({"sys_id": "test-sys-id"})

print("FINAL RESULT:")
print(result)