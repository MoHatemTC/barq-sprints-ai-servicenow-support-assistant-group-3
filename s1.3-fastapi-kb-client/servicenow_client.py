import httpx
from typing import List, Dict, Any
from config import settings

class ServiceNowKBClient:
    def __init__(self):
        self.base_url = settings.servicenow_instance_url.rstrip("/")
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        self._token = None

    async def _get_token(self) -> str:
        if self._token:
            return self._token
        token_url = f"{self.base_url}/oauth_token.do"
        data = {
            "grant_type": "password",
            "client_id": settings.servicenow_client_id,
            "client_secret": settings.servicenow_client_secret,
            "username": settings.servicenow_username,
            "password": settings.servicenow_password,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(token_url, data=data)
            resp.raise_for_status()
            self._token = resp.json()["access_token"]
        return self._token

    async def get_published_kb_articles(self, limit: int = 10) -> List[Dict[str, Any]]:
        token = await self._get_token()
        url = f"{self.base_url}/api/now/table/kb_knowledge"
        params = {
            "sysparm_query": "workflow_state=published",
            "sysparm_limit": limit,
            "sysparm_fields": "sys_id,number,short_description,text,workflow_state"
        }
        auth_headers = {**self.headers, "Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient(headers=auth_headers, timeout=15.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            return data.get("result", [])