# barq-sprints-ai-servicenow-support-assistant-group-3

An event-driven, RAG-powered ServiceNow assistant that retrieves trusted knowledge, drafts cited resolutions, and routes responses for human approval.

## Layout

```
src/barq_support/
  config.py                 # shared settings (Qdrant, chunking)      - S2.1 (Malak)
  ingestion/                # chunk -> embed -> upsert pipeline       - S2.1 (Malak)
    chunker.py  embedder.py  embedding_cache.py  ingest.py  qdrant_store.py
    sample_articles.json
  retrieval/                # vector search + threshold gate          - S2.2 (Aliaa)
    retriever.py
  agent/                    # tool-calling agent, strict grounding    - S2.3/S2.4
    tools.py                #   S2.3 tool schemas (AGENT_TOOLS)
    scoped_tools.py         #   request-scoped read-only tool bodies  - S2.4 (Dana)
    agent.py  prompts.py  formatting.py  validation.py  models.py
    settings.py  mock_data.py
  benchmark/                # threshold evaluation                    - S2.5 (Ashraf)
    runner.py  dataset.json  THRESHOLD_ANALYSIS.md
tests/                      # everything runnable via `uv run pytest`
scripts/                    # verify_tools.py, check_connection.py, run_samples.py
docs/                       # sample_runs.md (generated live runs)
```

## Quick start

```
uv sync
cp .env.example .env      # fill in QDRANT_*, GEMINI_API_KEY, LLM_*
uv run pytest             # offline tests; live-Qdrant tests skip automatically
```

## Sprints

| Sprint | Scope | Owner |
|---|---|---|
| S2.1 | Chunking, embedding, Qdrant storage | Malak |
| S2.2 | Semantic retrieval + threshold gate | Aliaa |
| S2.3 | Agent tool schemas (no resolve/close/reassign) | team |
| S2.4 | Agent reasoning + grounded generation | Dana |
| S2.5 | Retrieval benchmark & threshold evaluation | Ashraf |
