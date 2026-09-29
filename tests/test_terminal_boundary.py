from unittest.mock import patch

from barq_support.agent.agent import run_agent


class FakeTool:
    name = "requestHR"

    def __init__(self):
        self.called = False
        self.input = None

    def invoke(self, input_data):
        self.called = True
        self.input = input_data
        print("FAIL-SAFE requestHR EXECUTED")
        return {
            "status": "escalated",
            "reason": input_data["reason"],
        }


class FakeSettings:
    agent_max_iterations = 2
    llm_model = "fake"
    llm_api_key = "fake"
    llm_base_url = "http://localhost:0/v1"
    langfuse_public_key = "fake"
    langfuse_secret_key = "fake"
    langfuse_host = "http://localhost:0"


fake_hr_tool = FakeTool()


def fake_build_tools(servicenow, incident_sys_id, qdrant_client):
    repeatable_tools = []
    terminal_tools = [fake_hr_tool]
    return repeatable_tools, terminal_tools


def fake_build_llm(settings):
    return None


def fake_build_agent(llm, tools, max_iterations):
    class FakeAgent:
        def invoke(self, input_data, **kwargs):
            print("FAKE AGENT FINISHED WITHOUT TERMINAL DECISION")
            return {
                "s3_budget_exhausted": True,
                "s3_terminal_called": False,
                "messages": [],
            }

    return FakeAgent()


with patch(
    "barq_support.agent.tools.build_tools",
    side_effect=fake_build_tools,
), patch(
    "barq_support.agent.agent.build_llm",
    side_effect=fake_build_llm,
), patch(
    "barq_support.agent.agent.build_agent",
    side_effect=fake_build_agent,
):
    result = run_agent(
        settings=FakeSettings(),
        incident={
            "number": "INC001",
            "sys_id": "test-sys-id",
            "short_description": "Test incident",
            "description": "Test description",
            "category": "software",
        },
        servicenow=object(),
        qdrant_client=object(),
    )

print("Agent result:")
print(result)
print("Fail-safe called:", fake_hr_tool.called)
print("Fail-safe input:", fake_hr_tool.input)