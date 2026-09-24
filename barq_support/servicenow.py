import time
from typing import Any

import httpx

from .settings import Settings


class ServiceNowClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = settings.servicenow_instance_url.rstrip("/")
        self.auth = (
            settings.servicenow_username,
            settings.servicenow_password,
        )

    def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{endpoint}"

        for attempt in range(2):
            try:
                response = httpx.request(
                    method,
                    url,
                    auth=self.auth,
                    timeout=30.0,
                    headers={"Accept": "application/json"},
                    **kwargs,
                )

                if response.status_code == 429 or response.status_code >= 500:
                    if attempt == 0:
                        time.sleep(1)
                        continue

                response.raise_for_status()
                return response.json()

            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt == 0:
                    time.sleep(1)
                    continue
                raise

        raise RuntimeError("ServiceNow request failed after one retry")

    def get_incident(self, sys_id: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/api/now/table/incident/{sys_id}",
            params={
                "sysparm_fields": (
                    "number,sys_id,short_description,"
                    "description,category"
                )
            },
        )

    def add_work_note(self, sys_id: str, note: str) -> dict[str, Any]:
        return self._request(
            "PATCH",
            f"/api/now/table/incident/{sys_id}",
            json={"work_notes": note},
        )

    def suggest_answer(
        self,
        sys_id: str,
        response: str,
        confidence: float,
    ) -> dict[str, Any]:
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")

        return self._request(
            "PATCH",
            f"/api/now/table/incident/{sys_id}",
            json={
                  "x_2215697_ai_ser_0_ai_status": "suggested",
                  "x_2215697_ai_ser_0_ai_suggested_response": response,
                  "x_2215697_ai_ser_0_ai_confidence": confidence,
                  "x_2215697_ai_ser_0_human_review_required": True,
                  "x_2215697_ai_ser_0_ai_processed": 1,
                },
           
        )

    def request_hr(
        self,
        sys_id: str,
        reason: str,
    ) -> dict[str, Any]:
        return self._request(
            "PATCH",
            f"/api/now/table/incident/{sys_id}",
            json={
               "x_2215697_ai_ser_0_ai_status": "escalated",
               "x_2215697_ai_ser_0_human_review_required": True,
               "x_2215697_ai_ser_0_ai_processed": 1,
               "work_notes": f"AI escalation: {reason}",}
        )
    def mark_processing_failure(self, sys_id: str, error_type: str) -> dict[str, Any]:
      return self._request(
        "PATCH",
        f"/api/now/table/incident/{sys_id}",
        json={
            "x_2215697_ai_ser_0_ai_status": "in_progress",
            "x_2215697_ai_ser_0_ai_processed": 0,
            "work_notes": (
                "AI processing failed. "
                f"Incident remains recoverable. Error: {error_type}"
            ),
        },
    )