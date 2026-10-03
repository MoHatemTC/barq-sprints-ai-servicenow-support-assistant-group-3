"""Clean ServiceNow article bodies (HTML or plain text) into normalized plain text."""

from __future__ import annotations

import re
from html.parser import HTMLParser

_BLOCK_TAGS = {
    "p", "div", "br", "tr", "table", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6",
    "pre", "blockquote", "section", "article", "hr", "dl", "dt", "dd", "header", "footer",
}  # fmt: skip
_SKIP_TAGS = {"script", "style", "head", "noscript"}
_INVISIBLE = re.compile("[\u200b\u200c\u200d\ufeff]")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")
        elif tag in {"td", "th"}:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip_depth:
            self.parts.append(data)


def normalize_content(raw: str | None) -> str:
    """Strip markup, decode entities and collapse whitespace.

    Paragraph structure is preserved as blank lines so the chunker can split on it.
    Returns an empty string for empty/None input.
    """
    if not raw or not raw.strip():
        return ""
    parser = _TextExtractor()
    parser.feed(raw)
    parser.close()
    text = "".join(parser.parts)
    text = _INVISIBLE.sub("", text).replace("\xa0", " ").replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t\f\v]+", " ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
