"""runbook_pdf.py

Vision-based PDF runbook extraction and indexing for ServiceNow attachments.
Uses multimodal Gemini vision extraction with automatic orientation correction
and fallback to native text extraction when vision is unconfigured or unavailable.
"""

import logging
import os
import tempfile
from typing import Any

from openai import OpenAI
import pymupdf as fitz

from .multimodal_pdf import (
    build_pdf_chunks,
    correct_pdf_orientation,
    embed_with_retry,
    extract_page_markdown,
    load_pages,
)
from .qdrant_store import delete_article_chunks, ensure_collection, get_client, upsert_chunks
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
    """Extract and index a ServiceNow PDF runbook using vision with text fallback."""
    if not file_name.lower().endswith(".pdf"):
        raise ValueError("Only PDF runbooks can be ingested")
    if not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError("ServiceNow attachment is not a valid PDF")

    settings = get_settings()
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as probe:
            probe_page_count = probe.page_count
    except Exception as exc:
        raise ValueError("ServiceNow attachment is not a readable PDF") from exc
    if probe_page_count > settings.servicenow_runbook_max_pages:
        raise ValueError(
            f"PDF has {probe_page_count} pages; the limit is "
            f"{settings.servicenow_runbook_max_pages}"
        )

    article_id = f"servicenow-attachment:{attachment_sys_id}"

    # Write attachment bytes to a temporary file for rendering & vision
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_file:
        temp_file.write(pdf_bytes)
        temp_path = temp_file.name

    oriented_path = temp_path
    try:
        oriented_path = correct_pdf_orientation(temp_path)
        pages = load_pages(oriented_path, dpi=200)

        if not pages:
            raise ValueError("PDF contains no readable pages")

        vision_client = None
        vision_model = settings.llm_vision_model or "gemini/gemini-3.6-flash"
        if settings.llm_api_key:
            try:
                vision_client = OpenAI(
                    api_key=settings.llm_api_key,
                    base_url=settings.llm_base_url or None,
                )
            except Exception as exc:
                logger.warning("Could not initialize vision client: %s; falling back to native text", exc)

        page_markdowns: list[tuple[int, str]] = []
        for page in pages:
            page_num = page["page_number"]
            markdown = None

            # Attempt vision-based extraction if client available
            if vision_client:
                try:
                    markdown = extract_page_markdown(vision_client, vision_model, page)
                except Exception as exc:
                    logger.warning("Vision extraction failed for page %s: %s", page_num, exc)

            # Fall back to native extracted text if vision extraction yielded nothing
            if not markdown and page.get("native_text"):
                markdown = page["native_text"]

            if markdown:
                page_markdowns.append((page_num, markdown))

        if not page_markdowns:
            raise ValueError(
                "PDF contains no extractable text or vision content; "
                "scanned/unreadable PDFs without OCR or vision support cannot be ingested"
            )

        chunks = build_pdf_chunks(
            page_markdowns=page_markdowns,
            article_id=article_id,
            source_document=file_name,
            sys_id=attachment_sys_id,
        )

        for chunk in chunks:
            chunk["metadata"]["attachment_sys_id"] = attachment_sys_id
            if title:
                chunk["metadata"]["title"] = title
            if category:
                chunk["metadata"]["category"] = category
            if runbook_notes:
                chunk["metadata"]["runbook_notes"] = runbook_notes

        vectors = embed_with_retry([c["text"] for c in chunks])

        qdrant = get_client()
        ensure_collection(qdrant)
        delete_article_chunks(qdrant, article_id)
        upsert_chunks(qdrant, chunks, vectors)

        logger.info(
            "Indexed %d chunks from ServiceNow runbook %s (%d pages)",
            len(chunks),
            attachment_sys_id,
            len(pages),
        )

        return {
            "attachment_sys_id": attachment_sys_id,
            "file_name": file_name,
            "pages": len(pages),
            "chunks": len(chunks),
            "status": "upserted",
        }
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        if oriented_path != temp_path and os.path.exists(oriented_path):
            os.remove(oriented_path)
