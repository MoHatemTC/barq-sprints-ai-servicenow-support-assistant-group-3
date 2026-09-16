"""
Thin ServiceNow REST client for the BARQ G3 support assistant.

Design note — why this client is deliberately narrow:

The S2.3 requirement is an *absolute* exclusion of incident resolution,
closure, and reassignment. Descriptions alone don't enforce that: if the
agent had a generic "update incident" capability, a model could set
state=6 or assignment_group and quietly resolve or reassign a ticket.

So the guarantee is enforced here, at the transport layer:

  * ``update_incident`` accepts ONLY fields in ``ALLOWED_INCIDENT_FIELDS``
    (currently: work_notes). Anything else raises ForbiddenFieldError
    before a request is ever sent.
  * ``BLOCKED_INCIDENT_FIELDS`` is checked explicitly and named in the
    error, so the failure is loud and auditable rather than silent.
  * There is no delete method, and no generic PATCH/POST passthrough.

Credentials are read from environment variables only. Never hardcode
them and never commit a populated .env file.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)


class ServiceNowConfigError(RuntimeError):
    """Raised when required ServiceNow configuration is missing."""


class ForbiddenFieldError(PermissionError):
    """Raised when a write is attempted on a field the agent may not touch."""


# Fields the agent is permitted to write on an incident. Keep this list
# minimal — adding to it widens the agent's authority.
ALLOWED_INCIDENT_FIELDS = {"work_notes"}

# Explicitly named so violations produce a clear, auditable error.
BLOCKED_INCIDENT_FIELDS = {
    "state",
    "incident_state",
    "close_code",
    "close_notes",
    "closed_at",
    "closed_by",
    "resolved_at",
    "resolved_by",
    "resolution_code",
    "assignment_group",
    "assigned_to",
    "active",
}


class ServiceNowClient:
    def __init__(
        self,
        instance_url: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        timeout: int = 30,
        live_writes: Optional[bool] = None,
    ) -> None:
        self.instance_url = (instance_url or os.getenv("SERVICENOW_INSTANCE_URL", "")).rstrip("/")
        user = user or os.getenv("SERVICENOW_USER", "")
        password = password or os.getenv("SERVICENOW_PASSWORD", "")

        # Writes (work notes) are OFF by default. This is a definitions-task
        # deliverable (S2.3) — nothing should land on a shared team instance
        # unless someone deliberately opts in. Reads (KB search, incident
        # lookup) are unaffected; only update_incident is gated.
        if live_writes is None:
            live_writes = os.getenv("SERVICENOW_LIVE_WRITES", "false").strip().lower() in (
                "1", "true", "yes", "on",
            )
        self.live_writes = live_writes

        missing = [
            name
            for name, value in (
                ("SERVICENOW_INSTANCE_URL", self.instance_url),
                ("SERVICENOW_USER", user),
                ("SERVICENOW_PASSWORD", password),
            )
            if not value
        ]
        if missing:
            raise ServiceNowConfigError(
                "Missing required environment variable(s): "
                + ", ".join(missing)
                + ". Copy .env.example to .env and fill it in."
            )

        self.timeout = timeout
        self._session = requests.Session()
        self._session.auth = HTTPBasicAuth(user, password)
        self._session.headers.update(
            {"Accept": "application/json", "Content-Type": "application/json"}
        )

    # -- internals ---------------------------------------------------------

    def _url(self, path: str) -> str:
        return f"{self.instance_url}/{path.lstrip('/')}"

    def _get(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        resp = self._session.get(self._url(path), params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    # -- knowledge base ----------------------------------------------------

    def search_knowledge(
        self, query: str, limit: int = 5, kb_sys_id: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """Search knowledge articles.

        Tries the Knowledge Management API first (better relevance ranking),
        and falls back to a Table API LIKE query if that API isn't exposed
        on the instance.
        """
        kb_sys_id = kb_sys_id or os.getenv("SERVICENOW_KB_SYS_ID") or None

        params: Dict[str, Any] = {"query": query, "limit": limit}
        if kb_sys_id:
            params["kb"] = kb_sys_id

        try:
            data = self._get("/api/sn_km_api/knowledge/articles", params)
            articles = data.get("result", {}).get("articles", [])
            return [
                {
                    "number": a.get("number", ""),
                    "title": a.get("title", ""),
                    "snippet": a.get("snippet", ""),
                    "sys_id": a.get("id", ""),
                }
                for a in articles
            ]
        except requests.HTTPError:
            return self._search_knowledge_table(query, limit, kb_sys_id)

    def _search_knowledge_table(
        self, query: str, limit: int, kb_sys_id: Optional[str]
    ) -> List[Dict[str, str]]:
        sysparm_query = (
            f"workflow_state=published^active=true"
            f"^short_descriptionLIKE{query}^ORtextLIKE{query}"
        )
        if kb_sys_id:
            sysparm_query += f"^kb_knowledge_base={kb_sys_id}"

        data = self._get(
            "/api/now/table/kb_knowledge",
            {
                "sysparm_query": sysparm_query,
                "sysparm_limit": limit,
                "sysparm_fields": "number,short_description,text,sys_id",
                "sysparm_display_value": "true",
            },
        )
        return [
            {
                "number": r.get("number", ""),
                "title": r.get("short_description", ""),
                "snippet": (r.get("text", "") or "")[:400],
                "sys_id": r.get("sys_id", ""),
            }
            for r in data.get("result", [])
        ]

    # -- incidents (read + tightly-scoped write) ---------------------------

    def get_incident(self, incident_number: str) -> Optional[Dict[str, Any]]:
        data = self._get(
            "/api/now/table/incident",
            {
                "sysparm_query": f"number={incident_number}",
                "sysparm_limit": 1,
                "sysparm_display_value": "true",
            },
        )
        results = data.get("result", [])
        return results[0] if results else None

    def update_incident(self, sys_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        """Patch an incident — restricted to ALLOWED_INCIDENT_FIELDS.

        This is the single choke point for every incident write in the
        project. Widening it widens the agent's authority, so don't.

        The field guard below runs unconditionally, live_writes or not —
        it's a safety check, not a convenience, so it must not depend on
        configuration. Only the actual network call is gated by
        ``self.live_writes``: when off (the default), the write is
        validated and logged but never sent, so running the agent against
        the shared dev instance can't leave notes on a teammate's incident
        by accident.
        """
        requested = set(fields)

        blocked = requested & BLOCKED_INCIDENT_FIELDS
        if blocked:
            raise ForbiddenFieldError(
                "The support agent is not permitted to resolve, close, or "
                f"reassign incidents. Blocked field(s): {sorted(blocked)}"
            )

        disallowed = requested - ALLOWED_INCIDENT_FIELDS
        if disallowed:
            raise ForbiddenFieldError(
                f"Field(s) not in the agent's allow-list: {sorted(disallowed)}. "
                f"Allowed: {sorted(ALLOWED_INCIDENT_FIELDS)}"
            )

        if not self.live_writes:
            logger.info(
                "DRY RUN (SERVICENOW_LIVE_WRITES=false): would PATCH incident "
                "%s with %s — no request sent.", sys_id, fields,
            )
            return {"sys_id": sys_id, "dry_run": True, **fields}

        resp = self._session.patch(
            self._url(f"/api/now/table/incident/{sys_id}"),
            json=fields,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json().get("result", {})

    def add_work_note(self, sys_id: str, note_text: str) -> Dict[str, Any]:
        return self.update_incident(sys_id, {"work_notes": note_text})
