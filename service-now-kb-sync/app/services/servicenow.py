"""ServiceNow Table API client for knowledge articles (`kb_knowledge` by default).

All ServiceNow-specific parsing lives here; callers only see `KnowledgeArticle`.
Only fields documented on kb_knowledge are requested, and parsing tolerates instances that expose
the title/body under different names (see TITLE_KEYS / BODY_KEYS).
"""

from __future__ import annotations

import logging
import re
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from app.config import Settings
from app.exceptions import (
    ServiceNowAuthError,
    ServiceNowError,
    ServiceNowNotFoundError,
    ServiceNowResponseError,
)
from app.models.knowledge import KnowledgeArticle

logger = logging.getLogger(__name__)

FIELDS = (
    "sys_id,number,short_description,text,wiki,workflow_state,active,published,"
    "sys_updated_on,kb_knowledge_base"
)
TITLE_KEYS = ("short_description", "title")
BODY_KEYS = ("text", "article_content", "wiki")
_RETRY_STATUS = {429, 500, 502, 503, 504}
_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9_\-]+$")


class FetchFailure:
    """A record that could not be parsed while listing articles."""

    def __init__(self, sys_id: str | None, error: str) -> None:
        self.sys_id = sys_id
        self.error = error

    def __repr__(self) -> str:  # pragma: no cover
        return f"FetchFailure(sys_id={self.sys_id!r}, error={self.error!r})"


def _scalar(value: Any) -> str:
    """ServiceNow returns plain strings, or {"value":..,"display_value":..} for references."""
    if value is None:
        return ""
    if isinstance(value, dict):
        return _scalar(value.get("value") or value.get("display_value"))
    return str(value)


def _parse_bool(value: Any, default: bool = True) -> bool:
    text = _scalar(value).strip().lower()
    if not text:
        return default
    return text in {"true", "1", "yes"}


def _parse_datetime(value: str) -> datetime | None:
    value = value.strip()
    if not value:
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            logger.warning("Could not parse ServiceNow timestamp %r", value)
            return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


