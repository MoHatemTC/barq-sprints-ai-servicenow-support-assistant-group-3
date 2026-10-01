"""Pure helpers for the S4.2 DeepEval harness (mentor dataset: barq_rag_eval_dataset.json).

No deepeval / langchain / qdrant / network imports here, so everything is unit-testable offline
(see tests/test_eval_utils.py).
"""

from __future__ import annotations

import csv
import json
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlparse

BEHAVIOURS = ("answer", "refuse", "clarify")
# The agent has exactly two terminal tools. "clarify" has no tool, so escalation is the only
# non-answer outcome the architecture can produce (see README "Known gaps").
ROUTE_FOR_BEHAVIOUR = {"answer": "suggestAnswer", "refuse": "requestHR", "clarify": "requestHR"}
SAFETY_TAGS = {"safety_critical", "privacy"}
SAFETY_REQUIRES = {"prompt_injection", "authority_claim", "pii", "adversarial"}
CITATION_RE = re.compile(r"\b\d{1,2}\.\d{1,2}\b|\bKB\d{3,}\b")
MIN_SECRET_LEN = 8
REQUIRED_TURN_FIELDS = (
    "turn_id", "session_id", "input", "standalone_input", "reference", "reference_contexts",
    "expected_sections", "expected_behaviour", "requires", "difficulty", "must_not_retrieve",
    "tags", "geval_criteria",
)


class DatasetError(ValueError):
    pass


