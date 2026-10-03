"""Deterministic, overlap-preserving text chunker.

Sizes are measured in characters. The algorithm is a sliding window whose right edge snaps back
to the best natural boundary (paragraph > sentence > line > word) and whose next start is
`end - overlap`, nudged forward to a word boundary. Consecutive chunks therefore always overlap
(or touch), so no content is lost, and the output depends only on the input text + settings.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.knowledge import Chunk, KnowledgeArticle
from app.services.sections import Section

SOURCE = "servicenow"
_SENTENCE_ENDS = (". ", "? ", "! ", ".\n", "?\n", "!\n")


@dataclass(frozen=True)
class TextSpan:
    index: int
    text: str
    start: int
    end: int


class Chunker:
    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be >= 0 and smaller than chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    # ------------------------------------------------------------------ public API
    def split(self, text: str) -> list[TextSpan]:
        """Split text into spans. Empty/whitespace-only text yields no spans."""
        text = (text or "").strip()
        if not text:
            return []
        n = len(text)
        spans: list[TextSpan] = []
        start = 0
        while start < n:
            hard_end = min(start + self.chunk_size, n)
            end = hard_end if hard_end == n else self._find_break(text, start, hard_end)
            piece = text[start:end].strip()
            if piece:
                spans.append(TextSpan(len(spans), piece, start, end))
            if end >= n:
                break
            start = self._next_start(text, start, end)
        return spans

    def chunk_sections(self, article: KnowledgeArticle, sections: list[Section]) -> list[Chunk]:
        """Chunk each section separately; chunk_index runs across the whole article."""
        chunks: list[Chunk] = []
        for section in sections:
            for span in self.split(section.text):
                index = len(chunks)
                chunks.append(
                    Chunk(
                        index=index,
                        text=span.text,
                        start=span.start,  # offsets are relative to the section text
                        end=span.end,
                        metadata={
                            "sys_id": article.sys_id,
                            "number": article.number,
                            "title": article.title,
                            "chunk_index": index,
                            "source": SOURCE,
                            "section": section.name,
                        },
                    )
                )
        return chunks

    def chunk_article(self, article: KnowledgeArticle, content: str) -> list[Chunk]:
        """Chunk already-normalized plain text as a single "Body" section."""
        return self.chunk_sections(article, [Section("Body", content)])

    # ------------------------------------------------------------------ internals
    def _find_break(self, text: str, start: int, hard_end: int) -> int:
        # Never break so early that the next window (end - overlap) fails to advance.
        min_end = start + max(self.chunk_size // 2, self.chunk_overlap + 1)

        pos = text.rfind("\n\n", min_end, hard_end)
        if pos != -1:
            return pos + 2

        best = max((text.rfind(sep, min_end, hard_end) for sep in _SENTENCE_ENDS), default=-1)
        if best != -1:
            return best + 2

        pos = text.rfind("\n", min_end, hard_end)
        if pos != -1:
            return pos + 1

        if text[hard_end].isspace():
            return hard_end

        for i in range(hard_end - 1, min_end - 1, -1):
            if text[i].isspace():
                return i + 1
        return hard_end  # no whitespace at all: hard split

    def _next_start(self, text: str, start: int, end: int) -> int:
        nxt = max(end - self.chunk_overlap, start + 1)
        if nxt > start and not text[nxt - 1].isspace() and not text[nxt].isspace():
            # Landed mid-word: move to the start of the next word, but never past `end`.
            for i in range(nxt, end):
                if text[i].isspace():
                    nxt = i + 1
                    break
        n = len(text)
        while nxt < n and text[nxt].isspace():
            nxt += 1
        return nxt