class ServiceNowClient:
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        *,
        table: str = "kb_knowledge",
        published_states: list[str] | tuple[str, ...] = ("published",),
        kb_sys_ids: list[str] | tuple[str, ...] = (),
        page_size: int = 100,
        timeout: float = 30.0,
        max_retries: int = 3,
        backoff_base: float = 0.5,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        for token in (table, *published_states, *kb_sys_ids):
            if not _SAFE_TOKEN.match(token):
                raise ValueError(f"Unsafe value for ServiceNow query: {token!r}")
        self.table = table
        self.published_states = tuple(s.lower() for s in published_states)
        self.kb_sys_ids = tuple(kb_sys_ids)
        self.page_size = page_size
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            auth=httpx.BasicAuth(username, password),
            headers={"Accept": "application/json"},
            timeout=timeout,
            transport=transport,
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> ServiceNowClient:
        return cls(
            settings.service_now_url,
            settings.service_now_username,
            settings.service_now_password.get_secret_value(),
            table=settings.service_now_table,
            published_states=settings.published_states,
            kb_sys_ids=settings.kb_sys_ids,
            page_size=settings.service_now_page_size,
            timeout=settings.service_now_timeout_seconds,
            max_retries=settings.service_now_max_retries,
        )

    def close(self) -> None:
        self._client.close()

    # ------------------------------------------------------------------ public API
    def get_article(self, sys_id: str) -> KnowledgeArticle:
        """Fetch one article by sys_id (regardless of its workflow state)."""
        if not _SAFE_TOKEN.match(sys_id):
            raise ValueError(f"Invalid sys_id: {sys_id!r}")
        result = self._request(f"/api/now/table/{self.table}/{sys_id}", self._base_params())
        if not isinstance(result, dict) or not result:
            raise ServiceNowResponseError(f"Empty response for article sys_id={sys_id}")
        return self.parse_article(result)

    def get_articles_modified_since(
        self, since: datetime | None, errors: list[FetchFailure] | None = None
    ) -> list[KnowledgeArticle]:
        """Articles in ANY state updated at/after `since` (None = all).

        Unpublished articles are included on purpose so the caller can remove their vectors.
        Malformed records are logged and appended to `errors` (if given) instead of aborting.
        """
        return self._list(self._build_query(since=since), errors)

    def get_published_articles(
        self, errors: list[FetchFailure] | None = None
    ) -> list[KnowledgeArticle]:
        """All articles currently in a published state and active."""
        return self._list(self._build_query(published_only=True), errors)

    def ping(self) -> None:
        """Cheap connectivity/credential check; raises ServiceNowError on failure."""
        self._request(f"/api/now/table/{self.table}", {**self._base_params(), "sysparm_limit": 1})

    # ------------------------------------------------------------------ parsing
    def parse_article(self, record: Any) -> KnowledgeArticle:
        if not isinstance(record, dict):
            raise ServiceNowResponseError("Article record is not a JSON object")
        sys_id = _scalar(record.get("sys_id")).strip()
        if not sys_id:
            raise ServiceNowResponseError("Article record has no sys_id")
        title = next((t for k in TITLE_KEYS if (t := _scalar(record.get(k)).strip())), "")
        body = next((b for k in BODY_KEYS if (b := _scalar(record.get(k)).strip())), "")
        state = _scalar(record.get("workflow_state")).strip() or None
        active = _parse_bool(record.get("active"), default=True)
        return KnowledgeArticle(
            sys_id=sys_id,
            number=_scalar(record.get("number")).strip() or None,
            title=title,
            text=body,
            workflow_state=state,
            active=active,
            published=bool(state and state.lower() in self.published_states and active),
            updated_on=_parse_datetime(_scalar(record.get("sys_updated_on"))),
            knowledge_base=_scalar(record.get("kb_knowledge_base")).strip() or None,
        )

    # ------------------------------------------------------------------ internals
    @staticmethod
    def _base_params() -> dict[str, Any]:
        return {
            "sysparm_fields": FIELDS,
            "sysparm_display_value": "false",
            "sysparm_exclude_reference_link": "true",
        }

    def _build_query(self, *, since: datetime | None = None, published_only: bool = False) -> str:
        parts: list[str] = []
        if published_only:
            parts.append(f"workflow_stateIN{','.join(self.published_states)}")
            parts.append("active=true")
        if since is not None:
            since = since.replace(tzinfo=UTC) if since.tzinfo is None else since.astimezone(UTC)
            parts.append(
                f"sys_updated_on>=javascript:gs.dateGenerate('{since:%Y-%m-%d}','{since:%H:%M:%S}')"
            )
        if self.kb_sys_ids:
            parts.append(f"kb_knowledge_baseIN{','.join(self.kb_sys_ids)}")
        # Stable ordering (with a unique tie-breaker) so pagination never skips/duplicates rows.
        parts.append("ORDERBYsys_updated_on")
        parts.append("ORDERBYsys_id")
        return "^".join(parts)

    def _list(self, query: str, errors: list[FetchFailure] | None) -> list[KnowledgeArticle]:
        articles: list[KnowledgeArticle] = []
        offset = 0
        while True:
            params = {
                **self._base_params(),
                "sysparm_query": query,
                "sysparm_limit": self.page_size,
                "sysparm_offset": offset,
            }
            result = self._request(f"/api/now/table/{self.table}", params)
            if not isinstance(result, list):
                raise ServiceNowResponseError("Expected a list of articles in 'result'")
            for record in result:
                try:
                    articles.append(self.parse_article(record))
                except ServiceNowResponseError as exc:
                    sys_id = _scalar(record.get("sys_id")) if isinstance(record, dict) else None
                    logger.error("Skipping malformed article record sys_id=%s: %s", sys_id, exc)
                    if errors is not None:
                        errors.append(FetchFailure(sys_id or None, str(exc)))
            if len(result) < self.page_size:
                break
            offset += self.page_size
        logger.info("Fetched %d article(s) from ServiceNow", len(articles))
        return articles

    def _request(self, path: str, params: dict[str, Any]) -> Any:
        last_error = "unknown error"
        for attempt in range(self.max_retries + 1):
            try:
                response = self._client.get(path, params=params)
            except httpx.TimeoutException:
                last_error = "request timed out"
            except httpx.TransportError as exc:
                last_error = f"connection problem ({type(exc).__name__})"
            else:
                status = response.status_code
                if status in (401, 403):
                    raise ServiceNowAuthError(
                        f"ServiceNow rejected the credentials or access (HTTP {status})"
                    )
                if status == 404:
                    raise ServiceNowNotFoundError(f"ServiceNow record not found: {path}")
                if status in _RETRY_STATUS:
                    last_error = f"HTTP {status}"
                elif status >= 400:
                    raise ServiceNowError(f"ServiceNow request failed (HTTP {status})")
                else:
                    return self._unwrap(response)
            if attempt < self.max_retries:
                delay = self.backoff_base * (2**attempt)
                logger.warning(
                    "ServiceNow request failed (%s); retrying in %.1fs (%d/%d)",
                    last_error, delay, attempt + 1, self.max_retries,
                )  # fmt: skip
                time.sleep(delay)
        raise ServiceNowError(f"ServiceNow request failed after retries: {last_error}")

    @staticmethod
    def _unwrap(response: httpx.Response) -> Any:
        if not response.content or not response.content.strip():
            raise ServiceNowResponseError("Empty response body from ServiceNow")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ServiceNowResponseError("ServiceNow response was not valid JSON") from exc
        if not isinstance(payload, dict):
            raise ServiceNowResponseError("Unexpected ServiceNow response shape")
        if "error" in payload:
            message = (
                _scalar(payload["error"].get("message"))
                if isinstance(payload["error"], dict)
                else _scalar(payload["error"])
            )
            raise ServiceNowError(f"ServiceNow returned an error: {message or 'unknown'}")
        if "result" not in payload:
            raise ServiceNowResponseError("ServiceNow response is missing 'result'")
        return payload["result"]