# --------------------------------------------------------------------------- dataset
def load_dataset(path: Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for key in ("dataset", "metric_suite", "sessions"):
        if key not in data:
            raise DatasetError(f"dataset missing top-level key {key!r}")
    seen: set[str] = set()
    for s in data["sessions"]:
        for t in s["turns"]:
            missing = [f for f in REQUIRED_TURN_FIELDS if f not in t]
            if missing:
                raise DatasetError(f"{t.get('turn_id', '?')} missing fields: {missing}")
            if t["turn_id"] in seen:
                raise DatasetError(f"duplicate turn_id {t['turn_id']}")
            seen.add(t["turn_id"])
            if t["expected_behaviour"] not in BEHAVIOURS:
                raise DatasetError(f"{t['turn_id']}: bad behaviour {t['expected_behaviour']!r}")
    behaviours = {t["expected_behaviour"] for t in all_turns(data)}
    if "answer" not in behaviours or "refuse" not in behaviours:
        raise DatasetError("dataset needs both answer and refuse turns")
    return data


def all_turns(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [t for s in data["sessions"] for t in s["turns"]]


def select_turns(
    turns: list[dict], ids: Iterable[str] | None = None, sessions: Iterable[str] | None = None,
    behaviour: str | None = None, capability: str | None = None, limit: int | None = None,
) -> list[dict]:
    if ids:
        wanted = set(ids)
        unknown = wanted - {t["turn_id"] for t in turns}
        if unknown:
            raise DatasetError(f"unknown turn ids: {sorted(unknown)}")
        turns = [t for t in turns if t["turn_id"] in wanted]
    if sessions:
        turns = [t for t in turns if t["session_id"] in set(sessions)]
    if behaviour:
        turns = [t for t in turns if t["expected_behaviour"] == behaviour]
    if capability:
        turns = [t for t in turns if capability in t["requires"]]
    if limit is not None:
        turns = turns[:limit]
    return turns


def query_for(turn: dict, input_mode: str) -> str:
    """standalone = self-contained question (isolates retrieval+agent); input = raw text incl. pronouns."""
    return turn["standalone_input"] if input_mode == "standalone" else turn["input"]


def build_incident(turn: dict, input_mode: str = "standalone") -> dict[str, str]:
    """Wrap a manual question as an incident in the exact shape worker._extract_incident() produces.

    The deployed agent only ever sees incidents, so questions are framed that way (category 'inquiry').
    """
    q = query_for(turn, input_mode)
    return {
        "number": f"EVAL-{turn['turn_id']}",
        "sys_id": f"eval-{turn['turn_id'].lower()}",
        "short_description": q[:160],
        "description": q,
        "category": "inquiry",
    }


def expected_route(turn: dict) -> str:
    return ROUTE_FOR_BEHAVIOUR[turn["expected_behaviour"]]


def needs_safety_check(turn: dict) -> bool:
    return bool(SAFETY_TAGS & set(turn["tags"])) or bool(SAFETY_REQUIRES & set(turn["requires"]))


def needs_citation_check(turn: dict) -> bool:
    return turn["expected_behaviour"] == "answer" and bool(CITATION_RE.search(turn["reference"] or ""))


# ------------------------------------------------- retrieval scoring (deterministic, no judge)
# The ingested PDF chunks carry section="page_N_<type>", NOT the manual's section numbers, so the
# mentor's section-id scorer (adapters.score_retrieval) cannot be fed directly. We instead match
# retrieved chunk text against the dataset's reference_contexts (token containment) and infer
# section ids from those passages. Both are heuristics and are labelled as such in reports.
_TOKEN = re.compile(r"\w+", re.UNICODE)
HEADING_NUM = re.compile(r"(?m)^\s*#{0,6}\s*(\d{1,2}\.\d{1,2})\b")


def _tokens(s: str) -> list[str]:
    return _TOKEN.findall(s.lower())


def passage_body(ctx: str) -> str:
    """Strip the '<section> — ' prefix used in reference_contexts."""
    return ctx.split(" — ", 1)[1] if " — " in ctx else ctx


def chunk_matches_passage(chunk_text: str, passage: str, ref_cover: float = 0.6, chunk_cover: float = 0.8) -> bool:
    r, c = set(_tokens(passage_body(passage))), set(_tokens(chunk_text))
    if len(r) < 3 or len(c) < 5:
        return False
    inter = len(r & c)
    return inter / len(r) >= ref_cover or inter / len(c) >= chunk_cover


def build_section_index(data: dict[str, Any]) -> dict[str, list[str]]:
    """section id -> reference passages, parsed from every turn's reference_contexts."""
    turns = all_turns(data)
    known = sorted(
        {s for t in turns for s in t["expected_sections"] + t["must_not_retrieve"] if s and s != "—"},
        key=len, reverse=True,
    )
    index: dict[str, list[str]] = {}
    for t in turns:
        for ctx in t["reference_contexts"]:
            head = ctx.split(" — ", 1)[0] if " — " in ctx else ctx.split(" · ", 1)[0]
            sec = next((k for k in known if head.startswith(k)), None)
            if sec:
                index.setdefault(sec, [])
                if ctx not in index[sec]:
                    index[sec].append(ctx)
    return index


def infer_sections(chunk_text: str, index: dict[str, list[str]]) -> set[str]:
    found = {m for m in HEADING_NUM.findall(chunk_text) if m in index}
    for sec, passages in index.items():
        if any(chunk_matches_passage(chunk_text, p) for p in passages):
            found.add(sec)
    return found


def score_retrieval_chunks(chunk_texts: list[str], turn: dict, index: dict[str, list[str]]) -> dict[str, Any]:
    refs = turn["reference_contexts"]
    covered = [i for i, r in enumerate(refs) if any(chunk_matches_passage(c, r) for c in chunk_texts)]
    useful = [c for c in chunk_texts if any(chunk_matches_passage(c, r) for r in refs)]
    got: set[str] = set()
    for c in chunk_texts:
        got |= infer_sections(c, index)
    forbidden = set(turn["must_not_retrieve"]) & set(index)  # only ids we can actually detect
    uninferable = sorted(set(turn["must_not_retrieve"]) - set(index))
    want = {s for s in turn["expected_sections"] if s != "—"} & set(index)
    return {
        "ref_recall": round(len(covered) / len(refs), 4) if refs else None,
        "ref_precision": round(len(useful) / len(chunk_texts), 4) if chunk_texts else (0.0 if refs else None),
        "hit_any": bool(covered) if refs else None,
        "hit_all": len(covered) == len(refs) if refs else None,
        "sections_inferred": sorted(got),
        "expected_sections_found": sorted(want & got),
        "forbidden_retrieved": sorted(forbidden & got),
        "forbidden_uninferable": uninferable,
        "clean": not (forbidden & got),
    }


# ------------------------------------------------------------------ capture doubles
class CapturingServiceNow:
    """Stands in for ServiceNowClient during evaluation: records writebacks, performs no I/O."""

    def __init__(self) -> None:
        self.work_notes: list[str] = []
        self.suggest_calls: list[dict[str, Any]] = []
        self.hr_calls: list[dict[str, Any]] = []

    def add_work_note(self, sys_id: str, note: str) -> dict:
        self.work_notes.append(note)
        return {"result": {"sys_id": sys_id}}

    def suggest_answer(self, sys_id: str, response: str, confidence: float) -> dict:
        self.suggest_calls.append({"response": response, "confidence": confidence})
        return {"result": {"sys_id": sys_id, "ai_status": "suggested"}}

    def request_hr(self, sys_id: str, reason: str) -> dict:
        self.hr_calls.append({"reason": reason})
        return {"result": {"sys_id": sys_id, "ai_status": "escalated"}}

    def outcome(self) -> dict[str, Any]:
        if self.suggest_calls:
            call = self.suggest_calls[-1]
            return {"route": "suggestAnswer", "output": call["response"], "confidence": call["confidence"],
                    "multiple_terminal_calls": len(self.suggest_calls) + len(self.hr_calls) > 1}
        if self.hr_calls:
            return {"route": "requestHR", "output": self.hr_calls[-1]["reason"], "confidence": None,
                    "multiple_terminal_calls": len(self.hr_calls) > 1}
        return {"route": "none", "output": "", "confidence": None, "multiple_terminal_calls": False}


class RetrievalRecorder:
    """Wraps search_kb and records every chunk the agent actually retrieved."""

    def __init__(self) -> None:
        self.queries: list[str] = []
        self.chunks: list[dict[str, Any]] = []

    def wrap(self, fn: Callable[..., list[dict]]) -> Callable[..., list[dict]]:
        def recorded(query: str, *args: Any, **kwargs: Any) -> list[dict]:
            results = fn(query, *args, **kwargs)
            self.queries.append(query)
            self.chunks.extend(
                {"article_id": r.get("article_id"), "chunk_index": r.get("chunk_index"),
                 "section": r.get("section"), "score": r.get("score"), "text": r.get("text", "")}
                for r in results
            )
            return results
        return recorded

    def unique_chunks(self) -> list[dict[str, Any]]:
        seen: "OrderedDict[tuple, dict]" = OrderedDict()
        for c in self.chunks:
            key = (c["article_id"], c["chunk_index"], c["text"])
            if key not in seen or (c["score"] or 0) > (seen[key]["score"] or 0):
                seen[key] = c
        return list(seen.values())

    def retrieval_context(self) -> list[str]:
        return [c["text"] for c in self.unique_chunks() if c["text"]]

    def top_score(self) -> float | None:
        scores = [c["score"] for c in self.chunks if c["score"] is not None]
        return max(scores) if scores else None


# ------------------------------------------------------------------------ LLM JSON
def extract_json(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start: end + 1])
        raise


# ------------------------------------------------------------- credential hygiene
def secret_values_from(settings: Any, extra_env: dict[str, str] | None = None) -> list[str]:
    markers = ("key", "secret", "password", "token")
    values: set[str] = set()
    names = getattr(type(settings), "model_fields", None) or getattr(settings, "model_fields", {})
    for name in names:
        if any(m in name.lower() for m in markers):
            v = getattr(settings, name, "")
            if isinstance(v, str) and len(v) >= MIN_SECRET_LEN:
                values.add(v)
    for name, v in (extra_env or {}).items():
        if any(m in name.lower() for m in markers) and isinstance(v, str) and len(v) >= MIN_SECRET_LEN:
            values.add(v)
    return sorted(values, key=len, reverse=True)


def redact(text: str, secrets: Iterable[str]) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, "***REDACTED***")
    return text


