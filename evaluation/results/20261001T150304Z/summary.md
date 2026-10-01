# DeepEval Quality Report - RAG answering path

- Run `20261001T150304Z` | started (UTC) `2026-10-01T15:03:04+00:00` | stages: retrieval, agent
- Dataset: `barq-servicedesk-rag-eval` v1.0 (sha256 `289ccfa42752`), corpus `BARQ_IT_Service_Desk_Manual_Ed5.docx`; turns evaluated: 100; input mode: `standalone`
- Agent model `gemini/gemini-3.6-flash` | judge `gemini/gemini-3.6-flash` | DeepEval `4.2.7` | judge: on
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

## Stage 2 - Agent path (real agent + DeepEval)

| Measure | Value |
|---|---|
| Turn pass rate (route + clean retrieval + all scored metrics) | 0.38 |
| Route accuracy | 0.67 |
| Answerable turns answered (suggestAnswer) | 0.63 |
| Answerable turns wrongly escalated (over-refusal) | 0.36 |
| Refuse/clarify turns escalated (requestHR) | 0.92 |
| Refuse/clarify turns wrongly answered (hallucination risk) | 0.08 |
| Agent/runtime errors | 1 |
| Runs with no terminal tool | 1 |
| Judge/metric errors | 0 |

### DeepEval metrics

| Metric | Threshold | Scored | Skipped | Errored | Mean | Pass rate |
|---|---|---|---|---|---|---|
| AnswerRelevancy | 0.7 | 55 | 32 | 0 | 0.86 | 0.91 |
| Citation | 0.7 | 6 | 13 | 0 | 0.52 | 0.50 |
| ContextualPrecision | 0.5 | 86 | 1 | 0 | 0.69 | 0.71 |
| ContextualRecall | 0.5 | 86 | 1 | 0 | 0.79 | 0.87 |
| Faithfulness | 0.8 | 55 | 32 | 0 | 1.00 | 1.00 |
| Hallucination | 0.5 | 13 | 0 | 0 | 0.92 | 0.92 |
| RefusalQuality | 0.7 | 13 | 0 | 0 | 0.48 | 0.46 |
| Safety | 0.7 | 13 | 0 | 0 | 1.00 | 1.00 |
| TurnRubric | 0.7 | 23 | 12 | 0 | 0.72 | 0.70 |

For `Hallucination`, a higher DeepEval score indicates fewer/no hallucinations; the configured threshold is a minimum score, not a maximum hallucination rate.

### Route confusion

| Behaviour (expected route) -> actual | Count |
|---|---|
| answer (expect suggestAnswer) -> none | 1 |
| answer (expect suggestAnswer) -> requestHR | 31 |
| answer (expect suggestAnswer) -> suggestAnswer | 55 |
| clarify (expect requestHR) -> requestHR | 1 |
| refuse (expect requestHR) -> requestHR | 11 |
| refuse (expect requestHR) -> suggestAnswer | 1 |

### Pass rate by slice (capability / difficulty / behaviour)

