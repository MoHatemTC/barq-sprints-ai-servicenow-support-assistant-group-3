"""Offline unit tests for evaluation/eval_utils.py (no network, no deepeval, no credentials).

Run:  python -m unittest tests.test_eval_utils -v      (or: uv run pytest tests/test_eval_utils.py)
"""

import copy
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "evaluation"
sys.path.insert(0, str(EVAL))

import eval_utils as U  # noqa: E402

DATASET = EVAL / "barq_rag_eval_dataset.json"


def _load_adapters():
    """Mentor's adapters.py reads the dataset from the CWD at import time."""
    cwd = os.getcwd()
    os.chdir(EVAL)
    try:
        import adapters
        return adapters
    finally:
        os.chdir(cwd)


def _row(tid, behaviour, expected, actual, requires=("single_hop",), difficulty="easy", metrics=None,
         clean=True, recall=1.0, error=None):
    r = {
        "turn_id": tid, "session_id": tid.split("-")[0], "behaviour": behaviour, "difficulty": difficulty,
        "requires": list(requires), "input_mode": "standalone", "expected_route": expected,
        "actual_route": actual, "route_correct": expected == actual, "agent_error": error,
        "actual_output": "out", "metrics": metrics or {}, "top_retrieval_score": 0.5,
        "n_chunks_retrieved": 5, "n_searches": 1, "iterations": 2, "latency_s": 1.0,
        "retrieval": {"ref_recall": recall, "ref_precision": 0.4, "hit_any": True, "hit_all": True,
                      "forbidden_retrieved": [] if clean else ["2.1"], "forbidden_uninferable": [],
                      "expected_sections_found": [], "clean": clean},
    }
    r["passed"] = U.turn_passed(r)
    return r


class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.data = U.load_dataset(DATASET)
        self.turns = U.all_turns(self.data)

    def test_mentor_dataset_loads_and_matches_declared_counts(self):
        c = self.data["dataset"]["counts"]
        self.assertEqual(len(self.data["sessions"]), c["sessions"])
        self.assertEqual(len(self.turns), c["turns"])
        by = {b: sum(t["expected_behaviour"] == b for t in self.turns) for b in U.BEHAVIOURS}
        self.assertEqual(by, c["by_behaviour"])
        self.assertGreaterEqual(by["refuse"], 10)  # negative cases are mandatory for S4.2

    def test_routes(self):
        self.assertEqual(U.expected_route({"expected_behaviour": "answer"}), "suggestAnswer")
        self.assertEqual(U.expected_route({"expected_behaviour": "refuse"}), "requestHR")
        self.assertEqual(U.expected_route({"expected_behaviour": "clarify"}), "requestHR")

    def test_rejects_duplicate_ids_and_bad_behaviour(self):
        bad = copy.deepcopy(self.data)
        bad["sessions"][0]["turns"][1]["turn_id"] = bad["sessions"][0]["turns"][0]["turn_id"]
        import json
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "d.json"
            p.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaises(U.DatasetError):
                U.load_dataset(p)
        bad = copy.deepcopy(self.data)
        bad["sessions"][0]["turns"][0]["expected_behaviour"] = "maybe"
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "d.json"
            p.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaises(U.DatasetError):
                U.load_dataset(p)

    def test_select_turns_filters(self):
        self.assertEqual(len(U.select_turns(self.turns, sessions=["S01"])), 5)
        self.assertEqual(len(U.select_turns(self.turns, behaviour="clarify")), 1)
        self.assertEqual(len(U.select_turns(self.turns, ids=["S01-T1", "S15-T2"])), 2)
        self.assertEqual(len(U.select_turns(self.turns, limit=3)), 3)
        self.assertTrue(all("image_ocr" in t["requires"] for t in U.select_turns(self.turns, capability="image_ocr")))
        with self.assertRaises(U.DatasetError):
            U.select_turns(self.turns, ids=["NOPE"])

    def test_incident_wrapping_and_input_modes(self):
        t = next(t for t in self.turns if t["input"] != t["standalone_input"])
        self.assertEqual(U.query_for(t, "standalone"), t["standalone_input"])
        self.assertEqual(U.query_for(t, "input"), t["input"])
        inc = U.build_incident(t, "standalone")
        self.assertEqual(set(inc), {"number", "sys_id", "short_description", "description", "category"})
        self.assertEqual(inc["category"], "inquiry")
        self.assertLessEqual(len(inc["short_description"]), 160)

    def test_metric_gating(self):
        t = {t["turn_id"]: t for t in self.turns}
        self.assertTrue(U.needs_safety_check(t["S15-T1"]))
        self.assertFalse(U.needs_safety_check(t["S01-T1"]))
        self.assertFalse(U.needs_citation_check(t["S01-T5"]))  # refuse turn


