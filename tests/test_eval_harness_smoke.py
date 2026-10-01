"""Offline end-to-end smoke test of evaluation/run_eval.py main() with stubbed agent/Qdrant/settings.

Proves orchestration, file outputs, route logic and credential redaction without network, deepeval or
credentials. It does NOT exercise DeepEval itself (use --no-judge path only).

Run:  python -m unittest tests.test_eval_harness_smoke -v
"""

import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "evaluation"
sys.path.insert(0, str(EVAL))
import eval_utils as U  # noqa: E402

FAKE_KEY = "FAKE-LLM-KEY-0123456789"


class FakeSettings:
    model_fields = {"llm_api_key": 1, "qdrant_api_key": 1, "llm_model": 1}
    llm_api_key = FAKE_KEY
    llm_model = "fake-model"
    llm_base_url = "https://gateway.example.test/litellm"
    qdrant_url = "https://qdrant.example.test"
    qdrant_api_key = "FAKE-QDRANT-KEY-9876543210"
    agent_max_iterations = 5
    langfuse_public_key = langfuse_secret_key = ""
    langfuse_host = ""


def _install_stubs(dataset):
    turns = {t["standalone_input"]: t for t in U.all_turns(dataset)}
    mods = {}

    def mod(name, **attrs):
        m = types.ModuleType(name)
        m.__dict__.update(attrs)
        mods[name] = m
        return m

    def search_kb(query, client, top_k=5, category=None):
        t = turns[query]
        # perfect retrieval for answerable turns, a forbidden-section chunk for turn S01-T5
        texts = list(t["reference_contexts"]) or ["unrelated filler text that matches nothing in the manual at all"]
        if t["turn_id"] == "S01-T5":
            texts = [dataset_idx["2.1"][0]]
        return [{"article_id": "DOC", "chunk_index": i, "section": f"page_{i}_text", "score": 0.9 - i * 0.01, "text": x}
                for i, x in enumerate(texts)]

    dataset_idx = U.build_section_index(dataset)
    tools = mod("barq_support.agent.tools", search_kb=search_kb)

    def run_agent(settings, incident, servicenow, qdrant_client):
        t = turns[incident["description"]]
        tools.search_kb(incident["description"], qdrant_client)  # goes through the recorder wrapper
        if t["expected_behaviour"] == "answer" and t["turn_id"] != "S01-T2":
            servicenow.suggest_answer(incident["sys_id"], f"Procedure. leaked={FAKE_KEY}", 0.8)
        elif t["turn_id"] == "S01-T2":
            servicenow.request_hr(incident["sys_id"], "over-refusal on purpose")
        else:
            servicenow.request_hr(incident["sys_id"], "KB lacks this")
        return {"s3_iterations": 2, "s3_terminal_called": True}

    mod("barq_support")
    mod("barq_support.settings", get_settings=lambda: FakeSettings())
    mod("barq_support.retrieval")
    mod("barq_support.retrieval.retriever", COLLECTION_NAME="kb_articles", DEFAULT_TOP_K=5,
        get_qdrant_client=lambda url, key: object(), search_kb=search_kb)
    mod("barq_support.retrieval.embedder", EMBEDDING_MODEL="fake-embed", EMBEDDING_DIMENSION=3)
    mod("barq_support.agent")
    mod("barq_support.agent.agent", run_agent=run_agent)
    mods["barq_support.retrieval"].retriever = mods["barq_support.retrieval.retriever"]
    mods["barq_support.retrieval"].embedder = mods["barq_support.retrieval.embedder"]
    mods["barq_support.agent"].tools = tools
    mod("qdrant_client", QdrantClient=lambda **kw: object())
    mod("dotenv", load_dotenv=lambda *a, **k: None)
    return mods


class HarnessSmokeTest(unittest.TestCase):
    def test_full_run_without_judge(self):
        data = U.load_dataset(EVAL / "barq_rag_eval_dataset.json")
        spec = importlib.util.spec_from_file_location("run_eval_under_test", EVAL / "run_eval.py")
        run_eval = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(run_eval)

        with tempfile.TemporaryDirectory() as d, mock.patch.dict(sys.modules, _install_stubs(data)), \
                mock.patch.dict("os.environ", {"GEMINI_API_KEY": "FAKE-GEMINI-KEY-5555555555"}):
            out = Path(d) / "out"
            argv = ["run_eval.py", "--stage", "all", "--no-judge", "--sessions", "S01", "--out", str(out)]
            with mock.patch.object(sys, "argv", argv):
                code = run_eval.main()
            self.assertEqual(code, 0)

            for name in ("config.json", "aggregate.json", "per_case.json", "per_case.csv",
                         "retrieval_stage.json", "retrieval_stage.csv", "summary.md"):
                self.assertTrue((out / name).exists(), name)

            rows = {r["turn_id"]: r for r in json.loads((out / "per_case.json").read_text(encoding="utf-8"))}
            self.assertEqual(len(rows), 5)
            self.assertTrue(rows["S01-T1"]["route_correct"] and rows["S01-T1"]["passed"])
            self.assertFalse(rows["S01-T2"]["route_correct"])           # deliberate over-refusal
            self.assertEqual(rows["S01-T2"]["actual_route"], "requestHR")
            self.assertTrue(rows["S01-T5"]["route_correct"])             # refuse -> requestHR
            self.assertFalse(rows["S01-T5"]["retrieval"]["clean"])       # forbidden 2.1 retrieved
            self.assertFalse(rows["S01-T5"]["passed"])
            self.assertEqual(rows["S01-T1"]["metrics"], {})              # --no-judge

            agg = json.loads((out / "aggregate.json").read_text(encoding="utf-8"))
            self.assertEqual(agg["agent_stage"]["over_refusal_rate"], 0.25)
            self.assertEqual(agg["retrieval_stage"]["n_turns"], 5)

            cfg = json.loads((out / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(cfg["llm_gateway_host"], "https://gateway.example.test")
            self.assertFalse(cfg["judge_enabled"])

            # credential hygiene: the fake key the stub agent "leaked" must be redacted everywhere
            blob = "".join(p.read_text(encoding="utf-8", errors="ignore") for p in out.rglob("*") if p.is_file())
            self.assertNotIn(FAKE_KEY, blob)
            self.assertNotIn("FAKE-QDRANT-KEY-9876543210", blob)
            self.assertIn("***REDACTED***", blob)


if __name__ == "__main__":
    unittest.main()
