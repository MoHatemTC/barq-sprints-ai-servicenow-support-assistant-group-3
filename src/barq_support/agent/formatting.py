"""Rendering of the knowledge block and the untrusted incident block.

Security notes
--------------
* Incident text is UNTRUSTED. Every value is stripped of control characters, length-capped,
  and has ``<`` / ``>`` escaped, so it can never contain a literal ``</incident_data>`` (or any
  other tag) that would let it "break out" of its data block.
* Only a whitelist of incident fields is forwarded (less PII, smaller injection surface).
* Knowledge content is retrieved from our own KB, but we still defang our reserved tag names
  so a poisoned article cannot forge block boundaries either.
"""

from __future__ import annotations

import html
import re
from typing import Any, Mapping, Sequence

from .models import KnowledgeChunk
from .prompts import HUMAN_TEMPLATE

# Only these incident fields are sent to the model.
INCIDENT_FIELDS: tuple[str, ...] = (
    "number",
    "short_description",
    "description",
    "category",
    "priority",
    "cmdb_ci",
)
MAX_FIELD_CHARS = 4000

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_RESERVED_TAG_RE = re.compile(
    r"<\s*(/?)\s*(knowledge_base|article|incident_data|field|tool_output)\b", re.IGNORECASE
)


def escape_untrusted(value: Any, max_chars: int = MAX_FIELD_CHARS) -> str:
    """Make arbitrary untrusted text safe to embed inside a delimited data block."""
    text = "" if value is None else str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_CHARS_RE.sub("", text)
    if len(text) > max_chars:
        text = text[:max_chars] + " [...truncated]"
    return text.replace("<", "&lt;").replace(">", "&gt;")


def defang_reserved_tags(text: str) -> str:
    """Neutralise only our own block tags inside otherwise-legitimate content."""
    return _RESERVED_TAG_RE.sub(lambda m: f"&lt;{m.group(1)}{m.group(2)}", text)


def _attr(value: Any) -> str:
    return html.escape(str(value), quote=True)


def format_knowledge_block(chunks: Sequence[KnowledgeChunk]) -> str:
    """Render retrieved chunks. This block is placed BEFORE the incident in the prompt."""
    if not chunks:
        return (
            "<knowledge_base>\n"
            "NO KNOWLEDGE ARTICLES WERE RETRIEVED FOR THIS INCIDENT.\n"
            "</knowledge_base>"
        )
    parts = ["<knowledge_base>"]
    for chunk in chunks:
        attrs = f'number="{_attr(chunk.article_number)}" title="{_attr(chunk.title)}"'
        if chunk.chunk_id is not None:
            attrs += f' chunk="{_attr(chunk.chunk_id)}"'
        if chunk.score is not None:
            attrs += f' relevance="{chunk.score:.2f}"'
        parts.append(f"<article {attrs}>")
        parts.append(defang_reserved_tags(chunk.content.strip()))
        parts.append("</article>")
    parts.append("</knowledge_base>")
    return "\n".join(parts)


def format_incident_block(incident: Mapping[str, Any]) -> str:
    """Render the incident as a clearly labelled UNTRUSTED data block."""
    lines = ['<incident_data trust="untrusted">']
    for name in INCIDENT_FIELDS:
        if name in incident and incident[name] not in (None, ""):
            lines.append(f'<field name="{name}">{escape_untrusted(incident[name])}</field>')
    lines.append("</incident_data>")
    return "\n".join(lines)


def render_user_message(incident: Mapping[str, Any], chunks: Sequence[KnowledgeChunk]) -> str:
    """The exact human message sent to the model (knowledge first, incident second)."""
    return HUMAN_TEMPLATE.format(
        knowledge_block=format_knowledge_block(chunks),
        incident_block=format_incident_block(incident),
    )