def redact_obj(obj: Any, secrets: list[str]) -> Any:
    if isinstance(obj, str):
        return redact(obj, secrets)
    if isinstance(obj, dict):
        return {k: redact_obj(v, secrets) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [redact_obj(v, secrets) for v in obj]
    return obj


def scan_dir_for_secrets(directory: Path, secrets: Iterable[str]) -> list[str]:
    hits: list[str] = []
    secrets = [s for s in secrets if s]
    for p in Path(directory).rglob("*"):
        if p.is_file():
            body = p.read_text(encoding="utf-8", errors="ignore")
            if any(s in body for s in secrets):
                hits.append(str(p))
    return hits


def host_only(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.hostname}" if parsed.hostname else ""


# ------------------------------------------------------------------- aggregation
def turn_passed(row: dict[str, Any]) -> bool:
    """A turn passes iff the agent ran, took the expected route, retrieved nothing forbidden and no
    scored DeepEval metric failed. Skipped/errored metrics don't fail a turn (errors are flagged)."""
    if row.get("agent_error") or row["actual_route"] == "none":
        return False
    if not row["route_correct"] or not row["retrieval"]["clean"]:
        return False
    return all(m["passed"] for m in row["metrics"].values() if m.get("score") is not None)


def _rate(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def slice_rates(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Same contract as adapters.slice_report(): pass rate per capability / difficulty / behaviour."""
    agg: dict[str, list[int]] = {}
    for r in rows:
        for cap in r["requires"] + [f"difficulty:{r['difficulty']}", f"behaviour:{r['behaviour']}"]:
            slot = agg.setdefault(cap, [0, 0])
            slot[1] += 1
            slot[0] += bool(r["passed"])
    return {k: {"passed": v[0], "total": v[1], "rate": round(v[0] / v[1], 3)} for k, v in sorted(agg.items())}


def aggregate_retrieval(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """rows: retrieval-stage rows {behaviour, retrieval:{...}}; reference metrics only on turns with references."""
    withref = [r for r in rows if r["retrieval"]["ref_recall"] is not None]
    return {
        "n_turns": len(rows),
        "n_with_reference": len(withref),
        "mean_ref_recall": _mean([r["retrieval"]["ref_recall"] for r in withref]),
        "mean_ref_precision": _mean([r["retrieval"]["ref_precision"] for r in withref]),
        "hit_any_rate": _rate(sum(1 for r in withref if r["retrieval"]["hit_any"]), len(withref)),
        "hit_all_rate": _rate(sum(1 for r in withref if r["retrieval"]["hit_all"]), len(withref)),
        "clean_rate": _rate(sum(1 for r in rows if r["retrieval"]["clean"]), len(rows)),
        "n_with_forbidden_sections": sum(1 for r in rows if r["retrieval"]["forbidden_retrieved"]),
    }


def aggregate_agent(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ans = [r for r in rows if r["behaviour"] == "answer"]
    neg = [r for r in rows if r["behaviour"] in ("refuse", "clarify")]
    agg: dict[str, Any] = {
        "n_turns": len(rows), "n_answer": len(ans), "n_negative": len(neg),
        "n_agent_errors": sum(1 for r in rows if r.get("agent_error")),
        "n_no_terminal_tool": sum(1 for r in rows if r["actual_route"] == "none"),
        "route_accuracy": _rate(sum(1 for r in rows if r["route_correct"]), len(rows)),
        "turn_pass_rate": _rate(sum(1 for r in rows if r["passed"]), len(rows)),
        # mentor rubric: over-refusal counts as much as a hallucination
        "answer_turns_answered": _rate(sum(1 for r in ans if r["actual_route"] == "suggestAnswer"), len(ans)),
        "over_refusal_rate": _rate(sum(1 for r in ans if r["actual_route"] == "requestHR"), len(ans)),
        "negative_turns_escalated": _rate(sum(1 for r in neg if r["actual_route"] == "requestHR"), len(neg)),
        "false_answer_rate": _rate(sum(1 for r in neg if r["actual_route"] == "suggestAnswer"), len(neg)),
        "n_judge_errors": sum(1 for r in rows for m in r["metrics"].values() if m.get("error")),
    }
    per_metric: dict[str, dict[str, Any]] = {}
    for r in rows:
        for name, m in r["metrics"].items():
            slot = per_metric.setdefault(name, {"n_scored": 0, "n_passed": 0, "n_errored": 0, "n_skipped": 0, "scores": []})
            if m.get("skipped"):
                slot["n_skipped"] += 1
            elif m.get("score") is None:
                slot["n_errored"] += 1
            else:
                slot["n_scored"] += 1
                slot["scores"].append(m["score"])
                slot["n_passed"] += bool(m.get("passed"))
    for slot in per_metric.values():
        scores = slot.pop("scores")
        slot["mean_score"] = _mean(scores)
        slot["pass_rate"] = _rate(slot["n_passed"], slot["n_scored"])
    agg["per_metric"] = dict(sorted(per_metric.items()))
    conf: dict[str, int] = {}
    for r in rows:
        k = f"{r['behaviour']} (expect {r['expected_route']}) -> {r['actual_route']}"
        conf[k] = conf.get(k, 0) + 1
    agg["route_confusion"] = dict(sorted(conf.items()))
    agg["slices"] = slice_rates(rows)
    return agg


# --------------------------------------------------------------------- reporting
def _clip(text: Any, n: int) -> str:
    s = "" if text is None else str(text).replace("\r", " ").replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"


def _fmt(v: Any) -> str:
    if v is None:
        return "n/a"
    return f"{v:.2f}" if isinstance(v, float) else str(v)


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    names = sorted({m for r in rows for m in r["metrics"]})
    header = ["turn_id", "session_id", "behaviour", "difficulty", "requires", "input_mode", "expected_route",
              "actual_route", "route_correct", "passed", "ref_recall", "ref_precision", "forbidden_retrieved",
              "top_retrieval_score", "n_chunks", "n_searches", "iterations", "latency_s", "agent_error", "actual_output"]
    for n in names:
        header += [f"{n}__score", f"{n}__passed", f"{n}__reason"]
    with Path(path).open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for r in rows:
            ret = r["retrieval"]
            line = [r["turn_id"], r["session_id"], r["behaviour"], r["difficulty"], ";".join(r["requires"]),
                    r["input_mode"], r["expected_route"], r["actual_route"], r["route_correct"], r["passed"],
                    ret["ref_recall"], ret["ref_precision"], ";".join(ret["forbidden_retrieved"]),
                    r.get("top_retrieval_score"), r["n_chunks_retrieved"], r["n_searches"], r.get("iterations"),
                    r.get("latency_s"), _clip(r.get("agent_error"), 200), _clip(r["actual_output"], 600)]
            for n in names:
                m = r["metrics"].get(n)
                if m is None:
                    line += ["", "", ""]
                else:
                    line += [m.get("score"), m.get("passed"), _clip(m.get("reason") or m.get("error") or m.get("skipped"), 400)]
            w.writerow(line)


def write_retrieval_csv(rows: list[dict[str, Any]], path: Path) -> None:
    with Path(path).open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["turn_id", "behaviour", "difficulty", "requires", "top_score", "ref_recall", "ref_precision",
                    "hit_all", "expected_sections", "expected_found", "forbidden_retrieved", "forbidden_uninferable"])
        for r in rows:
            x = r["retrieval"]
            w.writerow([r["turn_id"], r["behaviour"], r["difficulty"], ";".join(r["requires"]), r.get("top_score"),
                        x["ref_recall"], x["ref_precision"], x["hit_all"], ";".join(r["expected_sections"]),
                        ";".join(x["expected_sections_found"]), ";".join(x["forbidden_retrieved"]),
                        ";".join(x["forbidden_uninferable"])])


def render_summary_md(config: dict[str, Any], agent_rows: list[dict[str, Any]], agent_agg: dict[str, Any] | None,
                      retr_rows: list[dict[str, Any]], retr_agg: dict[str, Any] | None) -> str:
    L: list[str] = ["# DeepEval Quality Report - RAG answering path\n"]
    L.append(f"- Run `{config['run_id']}` | started (UTC) `{config['started_utc']}` | stages: {', '.join(config['stages'])}")
    L.append(f"- Dataset: `{config['dataset']['name']}` v{config['dataset']['version']} (sha256 `{config['dataset']['sha256'][:12]}`), "
             f"corpus `{config['dataset']['corpus_document']}`; turns evaluated: {config['n_turns']}; input mode: `{config['input_mode']}`")
    L.append(f"- Agent model `{config['agent_model']}` | judge `{config['judge_model']}` | DeepEval `{config['deepeval_version']}` | judge: {'on' if config['judge_enabled'] else 'OFF (--no-judge)'}")
    L.append(f"- Retrieval: `{config['retrieval']['embedding_model']}` ({config['retrieval']['embedding_dimension']}d), top_k={config['retrieval']['top_k']}, collection `{config['retrieval']['collection']}`, no score threshold\n")

    if retr_agg:
        L.append("## Stage 1 - Retrieval only (deterministic, no LLM judge)\n")
        L.append("Query = `standalone_input`; matching is token-containment against the dataset's `reference_contexts` (heuristic).\n")
        L.append("| Measure | Value |\n|---|---|")
        for k, label in [("n_with_reference", "Turns with reference passages"), ("mean_ref_recall", "Mean reference recall"),
                         ("mean_ref_precision", "Mean reference precision"), ("hit_any_rate", "Hit rate (>=1 reference passage retrieved)"),
                         ("hit_all_rate", "Hit rate (all reference passages retrieved)"),
                         ("clean_rate", "Turns with no forbidden section retrieved"),
                         ("n_with_forbidden_sections", "Turns retrieving a must-not-retrieve section")]:
            L.append(f"| {label} | {_fmt(retr_agg[k])} |")
        L.append("")
        if retr_agg["mean_ref_recall"] is not None and retr_agg["mean_ref_recall"] < 0.2:
            L.append("> **WARNING:** reference recall is very low. The manual is probably not in the Qdrant collection (or was ingested in a form the matcher cannot align). Verify ingestion before interpreting any agent-stage result.\n")

    if agent_agg:
        a = agent_agg
        L.append("## Stage 2 - Agent path (real agent + DeepEval)\n")
        L.append("| Measure | Value |\n|---|---|")
        for k, label in [("turn_pass_rate", "Turn pass rate (route + clean retrieval + all scored metrics)"),
                         ("route_accuracy", "Route accuracy"),
                         ("answer_turns_answered", "Answerable turns answered (suggestAnswer)"),
                         ("over_refusal_rate", "Answerable turns wrongly escalated (over-refusal)"),
                         ("negative_turns_escalated", "Refuse/clarify turns escalated (requestHR)"),
                         ("false_answer_rate", "Refuse/clarify turns wrongly answered (hallucination risk)"),
                         ("n_agent_errors", "Agent/runtime errors"), ("n_no_terminal_tool", "Runs with no terminal tool"),
                         ("n_judge_errors", "Judge/metric errors")]:
            L.append(f"| {label} | {_fmt(a[k])} |")
        L.append("")
        L.append("### DeepEval metrics\n")
        L.append("| Metric | Threshold | Scored | Skipped | Errored | Mean | Pass rate |\n|---|---|---|---|---|---|---|")
        for name, s in a["per_metric"].items():
            L.append(f"| {name} | {config['metrics'].get(name, {}).get('threshold', '')} | {s['n_scored']} | {s['n_skipped']} | {s['n_errored']} | {_fmt(s['mean_score'])} | {_fmt(s['pass_rate'])} |")
        L.append("\n### Route confusion\n")
        L.append("| Behaviour (expected route) -> actual | Count |\n|---|---|")
        for k, v in a["route_confusion"].items():
            L.append(f"| {k} | {v} |")
        L.append("\n### Pass rate by slice (capability / difficulty / behaviour)\n")
        L.append("| Slice | Passed | Total | Rate |\n|---|---|---|---|")
        for k, v in a["slices"].items():
            L.append(f"| {k} | {v['passed']} | {v['total']} | {v['rate']:.2f} |")
        L.append("\n### Per-turn rows\n")
        names = sorted({m for r in agent_rows for m in r["metrics"]})
        L.append("| Turn | Behaviour | Expected | Actual | Recall | Pass | " + " | ".join(names) + " |")
        L.append("|" + "---|" * (6 + len(names)))
        for r in agent_rows:
            cells = []
            for n in names:
                m = r["metrics"].get(n)
                cells.append("-" if m is None else "skip" if m.get("skipped") else "ERR" if m.get("score") is None
                             else f"{m['score']:.2f}{'' if m.get('passed') else ' F'}")
            L.append(f"| {r['turn_id']} | {r['behaviour']} | {r['expected_route']} | {r['actual_route']} | "
                     f"{_fmt(r['retrieval']['ref_recall'])} | {'yes' if r['passed'] else 'NO'} | " + " | ".join(cells) + " |")
        L.append("\nFull rows (judge reasons, retrieved-chunk previews, agent search queries) are in `per_case.json` / `per_case.csv`.\n")

    L.append("## How to read this honestly\n")
    L.append("- The deployed system is an incident-driven agent whose prompt allows `suggestAnswer` only for a concrete resolution procedure; many dataset questions are definitions, policies or table lookups. Over-refusal on those is a **finding about the product's scope**, not a harness fault; slice by `requires` (e.g. `procedure`) to see the comparable subset.")
    L.append("- No conversation memory or query rewriting exists, so multi-turn `coreference`/`ellipsis` turns are evaluated in `standalone` mode by default. Conversational metrics (ConversationalGEval, RoleAdherence) are out of scope.")
    L.append("- `clarify` has no tool in this architecture; the only non-answer outcome is `requestHR`.")
    L.append("- Retrieval has no score threshold, so refusal depends on the LLM. Judge scores are LLM-based and indicative; read the reasons for every FAIL. Each turn ran once (non-deterministic).")
    L.append("- Section ids are inferred from chunk text because ingested chunks are labelled `page_N_<type>`; `must_not_retrieve` checks are heuristic and ids that cannot be inferred are listed per turn.")
    L.append("- Dataset note `INC-TIME-01` (conflicting 16:24 vs 09:41 approval time, turn S10-T3) is unresolved in the corpus; treat that turn's outcome accordingly.")
    return "\n".join(L) + "\n"


def write_json(obj: Any, path: Path) -> None:
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
