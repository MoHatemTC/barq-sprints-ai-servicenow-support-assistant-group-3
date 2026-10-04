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

    def redact_incident_fields(
        self,
        sys_id: str,
        fields: dict[str, str],
    ) -> dict[str, Any]:
        allowed_fields = {"short_description", "description"}
        if not fields or not set(fields).issubset(allowed_fields):
            raise ValueError("Only non-empty incident description fields may be redacted")

        return self._request(
            "PATCH",
            f"/api/now/table/incident/{sys_id}",
            json=fields,
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
            "x_2215697_ai_ser_0_human_review_required": True,
            "x_2215697_ai_ser_0_ai_suggested_response": "",
        
            "work_notes": (
                "AI processing failed. "
                f"Incident remains recoverable. Error: {error_type}"
            ),
        },
    )

    def claim_incident(self, sys_id: str) -> dict[str, Any]:
        """Claim the incident by setting ai_status to in_progress via Table API PATCH."""
        return self._request(
            "PATCH",
            f"/api/now/table/incident/{sys_id}",
            json={
                "x_2215697_ai_ser_0_ai_status": "in_progress",
            },
        )

    def get_kb_article(self, sys_id: str) -> dict[str, Any]:
        """Fetch a single KB article by sys_id from kb_knowledge table."""
        return self._request(
            "GET",
            f"/api/now/table/kb_knowledge/{sys_id}",
            params={
                "sysparm_fields": (
                    "sys_id,number,short_description,text,category,workflow_state"
                )
            },
        )

    def list_kb_articles(self) -> list[dict[str, Any]]:
        """Fetch all published KB articles from kb_knowledge table."""
        resp = self._request(
            "GET",
            "/api/now/table/kb_knowledge",
            params={
                "sysparm_query": "workflow_state=published",
                "sysparm_fields": (
                    "sys_id,number,short_description,text,category"
                ),
                "sysparm_limit": "1000",
            },
        )
        return resp.get("result", [])

    def download_attachment(
        self,
        attachment_sys_id: str,
        max_bytes: int,
    ) -> bytes:
        """Stream one ServiceNow attachment, stopping if it exceeds max_bytes."""
        if len(attachment_sys_id) != 32 or any(
            char not in "0123456789abcdefABCDEF" for char in attachment_sys_id
        ):
            raise ValueError("attachment_sys_id must be a 32-character ServiceNow sys_id")
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")

        url = f"{self.base_url}/api/now/attachment/{attachment_sys_id}/file"
        for attempt in range(2):
            try:
                with httpx.stream(
                    "GET",
                    url,
                    auth=self.auth,
                    headers={"Accept": "application/pdf"},
                    timeout=60.0,
                ) as response:
                    if (
                        response.status_code == 429 or response.status_code >= 500
                    ) and attempt == 0:
                        time.sleep(1)
                        continue
                    response.raise_for_status()

                    content_length = response.headers.get("Content-Length")
                    if content_length and int(content_length) > max_bytes:
                        raise ValueError(
                            f"ServiceNow attachment exceeds the {max_bytes}-byte limit"
                        )

                    content = bytearray()
                    for chunk in response.iter_bytes():
                        content.extend(chunk)
                        if len(content) > max_bytes:
                            raise ValueError(
                                f"ServiceNow attachment exceeds the {max_bytes}-byte limit"
                            )
                    return bytes(content)
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt == 0:
                    time.sleep(1)
                    continue
                raise

        raise RuntimeError("ServiceNow attachment download failed after one retry")

    def update_runbook_upload(
        self,
        record_sys_id: str,
        status_value: str,
        notes: str,
    ) -> dict[str, Any]:
        """Write ingestion status to the configured ServiceNow runbook record."""
        if len(record_sys_id) != 32 or any(
            char not in "0123456789abcdefABCDEF" for char in record_sys_id
        ):
            raise ValueError("record_sys_id must be a 32-character ServiceNow sys_id")
        if status_value not in {"Processing", "Ingested", "Failed"}:
            raise ValueError("Invalid runbook ingestion status")

        return self._request(
            "PATCH",
            f"/api/now/table/{self.settings.servicenow_runbook_table}/{record_sys_id}",
            json={
                "status": status_value,
                "ingestion_notes": notes[:500],
            },
        )
