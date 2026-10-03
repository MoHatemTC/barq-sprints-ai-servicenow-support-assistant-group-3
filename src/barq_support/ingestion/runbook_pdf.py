"""PDF runbook extraction and indexing for ServiceNow attachments."""

import logging
from typing import Any

import pymupdf

from .chunker import chunk_article
from .qdrant_store import ensure_collection, get_client, upsert_chunks
from ..password_protection import sanitize_chunk_fields
from ..retrieval.embedder import EMBEDDING_BATCH_SIZE, embed_texts
from ..settings import get_settings

logger = logging.getLogger(__name__)


def ingest_runbook_pdf(
    attachment_sys_id: str,
    file_name: str,
    pdf_bytes: bytes,
    title: str = "",
    category: str = "",
    runbook_notes: str = "",
) -> dict[str, Any]:
    """Extract text from a bounded ServiceNow PDF and upsert its chunks."""
    if not file_name.lower().endswith(".pdf"):
        raise ValueError("Only PDF runbooks can be ingested")
    if not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError("ServiceNow attachment is not a valid PDF")

    try:
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as document:
            page_count = document.page_count
            text = "\n\n".join(
                page.get_text("text")
                for page in document
            ).strip()
    except pymupdf.FileDataError as exc:
        raise ValueError("ServiceNow attachment is not a readable PDF") from exc

    if not text:
        raise ValueError(
            "PDF contains no extractable text; scanned/image-only PDFs are not supported"
        )

    settings = get_settings()
    article_id = f"servicenow-attachment:{attachment_sys_id}"
    metadata = {
        "source_type": "pdf",
        "file_name": file_name,
        "attachment_sys_id": attachment_sys_id,
        "page_count": page_count,
    }
    if title:
        metadata["title"] = title
    if category:
        metadata["category"] = category
    if runbook_notes:
        metadata["runbook_notes"] = runbook_notes
    chunks = chunk_article(
        article_id=article_id,
        html_text=text,
        metadata=metadata,
        chunk_size=settings.chunk_size,
        overlap=settings.chunk_overlap,
    )
    for chunk in chunks:
        sanitize_chunk_fields(chunk, settings)

    vectors: list[list[float]] = []
    for start in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
        batch_text = [chunk["text"] for chunk in chunks[start:start + EMBEDDING_BATCH_SIZE]]
        vectors.extend(embed_texts(batch_text))

    qdrant = get_client()
    ensure_collection(qdrant)
    upsert_chunks(qdrant, chunks, vectors)
    logger.info(
        "Indexed %d chunks from ServiceNow runbook %s (%d pages)",
        len(chunks),
        attachment_sys_id,
        page_count,
    )
    return {
        "attachment_sys_id": attachment_sys_id,
        "file_name": file_name,
        "pages": page_count,
        "chunks": len(chunks),
        "status": "upserted",
    }
