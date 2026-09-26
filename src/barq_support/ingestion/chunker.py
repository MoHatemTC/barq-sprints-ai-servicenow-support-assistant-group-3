import re
from html import unescape
from typing import List, Dict, Optional

from bs4 import BeautifulSoup

# Section labels we recognize as heading boundaries inside the article HTML
SECTION_HEADING_PATTERNS = [
    r"^problem$",
    r"^diagnostic steps$",
    r"^resolution$",
    r"^symptoms?$",
    r"^cause$",
    r"^workaround$",
]


def _is_heading(label_text: str) -> bool:
    cleaned = label_text.strip().rstrip(":").strip().lower()
    return any(re.match(pattern, cleaned) for pattern in SECTION_HEADING_PATTERNS)


def extract_sections(html_text: str) -> List[Dict[str, str]]:
    """
    Parses article HTML and groups its content into sections based on
    bold labels like 'Problem:', 'Diagnostic Steps:', 'Resolution:'.
    Falls back to a single 'Body' section if no known headings are found.
    Returns [] for empty/missing text.
    """
    if not html_text or not html_text.strip():
        return []

    soup = BeautifulSoup(html_text, "html.parser")
    paragraphs = soup.find_all("p") or [soup]

    sections: List[Dict[str, str]] = []
    current_section = "Body"
    current_parts: List[str] = []

    def flush():
        text = re.sub(r"\s+", " ", " ".join(current_parts)).strip()
        if text:
            sections.append({"section": current_section, "text": text})

    for p in paragraphs:
        p_text = p.get_text(" ", strip=True)
        if not p_text:
            continue

        strong = p.find("strong")
        if strong is not None:
            strong_text = strong.get_text(" ", strip=True)
            if _is_heading(strong_text):
                flush()
                current_section = strong_text.rstrip(":").strip()
                current_parts = []
                remainder = p_text[len(strong_text):].strip()
                if remainder:
                    current_parts.append(remainder)
                continue

        current_parts.append(p_text)

    flush()
    return sections


def split_by_length(text: str, chunk_size: int, overlap: int) -> List[str]:
    """Character-length fallback splitter with configurable overlap."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be >= 0 and smaller than chunk_size")

    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    step = chunk_size - overlap
    start = 0
    while start < len(text):
        end = start + chunk_size
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start += step
    return chunks


def chunk_article(
    article_id: str,
    html_text: str,
    metadata: Optional[dict] = None,
    chunk_size: int = 500,
    overlap: int = 50,
) -> List[Dict]:
    """
    Chunks one article's HTML text, splitting first on detected section
    headings (Problem / Diagnostic Steps / Resolution / ...), then falling
    back to character-length splitting for any section longer than
    chunk_size. Each chunk carries provenance back to the article and
    section it came from, plus its index within the article.
    """
    metadata = metadata or {}
    sections = extract_sections(html_text)

    chunks: List[Dict] = []
    chunk_index = 0
    for section in sections:
        for piece in split_by_length(section["text"], chunk_size, overlap):
            chunks.append({
                "text": piece,
                "article_id": article_id,
                "section": section["section"],
                "chunk_index": chunk_index,
                "metadata": metadata,
            })
            chunk_index += 1
    return chunks