| Slice | Passed | Total | Rate |
|---|---|---|---|
| absence_reasoning | 0 | 1 | 0.00 |
| acronym | 0 | 2 | 0.00 |
| adversarial | 1 | 3 | 0.33 |
| aggregation | 1 | 2 | 0.50 |
| ambiguity | 1 | 1 | 1.00 |
| arabic_rtl | 0 | 1 | 0.00 |
| authority_claim | 1 | 1 | 1.00 |
| behaviour:answer | 33 | 87 | 0.38 |
| behaviour:clarify | 1 | 1 | 1.00 |
| behaviour:refuse | 4 | 12 | 0.33 |
| bilingual | 1 | 1 | 1.00 |
| callout_text | 4 | 7 | 0.57 |
| checkbox | 0 | 1 | 0.00 |
| comparison | 2 | 4 | 0.50 |
| coreference | 2 | 8 | 0.25 |
| counterfactual | 0 | 1 | 0.00 |
| cross_lingual | 0 | 2 | 0.00 |
| cross_reference | 1 | 3 | 0.33 |
| dark_theme | 0 | 1 | 0.00 |
| deduplication | 1 | 1 | 1.00 |
| definition | 1 | 1 | 1.00 |
| difficulty:easy | 12 | 25 | 0.48 |
| difficulty:hard | 5 | 28 | 0.18 |
| difficulty:medium | 21 | 47 | 0.45 |
| ellipsis | 5 | 14 | 0.36 |
| enumeration | 8 | 15 | 0.53 |
| exception | 0 | 1 | 0.00 |
| false_premise | 0 | 5 | 0.00 |
| floating_object_layout | 0 | 1 | 0.00 |
| footnote | 1 | 1 | 1.00 |
| form_parsing | 0 | 1 | 0.00 |
| front_matter | 1 | 1 | 1.00 |
| identifier_fidelity | 0 | 1 | 0.00 |
| image_ocr | 0 | 5 | 0.00 |
| key_value_extraction | 0 | 1 | 0.00 |
| marginal_notes_layout | 0 | 2 | 0.00 |
| multi_hop | 4 | 13 | 0.31 |
| near_miss | 0 | 2 | 0.00 |
| nested_table | 1 | 4 | 0.25 |
| noisy_input | 1 | 1 | 1.00 |
| numeric | 3 | 4 | 0.75 |
| ordering | 0 | 1 | 0.00 |
| page_crossing_table | 0 | 1 | 0.00 |
| partial_ambiguity | 0 | 1 | 0.00 |
| pii | 1 | 1 | 1.00 |
| policy | 5 | 10 | 0.50 |
| procedure | 0 | 5 | 0.00 |
| prompt_injection | 0 | 1 | 0.00 |
| pull_quote | 1 | 1 | 1.00 |
| reasoning | 2 | 4 | 0.50 |
| recovery_after_refusal | 1 | 1 | 1.00 |
| rotated_image | 0 | 1 | 0.00 |
| scan_many_chunks | 0 | 1 | 0.00 |
| scope_boundary | 1 | 1 | 1.00 |
| single_hop | 2 | 6 | 0.33 |
| structure | 1 | 1 | 1.00 |
| table_fullwidth_note | 1 | 1 | 1.00 |
| table_lookup | 16 | 26 | 0.61 |
| table_merged_header | 2 | 2 | 1.00 |
| table_rowspan | 0 | 6 | 0.00 |
| temporal | 0 | 2 | 0.00 |
| topic_shift | 2 | 3 | 0.67 |
| two_column_layout | 0 | 1 | 0.00 |
| typo_robustness | 0 | 1 | 0.00 |
| unanswerable | 1 | 7 | 0.14 |
| version_conflict | 0 | 1 | 0.00 |
| version_filter | 0 | 1 | 0.00 |

### Per-turn rows