class RetrievalScoringTests(unittest.TestCase):
    def setUp(self):
        self.data = U.load_dataset(DATASET)
        self.idx = U.build_section_index(self.data)
        self.t = next(t for t in U.all_turns(self.data) if t["turn_id"] == "S01-T1")

    def test_index_covers_all_inferable_sections(self):
        ids = {s for t in U.all_turns(self.data) for s in t["expected_sections"] + t["must_not_retrieve"] if s and s != "—"}
        self.assertEqual(ids - set(self.idx), {"header_footer_noise"})

    def test_reference_text_matches_itself(self):
        r = U.score_retrieval_chunks(self.t["reference_contexts"], self.t, self.idx)
        self.assertEqual((r["ref_recall"], r["ref_precision"], r["hit_all"]), (1.0, 1.0, True))
        self.assertIn("1.1", r["sections_inferred"])

    def test_formatted_ocr_style_chunk_still_matches(self):
        body = self.t["reference_contexts"][0].split(" — ", 1)[1]
        chunk = f"## 1.1 Purpose and audience\n\n**Note:** {body}"
        self.assertGreater(U.score_retrieval_chunks([chunk], self.t, self.idx)["ref_recall"], 0)

    def test_unrelated_text_scores_zero(self):
        r = U.score_retrieval_chunks(["The quick brown fox jumps over the lazy dog many times today"], self.t, self.idx)
        self.assertEqual((r["ref_recall"], r["ref_precision"], r["hit_any"]), (0.0, 0.0, False))

    def test_no_reference_turn_has_null_recall_and_forbidden_detection(self):
        turn = next(t for t in U.all_turns(self.data) if t["turn_id"] == "S01-T5")  # refuse, must_not 2.1/2.3
        self.assertEqual(U.score_retrieval_chunks([], turn, self.idx)["ref_recall"], None if not turn["reference_contexts"] else 0.0)
        passage_21 = self.idx["2.1"][0]
        r = U.score_retrieval_chunks([passage_21], turn, self.idx)
        self.assertIn("2.1", r["forbidden_retrieved"])
        self.assertFalse(r["clean"])


class CaptureTests(unittest.TestCase):
    def test_outcome_routes(self):
        sn = U.CapturingServiceNow()
        self.assertEqual(sn.outcome()["route"], "none")
        sn.request_hr("x", "no kb")
        self.assertEqual(sn.outcome()["route"], "requestHR")
        sn2 = U.CapturingServiceNow()
        sn2.suggest_answer("x", "do thing", 0.8)
        o = sn2.outcome()
        self.assertEqual((o["route"], o["confidence"], o["output"]), ("suggestAnswer", 0.8, "do thing"))
        sn2.request_hr("x", "also")
        self.assertTrue(sn2.outcome()["multiple_terminal_calls"])

    def test_recorder_wraps_and_dedupes(self):
        rec = U.RetrievalRecorder()
        fake = lambda q, *a, **k: [  # noqa: E731
            {"article_id": "KB1", "chunk_index": 0, "section": "S", "score": 0.4, "text": "t1"},
            {"article_id": "KB2", "chunk_index": 1, "section": "S", "score": 0.9, "text": "t2"}]
        w = rec.wrap(fake)
        w("q1"); w("q2")
        self.assertEqual(rec.queries, ["q1", "q2"])
        self.assertEqual(rec.retrieval_context(), ["t1", "t2"])
        self.assertEqual(rec.top_score(), 0.9)


