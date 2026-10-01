"""S4.2 DeepEval harness for the RAG answering path (mentor dataset barq_rag_eval_dataset.json).

Stage 1  retrieval : embed each question, search Qdrant, score against the dataset's reference passages
                     (deterministic, no LLM judge, cheap). Also tells you whether the manual is in Qdrant.
Stage 2  agent     : run the REAL agent loop (real retrieval + real LLM) per turn against a capture-only
                     ServiceNow stub (no writes), then score with DeepEval.

    uv run --with deepeval python evaluation/run_eval.py --stage retrieval              # start here
    uv run --with deepeval python evaluation/run_eval.py --stage agent --limit 3        # smoke
    uv run --with deepeval python evaluation/run_eval.py --stage agent --no-judge       # route/retrieval only
    uv run --with deepeval python evaluation/run_eval.py                                # everything

Credentials come from the environment/.env only; values are redacted and the output folder is scanned.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

import eval_utils as U  # noqa: E402

DATASET_PATH = HERE / "barq_rag_eval_dataset.json"
RESULTS_DIR = HERE / "results"

THRESHOLDS = {
    "Faithfulness": 0.8, "AnswerRelevancy": 0.7, "ContextualPrecision": 0.5, "ContextualRecall": 0.5,
    "Citation": 0.7, "TurnRubric": 0.7, "Hallucination": 0.5,  # Hallucination: LOWER is better (pass if <= threshold)
    "RefusalQuality": 0.7, "Safety": 0.7,
}
# answer-quality metrics are meaningless when the agent escalated instead of answering; that outcome is
# already counted as over-refusal by the route check, so these are recorded as skipped (not double-failed).
SKIP_ON_OVER_REFUSAL = {"Faithfulness", "AnswerRelevancy", "Citation", "TurnRubric"}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dataset", type=Path, default=DATASET_PATH)
    p.add_argument("--stage", choices=["retrieval", "agent", "all"], default="all")
    p.add_argument("--ids", nargs="*", help="Turn ids, e.g. S01-T1 S15-T2")
    p.add_argument("--sessions", nargs="*", help="Session ids, e.g. S01 S15")
    p.add_argument("--behaviour", choices=list(U.BEHAVIOURS))
    p.add_argument("--slice", dest="capability", help="Only turns requiring this capability (e.g. image_ocr)")
    p.add_argument("--limit", type=int)
    p.add_argument("--input-mode", choices=["standalone", "input"], default="standalone",
                   help="standalone (default): self-contained question. input: raw text incl. pronouns/ellipsis "
                        "(the system has no query rewriting, so this quantifies that gap)")
    p.add_argument("--no-judge", action="store_true", help="Skip DeepEval; agent stage records route + retrieval only")
    p.add_argument("--judge-model", default=os.getenv("EVAL_JUDGE_MODEL", ""))
    p.add_argument("--out", type=Path)
    return p.parse_args()


def require(settings, names: list[str]) -> None:
    missing = [n.upper() for n in names if not getattr(settings, n, "")]
    if not os.getenv("GEMINI_API_KEY"):
        missing.append("GEMINI_API_KEY")
    if missing:
        sys.exit(f"Missing required configuration (set in .env or environment): {', '.join(sorted(set(missing)))}")


# ------------------------------------------------------------------ stage 1
def run_retrieval_stage(turns, data, settings, index):
    from barq_support.retrieval.retriever import DEFAULT_TOP_K, get_qdrant_client, search_kb

    client = get_qdrant_client(settings.qdrant_url, settings.qdrant_api_key)
    rows = []
    for i, t in enumerate(turns, 1):
        q = t["standalone_input"]
        try:
            hits = search_kb(q, client, top_k=DEFAULT_TOP_K)
            err = None
        except Exception as exc:
            hits, err = [], f"{type(exc).__name__}: {str(exc)[:200]}"
        texts = [h.get("text", "") for h in hits]
        rows.append({
            "turn_id": t["turn_id"], "behaviour": t["expected_behaviour"], "difficulty": t["difficulty"],
            "requires": t["requires"], "expected_sections": t["expected_sections"], "query": q,
            "top_score": max((h["score"] for h in hits), default=None), "error": err,
            "retrieval": U.score_retrieval_chunks(texts, t, index),
            "retrieved": [{"article_id": h.get("article_id"), "section": h.get("section"),
                           "chunk_index": h.get("chunk_index"), "score": h.get("score"),
                           "text_preview": (h.get("text") or "")[:300]} for h in hits],
        })
        r = rows[-1]["retrieval"]
        print(f"[retrieval {i}/{len(turns)}] {t['turn_id']} recall={r['ref_recall']} clean={r['clean']}"
              + (f" ERROR={err}" if err else ""), flush=True)
    return rows


# ------------------------------------------------------------------ stage 2
def build_metrics(turn, judge, rubrics):
    from deepeval.metrics import (AnswerRelevancyMetric, ContextualPrecisionMetric, ContextualRecallMetric,
                                  FaithfulnessMetric, GEval, HallucinationMetric)
    from deepeval.test_case import LLMTestCaseParams as P

    common = dict(model=judge, include_reason=True, async_mode=False)

    def geval(name, criteria, params):
        return GEval(name=name, criteria=criteria, evaluation_params=params, threshold=THRESHOLDS[name],
                     model=judge, async_mode=False)

    m = {}
    if turn["expected_behaviour"] == "answer":
        m["Faithfulness"] = FaithfulnessMetric(threshold=THRESHOLDS["Faithfulness"], **common)
        m["AnswerRelevancy"] = AnswerRelevancyMetric(threshold=THRESHOLDS["AnswerRelevancy"], **common)
        m["ContextualPrecision"] = ContextualPrecisionMetric(threshold=THRESHOLDS["ContextualPrecision"], **common)
        m["ContextualRecall"] = ContextualRecallMetric(threshold=THRESHOLDS["ContextualRecall"], **common)
        if U.needs_citation_check(turn):
            m["Citation"] = geval("Citation", rubrics["citation"], [P.INPUT, P.ACTUAL_OUTPUT, P.EXPECTED_OUTPUT])
    else:
        m["Hallucination"] = HallucinationMetric(threshold=THRESHOLDS["Hallucination"], **common)
        m["RefusalQuality"] = geval("RefusalQuality", rubrics["refusal_quality"],
                                    [P.INPUT, P.ACTUAL_OUTPUT, P.EXPECTED_OUTPUT])
    if turn["geval_criteria"]:
        m["TurnRubric"] = geval("TurnRubric", turn["geval_criteria"],
                                [P.INPUT, P.ACTUAL_OUTPUT, P.EXPECTED_OUTPUT, P.RETRIEVAL_CONTEXT])
    if U.needs_safety_check(turn):
        m["Safety"] = geval("Safety", rubrics["safety"], [P.INPUT, P.ACTUAL_OUTPUT])
    return m


def run_agent_turn(turn, settings, qdrant_client, input_mode):
    import barq_support.agent.tools as tools_mod
    from barq_support.agent.agent import run_agent

    sn, rec = U.CapturingServiceNow(), U.RetrievalRecorder()
    original = tools_mod.search_kb
    tools_mod.search_kb = rec.wrap(original)
    result, error = {}, None
    t0 = time.perf_counter()
    try:
        result = run_agent(settings=settings, incident=U.build_incident(turn, input_mode),
                           servicenow=sn, qdrant_client=qdrant_client)
    except Exception as exc:
        error = f"{type(exc).__name__}: {str(exc)[:300]}"
    finally:
        tools_mod.search_kb = original
    return sn, rec, result, error, round(time.perf_counter() - t0, 2)


def evaluate_turn(turn, settings, qdrant_client, judge, rubrics, index, input_mode):
    sn, rec, result, error, latency = run_agent_turn(turn, settings, qdrant_client, input_mode)
    out = sn.outcome()
    chunks = rec.retrieval_context()
    query = U.query_for(turn, input_mode)
    route_ok = out["route"] == U.expected_route(turn)
    row = {
        "turn_id": turn["turn_id"], "session_id": turn["session_id"], "behaviour": turn["expected_behaviour"],
        "difficulty": turn["difficulty"], "requires": turn["requires"], "tags": turn["tags"],
        "input_mode": input_mode, "input": query, "reference": turn["reference"],
        "expected_route": U.expected_route(turn), "actual_route": out["route"], "route_correct": route_ok,
        "confidence": out["confidence"], "multiple_terminal_calls": out["multiple_terminal_calls"],
        "actual_output": out["output"], "agent_error": error,
        "iterations": result.get("s3_iterations") if isinstance(result, dict) else None,
        "budget_exhausted": bool(result.get("s3_budget_exhausted", False)) if isinstance(result, dict) else None,
        "latency_s": latency, "top_retrieval_score": rec.top_score(),
        "n_chunks_retrieved": len(rec.chunks), "n_searches": len(rec.queries), "search_queries": rec.queries,
        "retrieval": U.score_retrieval_chunks(chunks, turn, index),
        "retrieved_chunks": [{**{k: c[k] for k in ("article_id", "chunk_index", "section", "score")},
                              "text_preview": c["text"][:300]} for c in rec.unique_chunks()],
        "work_notes": sn.work_notes, "metrics": {},
    }
    if judge is None:
        return row

    metrics = build_metrics(turn, judge, rubrics)
    if not out["output"]:
        for name in metrics:
            row["metrics"][name] = {"score": None, "passed": None, "reason": None, "skipped": "no agent output"}
        return row

    from deepeval.test_case import LLMTestCase
    case = LLMTestCase(
        input=query, actual_output=out["output"], expected_output=turn["reference"] or "",
        retrieval_context=chunks or [""],
        context=turn["reference_contexts"] or chunks or [""],
    )
    over_refusal = turn["expected_behaviour"] == "answer" and out["route"] != "suggestAnswer"
    for name, metric in metrics.items():
        if over_refusal and name in SKIP_ON_OVER_REFUSAL:
            row["metrics"][name] = {"score": None, "passed": None, "reason": None,
                                    "skipped": "over-refusal: no answer to score (counted by route check)"}
            continue
        try:
            metric.measure(case)
            row["metrics"][name] = {"score": metric.score, "passed": bool(metric.is_successful()),
                                    "reason": getattr(metric, "reason", None), "threshold": metric.threshold}
        except Exception as exc:
            row["metrics"][name] = {"score": None, "passed": None, "reason": None,
                                    "error": f"{type(exc).__name__}: {str(exc)[:300]}"}
    return row


# ------------------------------------------------------------------ main
def main() -> int:
    args = parse_args()
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from barq_support.settings import get_settings
    settings = get_settings()

    data = U.load_dataset(args.dataset)
    index = U.build_section_index(data)
    turns = U.select_turns(U.all_turns(data), args.ids, args.sessions, args.behaviour, args.capability, args.limit)
    if not turns:
        sys.exit("No turns selected.")
    do_retr = args.stage in ("retrieval", "all")
    do_agent = args.stage in ("agent", "all")
    use_judge = do_agent and not args.no_judge

    require(settings, ["qdrant_url", "qdrant_api_key"] + (["llm_api_key", "llm_model", "llm_base_url"] if do_agent else []))

    judge, deepeval_version, judge_model = None, "not used", ""
    if use_judge:
        import deepeval
        from judge import GatewayJudge
        deepeval_version = getattr(deepeval, "__version__", "unknown")
        judge_model = args.judge_model or settings.llm_model
        judge = GatewayJudge(model=judge_model, base_url=settings.llm_base_url, api_key=settings.llm_api_key)

    from barq_support.retrieval import embedder, retriever
    started = datetime.now(timezone.utc)
    run_id = started.strftime("%Y%m%dT%H%M%SZ")
    out_dir = args.out or (RESULTS_DIR / run_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    secrets = U.secret_values_from(settings, dict(os.environ))
    ds = data["dataset"]

    config = {
        "run_id": run_id, "started_utc": started.isoformat(timespec="seconds"),
        "stages": [s for s, on in (("retrieval", do_retr), ("agent", do_agent)) if on],
        "n_turns": len(turns), "turn_ids": [t["turn_id"] for t in turns], "input_mode": args.input_mode,
        "filters": {"ids": args.ids, "sessions": args.sessions, "behaviour": args.behaviour,
                    "slice": args.capability, "limit": args.limit},
        "judge_enabled": use_judge, "deepeval_version": deepeval_version, "python": sys.version.split()[0],
        "agent_model": settings.llm_model if do_agent else "not used", "judge_model": judge_model or "not used",
        "judge_is_same_as_agent": bool(judge_model) and judge_model == settings.llm_model,
        "llm_gateway_host": U.host_only(settings.llm_base_url),
        "agent": {"max_iterations": settings.agent_max_iterations, "temperature": "gateway default (not set in build_llm)",
                  "question_framing": "wrapped as incident, category=inquiry"},
        "retrieval": {"collection": retriever.COLLECTION_NAME, "top_k": retriever.DEFAULT_TOP_K,
                      "embedding_model": embedder.EMBEDDING_MODEL, "embedding_dimension": embedder.EMBEDDING_DIMENSION,
                      "score_threshold": None, "reference_match": "token containment (ref>=0.6 or chunk>=0.8)"},
        "writeback": "capture-only stub (no ServiceNow calls)",
        "metrics": {n: {"threshold": t} for n, t in THRESHOLDS.items()},
        "metric_policy": "per-turn selection from dataset behaviour/tags/geval_criteria; see evaluation/README.md",
        "dataset": {"name": ds["name"], "version": ds["version"], "corpus_document": ds["corpus"]["document"],
                    "corpus_edition_declared": ds["corpus"]["edition"],
                    "file": args.dataset.name, "sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest()},
        "env_var_names_used": ["LLM_API_KEY", "LLM_MODEL", "LLM_BASE_URL", "GEMINI_API_KEY", "QDRANT_URL",
                               "QDRANT_API_KEY", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"],
        "secrets_policy": "values never written; outputs redacted and scanned before exit",
    }

    retr_rows, agent_rows, interrupted = [], [], False
    try:
        if do_retr:
            retr_rows = run_retrieval_stage(turns, data, settings, index)
        if do_agent:
            from qdrant_client import QdrantClient
            qc = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key, timeout=120)
            rubrics = data["metric_suite"]["geval_global_rubrics"]
            for i, t in enumerate(turns, 1):
                print(f"[agent {i}/{len(turns)}] {t['turn_id']} ({t['expected_behaviour']}) ...", flush=True)
                row = evaluate_turn(t, settings, qc, judge, rubrics, index, args.input_mode)
                row["passed"] = U.turn_passed(row)
                print(f"    expected={row['expected_route']} actual={row['actual_route']} "
                      f"{'OK' if row['route_correct'] else 'MISMATCH'} passed={row['passed']}"
                      + (f" ERROR={row['agent_error']}" if row["agent_error"] else ""), flush=True)
                agent_rows.append(row)
    except KeyboardInterrupt:
        interrupted = True
        print("\nInterrupted - writing partial results.", file=sys.stderr)
    config["interrupted"] = interrupted
    config["n_turns_completed"] = {"retrieval": len(retr_rows), "agent": len(agent_rows)}

    retr_agg = U.aggregate_retrieval(retr_rows) if retr_rows else None
    agent_agg = U.aggregate_agent(agent_rows) if agent_rows else None

    config, retr_rows, agent_rows = (U.redact_obj(x, secrets) for x in (config, retr_rows, agent_rows))
    retr_agg, agent_agg = U.redact_obj(retr_agg, secrets), U.redact_obj(agent_agg, secrets)

    U.write_json(config, out_dir / "config.json")
    U.write_json({"retrieval_stage": retr_agg, "agent_stage": agent_agg}, out_dir / "aggregate.json")
    if retr_rows:
        U.write_json(retr_rows, out_dir / "retrieval_stage.json")
        U.write_retrieval_csv(retr_rows, out_dir / "retrieval_stage.csv")
    if agent_rows:
        U.write_json(agent_rows, out_dir / "per_case.json")
        U.write_csv(agent_rows, out_dir / "per_case.csv")
    (out_dir / "summary.md").write_text(U.render_summary_md(config, agent_rows, agent_agg, retr_rows, retr_agg), encoding="utf-8")

    leaks = U.scan_dir_for_secrets(out_dir, secrets)
    if leaks:
        for f in leaks:
            Path(f).unlink()
        print(f"SECURITY: secret value detected in {len(leaks)} output file(s); files deleted. Do not commit.", file=sys.stderr)
        return 3
    print(f"\nResults written to {out_dir}")
    return 130 if interrupted else 0


if __name__ == "__main__":
    sys.exit(main())
