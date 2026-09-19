## S2.4 — AI Agent Reasoning & Grounded Generation

### What this PR adds
- LangChain tool-calling `AgentExecutor` wired to a live, OpenAI-compatible LLM endpoint;
  all credentials/endpoint settings come from environment variables (`.env.example` provided).
- System prompt enforcing strict grounding, numbered + cited output, recommend-only authority
  (cannot resolve/close/reassign), and an exact clean-decline message.
- Prompt layout: `<knowledge_base>` first, incident afterwards in a separate
  `<incident_data trust="untrusted">` block (escaped so it cannot break out).
- Fail-closed output validator (every step must cite a retrieved article) + deterministic
  decline when no chunks are retrieved.
- `generate_recommendation(incident, chunks)` entry point, mock incidents/chunks, four mocked
  read-only tools (no resolve/close/reassign tool exists).
- Tests (no network needed) and `docs/sample_runs.md` generated from live runs.

### How to review
1. `support_agent/prompts.py` — the prompt (sections 1–5 map to the brief).
2. `support_agent/formatting.py` + `validation.py` — isolation and fail-closed checks.
3. `docs/sample_runs.md` — grounded run, three clean declines, and an injection attempt.

### How to run
`pip install -r requirements.txt && cp .env.example .env` (fill in) `&& python scripts/run_samples.py && python -m pytest`

### Notes
- Tools are mocked (permitted by the brief); interfaces are ready to be wired.
- Known limitation: validator checks citation presence/validity, not semantic faithfulness.
