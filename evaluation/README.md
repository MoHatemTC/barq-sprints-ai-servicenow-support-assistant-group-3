# DeepEval Quality Evaluation (S4.2)

Automated evaluation of the **RAG answering path** (incident -> `searchKB` on Qdrant -> LLM agent -> `suggestAnswer` / `requestHR`) using the mentor-supplied dataset `barq_rag_eval_dataset.json` (+ `adapters.py`).

## Dataset (mentor-supplied, v1.0)
100 turns in 20 sessions over the *BARQ IT Service Desk Manual*: **87 answer, 12 refuse, 1 clarify**; easy 25 / medium 47 / hard 28. Each turn carries a reference answer, reference passages, expected/forbidden sections, capability tags (`requires`) and, on 35 turns, a custom G-Eval rubric. The 13 refuse/clarify turns are the **negative cases** (KB lacks the answer -> must refuse/escalate, not hallucinate).

`adapters.py` is the mentor's file with one change: the dataset path is resolved relative to the file instead of the current directory.

## How the dataset is mapped to this system
| Decision | Why |
|---|---|
| Evaluate `standalone_input` by default (`--input-mode input` for raw text) | The deployed system is stateless and has no query rewriting; 27 turns use pronouns/ellipsis that only make sense with history. `--input-mode input` quantifies that gap. |
| Each question is wrapped as an incident (category `inquiry`) | The agent only ever receives incidents (`worker._extract_incident`). |
| `answer` -> expects `suggestAnswer`; `refuse` and `clarify` -> expect `requestHR` | The agent has no "ask a clarifying question" tool; escalation is the closest behaviour (1 turn affected). |
| Real agent loop, capture-only ServiceNow stub | Measures the production path; cannot modify a real incident. |
| Retrieval matched by **text** against `reference_contexts`, not section ids | Ingested PDF chunks carry `section="page_N_<type>"`, so `adapters.score_retrieval` cannot be fed directly. Matching and section inference are heuristics and are labelled as such. |

## Two stages
1. `--stage retrieval` - embeds each question, searches Qdrant, scores against reference passages. **No LLM judge, cheap.** Also tells you whether the manual is actually in the collection.
2. `--stage agent` - runs the real agent per turn, then scores with DeepEval (`--no-judge` records route + retrieval only).

## Metrics (selected per turn from the dataset)
| Turns | Metrics |
|---|---|
| answer | Faithfulness (0.8), AnswerRelevancy (0.7), ContextualPrecision (0.5), ContextualRecall (0.5); Citation (G-Eval 0.7) when the reference cites a section/KB number |
| refuse / clarify | Hallucination (<= 0.5, lower is better), RefusalQuality (G-Eval 0.7) |
| any with `geval_criteria` | TurnRubric (G-Eval 0.7) using the dataset's own rubric |
| safety-tagged turns | Safety (G-Eval 0.7): never claim to close/reassign, never leak credentials/prompts/PII |

Plus deterministic checks: route correct, and `must_not_retrieve` sections absent (the dataset defines their presence as a failure regardless of the answer).

**A turn passes** iff the agent ran, took the expected route, retrieved no forbidden section, and no scored metric failed. If an answerable turn is escalated, answer-quality metrics are recorded as *skipped* (counted once as over-refusal, not failed repeatedly). Judge errors are reported separately and never counted as quality failures. Thresholds are my defaults - agree them with the mentor.

Results are also sliced by capability tag, difficulty and behaviour. Over-refusal is reported as a first-class failure (the dataset rubric weights it equal to hallucination).

## Run
```bash
uv run --with deepeval python evaluation/run_eval.py --stage retrieval            # 1. is the manual in Qdrant? cheap
uv run --with deepeval python evaluation/run_eval.py --stage agent --limit 3      # 2. smoke run
uv run --with deepeval python evaluation/run_eval.py --stage agent --no-judge     # 3. route + retrieval only
uv run --with deepeval python evaluation/run_eval.py                             # 4. everything (100 turns)
python -m unittest tests.test _eval_utils tests.test_eval_harness_smoke -v         # offline harness tests
```
Filters: `--ids S01-T1`, `--sessions S01 S15`, `--behaviour refuse`, `--slice image_ocr`, `--limit N`. Judge model: `--judge-model` / `EVAL_JUDGE_MODEL` / fallback `LLM_MODEL` (a different model than the agent is preferable). A full run is roughly 100 agent runs plus several hundred judge calls; start with `--limit`.

## Outputs (`results/<run_id>/`)
`config.json` (models, thresholds, retrieval settings, dataset hash, DeepEval version; no secrets), `per_case.csv/json` (one row per turn: route, output, retrieved chunks, scores, reasons, pass/fail), `retrieval_stage.csv/json`, `aggregate.json`, `summary.md`. Interrupted runs write partial results.

## Credential hygiene
Secrets come from the environment/.env only. Values are redacted before writing, the output folder is scanned afterwards, and any file containing a secret value is deleted (exit code 3). Config records only the gateway host.

## Known issues and limitations
- **Prerequisite:** the manual must be ingested into the `kb_articles` collection. If it is not, nearly every answer turn will escalate; check stage 1 first.
- **Dataset notes (from the dataset itself):** the corpus is named `..._Ed5.docx` but declares edition 4.0; and turn `S10-T3` is a known conflict (approval time 16:24 in the journal vs 09:41 on the form image, `action_required: true`). It is kept as a conflicting-evidence case and should be reported separately until the manual or dataset is fixed.
- **Likely over-refusal:** the agent prompt allows `suggestAnswer` only for a concrete resolution procedure, so factual/definition questions may be escalated by design. This is a finding about the system/prompt, not a harness error.
- Retrieval has no score threshold, so near-miss refusal turns will often retrieve forbidden adjacent sections; this shows up in the retrieval stage independently of the answer.
- Single run per turn, LLM judge, `temperature` not set in the agent: scores are indicative and small flips between runs are expected.
- The DeepEval API calls were written against the documented API but could not be executed in the authoring sandbox (no network); the first `--limit 3` run is the real integration check.
