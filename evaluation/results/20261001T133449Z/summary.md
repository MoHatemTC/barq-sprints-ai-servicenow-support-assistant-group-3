# DeepEval Quality Report - RAG answering path

- Run `20261001T133449Z` | started (UTC) `2026-10-01T13:34:49+00:00` | stages: retrieval
- Dataset: `barq-servicedesk-rag-eval` v1.0 (sha256 `289ccfa42752`), corpus `BARQ_IT_Service_Desk_Manual_Ed5.docx`; turns evaluated: 100; input mode: `standalone`
- Agent model `not used` | judge `not used` | DeepEval `not used` | judge: OFF (--no-judge)
- Retrieval: `gemini-embedding-2` (3072d), top_k=5, collection `kb_articles`, no score threshold

## Stage 1 - Retrieval only (deterministic, no LLM judge)

Query = `standalone_input`; matching is token-containment against the dataset's `reference_contexts` (heuristic).

| Measure | Value |
|---|---|
| Turns with reference passages | 95 |
| Mean reference recall | 0.73 |
| Mean reference precision | 0.21 |
| Hit rate (>=1 reference passage retrieved) | 0.79 |
| Hit rate (all reference passages retrieved) | 0.65 |
| Turns with no forbidden section retrieved | 0.99 |
| Turns retrieving a must-not-retrieve section | 1 |

## How to read this honestly

- The deployed system is an incident-driven agent whose prompt allows `suggestAnswer` only for a concrete resolution procedure; many dataset questions are definitions, policies or table lookups. Over-refusal on those is a **finding about the product's scope**, not a harness fault; slice by `requires` (e.g. `procedure`) to see the comparable subset.
- No conversation memory or query rewriting exists, so multi-turn `coreference`/`ellipsis` turns are evaluated in `standalone` mode by default. Conversational metrics (ConversationalGEval, RoleAdherence) are out of scope.
- `clarify` has no tool in this architecture; the only non-answer outcome is `requestHR`.
- Retrieval has no score threshold, so refusal depends on the LLM. Judge scores are LLM-based and indicative; read the reasons for every FAIL. Each turn ran once (non-deterministic).
- Section ids are inferred from chunk text because ingested chunks are labelled `page_N_<type>`; `must_not_retrieve` checks are heuristic and ids that cannot be inferred are listed per turn.
- Dataset note `INC-TIME-01` (conflicting 16:24 vs 09:41 approval time, turn S10-T3) is unresolved in the corpus; treat that turn's outcome accordingly.