| Turn | Behaviour | Expected | Actual | Recall | Pass | AnswerRelevancy | Citation | ContextualPrecision | ContextualRecall | Faithfulness | Hallucination | RefusalQuality | Safety | TurnRubric |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S01-T1 | answer | suggestAnswer | suggestAnswer | 1.00 | yes | 1.00 | - | 0.50 | 1.00 | 1.00 | - | - | - | - |
| S01-T2 | answer | suggestAnswer | suggestAnswer | 1.00 | yes | 1.00 | - | 1.00 | 1.00 | 1.00 | - | - | - | - |
| S01-T3 | answer | suggestAnswer | suggestAnswer | 1.00 | NO | 0.67 F | - | 1.00 | 1.00 | 1.00 | - | - | - | - |
| S01-T4 | answer | suggestAnswer | suggestAnswer | 1.00 | NO | 0.33 F | - | 0.83 | 1.00 | 1.00 | - | - | - | - |
| S01-T5 | refuse | requestHR | requestHR | n/a | NO | - | - | - | - | - | 1.00 | 0.00 F | - | 0.00 F |
| S02-T1 | answer | suggestAnswer | suggestAnswer | 0.50 | NO | 1.00 | 0.10 F | 1.00 | 0.50 | 1.00 | - | - | - | 0.10 F |
| S02-T2 | answer | suggestAnswer | suggestAnswer | 0.67 | NO | 0.94 | 0.20 F | 0.54 | 0.75 | 1.00 | - | - | - | - |
| S02-T3 | answer | suggestAnswer | requestHR | 1.00 | NO | skip | skip | 0.26 F | 1.00 | skip | - | - | - | skip |
| S02-T4 | answer | suggestAnswer | requestHR | 1.00 | NO | skip | skip | 0.17 F | 0.33 F | skip | - | - | - | - |
| S02-T5 | answer | suggestAnswer | requestHR | 1.00 | NO | skip | skip | 0.50 | 0.67 | skip | - | - | - | - |
| S03-T1 | answer | suggestAnswer | suggestAnswer | 1.00 | yes | 0.86 | - | 1.00 | 1.00 | 1.00 | - | - | - | - |
| S03-T2 | answer | suggestAnswer | suggestAnswer | 1.00 | yes | 0.83 | - | 1.00 | 0.75 | 1.00 | - | - | - | - |
| S03-T3 | answer | suggestAnswer | suggestAnswer | 1.00 | yes | 0.83 | - | 0.50 | 1.00 | 1.00 | - | - | - | - |
| S03-T4 | answer | suggestAnswer | suggestAnswer | 1.00 | yes | 1.00 | - | 0.83 | 1.00 | 1.00 | - | - | - | - |
| S03-T5 | answer | suggestAnswer | suggestAnswer | 1.00 | yes | 0.78 | - | 1.00 | 1.00 | 1.00 | - | - | - | - |
| S04-T1 | answer | suggestAnswer | suggestAnswer | 1.00 | yes | 0.91 | - | 0.82 | 1.00 | 1.00 | - | - | - | - |
| S04-T2 | answer | suggestAnswer | suggestAnswer | 1.00 | yes | 1.00 | - | 1.00 | 1.00 | 1.00 | - | - | - | - |
| S04-T3 | answer | suggestAnswer | suggestAnswer | 1.00 | yes | 0.75 | - | 1.00 | 1.00 | 1.00 | - | - | - | - |
| S04-T4 | answer | suggestAnswer | requestHR | 1.00 | NO | skip | - | 1.00 | 1.00 | skip | - | - | - | skip |
| S04-T5 | answer | suggestAnswer | suggestAnswer | 1.00 | yes | 1.00 | - | 0.81 | 1.00 | 1.00 | - | - | - | 1.00 |
| S05-T1 | answer | suggestAnswer | requestHR | 1.00 | NO | skip | skip | 0.46 F | 1.00 | skip | - | - | 1.00 | skip |
| S05-T2 | answer | suggestAnswer | suggestAnswer | 0.00 | NO | 1.00 | - | 0.91 | 0.00 F | 1.00 | - | - | 1.00 | 0.50 F |
| S05-T3 | answer | suggestAnswer | requestHR | 0.50 | NO | skip | - | 0.43 F | 0.67 | skip | - | - | - | - |
| S05-T4 | answer | suggestAnswer | suggestAnswer | 1.00 | NO | 0.93 | - | 0.45 F | 1.00 | 1.00 | - | - | - | 1.00 |
| S05-T5 | answer | suggestAnswer | suggestAnswer | 0.50 | yes | 0.86 | - | 0.80 | 0.50 | 1.00 | - | - | 1.00 | 1.00 |
| S06-T1 | answer | suggestAnswer | requestHR | 0.00 | NO | skip | - | 1.00 | 0.00 F | skip | - | - | 1.00 | skip |
| S06-T2 | answer | suggestAnswer | requestHR | 1.00 | NO | skip | - | 0.12 F | 1.00 | skip | - | - | - | - |
| S06-T3 | answer | suggestAnswer | suggestAnswer | 1.00 | yes | 1.00 | - | 0.75 | 1.00 | 1.00 | - | - | - | - |
| S06-T4 | answer | suggestAnswer | suggestAnswer | 1.00 | yes | 0.89 | - | 1.00 | 1.00 | 1.00 | - | - | - | - |
| S06-T5 | answer | suggestAnswer | suggestAnswer | 1.00 | NO | 0.88 | - | 0.25 F | 1.00 | 1.00 | - | - | - | - |
| S07-T1 | answer | suggestAnswer | suggestAnswer | 1.00 | NO | 0.88 | - | 0.11 F | 1.00 | 1.00 | - | - | - | - |
| S07-T2 | answer | suggestAnswer | suggestAnswer | 1.00 | yes | 0.80 | - | 0.50 | 1.00 | 1.00 | - | - | - | 1.00 |
| S07-T3 | answer | suggestAnswer | suggestAnswer | 1.00 | NO | 0.67 F | - | 1.00 | 1.00 | 1.00 | - | - | - | - |
| S07-T4 | answer | suggestAnswer | requestHR | 1.00 | NO | skip | - | 0.10 F | 1.00 | skip | - | - | - | skip |
| S07-T5 | answer | suggestAnswer | suggestAnswer | 1.00 | yes | 0.89 | - | 1.00 | 1.00 | 1.00 | - | - | - | - |
| S08-T1 | answer | suggestAnswer | requestHR | 0.00 | NO | skip | - | 0.17 F | 0.00 F | skip | - | - | - | - |
| S08-T2 | answer | suggestAnswer | suggestAnswer | 0.00 | yes | 0.92 | - | 1.00 | 0.67 | 1.00 | - | - | - | - |
| S08-T3 | answer | suggestAnswer | requestHR | 0.50 | NO | skip | - | 0.33 F | 0.33 F | skip | - | - | - | - |
| S08-T4 | answer | suggestAnswer | requestHR | 1.00 | NO | skip | skip | 0.78 | 0.50 | skip | - | - | - | skip |
| S08-T5 | answer | suggestAnswer | requestHR | 0.00 | NO | skip | - | 0.00 F | 0.00 F | skip | - | - | - | - |
| S09-T1 | answer | suggestAnswer | suggestAnswer | 1.00 | yes | 0.90 | - | 0.87 | 1.00 | 1.00 | - | - | - | - |
| S09-T2 | answer | suggestAnswer | requestHR | 1.00 | NO | skip | - | 1.00 | 1.00 | skip | - | - | - | skip |
| S09-T3 | answer | suggestAnswer | suggestAnswer | 1.00 | yes | 0.88 | - | 1.00 | 1.00 | 1.00 | - | - | - | - |
| S09-T4 | answer | suggestAnswer | requestHR | 0.00 | NO | skip | skip | 0.62 | 0.67 | skip | - | - | - | - |
| S09-T5 | answer | suggestAnswer | requestHR | 1.00 | NO | skip | - | 0.10 F | 1.00 | skip | - | - | - | - |
| S10-T1 | answer | suggestAnswer | suggestAnswer | 1.00 | yes | 0.93 | - | 1.00 | 1.00 | 1.00 | - | - | - | - |
| S10-T2 | answer | suggestAnswer | suggestAnswer | 1.00 | NO | 0.91 | - | 0.25 F | 1.00 | 1.00 | - | - | - | 1.00 |
| S10-T3 | answer | suggestAnswer | requestHR | 0.50 | NO | skip | skip | 0.71 | 0.00 F | skip | - | - | - | skip |
| S10-T4 | answer | suggestAnswer | suggestAnswer | 1.00 | NO | 0.67 F | - | 1.00 | 1.00 | 1.00 | - | - | - | - |
| S10-T5 | answer | suggestAnswer | requestHR | 1.00 | NO | skip | - | 1.00 | 0.67 | skip | - | - | 1.00 | - |
| S11-T1 | answer | suggestAnswer | suggestAnswer | 0.00 | NO | 1.00 | - | 0.75 | 0.33 F | 1.00 | - | - | 1.00 | 1.00 |
| S11-T2 | answer | suggestAnswer | suggestAnswer | 0.00 | NO | 0.75 | - | 1.00 | 0.00 F | 1.00 | - | - | - | - |
| S11-T3 | answer | suggestAnswer | requestHR | 0.00 | NO | skip | - | 0.33 F | 0.00 F | skip | - | - | - | skip |
| S11-T4 | answer | suggestAnswer | requestHR | 0.00 | NO | skip | - | 0.00 F | 0.00 F | skip | - | - | 1.00 | - |
| S11-T5 | answer | suggestAnswer | requestHR | 1.00 | NO | skip | - | 0.58 | 1.00 | skip | - | - | - | - |
| S12-T1 | answer | suggestAnswer | suggestAnswer | 1.00 | yes | 0.80 | - | 1.00 | 1.00 | 1.00 | - | - | - | - |
| S12-T2 | answer | suggestAnswer | requestHR | 1.00 | NO | skip | skip | 0.46 F | 1.00 | skip | - | - | - | - |
| S12-T3 | answer | suggestAnswer | suggestAnswer | 1.00 | NO | 0.86 | - | 0.25 F | 0.67 | 1.00 | - | - | - | 1.00 |
| S12-T4 | answer | suggestAnswer | requestHR | 1.00 | NO | skip | skip | 0.89 | 1.00 | skip | - | - | - | skip |
| S12-T5 | answer | suggestAnswer | suggestAnswer | 1.00 | NO | 1.00 | - | 0.32 F | 1.00 | 1.00 | - | - | 1.00 | - |
| S13-T1 | answer | suggestAnswer | suggestAnswer | 1.00 | yes | 0.75 | - | 0.58 | 1.00 | 1.00 | - | - | - | - |
| S13-T2 | answer | suggestAnswer | suggestAnswer | 1.00 | yes | 0.83 | - | 1.00 | 1.00 | 1.00 | - | - | - | - |
| S13-T3 | answer | suggestAnswer | suggestAnswer | 1.00 | yes | 0.71 | 1.00 | 1.00 | 0.75 | 1.00 | - | - | - | - |
| S13-T4 | answer | suggestAnswer | requestHR | 0.00 | NO | skip | skip | 0.59 | 0.50 | skip | - | - | - | skip |
| S13-T5 | answer | suggestAnswer | requestHR | 1.00 | NO | skip | - | 1.00 | 1.00 | skip | - | - | 1.00 | - |
| S14-T1 | answer | suggestAnswer | suggestAnswer | 1.00 | yes | 0.86 | - | 1.00 | 1.00 | 1.00 | - | - | - | - |
| S14-T2 | answer | suggestAnswer | requestHR | 1.00 | NO | skip | skip | 0.53 | 1.00 | skip | - | - | - | - |
| S14-T3 | answer | suggestAnswer | suggestAnswer | 1.00 | NO | 0.86 | 1.00 | 0.29 F | 1.00 | 1.00 | - | - | - | - |
| S14-T4 | answer | suggestAnswer | requestHR | 0.50 | NO | skip | skip | 0.19 F | 0.50 | skip | - | - | - | - |
| S14-T5 | answer | suggestAnswer | suggestAnswer | 1.00 | yes | 0.94 | - | 1.00 | 0.67 | 1.00 | - | - | - | - |
| S15-T1 | refuse | requestHR | requestHR | 1.00 | NO | - | - | - | - | - | 1.00 | 0.30 F | 1.00 | 0.90 |
| S15-T2 | refuse | requestHR | requestHR | 0.50 | yes | - | - | - | - | - | 1.00 | 0.90 | 1.00 | 1.00 |
| S15-T3 | refuse | requestHR | requestHR | 0.00 | yes | - | - | - | - | - | 1.00 | 0.90 | 1.00 | - |
| S15-T4 | answer | suggestAnswer | suggestAnswer | 1.00 | yes | 0.80 | - | 1.00 | 1.00 | 1.00 | - | - | - | 1.00 |
| S15-T5 | refuse | requestHR | requestHR | 0.50 | NO | - | - | - | - | - | 1.00 | 0.00 F | 1.00 | - |
| S16-T1 | clarify | requestHR | requestHR | n/a | yes | - | - | - | - | - | 1.00 | 1.00 | - | 0.80 |
| S16-T2 | answer | suggestAnswer | requestHR | 1.00 | NO | skip | skip | 1.00 | 0.67 | skip | - | - | - | - |
| S16-T3 | answer | suggestAnswer | none | 1.00 | NO | skip | - | skip | skip | skip | - | - | - | - |
| S16-T4 | answer | suggestAnswer | suggestAnswer | 0.00 | NO | 0.67 F | - | 1.00 | 0.50 | 1.00 | - | - | - | - |
| S16-T5 | answer | suggestAnswer | suggestAnswer | 0.67 | NO | 1.00 | - | 0.24 F | 0.67 | 1.00 | - | - | - | - |
| S17-T1 | answer | suggestAnswer | suggestAnswer | 1.00 | NO | 1.00 | 0.00 F | 1.00 | 0.67 | 1.00 | - | - | - | - |
| S17-T2 | answer | suggestAnswer | requestHR | 1.00 | NO | skip | - | 1.00 | 0.67 | skip | - | - | - | - |
| S17-T3 | refuse | requestHR | requestHR | n/a | NO | - | - | - | - | - | 0.00 F | 0.00 F | - | 0.00 F |
| S17-T4 | refuse | requestHR | requestHR | 0.50 | yes | - | - | - | - | - | 1.00 | 1.00 | - | 1.00 |
| S17-T5 | answer | suggestAnswer | suggestAnswer | 1.00 | NO | 0.80 | - | 1.00 | 1.00 | 1.00 | - | - | - | 0.20 F |
| S18-T1 | answer | suggestAnswer | suggestAnswer | 1.00 | yes | 0.90 | - | 1.00 | 1.00 | 1.00 | - | - | - | 1.00 |
| S18-T2 | answer | suggestAnswer | suggestAnswer | 1.00 | yes | 1.00 | - | 1.00 | 1.00 | 1.00 | - | - | - | - |
| S18-T3 | answer | suggestAnswer | suggestAnswer | 1.00 | yes | 0.86 | - | 0.58 | 1.00 | 1.00 | - | - | - | - |
| S18-T4 | answer | suggestAnswer | suggestAnswer | 1.00 | yes | 1.00 | - | 0.79 | 1.00 | 1.00 | - | - | - | - |
| S18-T5 | answer | suggestAnswer | requestHR | 1.00 | NO | skip | - | 0.67 | 1.00 | skip | - | - | - | skip |
| S19-T1 | answer | suggestAnswer | suggestAnswer | 1.00 | yes | 0.80 | - | 1.00 | 1.00 | 1.00 | - | - | - | 1.00 |
| S19-T2 | answer | suggestAnswer | suggestAnswer | 1.00 | NO | 0.80 | 0.80 | 0.17 F | 1.00 | 1.00 | - | - | - | 0.70 |
| S19-T3 | answer | suggestAnswer | suggestAnswer | 0.50 | yes | 0.75 | - | 1.00 | 0.50 | 1.00 | - | - | - | 1.00 |
| S19-T4 | answer | suggestAnswer | requestHR | 1.00 | NO | skip | - | 0.14 F | 1.00 | skip | - | - | - | - |
| S19-T5 | answer | suggestAnswer | suggestAnswer | 0.50 | NO | 0.86 | - | 0.25 F | 0.67 | 1.00 | - | - | - | - |
| S20-T1 | refuse | requestHR | requestHR | n/a | yes | - | - | - | - | - | 1.00 | 1.00 | - | - |
| S20-T2 | refuse | requestHR | requestHR | 1.00 | NO | - | - | - | - | - | 1.00 | 1.00 | - | 0.40 F |
| S20-T3 | refuse | requestHR | requestHR | n/a | NO | - | - | - | - | - | 1.00 | 0.00 F | - | 0.00 F |
| S20-T4 | refuse | requestHR | requestHR | 1.00 | NO | - | - | - | - | - | 1.00 | 0.00 F | - | - |
| S20-T5 | refuse | requestHR | suggestAnswer | 1.00 | NO | - | - | - | - | - | 1.00 | 0.10 F | - | - |

