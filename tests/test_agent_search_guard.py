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


def test_first_search_allows_tools_and_second_search_enforces_terminal():
    middleware = ExecutionGuardMiddleware(max_searches=2)
    middleware.before_agent({}, None)
    tools = [
        FakeTool("searchKB"),
        FakeTool("addWorkNote"),
        FakeTool("suggestAnswer"),
        {"name": "requestHR", "description": "Escalate for review"},
    ]
    request = FakeRequest(tools=tools)

    # Initial model call: all tools available
    first_request = middleware.wrap_model_call(request, lambda value: value)
    assert first_request.tools == tools

    # 1st search performed
    middleware.wrap_tool_call(
        SimpleNamespace(tool_call={"name": "searchKB"}),
        lambda _: [{"article_id": "KB001"}],
    )
    # After 1st search: still within limit (count=1 < 2), so tools remain available
    after_first_search_request = middleware.wrap_model_call(
        request,
        lambda value: value,
    )
    assert after_first_search_request.tools == tools

    # 2nd search performed
    middleware.wrap_tool_call(
        SimpleNamespace(tool_call={"name": "searchKB"}),
        lambda _: [{"article_id": "KB002"}],
    )
    # After 2nd search: limit reached (count=2 >= 2), only terminal tools remain
    after_second_search_request = middleware.wrap_model_call(
        request,
        lambda value: value,
    )

    assert [
        tool.name if isinstance(tool, FakeTool) else tool["name"]
        for tool in after_second_search_request.tools
    ] == [
        "suggestAnswer",
        "requestHR",
    ]
    assert "Knowledge retrieval limit reached (2 searches performed)" in after_second_search_request.system_message.text
    assert "Do not search again" in after_second_search_request.system_message.text


def test_third_search_is_rejected():
    middleware = ExecutionGuardMiddleware(max_searches=2)
    middleware.before_agent({}, None)
    request = SimpleNamespace(tool_call={"name": "searchKB"})
    handler = lambda _: ["retrieved results"]

    # 1st search succeeds
    assert middleware.wrap_tool_call(request, handler) == ["retrieved results"]
    # 2nd search succeeds
    assert middleware.wrap_tool_call(request, handler) == ["retrieved results"]

    # 3rd search raises RuntimeError
    with pytest.raises(RuntimeError, match="at most 2 times"):
        middleware.wrap_tool_call(request, handler)


def test_search_flag_resets_for_each_agent_run():
    middleware = ExecutionGuardMiddleware(max_searches=2)
    middleware.before_agent({}, None)
    request = SimpleNamespace(tool_call={"name": "searchKB"})
    handler = lambda _: ["retrieved results"]

    middleware.wrap_tool_call(request, handler)
    middleware.wrap_tool_call(request, handler)

    # Next agent execution
    middleware.before_agent({}, None)

    assert middleware.wrap_tool_call(request, lambda _: ["new results 1"]) == [
        "new results 1"
    ]
    assert middleware.wrap_tool_call(request, lambda _: ["new results 2"]) == [
        "new results 2"
    ]
