# DeepEval Quality Report - RAG answering path

- Run `20261001T135441Z` | started (UTC) `2026-10-01T13:54:41+00:00` | stages: agent
- Dataset: `barq-servicedesk-rag-eval` v1.0 (sha256 `289ccfa42752`), corpus `BARQ_IT_Service_Desk_Manual_Ed5.docx`; turns evaluated: 3; input mode: `standalone`
- Agent model `gemini/gemini-3.6-flash` | judge `gemini/gemini-3.6-flash` | DeepEval `4.2.7` | judge: on
- Retrieval: `gemini-embedding-2` (3072d), top_k=5, collection `kb_articles`, no score threshold

## Stage 2 - Agent path (real agent + DeepEval)

| Measure | Value |
|---|---|
| Turn pass rate (route + clean retrieval + all scored metrics) | 0.67 |
| Route accuracy | 1.00 |
| Answerable turns answered (suggestAnswer) | 1.00 |
| Answerable turns wrongly escalated (over-refusal) | 0.00 |
| Refuse/clarify turns escalated (requestHR) | n/a |
| Refuse/clarify turns wrongly answered (hallucination risk) | n/a |
| Agent/runtime errors | 0 |
| Runs with no terminal tool | 0 |
| Judge/metric errors | 0 |

### DeepEval metrics

| Metric | Threshold | Scored | Skipped | Errored | Mean | Pass rate |
|---|---|---|---|---|---|---|
| AnswerRelevancy | 0.7 | 3 | 0 | 0 | 0.72 | 0.67 |
| ContextualPrecision | 0.5 | 3 | 0 | 0 | 0.83 | 1.00 |
| ContextualRecall | 0.5 | 3 | 0 | 0 | 1.00 | 1.00 |
| Faithfulness | 0.8 | 3 | 0 | 0 | 1.00 | 1.00 |

### Route confusion

| Behaviour (expected route) -> actual | Count |
|---|---|
| answer (expect suggestAnswer) -> suggestAnswer | 3 |

### Pass rate by slice (capability / difficulty / behaviour)

| Slice | Passed | Total | Rate |
|---|---|---|---|
| behaviour:answer | 2 | 3 | 0.67 |
| coreference | 1 | 1 | 1.00 |
| difficulty:easy | 2 | 3 | 0.67 |
| ellipsis | 0 | 1 | 0.00 |
| single_hop | 1 | 1 | 1.00 |
| table_lookup | 1 | 2 | 0.50 |

### Per-turn rows

| Turn | Behaviour | Expected | Actual | Recall | Pass | AnswerRelevancy | ContextualPrecision | ContextualRecall | Faithfulness |
|---|---|---|---|---|---|---|---|---|---|
| S01-T1 | answer | suggestAnswer | suggestAnswer | 1.00 | yes | 0.90 | 0.50 | 1.00 | 1.00 |
| S01-T2 | answer | suggestAnswer | suggestAnswer | 1.00 | yes | 0.75 | 1.00 | 1.00 | 1.00 |
| S01-T3 | answer | suggestAnswer | suggestAnswer | 1.00 | NO | 0.50 F | 1.00 | 1.00 | 1.00 |

Full rows (judge reasons, retrieved-chunk previews, agent search queries) are in `per_case.json` / `per_case.csv`.

## How to read this honestly

- The deployed system is an incident-driven agent whose prompt allows `suggestAnswer` only for a concrete resolution procedure; many dataset questions are definitions, policies or table lookups. Over-refusal on those is a **finding about the product's scope**, not a harness fault; slice by `requires` (e.g. `procedure`) to see the comparable subset.
- No conversation memory or query rewriting exists, so multi-turn `coreference`/`ellipsis` turns are evaluated in `standalone` mode by default. Conversational metrics (ConversationalGEval, RoleAdherence) are out of scope.
- `clarify` has no tool in this architecture; the only non-answer outcome is `requestHR`.
- Retrieval has no score threshold, so refusal depends on the LLM. Judge scores are LLM-based and indicative; read the reasons for every FAIL. Each turn ran once (non-deterministic).
- Section ids are inferred from chunk text because ingested chunks are labelled `page_N_<type>`; `must_not_retrieve` checks are heuristic and ids that cannot be inferred are listed per turn.
- Dataset note `INC-TIME-01` (conflicting 16:24 vs 09:41 approval time, turn S10-T3) is unresolved in the corpus; treat that turn's outcome accordingly.
