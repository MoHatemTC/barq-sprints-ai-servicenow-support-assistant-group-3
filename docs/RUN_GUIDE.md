# Run Guide

This guide takes a clean checkout to a local backend and explains how to verify it. ServiceNow, Qdrant, Redis, and model-provider accounts are external prerequisites; no credentials or cloud services are bundled with the repository. Never commit a real `.env` file.

## 1. Prerequisites

- Python 3.11 or later and [`uv`](https://docs.astral.sh/uv/).
- Redis reachable by the API and Celery worker (the default is `redis://localhost:6379/0`).
- A Qdrant instance with access to the `kb_articles` collection.
- An OpenAI-compatible chat-completion endpoint plus model/API key (`LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`).
- Ollama running on the Docker host with the configured classifier model pulled.
- Gemini API key for `gemini-embedding-2` embeddings (`GEMINI_API_KEY`).
- For live incident/KB processing: a ServiceNow instance with the scoped app and custom incident fields used by this project.
- For ServiceNow-to-local callbacks: a public HTTPS tunnel such as ngrok. This is not needed for unit tests or DeepEval's capture-only writeback.
- Optional: Langfuse credentials for tracing. PDF ingestion additionally depends on local PDF rendering/OCR tools such as Poppler and Tesseract.

## 2. Install and configure

```powershell
git clone <repository-url>
Set-Location <repository-directory>
uv sync
Copy-Item .env.example .env
```

Fill in `.env` locally. Keep the Qdrant collection set to `kb_articles`: ingestion can be configured to write to another name, but the retrieval implementation currently queries the hard-coded `kb_articles` collection.

| Variable(s) | Required for | Notes |
|---|---|---|
| `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` | Agent and evaluation | The evaluation judge uses this gateway unless `EVAL_JUDGE_MODEL` / `--judge-model` overrides the model. |
| `PASSWORD_CLASSIFIER_BASE_URL`, `PASSWORD_CLASSIFIER_MODEL` | Ollama password classification | From Docker Desktop on Windows, use `http://host.docker.internal:11434`; the default model is `qwen2.5:1.5b`. |
| `PASSWORD_CLASSIFIER_TIMEOUT_SECONDS` | Ollama password classification | Timeout for one Ollama request, in seconds; defaults to 120 to allow for model loading. |
| `GEMINI_API_KEY` | Retrieval and ingestion | Used directly by the Gemini embedding client; the embedding model is `gemini-embedding-2`, output dimension 3072. |
| `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION` | Retrieval and ingestion | Keep the collection name `kb_articles` because retrieval does not read the configurable collection setting. |
| `SERVICENOW_INSTANCE_URL`, `SERVICENOW_USERNAME`, `SERVICENOW_PASSWORD` | Live ServiceNow access | Use a least-privilege integration user. These are unnecessary for offline tests and the DeepEval capture stub. |
| `SERVICENOW_WEBHOOK_SECRET` | Receiving ServiceNow callbacks | Must match the ServiceNow `x_2215697_ai_ser_0.webhook.secret` property. |
| `REDIS_URL`, `CELERY_BROKER_URL` | API and worker | Point both services to the same Redis database. |
| `CELERY_RESULT_BACKEND` | Optional Celery results | Set this to empty in `.env` (the example file contains a Redis URL); application results are written to ServiceNow and task results are ignored. |
| `AGENT_MAX_ITERATIONS` | Agent | Optional; defaults to 5. The agent searches once per incident; after retrieval, only `suggestAnswer` and `requestHR` remain available. |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` | Optional tracing | The configured host variable is `LANGFUSE_HOST`. |

## 3. Configure ServiceNow (live integration only)

1. Deploy the Business Rules represented in [`servicenow/scripts/incident.js`](../servicenow/scripts/incident.js) and [`servicenow/scripts/KB.js`](../servicenow/scripts/KB.js) into the appropriate scoped application/tables.
2. The scripts instantiate `x_2215697_ai_ser_0.HmacSha256`, but the Script Include implementation is **not present in this repository**. Provision that dependency in ServiceNow from the approved project source; do not assume it is supplied by these files.
3. Configure these system properties in ServiceNow:

   | Property | Value |
   |---|---|
   | `x_2215697_ai_ser_0.webhook.url` | `https://<your-public-host>/api/v1/events/servicenow` |
   | `x_2215697_ai_ser_0.webhook.secret` | Same private value as `SERVICENOW_WEBHOOK_SECRET` in `.env` |

4. Ensure the scoped incident table fields referenced in [`servicenow.py`](../src/barq_support/servicenow.py) exist and are accessible through the Table API, including AI status, suggested response, confidence, processed flag and human-review flag.

### Configure the Ollama password classifier

The API and worker call Ollama on the Docker host. Ollama uses Qwen to classify
the incident text; the backend masks supported credential formats locally and
fails closed if the model detects a credential the local rules cannot locate.
No second model call is used to rewrite the text.

1. Install and start Ollama on the host machine. Pull the configured model:

   ```powershell
   ollama pull qwen2.5:1.5b
   ```

2. In the application project's `.env`, configure:

   ```dotenv
   PASSWORD_CLASSIFIER_BASE_URL=http://host.docker.internal:11434
   PASSWORD_CLASSIFIER_MODEL=qwen2.5:1.5b
   PASSWORD_CLASSIFIER_TIMEOUT_SECONDS=120
   ```

   `host.docker.internal` lets Docker Desktop containers reach the host. If
   Ollama is bound only to loopback and the containers cannot connect, configure
   Ollama to listen on an address reachable from Docker and restrict that
   listener with your host firewall. Do not expose the Ollama port publicly.
   Remove obsolete `PASSWORD_CLASSIFIER_SPACE_ID` and
   `PASSWORD_CLASSIFIER_HF_TOKEN` settings.
3. From PowerShell in the application project folder, recreate the API and
   worker so they load the new environment:

```powershell
docker compose --progress plain build api worker
docker compose up -d --force-recreate api worker
```

4. Verify the backend can call Ollama:

   ```powershell
   docker compose exec worker /app/.venv/bin/python -c "from barq_support.password_protection import classify_password_presence; from barq_support.settings import get_settings; print(classify_password_presence('Synthetic printer connectivity check; no credentials included.', get_settings()))"
   ```

   This checks connectivity and response parsing, not model accuracy. It should
   print `False` for the synthetic safe example. Review worker logs for
   connection or model errors.

Ollama generates a constrained JSON boolean classification; unlike the direct
next-token-logit method, this approach generates a short response. Known
password-change and explicit credential-assignment formats are masked locally.
If the classifier flags a credential that the local rules cannot locate,
processing fails closed instead of forwarding that text to the support agent.
The raw incident text is sent to the configured Ollama server for detection,
so keep Ollama on a trusted, access-controlled host. These rules do not
guarantee detection or redaction of every credential format; evaluate false
positives and false negatives with representative synthetic data before
production. The same classifier/redaction gate is used for KB and PDF chunks
and search text. Existing incidents and stored Qdrant/PDF/cache data are not
retroactively scrubbed.

The incident Business Rule gates on active status, supported categories, and the AI status/processed fields. The KB Business Rule emits events for published articles and deletes. See the [Architecture](ARCHITECTURE.md) for event contracts and caveats.

### Optional: ServiceNow runbook upload dashboard

For manager-uploaded PDF runbooks and automatic ingestion, follow the complete
[Runbook Upload Dashboard guide](RUNBOOK_DASHBOARD.md). It covers the Runbook
table/list-form module, access controls, `sys_attachment` Business Rule,
webhook properties, and end-to-end verification. The backend also needs
`SERVICENOW_ATTACHMENT_MAX_BYTES` (default 25 MiB) and a ServiceNow integration
user authorized to download attachments.

## 4. Load knowledge into Qdrant

For ServiceNow KB articles:

```powershell
uv run python -m barq_support.ingestion.ingest
```

For a PDF manual (manual operation, not part of the event pipeline):

```powershell
uv run python scripts/ingest_pdf.py --file "<path-to-manual.pdf>"
```

The PDF command uses a vision-capable LLM and local PDF rendering/OCR dependencies. It can be slow and incurs model usage. Both ingestion paths create/use the configured Qdrant collection; the live retriever expects the collection to be named `kb_articles`. Check collection contents and run the retrieval evaluation stage before drawing quality conclusions about a newly loaded corpus.

## 5. Start the backend

Start Redis first. Then run each command in a separate terminal from the repository root:

**Terminal 1 — FastAPI receiver**

```powershell
uv run uvicorn barq_support.main:app --host 0.0.0.0 --port 8000
```

**Terminal 2 — Celery worker**

```powershell
uv run celery -A barq_support.celery_app worker --loglevel=info --pool=solo
```

The `solo` pool is suitable for the current Windows-oriented development setup and processes one task at a time per worker.

**Terminal 3 — optional public HTTPS tunnel**

```powershell
ngrok http 8000
```

Update the ServiceNow webhook URL property to the tunnel URL. No Dockerfile or Compose configuration is checked in; start the services directly as above.

## 6. Verify

Check the local health endpoint:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Run the offline tests that cover webhook handling and the evaluation harness:

The webhook integration tests need a signing secret, but they mock ServiceNow and do not call external services. Set a throwaway test-only value for this command; do not reuse a production secret:

```powershell
$env:SERVICENOW_WEBHOOK_SECRET = "local-test-only"
uv run pytest tests/test_webhook_ingestion.py tests/test_eval_utils.py tests/test_eval_harness_smoke.py -q
Remove-Item Env:SERVICENOW_WEBHOOK_SECRET
```

The repository also contains legacy/demo scripts that may execute at import time or need live credentials; the focused test command above avoids treating those as ordinary offline unit tests.

A live end-to-end check creates/updates a real incident and must only be run against a development ServiceNow instance:

```powershell
uv run python -u scripts/test_live_incident_e2e.py
```

## 7. Run DeepEval

The 100-turn run is already captured under [`evaluation/results/20261001T150304Z/`](../evaluation/results/20261001T150304Z/). To reproduce or create a new run, configure the LLM, Gemini, and Qdrant variables above:

```powershell
# Retrieval metrics only (does not call the LLM judge)
uv run python evaluation/run_eval.py --stage retrieval

# Small agent-path smoke run
uv run python evaluation/run_eval.py --stage agent --limit 3

# Full retrieval + agent run, including DeepEval metrics (costs model/API calls)
uv run python evaluation/run_eval.py
```

Each run writes `config.json`, aggregate metrics, per-case CSV/JSON, and a Markdown summary under a new timestamp directory in `evaluation/results/`. The agent stage uses a capture-only ServiceNow implementation and does not write to real incidents. Dataset filters and metric details are in the [evaluation guide](../evaluation/README.md).

## Security

- Put credentials only in `.env` or an approved secret manager; `.env` is ignored by Git.
- Use placeholders in documentation, examples, and screenshots. Never copy live credentials into evaluation artifacts.
- Review `git status` and staged changes before publishing. If a credential was committed at any point, removing it from the current file does not revoke it; rotate it.
- The evaluation harness redacts configured secret values and scans the run output, but this is a safeguard, not a replacement for human review.
