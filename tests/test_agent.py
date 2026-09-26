"""Agent-level behaviour. Runs offline"""

import importlib.util
import os
import re
import unittest
from pathlib import Path
from unittest import mock

from barq_support.agent.agent import generate_recommendation
from barq_support.agent.settings import ConfigError, Settings
from barq_support.agent.mock_data import INCIDENT_SAP, INCIDENT_VPN, KB_VPN_809
from barq_support.agent.prompts import DECLINE_TEXT

HAS_LANGCHAIN = all(
    importlib.util.find_spec(m) for m in ("langchain", "langchain_core", "langchain_openai")
)
ROOT = Path(__file__).resolve().parents[1]


class CleanDeclineWithoutChunks(unittest.TestCase):
    def test_no_chunks_declines_without_calling_llm_or_needing_credentials(self):
        with mock.patch.dict(os.environ, {}, clear=True):  # no env at all
            r = generate_recommendation(INCIDENT_SAP, [])
        self.assertEqual(r.status, "DECLINED")
        self.assertFalse(r.llm_called)
        self.assertEqual(r.decline_reason, "no_knowledge_chunks")
        self.assertEqual(r.text, DECLINE_TEXT)
        self.assertNotRegex(r.text, r"(?m)^\s*\d+[.)]")  # no invented steps

    def test_blank_chunks_count_as_no_chunks(self):
        r = generate_recommendation(
            INCIDENT_SAP, [{"article_number": "KB1", "title": "t", "content": "   "}]
        )
        self.assertFalse(r.llm_called)
        self.assertEqual(r.status, "DECLINED")


class ConfigFromEnvironment(unittest.TestCase):
    def test_missing_variables_raise_and_never_echo_values(self):
        with mock.patch.dict(os.environ, {"LLM_MODEL": "m"}, clear=True), mock.patch(
            "dotenv.load_dotenv", lambda *a, **k: None
        ):
            with self.assertRaises(ConfigError) as ctx:
                Settings.from_env()
        self.assertIn("LLM_API_KEY", str(ctx.exception))

    def test_reads_everything_from_env_and_hides_key_in_repr(self):
        env = {
            "LLM_API_KEY": "secret-123",
            "LLM_MODEL": "some-model",
            "LLM_BASE_URL": "https://llm.example.internal/v1",
            "LLM_TEMPERATURE": "none",
        }
        with mock.patch.dict(os.environ, env, clear=True), mock.patch(
            "dotenv.load_dotenv", lambda *a, **k: None
        ):
            s = Settings.from_env()
        self.assertEqual(s.base_url, "https://llm.example.internal/v1")
        self.assertIsNone(s.temperature)
        self.assertNotIn("secret-123", repr(s))

    def test_no_hardcoded_secrets_or_endpoints_in_source(self):
        pattern = re.compile(r"sk-[A-Za-z0-9_-]{16,}|https?://api\.[a-z]+\.(com|ai)", re.I)
        for path in list((ROOT / "src" / "barq_support" / "agent").glob("*.py")) + list((ROOT / "scripts").glob("*.py")):
            self.assertIsNone(pattern.search(path.read_text()), f"hardcoded secret/endpoint in {path}")


@unittest.skipUnless(HAS_LANGCHAIN, "LangChain not installed")
class ExecutorLoopOffline(unittest.TestCase):
    """Drives the REAL AgentExecutor with a scripted fake model (no network)."""

    @staticmethod
    def _fake_model(responses):
        from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel

        class FakeToolModel(FakeMessagesListChatModel):
            def bind_tools(self, tools, **kwargs):
                return self

        return FakeToolModel(responses=responses)

    def test_prompt_message_order_is_system_then_knowledge_then_incident(self):
        from barq_support.agent.formatting import format_incident_block, format_knowledge_block
        from barq_support.agent.models import normalize_chunks
        from barq_support.agent.prompts import build_prompt

        msgs = build_prompt().format_messages(
            knowledge_block=format_knowledge_block(normalize_chunks([KB_VPN_809])),
            incident_block=format_incident_block(INCIDENT_VPN),
            agent_scratchpad=[],
        )
        self.assertEqual([m.type for m in msgs], ["system", "human"])
        human = msgs[1].content
        self.assertLess(human.index("<knowledge_base>"), human.index("<incident_data"))

    def test_tool_loop_then_grounded_answer(self):
        from langchain_core.messages import AIMessage

        final = (
            "STATUS: GROUNDED\nRecommended resolution procedure (draft for human support agent review):\n"
            "1. Test on a mobile hotspot. [KB0010234]\nSources:\n- KB0010234 - Resolving VPN Error 809 on Windows"
        )
        llm = self._fake_model(
            [
                AIMessage(content="", tool_calls=[{"name": "get_kb_article", "args": {"article_number": "KB0010234"}, "id": "c1"}]),
                AIMessage(content=final),
            ]
        )
        r = generate_recommendation(INCIDENT_VPN, [KB_VPN_809], llm=llm)
        self.assertEqual(r.status, "GROUNDED")
        self.assertEqual(r.cited_articles, ["KB0010234"])
        self.assertEqual([c["tool"] for c in r.tool_calls], ["get_kb_article"])

    def test_model_that_invents_a_citation_is_declined(self):
        from langchain_core.messages import AIMessage

        llm = self._fake_model(
            [AIMessage(content="STATUS: GROUNDED\nHeader\n1. Do a thing. [KB0099999]")]
        )
        r = generate_recommendation(INCIDENT_VPN, [KB_VPN_809], llm=llm)
        self.assertEqual(r.status, "DECLINED")

    def test_scoped_tool_refuses_unretrieved_article_and_no_mutating_tools_exist(self):
        from barq_support.agent.models import normalize_chunks
        from barq_support.agent.scoped_tools import build_tools

        tools = {t.name: t for t in build_tools(normalize_chunks([KB_VPN_809]))}
        self.assertIn("not among the retrieved", tools["get_kb_article"].invoke({"article_number": "KB0099999"}))
        self.assertEqual(len(tools), 4)
        for name in tools:
            self.assertNotRegex(name, r"resolve|close|reassign|update|assign")


if __name__ == "__main__":
    unittest.main()
