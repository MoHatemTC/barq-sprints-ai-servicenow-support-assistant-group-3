from __future__ import annotations

from typing import Any, NotRequired

from langgraph.types import Command

from langchain.agents.middleware import AgentMiddleware, AgentState, hook_config


class S3AgentState(AgentState):
    """State used by the S3.4 execution guard."""

    s3_iterations: NotRequired[int]
    s3_terminal_called: NotRequired[bool]
    s3_budget_exhausted: NotRequired[bool]


class ExecutionGuardMiddleware(AgentMiddleware):
    """Enforce the S3.4 agent execution boundary."""

    def __init__(self, max_iterations: int = 5):
        super().__init__()

        if max_iterations < 1:
            raise ValueError("max_iterations must be at least 1")

        self.max_iterations = max_iterations
        
    @hook_config(can_jump_to=["end"])
    def before_agent(
        self,
        state: Any,
        runtime: Any,
    ) -> dict[str, Any] | None:
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
        
    def wrap_tool_call(self, request, handler):
        tool_name = request.tool_call["name"]

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