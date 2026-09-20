"""LangChain agent executor + the public ``generate_recommendation`` function.

Flow
----
1. Normalise retrieved chunks.  No usable chunk  -> deterministic clean decline (LLM not called).
2. Build the LLM from environment settings (live endpoint) and the scoped, read-only tools.
3. Run a tool-calling ``AgentExecutor`` whose prompt = strict system prompt +
   [knowledge block] + [untrusted incident block].
4. Validate the output deterministically (fail-closed) and return an ``AgentResult``.

LangChain imports are lazy so pure-Python parts of the package stay importable/testable
without the framework installed.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Mapping

from .settings import Settings
from .formatting import format_incident_block, format_knowledge_block
from .models import AgentResult, KnowledgeChunk, normalize_chunks
from .prompts import DECLINE_TEXT
from .validation import validate_output

logger = logging.getLogger(__name__)

DEFAULT_MAX_ITERATIONS = 5


def build_llm(settings: Settings):
    """Create the chat model for a live, OpenAI-compatible endpoint from env-based settings."""
    from langchain_openai import ChatOpenAI

    kwargs: dict[str, Any] = {
        "model": settings.model,
        "api_key": settings.api_key,
        "timeout": settings.timeout_seconds,
        "max_retries": settings.max_retries,
    }
    if settings.base_url:
        kwargs["base_url"] = settings.base_url
    if settings.temperature is not None:
        kwargs["temperature"] = settings.temperature
    return ChatOpenAI(**kwargs)


def build_agent_executor(llm, tools, max_iterations: int = DEFAULT_MAX_ITERATIONS):
    """Assemble the LangChain tool-calling agent executor (the reasoning loop)."""
    try:  # LangChain 0.3.x
        from langchain.agents import AgentExecutor, create_tool_calling_agent
    except ImportError:  # LangChain 1.x moved the classic executor
        from langchain_classic.agents import AgentExecutor, create_tool_calling_agent

    from .prompts import build_prompt

    agent = create_tool_calling_agent(llm, tools, build_prompt())
    return AgentExecutor(
        agent=agent,
        tools=tools,
        max_iterations=max_iterations,  # hard cap on the loop
        early_stopping_method="force",  # on the cap, return a stop message -> validator declines
        handle_parsing_errors=True,
        return_intermediate_steps=True,
        verbose=False,
    )


def _coerce_text(output: Any) -> str:
    """Some providers return a list of content blocks instead of a string."""
    if isinstance(output, str):
        return output
    if isinstance(output, list):
        return "".join(
            part if isinstance(part, str) else str(part.get("text", "")) for part in output
        )
    return str(output or "")


def generate_recommendation(
    incident: Mapping[str, Any],
    retrieved_chunks: Iterable[Mapping[str, Any] | KnowledgeChunk] | None,
    *,
    llm=None,
    settings: Settings | None = None,
    short_circuit_on_empty: bool = True,
) -> AgentResult:
    """Produce a grounded, cited resolution *recommendation* - or a clean decline.

    Args:
        incident: incident data (see ``formatting.INCIDENT_FIELDS``). Treated as untrusted.
        retrieved_chunks: retrieval output; dicts with ``article_number``, ``title``,
            ``content`` (optional ``chunk_id``, ``score``) or ``KnowledgeChunk`` objects.
        llm: optional pre-built chat model (tests / custom endpoints). Default: built from env.
        settings: optional settings; default ``Settings.from_env()``.
        short_circuit_on_empty: if True (default) an empty chunk list declines WITHOUT calling
            the LLM. Set False to let the *prompt itself* handle the empty case.

    Raises:
        ConfigError: required environment variables are missing.
        Exception: network / auth errors from the LLM endpoint propagate, so callers can
            tell an outage apart from a genuine decline.
    """
    chunks = normalize_chunks(retrieved_chunks)

    if not chunks and short_circuit_on_empty:
        return AgentResult(
            status="DECLINED",
            text=DECLINE_TEXT,
            decline_reason="no_knowledge_chunks",
            llm_called=False,
        )

    if llm is None:
        settings = settings or Settings.from_env()
        llm = build_llm(settings)
    max_iterations = settings.agent_max_iterations if settings else DEFAULT_MAX_ITERATIONS

    from .scoped_tools import build_tools  # lazy: needs langchain_core

    tools = build_tools(chunks)
    executor = build_agent_executor(llm, tools, max_iterations)

    result = executor.invoke(
        {
            # Order in the rendered prompt: system rules -> knowledge -> untrusted incident.
            "knowledge_block": format_knowledge_block(chunks),
            "incident_block": format_incident_block(incident),
        }
    )

    tool_calls = [
        {"tool": action.tool, "input": action.tool_input}
        for action, _observation in result.get("intermediate_steps", [])
    ]
    raw_text = _coerce_text(result.get("output"))
    logger.debug("agent finished; %d tool call(s)", len(tool_calls))

    return validate_output(raw_text, {c.article_number for c in chunks}, tool_calls)
