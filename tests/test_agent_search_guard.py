from dataclasses import dataclass, replace
from types import SimpleNamespace

import pytest

from barq_support.agent.middleware import ExecutionGuardMiddleware


@dataclass
class FakeTool:
    name: str


@dataclass
class FakeRequest:
    tools: list[FakeTool]
    system_message: object | None = None

    def override(self, **overrides):
        return replace(self, **overrides)


def test_search_removes_nonterminal_tools_from_followup_model_call():
    middleware = ExecutionGuardMiddleware()
    middleware.before_agent({}, None)
    tools = [
        FakeTool("searchKB"),
        FakeTool("addWorkNote"),
        FakeTool("suggestAnswer"),
        {"name": "requestHR", "description": "Escalate for review"},
    ]
    request = FakeRequest(tools=tools)

    first_request = middleware.wrap_model_call(request, lambda value: value)
    assert first_request.tools == tools

    middleware.wrap_tool_call(
        SimpleNamespace(tool_call={"name": "searchKB"}),
        lambda _: [{"article_id": "KB001"}],
    )
    followup_request = middleware.wrap_model_call(
        request,
        lambda value: value,
    )

    assert [
        tool.name if isinstance(tool, FakeTool) else tool["name"]
        for tool in followup_request.tools
    ] == [
        "suggestAnswer",
        "requestHR",
    ]
    assert "Do not search again" in followup_request.system_message.text


def test_repeated_search_is_rejected():
    middleware = ExecutionGuardMiddleware()
    middleware.before_agent({}, None)
    request = SimpleNamespace(tool_call={"name": "searchKB"})
    handler = lambda _: ["retrieved results"]

    assert middleware.wrap_tool_call(request, handler) == ["retrieved results"]

    with pytest.raises(RuntimeError, match="only be called once"):
        middleware.wrap_tool_call(request, handler)


def test_search_flag_resets_for_each_agent_run():
    middleware = ExecutionGuardMiddleware()
    middleware.before_agent({}, None)
    middleware.wrap_tool_call(
        SimpleNamespace(tool_call={"name": "searchKB"}),
        lambda _: ["retrieved results"],
    )

    middleware.before_agent({}, None)

    request = SimpleNamespace(tool_call={"name": "searchKB"})
    assert middleware.wrap_tool_call(request, lambda _: ["new results"]) == [
        "new results"
    ]
