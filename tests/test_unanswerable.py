from unittest.mock import patch

from barq_support.agent.agent import run_agent


class FakeSettings:
    agent_max_iterations = 5
    llm_model = "fake"
    llm_api_key = "fake"
    llm_base_url = "http://localhost:0/v1"
    langfuse_public_key = "fake"
    langfuse_secret_key = "fake"
    langfuse_host = "http://localhost:0"


class FakeServiceNow:
    def request_hr(self, sys_id, reason):
        print("SERVICENOW ESCALATION")
        print("PATCH /api/now/table/incident/" + sys_id)
        print("ai_status=escalated")
        print("human_review_required=True")
        print("ai_processed=True")
        print("work_notes=AI escalation: " + reason)

        return {
            "status": "escalated",
            "sys_id": sys_id,
        }


class FakeQdrant:
    pass


class FakeTool:
    def __init__(self, name, func):
        self.name = name
        self.func = func

    def invoke(self, input_data):
        return self.func(**input_data)


def fake_build_tools(servicenow, incident_sys_id, qdrant_client):

    def search_kb(query):
        print("TOOL CALL: searchKB")
        print("Query:", query)

        # No relevant KB evidence
        return []

    def request_hr(reason):
        print("TOOL CALL: requestHR")
        print("Reason:", reason)

        return servicenow.request_hr(
            sys_id=incident_sys_id,
            reason=reason,
        )

    search_tool = FakeTool("searchKB", search_kb)
    hr_tool = FakeTool("requestHR", request_hr)

    return [search_tool], [hr_tool]


def fake_build_llm(settings):
    return None


def fake_build_agent(llm, tools, max_iterations):

    class FakeAgent:

        def invoke(self, input_data, **kwargs):
            print("AGENT STARTED")

            search_tool = next(
                tool for tool in tools
                if tool.name == "searchKB"
            )

            hr_tool = next(
                tool for tool in tools
                if tool.name == "requestHR"
            )

            evidence = search_tool.invoke(
                {
                    "query": "unknown proprietary system failure"
                }
            )

            print("Retrieved evidence:", evidence)

            result = hr_tool.invoke(
                {
                    "reason": (
                        "No relevant knowledge-base evidence was found "
                        "to support a safe grounded recommendation."
                    )
                }
            )

            print("TERMINAL TOOL COMPLETED")

            return {
                "s3_iterations": 2,
                "s3_terminal_called": True,
                "messages": [result],
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
            "number": "INC002",
            "sys_id": "test-hr-sys-id",
            "short_description": "Unknown proprietary system failure",
            "description": "The system is failing with an undocumented error.",
            "category": "software",
        },
        servicenow=FakeServiceNow(),
        qdrant_client=FakeQdrant(),
    )

print("\nFINAL RESULT:")
print(result)