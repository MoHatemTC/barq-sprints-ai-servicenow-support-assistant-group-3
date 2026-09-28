# BARQ - ServiceNow AI Support Assistant (Group 3)

An intelligent ServiceNow Tier-1 support assistant that ingests incident and knowledge base (KB) events via HMAC-signed webhooks, orchestrates asynchronous processing with Celery and Redis, executes a retrieval-augmented agent (RAG with Qdrant and Gemini/LiteLLM), and writes diagnoses and suggested resolutions directly back to ServiceNow.

---

## Architecture Overview

```
                      +-----------------------------+
                      |     ServiceNow Instance     |
                      |  (Business Rules + HMAC)   |
                      +--------------+--------------+
                                     |
                                     | POST (HMAC-SHA256)
                                     v
                      +-----------------------------+
                      |         ngrok Tunnel        |
                      | (Public HTTPS -> Localhost) |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |       FastAPI / Uvicorn     |
                      |  - HMAC Signature Verify    |
                      |  - Redis Deduplication      |
                      +--------------+--------------+
                                     |
                                     v Enqueue Task
                      +-----------------------------+
                      |      Redis (Port 6379)      |
                      |     Celery Task Broker      |
                      +--------------+--------------+
                                     |
                                     v Dequeue
                      +-----------------------------+
                      |   Celery Worker (Solo Pool) |
                      |  1. Claim incident in SN    |
                      |  2. Semantic Search (Qdrant)|
                      |  3. LLM Agent Reasoning     |
                      |  4. Writeback to ServiceNow |
                      +-----------------------------+
```

---

## Prerequisites

