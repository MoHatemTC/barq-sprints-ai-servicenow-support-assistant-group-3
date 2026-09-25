#!/usr/bin/env python3
"""
scripts/ingest_pdf.py
Hybrid Pipeline: Unstructured (YOLOX/Tesseract) for corrupted text/tables + Custom Vector Heuristics for Flowcharts.
Includes deterministic UUIDv5 generation and explicit provenance metadata stamping.
"""

import argparse
import base64
import hashlib
import io
import os
import sys
import uuid

from dotenv import load_dotenv
import pymupdf as fitz
import pdfplumber
from PIL import Image

from langchain_core.documents import Document
from langchain_community.document_loaders import UnstructuredPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from openai import OpenAI

# Fixed namespace for generating deterministic UUIDv5 keys
NAMESPACE_PDF = uuid.UUID("6f8f2c2a-6f1b-4b2a-9b3e-1f0a2b7c9d10")

def summarize_figure(client: OpenAI, model: str, pil_image: Image.Image) -> str | None:
    buf = io.BytesIO()
    pil_image.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": 
                        "You are an expert data extractor. Describe this flowchart precisely. "
                        "List every node and its exact connections. Transcribe text EXACTLY as written. "
                        "Format as:\nNodes:\n- [Node 1]\nEdges:\n- [Node 1] -> [Node 2] [Label]\n"
                        "If the image is just a blank shape or solid color, reply EXACTLY with the word: SKIP."
                    },
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ],
            }],
            max_tokens=500,
            temperature=0.0
        )
        summary = resp.choices[0].message.content.strip()
        return None if summary == "SKIP" or "```json" in summary or summary == "{}" else summary
    except Exception as exc: 
        print(f"    [!] Figure summarization failed: {exc}")
        return None

def extract_vector_flowcharts(pdf_path: str, vision_client: OpenAI, vision_model: str) -> list[Document]:
    print("[*] Scanning for vector-based flowcharts and diagrams...")
    flowchart_docs = []
    
    with fitz.open(pdf_path) as doc, pdfplumber.open(pdf_path) as pdf:
        for i, (page, pdf_page) in enumerate(zip(doc, pdf.pages), start=1):
            table_bboxes = [t.bbox for t in pdf_page.find_tables()]
            elements = pdf_page.lines + pdf_page.rects + pdf_page.curves
            
            valid_elements = []
            for el in elements:
                if not any((el['x0'] >= tb[0]-2 and el['x1'] <= tb[2]+2 and el['top'] >= tb[1]-2 and el['bottom'] <= tb[3]+2) for tb in table_bboxes):
                    valid_elements.append(el)
            
            if len(valid_elements) > 10:
                x0, top = min(el['x0'] for el in valid_elements), min(el['top'] for el in valid_elements)
                x1, bottom = max(el['x1'] for el in valid_elements), max(el['bottom'] for el in valid_elements)
                
                if (x1 - x0) > 50 and (bottom - top) > 50:
                    print(f"    - Found flowchart on page {i}, generating summary...")
                    pix = page.get_pixmap(dpi=300)
                    page_image = Image.open(io.BytesIO(pix.tobytes("png")))
                    scale = page_image.width / page.rect.width
                    
                    crop_img = page_image.crop((int(x0 * scale), int(top * scale), int(x1 * scale), int(bottom * scale)))
                    summary = summarize_figure(vision_client, vision_model, crop_img)
                    
                    if summary:
                        flowchart_docs.append(Document(
                            page_content=f"[Flowchart on page {i}]:\n{summary}",
                            metadata={"page_number": i, "chunk_type": "figure", "source_document": os.path.basename(pdf_path)}
                        ))
    return flowchart_docs

