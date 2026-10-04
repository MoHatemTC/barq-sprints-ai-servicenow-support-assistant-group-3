from __future__ import annotations

from threading import Lock
from typing import Any, NotRequired

from langchain_core.messages import SystemMessage
from langgraph.types import Command

from langchain.agents.middleware import AgentMiddleware, AgentState, hook_config

_TERMINAL_TOOL_NAMES = {"suggestAnswer", "requestHR"}


def _tool_name(tool: Any) -> str | None:
    if isinstance(tool, dict):
        name = tool.get("name")
    else:
        name = getattr(tool, "name", None)
    return name if isinstance(name, str) else None


class S3AgentState(AgentState):
    """State used by the S3.4 execution guard."""

    s3_iterations: NotRequired[int]
    s3_terminal_called: NotRequired[bool]
    s3_budget_exhausted: NotRequired[bool]


class ExecutionGuardMiddleware(AgentMiddleware):
    """Enforce the S3.4 agent execution boundary."""

    def __init__(self, max_iterations: int = 5, max_searches: int = 2):
        super().__init__()

        if max_iterations < 1:
            raise ValueError("max_iterations must be at least 1")
        if max_searches < 1:
            raise ValueError("max_searches must be at least 1")

        self.max_iterations = max_iterations
        self.max_searches = max_searches
        self._search_count = 0
        self._search_lock = Lock()
        
    @hook_config(can_jump_to=["end"])
    def before_agent(
        self,
        state: Any,
        runtime: Any,
    ) -> dict[str, Any] | None:
        with self._search_lock:
            self._search_count = 0
        return {
            "s3_iterations": 0,
            "s3_terminal_called": False,
        }

    @hook_config(can_jump_to=["end"])
    def before_model(
    self,
    state: Any,
    runtime: Any,
) -> dict[str, Any] | None:
     if state.get("s3_terminal_called", False):
        return {"jump_to": "end"}

     iterations = state.get("s3_iterations", 0) + 1

     if iterations > self.max_iterations:
            return {
            "s3_budget_exhausted": True,
            "jump_to": "end",
        }

     return {
        "s3_iterations": iterations,
    }

    def wrap_model_call(self, request, handler):
        with self._search_lock:
            reached_limit = self._search_count >= self.max_searches

        if not reached_limit:
            return handler(request)

        terminal_tools = [
            tool
            for tool in request.tools
            if _tool_name(tool) in _TERMINAL_TOOL_NAMES
        ]
        if not terminal_tools:
            raise RuntimeError(
                "No terminal agent tools are available after knowledge retrieval"
            )

        system_text = (
            request.system_message.text
            if request.system_message is not None
            else ""
        )
        system_message = SystemMessage(
            content=(
                f"{system_text}\n\n"
                f"Knowledge retrieval limit reached ({self.max_searches} searches performed). "
                "Do not search again. "
                "Use the retrieved evidence already in the conversation and "
                "call exactly one terminal tool now: suggestAnswer if it "
                "supports a safe, grounded procedure, otherwise requestHR."
            )
        )
        return handler(
            request.override(
                tools=terminal_tools,
                system_message=system_message,
            )
        )

    def wrap_tool_call(self, request, handler):
        tool_name = request.tool_call["name"]

        if tool_name == "searchKB":
            with self._search_lock:
                if self._search_count >= self.max_searches:
                    raise RuntimeError(
                        f"searchKB may only be called at most {self.max_searches} times per incident execution"
                    )
                self._search_count += 1

        result = handler(request)

        if tool_name in {"suggestAnswer", "requestHR"}:
            return Command(
                update={
                    "s3_terminal_called": True,
                    "messages": [result],
                }
            )

        return result    
        

    def after_agent(
        self,
        state: Any,
        runtime: Any,
    ) -> dict[str, Any] | None:
        return {
            "s3_iterations": state.get("s3_iterations", 0),
            "s3_terminal_called": state.get(
                "s3_terminal_called",
                False,
            ),
        }