"""multimodal_pdf.py

Reusable per-page multimodal vision PDF extraction and chunking pipeline.
"""

import base64
import io
import logging
import os
import re
import time
from typing import Any

from dotenv import load_dotenv
import pymupdf as fitz
import pytesseract
from PIL import Image
from openai import OpenAI
from google.genai.errors import ClientError
from langchain_text_splitters import RecursiveCharacterTextSplitter

from barq_support.retrieval.embedder import embed_texts, EMBEDDING_BATCH_SIZE
from barq_support.ingestion.qdrant_store import get_client, ensure_collection, upsert_chunks

logger = logging.getLogger(__name__)

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
MAX_EMBEDDED_IMAGES_PER_PAGE = 4
MIN_EMBEDDED_IMAGE_DIM = 80  # px - skip tiny icons/decorative artifacts

PAGE_EXTRACTION_PROMPT = """You are converting a PDF page into clean, structured Markdown for a retrieval system. The first image is the full page. Any further images are embedded diagrams/photos from this page, extracted and rotated upright individually for closer reading - use them to read fine detail, but reconstruct the page in the reading order shown by the full page image.

Rules:
1. Transcribe all body text exactly as written; only fix obvious OCR line-break artifacts.
2. For any photo, screenshot, icon or illustration, insert a line in the form `> [Image: <precise description, including any text visible inside it>]` at the position it appears.
3. Render every table as a GitHub-flavored Markdown table, positioned where it appears. If a table has a nested sub-table, render the sub-table as its own separate Markdown table immediately after, with a one-line note on how it relates to the parent table. If a table has multi-span headers or a nesting/spanning structure that a Markdown table cannot faithfully represent, instead emit it as a fenced ```json code block containing an array of row objects with clear, descriptive keys derived from the header hierarchy - do not scramble spanning cells into flat rows that lose the relationship.
4. Render every flowchart, diagram, architecture schematic or network graph as a Mermaid diagram inside a ```mermaid code fence. Use flowchart syntax for process/architecture diagrams and the closest appropriate Mermaid diagram type otherwise. Preserve every node label, connection, arrow direction and edge label exactly as drawn. Immediately after the ```mermaid line, add one or two %% comment lines giving a plain-English summary of the sequence, key decision points, and outcomes, so the diagram's meaning is findable by a text search even without parsing Mermaid syntax.
5. Arabic text: transcribe it exactly as shown, preserving right-to-left reading order and correct letter shaping. Do not transliterate to Latin script. Where English and Arabic are mixed on the same line or image, transcribe each in its own script exactly as it appears, in their original relative order.
6. Preserve heading structure using Markdown headings (#, ##, ...).
7. If the page is blank or has no meaningful content, respond with exactly: EMPTY_PAGE
8. Output ONLY the reconstructed Markdown for this page. No preamble, no explanation, no outer code fence wrapping the whole response.
"""


def correct_pdf_orientation(pdf_path: str) -> str:
    """Whole-page rotation correction via Tesseract OSD, before anything is rendered."""
    try:
        doc = fitz.open(pdf_path)
        needs_correction = False

        for page in doc:
            pix = page.get_pixmap(dpi=150)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            try:
                osd = pytesseract.image_to_osd(img)
                match = re.search(r"Rotate:\s*(\d+)", osd)
                angle = int(match.group(1)) if match else 0
                if angle != 0:
                    page.set_rotation(angle)
                    needs_correction = True
            except (pytesseract.pytesseract.TesseractError, Exception):
                pass

        if needs_correction:
            temp_path = f"oriented_temp_{os.path.basename(pdf_path)}"
            doc.save(temp_path)
            doc.close()
            return temp_path

        doc.close()
    except Exception as exc:
        logger.warning("PDF orientation pre-processing encountered error: %s", exc)
    return pdf_path


def _orient_upright(pil_img: Image.Image) -> Image.Image:
    """Detects and corrects an individual image's own rotation via OSD."""
    try:
        osd = pytesseract.image_to_osd(pil_img)
        match = re.search(r"Rotate:\s*(\d+)", osd)
        angle = int(match.group(1)) if match else 0
    except (pytesseract.pytesseract.TesseractError, Exception):
        angle = 0
    return pil_img.rotate(-angle, expand=True) if angle else pil_img


