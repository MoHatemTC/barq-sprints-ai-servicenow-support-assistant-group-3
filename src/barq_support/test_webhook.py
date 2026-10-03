"""Manual smoke test: send one HMAC-signed incident webhook to a locally running API.

Usage (API must be running on localhost:8000):
    SERVICENOW_WEBHOOK_SECRET=<your-secret> uv run python src/barq_support/test_webhook.py
The secret is read from the environment / .env only and must never be hard-coded.
"""
import hashlib
import hmac
import json
import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

SECRET = os.getenv("SERVICENOW_WEBHOOK_SECRET", "")
if not SECRET:
    sys.exit("SERVICENOW_WEBHOOK_SECRET is not set (put it in .env or the environment).")

url = os.getenv("WEBHOOK_TEST_URL", "http://localhost:8000/api/v1/events/servicenow")

payload = {
    "incident_sys_id": "bbc2e7c32fcf4b102e0e5b707fa4e3a3",
    "number": "INC0010032",
}
body = json.dumps(payload).encode("utf-8")
sig = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()

resp = httpx.post(
    url,
    data=body,
    headers={"Content-Type": "application/json", "X-Signature": sig},
)
print(resp.status_code, resp.json())