1. **Python 3.11+** with [`uv`](https://github.com/astral-sh/uv) package manager.
2. **Redis**: Running locally on port `6379` (e.g. Windows service `redis-server`).
3. **ngrok CLI**: Authenticated with your ngrok account.
4. **ServiceNow Instance**: Access to a ServiceNow instance with the scoped application `x_2215697_ai_ser_0`.

---

## 1. Environment Setup (`.env`)

Clone the repository and install dependencies using `uv`:

```powershell
uv sync
```

Copy the example environment file:

```powershell
copy .env.example .env
```

Configure the following variables in `.env`:

```ini
# --- LLM & Embeddings ---
LLM_API_KEY=your_litellm_or_gemini_key
LLM_MODEL=gemini/gemini-2.5-flash
LLM_BASE_URL=https://management.sprints.ai/litellm
GEMINI_API_KEY=your_google_gemini_key

# --- ServiceNow Instance Credentials ---
SERVICENOW_INSTANCE_URL=https://devXXXXXX.service-now.com
SERVICENOW_USERNAME=admin
SERVICENOW_PASSWORD=your_instance_password

# --- Qdrant Vector Store ---
QDRANT_URL=https://your-cluster.qdrant.io:6333
QDRANT_API_KEY=your_qdrant_key
QDRANT_COLLECTION=kb_articles

# --- Agent Configuration ---
AGENT_MAX_ITERATIONS=5

# --- Langfuse Tracing (Optional / S3.4) ---
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com

# --- Webhook Security ---
# Shared secret for HMAC-SHA256 signature verification.
# Must match x_2215697_ai_ser_0.webhook.secret in ServiceNow.
SERVICENOW_WEBHOOK_SECRET=your_webhook_shared_secret

# --- Redis & Celery ---
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

> **Note on Redis 3.x Compatibility:** The Celery configuration in `src/barq_support/celery_app.py` is pre-patched with RESP2 (`protocol=2`) and disables the result backend to ensure full compatibility with local Redis 3.0.x on Windows without unsupported `HELLO` handshake errors.

---

## 2. ServiceNow System Properties Configuration

In your ServiceNow instance, navigate to **System Properties (`sys_properties.list`)** and ensure the following two properties are set:

| Property Name | Type | Value / Description |
| :--- | :--- | :--- |
| `x_2215697_ai_ser_0.webhook.url` | `string` | The public webhook URL pointing to your ngrok tunnel, e.g.:<br>`https://<your-subdomain>.ngrok-free.app/api/v1/events/servicenow` |
| `x_2215697_ai_ser_0.webhook.secret` | `string` | The shared secret used to sign the webhook payload. Must be identical to `SERVICENOW_WEBHOOK_SECRET` in `.env`. |

### ServiceNow Business Rules
- **Incident Webhook (`Outbound Webhook - Incident Events`)**: Listens on `incident` creation/update. Checks `category` (`network`, `software`, `hardware`, `inquiry`), verifies `active=true`, and skips if `x_2215697_ai_ser_0_ai_processed` is true or `x_2215697_ai_ser_0_ai_status` is in (`in_progress`, `suggested`, `escalated`). Signs payload with HMAC-SHA256 via Script Include `HmacSha256`.
- **KB Webhook (`Outbound Webhook - KB Events`)**: Listens on `kb_knowledge` published articles and deletions, dispatching sync events to the webhook.

---

## 3. Running the Services (3 Terminals)

Ensure the local Redis service is running on port `6379`. Then open **three separate terminals** in the project root:

### Terminal 1: FastAPI Webhook Receiver (Uvicorn)
```powershell
uv run uvicorn barq_support.main:app --port 8000
```
*Listens on `http://127.0.0.1:8000`. Exposes `/health` and `/api/v1/events/servicenow`.*

### Terminal 2: Celery Worker
```powershell
uv run celery -A barq_support.celery_app worker --loglevel=info --pool=solo
```
*Processes queued incident and KB events asynchronously using the `solo` execution pool on Windows.*

### Terminal 3: ngrok Tunnel
```powershell
ngrok http 8000 --url=https://<your-subdomain>.ngrok-free.app
```
*(If using a free ephemeral URL, omit `--url` and update `x_2215697_ai_ser_0.webhook.url` in ServiceNow with the assigned URL).*

---

## 4. Verification & Testing

### Automated Unit and Integration Tests
Run the pytest test suite:
```powershell
uv run pytest -q
```

### Live End-to-End Incident Verification
To verify the entire chain against live ServiceNow, run the end-to-end test script:
```powershell
uv run python -u scripts/test_live_incident_e2e.py
```
This script will:
1. Create a test incident in ServiceNow via the Table API.
2. Trigger the ServiceNow Business Rule to post an HMAC-signed webhook.
3. Ingest through ngrok -> FastAPI -> Redis deduplication.
4. Dispatch to Celery to claim the incident (`ai_status=in_progress`).
5. Execute the RAG agent to retrieve KB articles and generate a grounded suggestion.
6. Write the final resolution, confidence score, and status (`ai_status=suggested`, `ai_processed=true`) back to ServiceNow.

---

## Confidence Score Heuristics

The `confidence` value is an LLM-assigned heuristic score between 0.0 and 1.0.

It is based on:
- How directly the retrieved KB evidence addresses the incident.
- Whether the retrieved evidence provides a concrete resolution procedure.
- Whether all proposed resolution steps are supported by the retrieved KB content.
- Whether any important part of the incident remains unsupported.

The score is validated by the `SuggestAnswerInput` schema and must be within the range `0.0 <= confidence <= 1.0`.

The confidence score is not:
- A calibrated probability of correctness.
- A direct Qdrant similarity score.
- Computed mathematically from the retrieval score.

---

## Sprints & Contributions

| Sprint / Feature | Scope | Contributors |
|---|---|---|
| **S3.1** | Vision LLM PDF & KB Ingestion CLI (`scripts/ingest_pdf.py`) | Ashar |
| **S3.2** | Outbound Webhooks, HMAC-SHA256 Business Rules & Script Includes | Dana |
| **S3.3** | Webhook Receiver, Redis Deduplication, Celery Worker Architecture | Aliaa, Malak |
| **S3.4** | Core LangGraph Agent, Scoped Tools, Terminal Actions, Langfuse Tracing | Creative-Geek (Ahmed Taha) & Team |
| **S4 Integration** | Multi-vertical merge, Redis 3 compatibility, KB sync pipeline, E2E validation | Creative-Geek (Ahmed Taha) |\n