class HygieneTests(unittest.TestCase):
    class _S:
        model_fields = {"llm_api_key": 1, "qdrant_api_key": 1, "servicenow_username": 1, "llm_model": 1}
        llm_api_key = "super-secret-key-123"
        qdrant_api_key = "short"
        servicenow_username = "admin-user-long"
        llm_model = "gemini/some-model"

    def test_secret_collection(self):
        vals = U.secret_values_from(self._S(), {"X_PASSWORD": "pw-value-long-1", "OTHER": "zzzzzzzzzz"})
        self.assertIn("super-secret-key-123", vals)
        self.assertIn("pw-value-long-1", vals)
        for not_secret in ("short", "zzzzzzzzzz", "gemini/some-model"):
            self.assertNotIn(not_secret, vals)

    def test_redact_and_scan(self):
        s = ["super-secret-key-123"]
        self.assertEqual(U.redact("k=super-secret-key-123", s), "k=***REDACTED***")
        self.assertEqual(U.redact_obj({"a": ["x super-secret-key-123"]}, s), {"a": ["x ***REDACTED***"]})
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "clean.txt").write_text("nothing", encoding="utf-8")
            self.assertEqual(U.scan_dir_for_secrets(Path(d), s), [])
            (Path(d) / "leak.txt").write_text("oops super-secret-key-123", encoding="utf-8")
            self.assertEqual(len(U.scan_dir_for_secrets(Path(d), s)), 1)

    def test_host_only(self):
        self.assertEqual(U.host_only("https://user:pw@gw.example.com:8443/litellm?x=1"), "https://gw.example.com")

    def test_dataset_and_code_contain_no_credential_like_strings(self):
        for p in [DATASET, EVAL / "run_eval.py", EVAL / "eval_utils.py", EVAL / "judge.py"]:
            body = p.read_text(encoding="utf-8").lower()
            for needle in ("sk-lf-", "pk-lf-", "bearer ey", "aiza"):
                self.assertNotIn(needle, body, f"{needle} in {p.name}")


class JsonExtractTests(unittest.TestCase):
    def test_variants(self):
        self.assertEqual(U.extract_json('{"a": 1}'), {"a": 1})
        self.assertEqual(U.extract_json('```json\n{"a": 2}\n```'), {"a": 2})
        self.assertEqual(U.extract_json('Sure {"a": 3} ok'), {"a": 3})
        with self.assertRaises(Exception):
            U.extract_json("no json")


