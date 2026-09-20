"""
BARQ G3 - Sprint 2 (S2.3) - Agent Tool Definitions
AI ServiceNow Support Assistant

Defines the four LangChain-compatible tools the agent can invoke. This is
strictly a definitions task: tool bodies here are mocks/stubs that return
a dummy string, with no network calls and no dependency on how the caller
passes incident context.

Deliberately NOT included in this sprint:
  * Any real ServiceNow API call. Knowledge retrieval in this pipeline is
    handled by the team's vector store (Qdrant), not ServiceNow keyword
    search — wiring that up belongs to the sprint where retrieval
    components merge, not here.
  * Any ambient state (ContextVar, globals, etc.) for the current
    incident. Keeping tool bodies pure/self-contained means a teammate
    can import and call any tool directly with no setup and no
    credentials, which matters for testing the agent loop in S2.4.

The incident is preloaded into context by the caller, so there is no
"fetch incident" tool here.

STRUCTURAL GUARANTEE — no resolve / close / reassign:
Exactly four tools are exported in AGENT_TOOLS. None of the four input
schemas has a field that could carry a resolve/close/reassign instruction
(no state, close_code, assignment_group, or assigned_to field exists
anywhere in this module) — so there is no code path, mocked or real,
through which such an action could be requested.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool


# ---------------------------------------------------------------------------
# 1. Knowledge Base Search Tool  — REPEATABLE
# ---------------------------------------------------------------------------

class KnowledgeBaseSearchInput(BaseModel):
    query: str = Field(
        ...,
        description="The search query used to look up relevant knowledge base articles.",
    )


def _knowledge_base_search(query: str) -> str:
    """Stub. Real retrieval is handled by the Qdrant vector store in a
    later sprint; this returns a placeholder so the tool contract can be
    exercised end-to-end without that dependency."""
    return f"[STUB] knowledge_base_search called with query='{query}'. No retrieval backend wired yet."


knowledge_base_search_tool = StructuredTool.from_function(
    func=_knowledge_base_search,
    name="knowledge_base_search",
    description=(
        "Searches the support knowledge base for articles relevant to the "
        "incident currently loaded in context. Use it to gather candidate "
        "solutions, troubleshooting steps, or reference material before "
        "forming an answer. This tool can be called repeatedly without "
        "ending the run — invoke it as many times as needed to refine a "
        "query or explore different angles before you commit to a final "
        "action."
    ),
    args_schema=KnowledgeBaseSearchInput,
)


# ---------------------------------------------------------------------------
# 2. Internal Work Note Tool  — REPEATABLE
# ---------------------------------------------------------------------------

class InternalWorkNoteInput(BaseModel):
    note_text: str = Field(
        ...,
        description="Free-text note to log internally against the incident. Not visible to the end user.",
    )


def _internal_work_note(note_text: str) -> str:
    """Stub. Real persistence (ServiceNow work_notes write) is deferred
    to the sprint where components merge."""
    return f"[STUB] internal_work_note called with note_text='{note_text}'. Not persisted."


internal_work_note_tool = StructuredTool.from_function(
    func=_internal_work_note,
    name="internal_work_note",
    description=(
        "Records an internal, agent-only note against the incident — for "
        "example a reasoning checkpoint, an interim finding, or context "
        "meant for a future human reviewer. Notes are internal-only and are "
        "never shown to the requester. This tool can be called repeatedly "
        "without ending the run — use it as often as you like to keep a "
        "trail of your reasoning while you work through the incident."
    ),
    args_schema=InternalWorkNoteInput,
)


# ---------------------------------------------------------------------------
# 3. Final Grounded Answer Tool  — TERMINAL
# ---------------------------------------------------------------------------

class FinalGroundedAnswerInput(BaseModel):
    resolution_procedure: str = Field(
        ...,
        description="The step-by-step resolution procedure to present to the user, grounded in retrieved knowledge.",
    )
    knowledge_article_references: List[str] = Field(
        ...,
        min_length=1,
        description="One or more knowledge article identifiers or titles that support this answer.",
    )


def _final_grounded_answer(
    resolution_procedure: str, knowledge_article_references: List[str]
) -> str:
    """Stub. No network I/O — just formats and returns the terminal payload."""
    refs = ", ".join(knowledge_article_references)
    return f"[STUB] FINAL ANSWER — Procedure: {resolution_procedure} | Sources: {refs}"


final_grounded_answer_tool = StructuredTool.from_function(
    func=_final_grounded_answer,
    name="final_grounded_answer",
    description=(
        "Delivers the agent's final, knowledge-grounded resolution "
        "procedure to the user, together with the specific knowledge "
        "article(s) it is based on. This tool ends the run — it is the "
        "agent's terminal action when it has a complete, sourced answer. "
        "Only call it once the procedure is backed by at least one "
        "concrete knowledge article reference; never call it speculatively "
        "or without a citation."
    ),
    args_schema=FinalGroundedAnswerInput,
)


# ---------------------------------------------------------------------------
# 4. Human Review Hand-off Tool  — TERMINAL
# ---------------------------------------------------------------------------

class HumanReviewHandoffInput(BaseModel):
    handoff_reason: str = Field(
        ...,
        description="Explanation of why this incident needs to be handed off to a human reviewer instead of being answered by the agent.",
    )


def _human_review_handoff(handoff_reason: str) -> str:
    """Stub. No network I/O — just formats and returns the terminal payload."""
    return f"[STUB] HAND-OFF TO HUMAN REVIEW — Reason: {handoff_reason}"


human_review_handoff_tool = StructuredTool.from_function(
    func=_human_review_handoff,
    name="human_review_handoff",
    description=(
        "Hands the incident off to a human reviewer when the agent cannot "
        "safely or confidently resolve it — for example insufficient "
        "knowledge base coverage, ambiguous requester intent, or a request "
        "outside the agent's authority. This tool ends the run — it is the "
        "agent's terminal action when a human needs to take over. Note: "
        "this tool only flags the incident for a human; it does not "
        "resolve, close, or reassign the incident itself."
    ),
    args_schema=HumanReviewHandoffInput,
)


# ---------------------------------------------------------------------------
# Exported tool list — exactly four tools, no more, no less.
# ---------------------------------------------------------------------------

REPEATABLE_TOOLS = [knowledge_base_search_tool, internal_work_note_tool]
TERMINAL_TOOLS = [final_grounded_answer_tool, human_review_handoff_tool]

AGENT_TOOLS = REPEATABLE_TOOLS + TERMINAL_TOOLS

assert len(AGENT_TOOLS) == 4, "Exactly four tools must be defined for S2.3."
