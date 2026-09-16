# BARQ G3 — Sprint 2 (S2.3) — Agent Tool Definitions

AI ServiceNow Support Assistant · Sprint 2 of 4

## Scope (per review feedback)

This PR defines the four tools and their contracts only. Tool bodies are
mocks/stubs — no ServiceNow network calls, no ambient state. Real
integration is deferred:

- Knowledge retrieval in this pipeline goes through the team's Qdrant
  vector store, not direct ServiceNow keyword search — wiring that in
  belongs to the sprint where retrieval components merge.
- Any ServiceNow write (work notes, etc.) belongs with the agent-loop
  work in a later sprint.

Keeping the bodies pure and dependency-free means anyone (e.g. S2.4
agent-loop work) can import and call these tools with no credentials and
no setup.

## Tools

| Tool | Type | Input schema |
|---|---|---|
| `knowledge_base_search` | Repeatable | `query: str` |
| `internal_work_note` | Repeatable | `note_text: str` |
| `final_grounded_answer` | Terminal | `resolution_procedure: str`, `knowledge_article_references: List[str]` (min 1) |
| `human_review_handoff` | Terminal | `handoff_reason: str` |

The incident is preloaded into context by the caller, so there is no
"fetch incident" tool.

**Repeatable** tools state in their purpose text that they can be called
repeatedly without ending the run. **Terminal** tools state that they end
the run.

## How resolve / close / reassign is excluded

No tool's input schema has a `state`, `close_code`, `assignment_group`,
or `assigned_to` field — there is no field anywhere in this module that
could carry a resolve/close/reassign instruction, mocked or otherwise.
`human_review_handoff`'s docstring also explicitly notes it only flags
the incident for a human; it does not resolve, close, or reassign it.

## Verifying

```bash
pip install -r requirements.txt
python PoCs/verify_tools.py
```

Runs fully offline — no credentials, no network. Checks tool count,
schemas, repeatable/terminal wording, absence of forbidden fields, and
exercises each tool with a sample payload.

## Structure

```
tools/
  agent_tools.py   # the four tool definitions (mocked bodies)
PoCs/
  verify_tools.py  # offline structural check
README.md
requirements.txt
```
