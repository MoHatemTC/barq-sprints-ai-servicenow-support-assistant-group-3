"""Split a ServiceNow article body into labelled sections (Problem / Symptoms / Cause / ...).

Mirrors the Agent's existing KB ingestion: a bold label such as "Resolution:" starts a new
section, text before the first label is the "Body" section, and an article without labels is a
single "Body" section.

Differences from the Agent's splitter (deliberate): content outside <p> tags (lists, divs, ...) is
kept instead of dropped, and a bold word in the middle of a sentence ("the <b>cause</b> is ...")
is not mistaken for a section heading.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup, NavigableString, Tag

from app.services.normalizer import normalize_content

HEADING_PATTERNS = [
    r"^problem$",
    r"^diagnostic steps$",
    r"^resolution$",
    r"^symptoms?$",
    r"^cause$",
    r"^workaround$",
]
_OPEN, _CLOSE = "@@KBSECTION@@", "@@KBEND@@"
_MARKER = re.compile(re.escape(_OPEN) + r"(.*?)" + re.escape(_CLOSE))


@dataclass(frozen=True)
class Section:
    name: str
    text: str


def _is_heading(label: str) -> bool:
    cleaned = label.strip().rstrip(":").strip().lower()
    return any(re.match(pattern, cleaned) for pattern in HEADING_PATTERNS)


def _starts_block(tag: Tag) -> bool:
    """True if nothing but whitespace precedes the tag inside its parent element."""
    for sibling in tag.previous_siblings:
        if isinstance(sibling, NavigableString):
            if sibling.strip():
                return False
        elif isinstance(sibling, Tag) and sibling.get_text(strip=True):
            return False
    return True


def extract_sections(html_text: str | None) -> list[Section]:
    """Group the article into sections. Returns [] for empty/missing text."""
    if not html_text or not html_text.strip():
        return []

    soup = BeautifulSoup(html_text, "html.parser")
    for tag in soup.find_all(["strong", "b"]):
        label = tag.get_text(" ", strip=True)
        if _is_heading(label) and _starts_block(tag):
            name = label.rstrip(":").strip()
            tag.replace_with(NavigableString(f"\n{_OPEN}{name}{_CLOSE}\n"))

    text = normalize_content(str(soup))
    parts = _MARKER.split(text)  # [before, name1, body1, name2, body2, ...]

    sections: list[Section] = []
    before = parts[0].strip()
    if before:
        sections.append(Section("Body", before))
    for name, body in zip(parts[1::2], parts[2::2], strict=False):
        body = body.lstrip(": \n").strip()  # tolerate "<b>Problem</b>: text"
        if body:
            sections.append(Section(name, body))
    return sections
