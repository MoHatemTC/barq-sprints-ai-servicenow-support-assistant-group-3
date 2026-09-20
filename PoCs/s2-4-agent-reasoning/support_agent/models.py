"""Plain data models (no LangChain imports, so they are cheap to import and test)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Literal, Mapping

Status = Literal["GROUNDED", "DECLINED"]


@dataclass(frozen=True)
class KnowledgeChunk:
    """One retrieved chunk of a knowledge article (output of the retrieval layer)."""

    article_number: str  # e.g. "KB0010234" - this is the citation key
    title: str
    content: str
    chunk_id: str | None = None
    score: float | None = None  # retrieval relevance, if the retriever provides one

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "KnowledgeChunk":
        number = str(data.get("article_number", "")).strip()
        if not number:
            raise ValueError("Every retrieved chunk needs an 'article_number' (used for citations).")
        return cls(
            article_number=number,
            title=str(data.get("title", "")).strip() or "Untitled article",
            content=str(data.get("content", "")),
            chunk_id=None if data.get("chunk_id") is None else str(data["chunk_id"]),
            score=None if data.get("score") is None else float(data["score"]),
        )


def normalize_chunks(raw: Iterable[Mapping[str, Any] | KnowledgeChunk] | None) -> list[KnowledgeChunk]:
    """Coerce retrieval output to ``KnowledgeChunk`` objects, dropping empty chunks.

    A chunk with no text cannot ground anything, so it is treated as "not retrieved".
    """
    chunks: list[KnowledgeChunk] = []
    for item in raw or []:
        chunk = item if isinstance(item, KnowledgeChunk) else KnowledgeChunk.from_dict(item)
        if chunk.content.strip():
            chunks.append(chunk)
    return chunks


@dataclass(frozen=True)
class AgentResult:
    """What ``generate_recommendation`` returns."""

    status: Status
    text: str  # final text for the human support agent (validated)
    cited_articles: list[str] = field(default_factory=list)
    decline_reason: str | None = None  # "no_knowledge_chunks" | "model_declined" | "validation_failed: ..."
    warnings: list[str] = field(default_factory=list)
    raw_output: str | None = None  # untouched model output (None when the LLM was not called)
    llm_called: bool = True
    tool_calls: list[dict[str, Any]] = field(default_factory=list)

    @property
    def is_grounded(self) -> bool:
        return self.status == "GROUNDED"
