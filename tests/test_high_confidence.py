from unittest.mock import patch

from barq_support.agent.agent import run_agent


class FakeSettings:
    agent_max_iterations = 5
    llm_model = "fake"
    gemini_api_key = "fake"


class FakeServiceNow:
    def suggest_answer(self, sys_id, response, confidence):
        print("SERVICENOW WRITEBACK")
        print("PATCH /api/now/table/incident/" + sys_id)
        print("ai_status=suggested")
        print("ai_suggested_response=" + response)
        print("ai_confidence=" + str(confidence))
        print("human_review_required=True")
        print("ai_processed=True")

        return {
            "status": "suggested",
            "sys_id": sys_id,
        }

    def add_work_note(self, sys_id, note):
        print("WORK NOTE:", note)
        return {"status": "ok"}


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

        return [
            {
                "score": 0.92,
                "article_id": "KB0012345",
                "section": "Password Reset",
                "chunk_index": 0,
                "text": (
                    "To reset the password, open the password reset portal "
                    "and follow the password reset procedure."
                ),
            }
        ]

    def suggest_answer(procedure, sources, confidence):
        print("TOOL CALL: suggestAnswer")
        print("Procedure:", procedure)
        print("Sources:", sources)
        print("Confidence:", confidence)

        return servicenow.suggest_answer(
            sys_id=incident_sys_id,
            response=procedure,
            confidence=confidence,
        )

    search_tool = FakeTool("searchKB", search_kb)
    suggest_tool = FakeTool("suggestAnswer", suggest_answer)

    return [search_tool], [suggest_tool]


def fake_build_llm(settings):
    return None


def fake_build_agent(llm, tools, max_iterations):

    class FakeAgent:

        def invoke(self, input_data):
            print("AGENT STARTED")

            search_tool = next(
                tool for tool in tools
                if tool.name == "searchKB"
            )

            suggest_tool = next(
                tool for tool in tools
                if tool.name == "suggestAnswer"
            )

            evidence = search_tool.invoke(
                {
                    "query": "password reset problem"
                }
            )

            print("Retrieved evidence:", evidence)

            result = suggest_tool.invoke(
                {
                    "procedure": (
                        "Follow the password reset procedure "
                        "described in KB0012345."
                    ),
                    "sources": ["KB0012345#chunk-0"],
                    "confidence": 0.92,
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
            "number": "INC001",
            "sys_id": "test-sys-id",
            "short_description": "Unable to reset password",
            "description": "User cannot reset their password.",
            "category": "software",
        },
        servicenow=FakeServiceNow(),
        qdrant_client=FakeQdrant(),
    )

print("\nFINAL RESULT:")
print(result)