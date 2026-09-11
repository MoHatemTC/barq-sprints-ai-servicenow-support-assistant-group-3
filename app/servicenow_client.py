import logging
from typing import Any

import httpx

from app.config import settings
from app.schemas import KBArticle


logger = logging.getLogger(__name__)


class ServiceNowError(Exception):
    """Base exception for ServiceNow errors."""


class ServiceNowAuthError(ServiceNowError):
    """Raised when ServiceNow authentication fails."""


class ServiceNowClient:

    def __init__(self):
        self.base_url = settings.servicenow_instance_url.rstrip("/")
        self.timeout = settings.servicenow_timeout_seconds

        self.auth = httpx.BasicAuth(
            username=settings.servicenow_username,
            password=settings.servicenow_password,
        )

    async def get_published_kb_articles(self) -> list[KBArticle]:

        url = f"{self.base_url}/api/now/table/kb_knowledge"

        params = {
            "sysparm_query": "workflow_state=published",
            "sysparm_limit": settings.servicenow_kb_fetch_limit,
            "sysparm_exclude_reference_link": "true",
        }

        headers = {
            "Accept": "application/json",
        }
        
        logger.info(
            "Requesting: %s | params=%s | user=%s",
            url, params, settings.servicenow_username,
        )

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                auth=self.auth,
            ) as client:

                response = await client.get(
                    url,
                    headers=headers,
                    params=params,
                )

        except httpx.RequestError as exc:
            logger.error(
                "Could not connect to ServiceNow Knowledge API: %s",
                repr(exc),
            )

            raise ServiceNowError(
                "Could not connect to ServiceNow Knowledge API"
            ) from exc

        logger.info(
            "Response status=%s | body=%s",
            response.status_code, response.text[:300],
        )
        
        if response.status_code == 401:
            raise ServiceNowAuthError(
                "ServiceNow authentication failed (401) - "
                "check username/password"
            )

        if response.status_code == 403:
            raise ServiceNowError(
                "Authentication succeeded, but the user does not "
                "have permission to access the Knowledge Base"
            )

        if response.status_code != 200:
            logger.error(
                "ServiceNow Knowledge API failed with status %s",
                response.status_code,
            )

            raise ServiceNowError(
                f"ServiceNow Knowledge API failed "
                f"({response.status_code})"
            )

        try:
            payload: dict[str, Any] = response.json()
            results = payload.get("result", [])

        except ValueError as exc:
            raise ServiceNowError(
                "ServiceNow returned an invalid JSON response"
            ) from exc

        articles: list[KBArticle] = []

        for item in results:
            try:
                article = KBArticle(
                    sys_id=item.get("sys_id", ""),
                    number=item.get("number", ""),
                    short_description=item.get(
                        "short_description", ""
                    ),
                    text=item.get("text"),
                    workflow_state=item.get(
                        "workflow_state"
                    ),
                    category=item.get("category"),
                    kb_knowledge_base=item.get(
                        "kb_knowledge_base"
                    ),
                    sys_created_on=item.get(
                        "sys_created_on"
                    ),
                    sys_updated_on=item.get(
                        "sys_updated_on"
                    ),
                )

                articles.append(article)

            except Exception as exc:
                logger.warning(
                    "Skipping invalid Knowledge Base article: %s",
                    exc,
                )

        return articles