"""Deterministic post-check of the model output (defence in depth, fail-closed).

The prompt asks the model to ground and cite. This module *verifies* it, so a slip by the
model can never reach a human agent as an unsupported recommendation:

* first line must be ``STATUS: GROUNDED`` or ``STATUS: DECLINED``;
* DECLINED  -> replaced by the canonical decline text (no speculative leftovers survive);
* GROUNDED  -> must contain >= 1 numbered step, EVERY step must cite an article that was
               actually retrieved, and no citation may point to an unknown article;
* anything else (missing status, uncited step, invented article, empty output,
  "iteration limit" message, ...) -> converted to the canonical decline.
"""

from __future__ import annotations

import re
from typing import Collection

from .models import AgentResult
from .prompts import DECLINE_TEXT

_STATUS_RE = re.compile(r"^\W*STATUS:\s*(GROUNDED|DECLINED)\W*$", re.IGNORECASE)
_STEP_RE = re.compile(r"^\s*\d+[.)]\s+\S")
_CITATION_RE = re.compile(r"\[([^\[\]\n]{1,64})\]")
_ARTICLE_LIKE_RE = re.compile(r"^KB[\w-]*\d+$", re.IGNORECASE)


def _decline(reason: str, raw: str | None, tool_calls=None) -> AgentResult:
    return AgentResult(
        status="DECLINED",
        text=DECLINE_TEXT,
        decline_reason=reason,
        raw_output=raw,
        llm_called=True,
        tool_calls=list(tool_calls or []),
    )


def validate_output(raw_output: str | None, known_articles: Collection[str], tool_calls=None) -> AgentResult:
    """Validate model output against the set of retrieved article numbers."""
    known = set(known_articles)
    text = (raw_output or "").strip()
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return _decline("validation_failed: empty model output", raw_output, tool_calls)

    match = _STATUS_RE.match(lines[0].strip())
    if not match:
        return _decline("validation_failed: missing STATUS line", raw_output, tool_calls)

    if match.group(1).upper() == "DECLINED":
        return AgentResult(
            status="DECLINED",
            text=DECLINE_TEXT,
            decline_reason="model_declined",
            raw_output=raw_output,
            llm_called=True,
            tool_calls=list(tool_calls or []),
        )

    # ---- GROUNDED: verify structure and citations -------------------------------------
    steps = [ln for ln in lines[1:] if _STEP_RE.match(ln)]
    if not steps:
        return _decline("validation_failed: no numbered steps", raw_output, tool_calls)

    # No citation anywhere may reference an article that was not retrieved.
    unknown = sorted(
        {c for c in _CITATION_RE.findall(text) if _ARTICLE_LIKE_RE.match(c) and c not in known}
    )
    if unknown:
        return _decline(
            "validation_failed: cites article(s) not in retrieved set: " + ", ".join(unknown),
            raw_output,
            tool_calls,
        )

    cited: list[str] = []
    for step in steps:
        valid = [c for c in _CITATION_RE.findall(step) if c in known]
        if not valid:
            return _decline(
                f"validation_failed: step without a valid citation: {step.strip()[:80]!r}",
                raw_output,
                tool_calls,
            )
        for c in valid:
            if c not in cited:
                cited.append(c)

    return AgentResult(
        status="GROUNDED",
        text=text,
        cited_articles=cited,
        raw_output=raw_output,
        llm_called=True,
        tool_calls=list(tool_calls or []),
    )
