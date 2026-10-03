# DeepEval Quality Report - RAG answering path

- Run `20261001T140047Z` | started (UTC) `2026-10-01T14:00:47+00:00` | stages: agent
- Dataset: `barq-servicedesk-rag-eval` v1.0 (sha256 `289ccfa42752`), corpus `BARQ_IT_Service_Desk_Manual_Ed5.docx`; turns evaluated: 100; input mode: `standalone`
- Agent model `gemini/gemini-3.6-flash` | judge `not used` | DeepEval `not used` | judge: OFF (--no-judge)
- Retrieval: `gemini-embedding-2` (3072d), top_k=5, collection `kb_articles`, no score threshold

## Stage 2 - Agent path (real agent + DeepEval)

| Measure | Value |
|---|---|
| Turn pass rate (route + clean retrieval + all scored metrics) | 0.70 |
| Route accuracy | 0.72 |
| Answerable turns answered (suggestAnswer) | 0.68 |
| Answerable turns wrongly escalated (over-refusal) | 0.30 |
| Refuse/clarify turns escalated (requestHR) | 1.00 |
| Refuse/clarify turns wrongly answered (hallucination risk) | 0.00 |
| Agent/runtime errors | 2 |
| Runs with no terminal tool | 2 |
| Judge/metric errors | 0 |

### DeepEval metrics

| Metric | Threshold | Scored | Skipped | Errored | Mean | Pass rate |
|---|---|---|---|---|---|---|

### Route confusion

| Behaviour (expected route) -> actual | Count |
|---|---|
| answer (expect suggestAnswer) -> none | 2 |
| answer (expect suggestAnswer) -> requestHR | 26 |
| answer (expect suggestAnswer) -> suggestAnswer | 59 |
| clarify (expect requestHR) -> requestHR | 1 |
| refuse (expect requestHR) -> requestHR | 12 |

### Pass rate by slice (capability / difficulty / behaviour)

| Slice | Passed | Total | Rate |
|---|---|---|---|
| absence_reasoning | 1 | 1 | 1.00 |
| acronym | 0 | 2 | 0.00 |
| adversarial | 2 | 3 | 0.67 |
| aggregation | 1 | 2 | 0.50 |
| ambiguity | 1 | 1 | 1.00 |
| arabic_rtl | 0 | 1 | 0.00 |
| authority_claim | 1 | 1 | 1.00 |
| behaviour:answer | 59 | 87 | 0.68 |
| behaviour:clarify | 1 | 1 | 1.00 |
| behaviour:refuse | 10 | 12 | 0.83 |
| bilingual | 1 | 1 | 1.00 |
| callout_text | 6 | 7 | 0.86 |
| checkbox | 0 | 1 | 0.00 |
| comparison | 2 | 4 | 0.50 |
| coreference | 6 | 8 | 0.75 |
| counterfactual | 1 | 1 | 1.00 |
| cross_lingual | 1 | 2 | 0.50 |
| cross_reference | 3 | 3 | 1.00 |
| dark_theme | 0 | 1 | 0.00 |
| deduplication | 1 | 1 | 1.00 |
| definition | 1 | 1 | 1.00 |
| difficulty:easy | 19 | 25 | 0.76 |
| difficulty:hard | 17 | 28 | 0.61 |
| difficulty:medium | 34 | 47 | 0.72 |
| ellipsis | 12 | 14 | 0.86 |
| enumeration | 11 | 15 | 0.73 |
| exception | 0 | 1 | 0.00 |
| false_premise | 3 | 5 | 0.60 |
| floating_object_layout | 1 | 1 | 1.00 |
| footnote | 1 | 1 | 1.00 |
| form_parsing | 0 | 1 | 0.00 |
| front_matter | 1 | 1 | 1.00 |
| identifier_fidelity | 0 | 1 | 0.00 |
| image_ocr | 1 | 5 | 0.20 |
| key_value_extraction | 0 | 1 | 0.00 |
| marginal_notes_layout | 0 | 2 | 0.00 |
| multi_hop | 10 | 13 | 0.77 |
| near_miss | 2 | 2 | 1.00 |
| nested_table | 1 | 4 | 0.25 |
| noisy_input | 1 | 1 | 1.00 |
| numeric | 3 | 4 | 0.75 |
| ordering | 1 | 1 | 1.00 |
| page_crossing_table | 1 | 1 | 1.00 |
| partial_ambiguity | 1 | 1 | 1.00 |
| pii | 1 | 1 | 1.00 |
| policy | 9 | 10 | 0.90 |
| procedure | 5 | 5 | 1.00 |
| prompt_injection | 1 | 1 | 1.00 |
| pull_quote | 1 | 1 | 1.00 |
| reasoning | 2 | 4 | 0.50 |
| recovery_after_refusal | 0 | 1 | 0.00 |
| rotated_image | 1 | 1 | 1.00 |
| scan_many_chunks | 0 | 1 | 0.00 |
| scope_boundary | 1 | 1 | 1.00 |
| single_hop | 2 | 6 | 0.33 |
| structure | 1 | 1 | 1.00 |
| table_fullwidth_note | 1 | 1 | 1.00 |
| table_lookup | 24 | 26 | 0.92 |
| table_merged_header | 2 | 2 | 1.00 |
| table_rowspan | 2 | 6 | 0.33 |
| temporal | 2 | 2 | 1.00 |
| topic_shift | 2 | 3 | 0.67 |
| two_column_layout | 1 | 1 | 1.00 |
| typo_robustness | 1 | 1 | 1.00 |
| unanswerable | 5 | 7 | 0.71 |
| version_conflict | 1 | 1 | 1.00 |
| version_filter | 1 | 1 | 1.00 |

