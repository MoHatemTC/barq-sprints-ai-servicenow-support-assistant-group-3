# BARQ ServiceNow AI Support Assistant

BARQ G3 is a human-reviewed Tier-1 support assistant. ServiceNow sends eligible incident and Knowledge Base (KB) events to a FastAPI webhook receiver. The backend verifies and de-duplicates the events, dispatches work through Celery/Redis, and runs a retrieval-augmented agent using Qdrant and an OpenAI-compatible LLM gateway. Suggested answers and escalations are written back to ServiceNow for human review; the assistant does not close or reassign incidents.

## Start here

- [Run Guide](docs/RUN_GUIDE.md) — prerequisites, environment configuration, ServiceNow setup, startup and verification.
- [Architecture](docs/ARCHITECTURE.md) — implemented event paths, component responsibilities and known limitations.
- [Decision Log](docs/DECISION_LOG.md) — operational choices visible in the merged implementation and the evaluation.
- [DeepEval Evaluation Guide](evaluation/README.md) — dataset, harness, metrics, execution and interpretation.
- [Latest DeepEval Quality Report](evaluation/results/20261001T150304Z/summary.md) — the complete 100-turn report with per-case rows.
- [Per-case CSV](evaluation/results/20261001T150304Z/per_case.csv) · [Per-case JSON](evaluation/results/20261001T150304Z/per_case.json) · [Run configuration](evaluation/results/20261001T150304Z/config.json) · [Aggregate metrics](evaluation/results/20261001T150304Z/aggregate.json).

## Repository map

| Path | Purpose |
|---|---|
| `src/barq_support/api/`, `main.py`, `security.py`, `dedup.py` | FastAPI endpoints, HMAC validation and Redis de-duplication |
| `src/barq_support/tasks.py`, `worker.py`, `celery_app.py` | Celery dispatch, incident processing and KB synchronization |
| `src/barq_support/agent/`, `retrieval/` | Agent prompt/tools/loop and Qdrant retrieval |
| `src/barq_support/ingestion/` | ServiceNow KB chunking, embeddings and Qdrant writes |
| `servicenow/scripts/` | Repository copies of incident and KB Business Rules; ServiceNow-side Script Include is not included |
| `scripts/` | Manual ingestion and live integration utilities |
| `tests/` | Focused webhook and evaluation-harness tests plus other legacy/demo scripts |
| `evaluation/` | DeepEval harness, dataset, adapters and versioned run artifacts |
| `docs/` | Run, architecture and decision documentation |

## Quick commands

Requires Python 3.11+, `uv`, Redis, Qdrant, and credentials for the LLM and Gemini embedding APIs. Follow the [Run Guide](docs/RUN_GUIDE.md) before starting services.

```powershell
uv sync
copy .env.example .env
```

Configure the environment variables in `.env` (LLM, ServiceNow, Qdrant, Celery/Redis, and Langfuse). See [Run Guide](docs/RUN_GUIDE.md) for full configuration details.

### Running the Services (3 Terminals)

Ensure the local Redis service is running on port `6379`. Then open **three separate terminals** in the project root:

#### Terminal 1: FastAPI Webhook Receiver (Uvicorn)
```powershell
uv run uvicorn barq_support.main:app --port 8000
```
*Listens on `http://127.0.0.1:8000`. Exposes `/health` and `/api/v1/events/servicenow`.*

#### Terminal 2: Celery Worker
```powershell
uv run celery -A barq_support.celery_app worker --loglevel=info --pool=solo
```
*Processes queued incident and KB events asynchronously using the `solo` execution pool on Windows.*

#### Terminal 3: ngrok Tunnel
```powershell
ngrok http 8000 --url=https://<your-subdomain>.ngrok-free.app
```

To run the DeepEval evaluation harness:
```powershell
uv run python evaluation/run_eval.py
```

## Current evaluation at a glance

The captured run used DeepEval 4.2.7 on 100 turns (87 answerable, 12 refuse, 1 clarify), with both retrieval and agent stages complete. It measured a 0.38 overall turn pass rate, 0.67 route accuracy, 0.36 over-refusal on answerable cases, and 12/13 negative cases escalated. Read the [report](evaluation/results/20261001T150304Z/summary.md) and its limitations before interpreting these scores. The run used a capture-only ServiceNow stub; it did not update live incidents.

## Security

Never commit `.env` or actual API keys, webhook secrets, passwords, or tokens. Keep real values in local environment configuration; the checked-in `.env.example` contains empty placeholders. Evaluation result files record configuration without writing secret values, and the harness scans generated results for configured secrets. See the [Run Guide security checklist](docs/RUN_GUIDE.md#security).
