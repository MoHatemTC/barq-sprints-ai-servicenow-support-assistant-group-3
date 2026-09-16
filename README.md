# BARQ G3 — Sprint 2 (S2.3) — Agent Tool Definitions

AI ServiceNow Support Assistant · Sprint 2 of 4

Four LangChain tools for the support agent, wired to the team's live
ServiceNow instance. No mocks.

## Tools

| Tool | Type | Input schema | Backed by |
|---|---|---|---|
| `knowledge_base_search` | Repeatable | `query: str` | Knowledge API, falls back to `kb_knowledge` table |
| `internal_work_note` | Repeatable | `note_text: str` | `work_notes` on the incident |
| `final_grounded_answer` | Terminal | `resolution_procedure: str`, `knowledge_article_references: List[str]` (min 1) | Returns answer + logs a work note |
| `human_review_handoff` | Terminal | `handoff_reason: str` | Logs a work note flagging for human review |

The incident is preloaded into context by the caller
(`servicenow/context.py`), so there is no "fetch incident" tool.

**Repeatable** tools state in their purpose text that they can be called
repeatedly without ending the run. **Terminal** tools state that they end
the run.

## How resolve / close / reassign is excluded

Descriptions alone don't enforce anything — a model can ignore prose. The
exclusion is enforced in three layers:

1. **No fifth tool.** `AGENT_TOOLS` holds exactly four, asserted at import.
2. **No input field could carry it.** None of the four schemas has a
   `state`, `close_code`, `assignment_group`, or `assigned_to` field.
3. **One choke point, allow-listed.** Every incident write in the project
   goes through `ServiceNowClient.update_incident`, which accepts only
   fields in `ALLOWED_INCIDENT_FIELDS` (currently just `work_notes`) and
   raises `ForbiddenFieldError` on anything else *before* a request is
   sent. 12 forbidden fields are named explicitly so violations are loud.

Hand-off deliberately does not set `assignment_group` — routing stays a
human decision, so hand-off is a flag, not a reassignment.

## Writes are off by default

S2.3 is a definitions task — nothing here should land on the team's
shared dev instance unless someone opts in deliberately. `SERVICENOW_LIVE_WRITES`
(env var, default `false`) gates the network call inside
`update_incident`:

- The field guard above runs **unconditionally**, regardless of this flag
  — it's a safety check, not a convenience.
- With the flag off, an allowed write (`work_notes`) is validated and
  logged, but no request is sent — `update_incident` returns
  `{"dry_run": True, ...}`.
- Set `SERVICENOW_LIVE_WRITES=true` in `.env` only when you deliberately
  want the agent to post real work notes on real incidents.

This keeps the PR's scope matched to the brief (tool *definitions*) while
the working integration is there, documented, and ready for whichever
future sprint actually calls for live ServiceNow writes.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env     # then fill in credentials
python PoCs/check_connection.py
```

`.env` is gitignored. Do not commit credentials — once they're in git
history they stay there even after deletion.

## Verifying

- `PoCs/check_connection.py` — live check: auth, KB search, incident read,
  and a real attempt to write forbidden fields (which must be blocked).
- `PoCs/verify_tools.py` — offline structural check, no credentials
  needed, safe for CI.

## Structure

```
servicenow/
  client.py       # REST client + field guard
  context.py      # incident preloaded by the caller
tools/
  agent_tools.py  # the four tool definitions
PoCs/
  check_connection.py
  verify_tools.py
.env.example
requirements.txt
```