def main():
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf_path")
    args = parser.parse_args()

    if not os.path.exists(args.pdf_path): sys.exit(1)
    filename = os.path.basename(args.pdf_path)
    
    # 1. Base Parsing with Unstructured (Handles RTL Arabic and Tables via YOLOX/Tesseract)
    print(f"[*] Parsing text and tables via Unstructured (hi_res)...")
    loader = UnstructuredPDFLoader(
        args.pdf_path,
        strategy="hi_res",
        languages=["eng", "ara"],
        mode="elements"
    )
    raw_docs = loader.load()
    
    docs = []
    for doc in raw_docs:
        if doc.metadata.get("category") == "Table" and "text_as_html" in doc.metadata:
            doc.page_content = doc.metadata["text_as_html"]
        doc.metadata["chunk_type"] = doc.metadata.get("category", "text").lower()
        doc.metadata["source_document"] = filename
        docs.append(doc)
    
    # 2. Supplementary Parsing
    vision_model = os.getenv("LLM_VISION_MODEL", "gemini/gemini-3.6-flash")
    vision_client = OpenAI(api_key=os.getenv("LLM_API_KEY"), base_url=os.getenv("LLM_BASE_URL")) if os.getenv("LLM_API_KEY") else None
    
    if vision_client:
        docs.extend(extract_vector_flowcharts(args.pdf_path, vision_client, vision_model))

    # 3. Chunking
    print("[*] Splitting text (Size: 700, Overlap: 120)...")
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=700, chunk_overlap=120)
    chunks = text_splitter.split_documents(docs)

    # 4. Metadata Stamping & Deterministic IDs
    print("[*] Stamping provenance metadata and generating UUIDv5 deterministic IDs...")
    deterministic_ids = []
    for chunk in chunks:
        # Explicitly stamp required provenance payload
        chunk.metadata["source_type"] = "pdf"
        
        page_num = chunk.metadata.get("page_number", 0)
        chunk_type = chunk.metadata.get("chunk_type", "text")
        content_hash = hashlib.sha256(chunk.page_content.encode("utf-8")).hexdigest()
        
        # Derive idempotent ID: filename + page + type + hash
        deterministic_key = f"{filename}::{page_num}::{chunk_type}::{content_hash}"
        chunk_id = str(uuid.uuid5(NAMESPACE_PDF, deterministic_key))
        deterministic_ids.append(chunk_id)
        
        # Keep hash in metadata for observability
        chunk.metadata["content_hash"] = content_hash

    # Output to markdown for inspection
    with open("inspection_output.md", "w", encoding="utf-8") as f:
        f.write(f"# Extracted Chunks: {filename}\n\n")
        for idx, c in enumerate(chunks):
            f.write(f"### Chunk {idx + 1} [ID: {deterministic_ids[idx][:8]}... | page {c.metadata.get('page_number', 'unknown')}]\n\n{c.page_content}\n\n---\n\n")

    # 5. Embeddings & Qdrant Upsert
    print("[*] Generating embeddings via LiteLLM...")
    embeddings = OpenAIEmbeddings(
        api_key=os.getenv("LLM_API_KEY"),
        base_url=os.getenv("LLM_BASE_URL"),
        model=os.getenv("LLM_EMBEDDING_MODEL", "gemini/gemini-embedding-2"),
        check_embedding_ctx_length=False,
        chunk_size=100
    )
    
    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    qdrant_api_key = os.getenv("QDRANT_API_KEY")
    collection_name = os.getenv("QDRANT_COLLECTION_NAME", "kb_articles")

    print(f"[*] Upserting {len(chunks)} points to Qdrant collection '{collection_name}' with deterministic IDs...")
    QdrantVectorStore.from_documents(
        documents=chunks,
        embedding=embeddings,
        url=qdrant_url,
        api_key=qdrant_api_key,
        collection_name=collection_name,
        ids=deterministic_ids, # Prevents duplicate vectors on re-run
        force_recreate=False
    )
    print("[+] Ingestion successful. Re-running will safely overwrite existing points.")

if __name__ == "__main__":
    main()