### Per-turn rows

| Turn | Behaviour | Expected | Actual | Recall | Pass |  |
|---|---|---|---|---|---|
| S01-T1 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S01-T2 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S01-T3 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S01-T4 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S01-T5 | refuse | requestHR | requestHR | n/a | NO |  |
| S02-T1 | answer | suggestAnswer | suggestAnswer | 0.50 | yes |  |
| S02-T2 | answer | suggestAnswer | suggestAnswer | 0.67 | yes |  |
| S02-T3 | answer | suggestAnswer | requestHR | 1.00 | NO |  |
| S02-T4 | answer | suggestAnswer | requestHR | 0.50 | NO |  |
| S02-T5 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S03-T1 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S03-T2 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S03-T3 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S03-T4 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S03-T5 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S04-T1 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S04-T2 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S04-T3 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S04-T4 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S04-T5 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S05-T1 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S05-T2 | answer | suggestAnswer | suggestAnswer | 0.00 | yes |  |
| S05-T3 | answer | suggestAnswer | suggestAnswer | 0.00 | yes |  |
| S05-T4 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S05-T5 | answer | suggestAnswer | suggestAnswer | 0.50 | yes |  |
| S06-T1 | answer | suggestAnswer | requestHR | 0.00 | NO |  |
| S06-T2 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S06-T3 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S06-T4 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S06-T5 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S07-T1 | answer | suggestAnswer | none | 0.00 | NO |  |
| S07-T2 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S07-T3 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S07-T4 | answer | suggestAnswer | requestHR | 1.00 | NO |  |
| S07-T5 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S08-T1 | answer | suggestAnswer | requestHR | 0.00 | NO |  |
| S08-T2 | answer | suggestAnswer | suggestAnswer | 0.00 | yes |  |
| S08-T3 | answer | suggestAnswer | requestHR | 0.50 | NO |  |
| S08-T4 | answer | suggestAnswer | requestHR | 1.00 | NO |  |
| S08-T5 | answer | suggestAnswer | requestHR | 0.00 | NO |  |
| S09-T1 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S09-T2 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S09-T3 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S09-T4 | answer | suggestAnswer | suggestAnswer | 0.00 | yes |  |
| S09-T5 | answer | suggestAnswer | requestHR | 1.00 | NO |  |
| S10-T1 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S10-T2 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S10-T3 | answer | suggestAnswer | requestHR | 1.00 | NO |  |
| S10-T4 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S10-T5 | answer | suggestAnswer | requestHR | 1.00 | NO |  |
| S11-T1 | answer | suggestAnswer | suggestAnswer | 0.00 | yes |  |
| S11-T2 | answer | suggestAnswer | suggestAnswer | 0.00 | yes |  |
| S11-T3 | answer | suggestAnswer | requestHR | 0.00 | NO |  |
| S11-T4 | answer | suggestAnswer | requestHR | 1.00 | NO |  |
| S11-T5 | answer | suggestAnswer | none | 0.00 | NO |  |
| S12-T1 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S12-T2 | answer | suggestAnswer | requestHR | 1.00 | NO |  |
| S12-T3 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S12-T4 | answer | suggestAnswer | requestHR | 1.00 | NO |  |
| S12-T5 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S13-T1 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S13-T2 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S13-T3 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S13-T4 | answer | suggestAnswer | requestHR | 1.00 | NO |  |
| S13-T5 | answer | suggestAnswer | requestHR | 1.00 | NO |  |
| S14-T1 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S14-T2 | answer | suggestAnswer | requestHR | 1.00 | NO |  |
| S14-T3 | answer | suggestAnswer | requestHR | 0.00 | NO |  |
| S14-T4 | answer | suggestAnswer | requestHR | 0.00 | NO |  |
| S14-T5 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S15-T1 | refuse | requestHR | requestHR | 0.00 | yes |  |
| S15-T2 | refuse | requestHR | requestHR | 0.50 | yes |  |
| S15-T3 | refuse | requestHR | requestHR | 0.00 | yes |  |
| S15-T4 | answer | suggestAnswer | requestHR | 1.00 | NO |  |
| S15-T5 | refuse | requestHR | requestHR | 0.50 | yes |  |
| S16-T1 | clarify | requestHR | requestHR | n/a | yes |  |
| S16-T2 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S16-T3 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S16-T4 | answer | suggestAnswer | suggestAnswer | 0.00 | yes |  |
| S16-T5 | answer | suggestAnswer | requestHR | 0.67 | NO |  |
| S17-T1 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S17-T2 | answer | suggestAnswer | requestHR | 1.00 | NO |  |
| S17-T3 | refuse | requestHR | requestHR | n/a | NO |  |
| S17-T4 | refuse | requestHR | requestHR | 0.50 | yes |  |
| S17-T5 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S18-T1 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S18-T2 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S18-T3 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S18-T4 | answer | suggestAnswer | requestHR | 1.00 | NO |  |
| S18-T5 | answer | suggestAnswer | requestHR | 1.00 | NO |  |
| S19-T1 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S19-T2 | answer | suggestAnswer | suggestAnswer | 1.00 | yes |  |
| S19-T3 | answer | suggestAnswer | suggestAnswer | 0.50 | yes |  |
| S19-T4 | answer | suggestAnswer | requestHR | 1.00 | NO |  |
| S19-T5 | answer | suggestAnswer | suggestAnswer | 0.50 | yes |  |
| S20-T1 | refuse | requestHR | requestHR | n/a | yes |  |
| S20-T2 | refuse | requestHR | requestHR | 1.00 | yes |  |
| S20-T3 | refuse | requestHR | requestHR | n/a | yes |  |
| S20-T4 | refuse | requestHR | requestHR | 0.00 | yes |  |
| S20-T5 | refuse | requestHR | requestHR | 0.50 | yes |  |

Full rows (judge reasons, retrieved-chunk previews, agent search queries) are in `per_case.json` / `per_case.csv`.

## How to read this honestly

- The deployed system is an incident-driven agent whose prompt allows `suggestAnswer` only for a concrete resolution procedure; many dataset questions are definitions, policies or table lookups. Over-refusal on those is a **finding about the product's scope**, not a harness fault; slice by `requires` (e.g. `procedure`) to see the comparable subset.
- No conversation memory or query rewriting exists, so multi-turn `coreference`/`ellipsis` turns are evaluated in `standalone` mode by default. Conversational metrics (ConversationalGEval, RoleAdherence) are out of scope.
- `clarify` has no tool in this architecture; the only non-answer outcome is `requestHR`.
- Retrieval has no score threshold, so refusal depends on the LLM. Judge scores are LLM-based and indicative; read the reasons for every FAIL. Each turn ran once (non-deterministic).
- Section ids are inferred from chunk text because ingested chunks are labelled `page_N_<type>`; `must_not_retrieve` checks are heuristic and ids that cannot be inferred are listed per turn.
- Dataset note `INC-TIME-01` (conflicting 16:24 vs 09:41 approval time, turn S10-T3) is unresolved in the corpus; treat that turn's outcome accordingly.