Full rows (judge reasons, retrieved-chunk previews, agent search queries) are in `per_case.json` / `per_case.csv`.

## How to read this honestly

- The deployed system is an incident-driven agent whose prompt allows `suggestAnswer` only for a concrete resolution procedure; many dataset questions are definitions, policies or table lookups. Over-refusal on those is a **finding about the product's scope**, not a harness fault; slice by `requires` (e.g. `procedure`) to see the comparable subset.
- No conversation memory or query rewriting exists, so multi-turn `coreference`/`ellipsis` turns are evaluated in `standalone` mode by default. Conversational metrics (ConversationalGEval, RoleAdherence) are out of scope.
- `clarify` has no tool in this architecture; the only non-answer outcome is `requestHR`.
- Retrieval has no score threshold, so refusal depends on the LLM. Judge scores are LLM-based and indicative; read the reasons for every FAIL. Each turn ran once (non-deterministic).
- Section ids are inferred from chunk text because ingested chunks are labelled `page_N_<type>`; `must_not_retrieve` checks are heuristic and ids that cannot be inferred are listed per turn.
- Dataset corpus name `BARQ_IT_Service_Desk_Manual_Ed5.docx` is not an exact match for retrieved text identifying itself as `BARQ Systems IT Service Operations Manual`, Edition 4.0 (`52 of 52` footer). The intended corpus/reference alignment is unresolved; verify provenance before interpreting reference scores as definitive.
- Dataset note `INC-TIME-01` (conflicting 16:24 vs 09:41 approval time, turn S10-T3) is unresolved in the corpus; treat that turn's outcome accordingly.
