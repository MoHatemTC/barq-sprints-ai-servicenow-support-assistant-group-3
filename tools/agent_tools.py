"""
BARQ G3 - Sprint 2 (S2.3) - Agent Tool Definitions
AI ServiceNow Support Assistant

The four tools the LangChain agent may invoke, backed by live
ServiceNow integrations (no mocks).

The incident is preloaded into context by the caller (see
servicenow/context.py), so there is no "fetch incident" tool.

STRUCTURAL GUARANTEE — no resolve / close / reassign:
  1. Exactly four tools are exported in AGENT_TOOLS. There is no fifth.
  2. None of the four takes state, close_code, assignment_group or
     assigned_to as input — the schemas below simply have no field that
     could carry such a value.
  3. The only incident write path in the entire project is
     ServiceNowClient.update_incident, which rejects every field outside
     ALLOWED_INCIDENT_FIELDS (= {"work_notes"}) before sending a request.
  So the exclusion holds even if a model tries to smuggle an instruction
  through free text: there is no code path that can carry it out.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import List

from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool

from servicenow.client import ServiceNowClient
from servicenow.context import get_current_incident

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _client() -> ServiceNowClient:
    """Lazily build one shared client, so importing this module doesn't
    require credentials to be present (useful in CI / for schema tests)."""
    return ServiceNowClient()


# ---------------------------------------------------------------------------
# 1. Knowledge Base Search Tool  — REPEATABLE
# ---------------------------------------------------------------------------

class KnowledgeBaseSearchInput(BaseModel):
    query: str = Field(
        ...,
        description="The search query used to look up relevant knowledge base articles.",
    )


def _knowledge_base_search(query: str) -> str:
    try:
        articles = _client().search_knowledge(query)
    except Exception as exc:  # surfaced to the agent, not raised into the loop
        logger.exception("Knowledge base search failed")
        return f"Knowledge base search failed: {exc}. Try rephrasing, or hand off for human review."

    if not articles:
        return (
            f"No knowledge articles matched '{query}'. Try different wording, "
            "or hand off for human review if the knowledge base has no coverage."
        )

    lines = []
    for a in articles:
        snippet = " ".join((a.get("snippet") or "").split())[:300]
        lines.append(
            f"[{a.get('number', 'n/a')}] {a.get('title', 'Untitled')}\n{snippet}"
        )
    return f"Found {len(articles)} article(s) for '{query}':\n\n" + "\n\n".join(lines)


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
    incident = get_current_incident()
    try:
        _client().add_work_note(incident.sys_id, note_text)
    except Exception as exc:
        logger.exception("Failed to add work note")
        return f"Failed to record work note: {exc}. You may continue working."
    return f"Work note recorded on {incident.number}."


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
    incident = get_current_incident()
    refs = ", ".join(knowledge_article_references)

    # The answer is logged as a work note for traceability. It does NOT
    # change incident state — the incident stays open for a human to act on.
    try:
        _client().add_work_note(
            incident.sys_id,
            f"[AI assistant — proposed answer]\n{resolution_procedure}\n\nSources: {refs}",
        )
    except Exception:
        logger.exception("Failed to log final answer as work note")

    return (
        f"FINAL ANSWER for {incident.number}\n\n"
        f"{resolution_procedure}\n\nSources: {refs}"
    )


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
    incident = get_current_incident()

    # Hand-off = flagging for a human via a work note. It deliberately does
    # not set assignment_group or assigned_to; routing stays a human decision.
    try:
        _client().add_work_note(
            incident.sys_id,
            f"[AI assistant — handed off for human review]\nReason: {handoff_reason}",
        )
    except Exception:
        logger.exception("Failed to log hand-off as work note")

    return f"HAND-OFF for {incident.number} — flagged for human review. Reason: {handoff_reason}"


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