def load_pages(pdf_path: str, dpi: int = 200) -> list[dict[str, Any]]:
    """Returns, per page: the full-page render plus individually orientation-corrected crops."""
    pages = []
    with fitz.open(pdf_path) as doc:
        for page in doc:
            pix = page.get_pixmap(dpi=dpi)
            full_page_img = Image.open(io.BytesIO(pix.tobytes("png")))

            embedded_images = []
            for img_info in page.get_images(full=True)[:MAX_EMBEDDED_IMAGES_PER_PAGE]:
                try:
                    base_image = doc.extract_image(img_info[0])
                    pil_img = Image.open(io.BytesIO(base_image["image"])).convert("RGB")
                    if min(pil_img.size) < MIN_EMBEDDED_IMAGE_DIM:
                        continue
                    embedded_images.append(_orient_upright(pil_img))
                except Exception:
                    continue

            pages.append({
                "page_number": page.number + 1,
                "full_page": full_page_img,
                "embedded_images": embedded_images,
                "native_text": page.get_text("text").strip(),
            })
    return pages


def _image_content_block(pil_image: Image.Image) -> dict[str, Any]:
    buf = io.BytesIO()
    pil_image.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}


def extract_page_markdown(
    client: OpenAI, model: str, page: dict[str, Any], max_retries: int = 5
) -> str | None:
    """Extract page Markdown using vision model; returns None on empty or failure."""
    content: list[dict[str, Any]] = [
        {"type": "text", "text": PAGE_EXTRACTION_PROMPT},
        _image_content_block(page["full_page"]),
    ]
    for crop in page.get("embedded_images", []):
        content.append(_image_content_block(crop))

    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": content}],
                max_tokens=8000,
                temperature=0.0,
            )
            text = resp.choices[0].message.content.strip()
            return None if text == "EMPTY_PAGE" else text
        except Exception as exc:
            is_rate_limit = "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc)
            if is_rate_limit and attempt < max_retries - 1:
                wait = 10 * (attempt + 1)
                time.sleep(wait)
            else:
                logger.warning("Vision extraction failed for page %s: %s", page.get("page_number"), exc)
                return None
    return None


def _split_into_blocks(markdown_text: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    lines = markdown_text.split("\n")
    i = 0
    buffer: list[str] = []

    def flush_text():
        if buffer:
            text = "\n".join(buffer).strip()
            if text:
                blocks.append(("text", text))
            buffer.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```mermaid") or stripped.startswith("```json"):
            block_type = "diagram" if "mermaid" in stripped else "table"
            flush_text()
            fence = [line]
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                fence.append(lines[i])
                i += 1
            if i < len(lines):
                fence.append(lines[i])  # closing ```
                i += 1
            blocks.append((block_type, "\n".join(fence)))
            continue

        if stripped.startswith("|"):
            flush_text()
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            blocks.append(("table", "\n".join(table_lines)))
            continue

        buffer.append(line)
        i += 1

    flush_text()
    return blocks


def split_page_markdown(markdown_text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[tuple[str, str]]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=overlap)
    out: list[tuple[str, str]] = []
    for block_type, block_text in _split_into_blocks(markdown_text):
        if block_type in ("table", "diagram"):
            out.append((block_type, block_text))
        else:
            for piece in splitter.split_text(block_text):
                if piece.strip():
                    out.append(("text", piece))
    return out


def build_pdf_chunks(
    page_markdowns: list[tuple[int, str]], article_id: str, source_document: str, sys_id: str | None = None
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    chunk_index = 0
    for page_number, markdown in page_markdowns:
        for block_type, block_text in split_page_markdown(markdown, CHUNK_SIZE, CHUNK_OVERLAP):
            metadata = {
                "source_type": "pdf",
                "source_document": source_document,
                "page_number": page_number,
                "chunk_type": block_type,
                "category": "pdf_runbook",
            }
            if sys_id:
                metadata["sys_id"] = sys_id
            chunks.append({
                "text": block_text,
                "article_id": article_id,
                "section": f"page_{page_number}_{block_type}",
                "chunk_index": chunk_index,
                "metadata": metadata,
            })
            chunk_index += 1
    return chunks


def embed_with_retry(texts: list[str], max_retries: int = 5) -> list[list[float]]:
    for attempt in range(max_retries):
        try:
            return embed_texts(texts)
        except ClientError as e:
            if e.code == 429 and attempt < max_retries - 1:
                time.sleep(30)
            else:
                raise
