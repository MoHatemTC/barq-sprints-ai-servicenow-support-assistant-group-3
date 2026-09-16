"""
Incident context for the current agent run.

Per the S2.3 brief the incident is preloaded into context by the caller,
so there is no "fetch incident" tool. The caller sets the incident once
before invoking the agent; the tools read it from here.

A ContextVar is used rather than a module global so concurrent runs
(e.g. several incidents processed in parallel, or async handlers) don't
leak each other's incident.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class IncidentContext:
    sys_id: str
    number: str
    short_description: str = ""
    description: str = ""


_current_incident: ContextVar[Optional[IncidentContext]] = ContextVar(
    "current_incident", default=None
)


def set_current_incident(incident: IncidentContext):
    """Set the incident for this run. Returns a token for reset()."""
    return _current_incident.set(incident)


def reset_current_incident(token) -> None:
    _current_incident.reset(token)


def get_current_incident() -> IncidentContext:
    incident = _current_incident.get()
    if incident is None:
        raise RuntimeError(
            "No incident is loaded in context. The caller must call "
            "set_current_incident(...) before invoking the agent."
        )
    return incident