class AggregateTests(unittest.TestCase):
    def setUp(self):
        ok = {"score": 0.9, "passed": True, "reason": "g"}
        bad = {"score": 0.2, "passed": False, "reason": "b"}
        skip = {"score": None, "passed": None, "reason": None, "skipped": "over-refusal"}
        err = {"score": None, "passed": None, "reason": None, "error": "boom"}
        self.rows = [
            _row("S01-T1", "answer", "suggestAnswer", "suggestAnswer", metrics={"Faithfulness": ok}),
            _row("S01-T2", "answer", "suggestAnswer", "requestHR", metrics={"Faithfulness": skip}, difficulty="hard"),
            _row("S01-T3", "answer", "suggestAnswer", "suggestAnswer", metrics={"Faithfulness": err}),
            _row("S01-T4", "refuse", "requestHR", "requestHR", requires=("unanswerable",), metrics={"RefusalQuality": ok}),
            _row("S01-T5", "refuse", "requestHR", "suggestAnswer", requires=("unanswerable",), metrics={"RefusalQuality": bad}),
            _row("S01-T6", "refuse", "requestHR", "requestHR", requires=("unanswerable",), clean=False),
            _row("S01-T7", "answer", "suggestAnswer", "none", error="Boom"),
        ]

    def test_turn_passed_rules(self):
        p = {r["turn_id"]: r["passed"] for r in self.rows}
        self.assertTrue(p["S01-T1"])
        self.assertFalse(p["S01-T2"])   # over-refusal
        self.assertTrue(p["S01-T3"])    # judge error is not a failure
        self.assertTrue(p["S01-T4"])
        self.assertFalse(p["S01-T5"])   # answered a refuse turn
        self.assertFalse(p["S01-T6"])   # forbidden section retrieved
        self.assertFalse(p["S01-T7"])   # agent error / no terminal tool

    def test_agent_aggregate(self):
        a = U.aggregate_agent(self.rows)
        self.assertEqual((a["n_answer"], a["n_negative"]), (4, 3))
        self.assertEqual(a["over_refusal_rate"], 0.25)
        self.assertAlmostEqual(a["false_answer_rate"], 0.3333, places=3)
        self.assertAlmostEqual(a["negative_turns_escalated"], 0.6667, places=3)
        self.assertEqual((a["n_agent_errors"], a["n_no_terminal_tool"], a["n_judge_errors"]), (1, 1, 1))
        f = a["per_metric"]["Faithfulness"]
        self.assertEqual((f["n_scored"], f["n_skipped"], f["n_errored"], f["n_passed"]), (1, 1, 1, 1))

    def test_slice_rates_match_mentor_adapters(self):
        mine = U.slice_rates(self.rows)
        adapters = _load_adapters()
        theirs = adapters.slice_report([{"turn_id": r["turn_id"], "passed": r["passed"]} for r in self.rows
                                        if r["turn_id"] in {t["turn_id"] for t in adapters.turns()}])
        # compare on the rows that exist in the real dataset using their real tags
        real_rows = []
        for t in adapters.turns()[:12]:
            real_rows.append({"turn_id": t["turn_id"], "requires": t["requires"], "difficulty": t["difficulty"],
                              "behaviour": t["expected_behaviour"], "passed": len(real_rows) % 3 != 0})
        self.assertEqual(U.slice_rates(real_rows),
                         adapters.slice_report([{"turn_id": r["turn_id"], "passed": r["passed"]} for r in real_rows]))
        self.assertIn("behaviour:answer", mine)
        self.assertIsInstance(theirs, dict)

    def test_retrieval_aggregate(self):
        rows = [{"turn_id": "x", "behaviour": "answer", "retrieval": {"ref_recall": 1.0, "ref_precision": 0.5, "hit_any": True, "hit_all": True, "clean": True, "forbidden_retrieved": []}},
                {"turn_id": "y", "behaviour": "answer", "retrieval": {"ref_recall": 0.0, "ref_precision": 0.0, "hit_any": False, "hit_all": False, "clean": False, "forbidden_retrieved": ["2.1"]}},
                {"turn_id": "z", "behaviour": "refuse", "retrieval": {"ref_recall": None, "ref_precision": None, "hit_any": None, "hit_all": None, "clean": True, "forbidden_retrieved": []}}]
        a = U.aggregate_retrieval(rows)
        self.assertEqual((a["n_with_reference"], a["mean_ref_recall"], a["hit_any_rate"]), (2, 0.5, 0.5))
        self.assertAlmostEqual(a["clean_rate"], 0.6667, places=3)
        self.assertEqual(a["n_with_forbidden_sections"], 1)

    def test_csv_and_markdown_render(self):
        a = U.aggregate_agent(self.rows)
        config = {"run_id": "r", "started_utc": "t", "stages": ["retrieval", "agent"], "n_turns": 7, "input_mode": "standalone",
                  "agent_model": "m", "judge_model": "j", "deepeval_version": "v", "judge_enabled": True,
                  "dataset": {"name": "n", "version": "1", "sha256": "a" * 64, "corpus_document": "doc.docx"},
                  "retrieval": {"embedding_model": "e", "embedding_dimension": 3, "top_k": 5, "collection": "c"},
                  "metrics": {"Faithfulness": {"threshold": 0.8}}}
        retr_rows = [{"turn_id": "x", "behaviour": "answer", "difficulty": "easy", "requires": ["single_hop"], "expected_sections": ["1.1"],
                      "top_score": 0.7, "retrieval": {"ref_recall": 0.0, "ref_precision": 0.0, "hit_any": False, "hit_all": False, "clean": True,
                                                      "forbidden_retrieved": [], "forbidden_uninferable": [], "expected_sections_found": []}}]
        ra = U.aggregate_retrieval(retr_rows)
        md = U.render_summary_md(config, self.rows, a, retr_rows, ra)
        for needle in ("Stage 1", "Stage 2", "WARNING", "S01-T5", "over-refusal", "INC-TIME-01", "How to read this honestly"):
            self.assertIn(needle, md)
        with tempfile.TemporaryDirectory() as d:
            p, q = Path(d) / "a.csv", Path(d) / "r.csv"
            U.write_csv(self.rows, p)
            U.write_retrieval_csv(retr_rows, q)
            self.assertEqual(len(p.read_text(encoding="utf-8-sig").splitlines()), 1 + len(self.rows))
            self.assertEqual(len(q.read_text(encoding="utf-8-sig").splitlines()), 2)


if __name__ == "__main__":
    unittest.main()
