# Run Guide

This guide takes a clean checkout to a local backend and explains how to verify it. ServiceNow, Qdrant, Redis, and model-provider accounts are external prerequisites; no credentials or cloud services are bundled with the repository. Never commit a real `.env` file.

## 1. Prerequisites

- Python 3.11 or later and [`uv`](https://docs.astral.sh/uv/).
- Redis reachable by the API and Celery worker (the default is `redis://localhost:6379/0`).
- A Qdrant instance with access to the `kb_articles` collection.
- An OpenAI-compatible chat-completion endpoint plus model/API key (`LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`).
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
| `PASSWORD_CLASSIFIER_BASE_URL` | Incident password classification | Private vLLM server root URL (for example, `http://localhost:8001`) serving `Qwen/Qwen2.5-1.5B-Instruct`; supports `/tokenize` and `/v1/chat/completions`. `PASSWORD_CLASSIFIER_API_KEY` is optional. The vLLM tokenizer endpoint is not covered by vLLM's `--api-key` protection; keep the service on a trusted private network or protect it with a reverse proxy. |
| `PASSWORD_CLASSIFIER_MODEL`, `PASSWORD_CLASSIFIER_TIMEOUT_SECONDS` | Incident password classification | Defaults to `Qwen/Qwen2.5-1.5B-Instruct` and 10 seconds. Configure the model name to match the vLLM served model. |
| `GEMINI_API_KEY` | Retrieval and ingestion | Used directly by the Gemini embedding client; the embedding model is `gemini-embedding-2`, output dimension 3072. |
| `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION` | Retrieval and ingestion | Keep the collection name `kb_articles` because retrieval does not read the configurable collection setting. |
| `SERVICENOW_INSTANCE_URL`, `SERVICENOW_USERNAME`, `SERVICENOW_PASSWORD` | Live ServiceNow access | Use a least-privilege integration user. These are unnecessary for offline tests and the DeepEval capture stub. |
| `SERVICENOW_WEBHOOK_SECRET` | Receiving ServiceNow callbacks | Must match the ServiceNow `x_2215697_ai_ser_0.webhook.secret` property. |
| `REDIS_URL`, `CELERY_BROKER_URL` | API and worker | Point both services to the same Redis database. |
| `CELERY_RESULT_BACKEND` | Optional Celery results | Set this to empty in `.env` (the example file contains a Redis URL); application results are written to ServiceNow and task results are ignored. |
| `AGENT_MAX_ITERATIONS` | Agent | Optional; defaults to 5. |
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

Serve the classifier separately from the backend, for example with vLLM on a private host. vLLM is not an application dependency, so do not add it to this project's `pyproject.toml`. The upstream vLLM package requires Linux and does not support native Windows; run it in WSL2 with a compatible GPU setup or on a Linux host, following the [vLLM installation guide](https://docs.vllm.ai/en/stable/getting_started/installation/gpu/). If WSL reports that `wsl2.processors` exceeds the available logical processors, edit `%UserProfile%\.wslconfig` in Windows to set `[wsl2]` and `processors=8` (or remove the `processors` entry), then run `wsl --shutdown` in PowerShell and reopen the Linux distribution.

Use a full supported Linux distribution such as Ubuntu in WSL, not a minimal shell/container distribution. Check the current distribution with `cat /etc/os-release`; vLLM needs Python 3.10–3.13 and a compatible GPU. In Ubuntu, install vLLM in its own fresh environment (do not use the app's environment):

```bash
sudo apt update
sudo apt install -y curl
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env"
uv venv --python 3.12 --seed --managed-python
source .venv/bin/activate
uv pip install vllm --torch-backend=auto
```

If `nvidia-smi` is unavailable in WSL or the machine has no compatible GPU, vLLM's documented GPU installation will not work; use a compatible Linux GPU host or choose another classifier service.

After installation, start the server from the Ubuntu/WSL shell (where `vllm` was installed), not directly from Windows PowerShell:

```bash
vllm serve Qwen/Qwen2.5-1.5B-Instruct --host 0.0.0.0 --port 8001 --api-key "<private-token>"
```

In PowerShell, `\` is not a line-continuation character; use a single line or PowerShell's backtick (`` ` ``) if you split a command there.

Set `PASSWORD_CLASSIFIER_BASE_URL` to the vLLM service root as reachable from the Celery worker. When the classifier flags a credential, the existing OpenAI-compatible chat model (`LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`) performs redaction; cleaned incident fields are rechecked before they are written to ServiceNow or passed to the support agent. The same check runs on KB text/metadata before embedding or Qdrant upsert, and on search text before embedding. Classifier/model failures stop processing rather than forwarding unredacted text. Existing Qdrant points and embedding-cache entries are not retroactively scrubbed; purge the existing index and rebuild it from sanitized KB articles after deployment.

The incident Business Rule gates on active status, supported categories, and the AI status/processed fields. The KB Business Rule emits events for published articles and deletes. See the [Architecture](ARCHITECTURE.md) for event contracts and caveats.

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
