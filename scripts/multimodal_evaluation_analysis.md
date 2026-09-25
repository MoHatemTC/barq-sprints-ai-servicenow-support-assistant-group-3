
# Sprint 3 R&D Technical Analysis: Multimodal PDF Ingestion & OCR Evaluation

## 1. Executive Summary

This document evaluates the parsing and OCR methodologies tested during Sprint 3 to satisfy Deliverable D-04 (Knowledge ingestion pipeline) and Deliverable D-05 (Qdrant collection) for the BARQ Systems AI ServiceNow Support Assistant. The goal was to accurately extract knowledge base articles from complex, multimodal PDFs containing nested tables, vector flowcharts, and right-to-left (RTL) Arabic text. Two distinct architectural approaches were engineered and evaluated: a Hybrid Local Pipeline and a Vision-Optimized LLM Pipeline.

## 2. Evaluation of Pipeline A: Hybrid Local OCR 

The initial approach relied on traditional local computer vision libraries, utilizing `pdfplumber` for layout extraction and `pytesseract` for optical character recognition.

### 2.1 Methodology

The script implemented custom line-banding heuristics and a dual-pass script probe to separate Arabic bounding boxes from English bounding boxes before routing them to the Tesseract LSTM engine.

### 2.2 Documented Failure Cases

When tested against the `Advanced_Extraction_Challenges.pdf` (representing page 44 of the BARQ Systems IT Service Operations Manual), this pipeline exhibited critical failures:

* **Rotated RTL Arabic Corruption:** Tesseract failed to accurately process rotated Arabic layouts and tight bounding boxes. It produced completely garbled artifacts (e.g., `ᓅᓚᓪلع فرعتلا ىلع`) and failed to shape logical Arabic text.


* **Fractured Nested Tables:** The naive grid extractor collapsed multi-span headers into flattened, single-column strings. For example, the monthly service review metrics (Volume, First-contact resolution) lost their structural relationship to their definitions. This destroys the semantic context required for accurate LLM retrieval.


* **Vector Graphic Omission:** Traditional OCR failed to capture the logical flow of diagram edges and nodes.

## 3. The Workaround: Vision-Optimized LLM 

To resolve the documented failures of local OCR, the architecture was rewritten to leverage a Vision-Optimized LLM pipeline.

### 3.1 Architectural Shift

This pipeline utilizes `UnstructuredPDFLoader` (with the `hi_res` YOLOX strategy) for base layout parsing and HTML table inference. Crucially, it incorporates a custom vector-heuristic fallback that detects flowchart bounding boxes, crops them as raster images, and passes them directly to `gemini/gemini-3.6-flash` via the LiteLLM router.

### 3.2 Concrete Improvements & Results

* **Structural Table Preservation:** The YOLOX model successfully extracts complex grids as structured HTML (`<table>...</table>`) rather than flattened text. This maintains the exact mapping between keys and values.


* **Native Spatial & RTL Comprehension:** The Vision LLM perfectly captures Arabic in its raw, logical Unicode state. It correctly isolates English technical identifiers (e.g., `INC0010023` and `KB0001 (v2)`) embedded within the Arabic text, satisfying the BARQ manual's strict "Never translate an identifier" rule.


* **Literal Diagram Transcription:** The Vision prompt successfully extracts nodes and connections from the certificate rotation failure path, converting vector shapes into highly searchable semantic text.



## 4. Deterministic Ingestion & Provenance

Beyond raw extraction, the final pipeline (`ingest_pdf.py`) implements strict governance logic to satisfy the project's functional and non-functional requirements.

### 4.1 Data Integrity & Idempotency (NFR-10)

To prevent duplicate data upon re-ingestion, the pipeline assigns every chunk a deterministic `UUIDv5`. The UUID is derived cryptographically from the `filename + page_number + chunk_type + content_hash`. Re-running the pipeline against an unchanged document safely overwrites existing Qdrant points rather than flooding the database.

### 4.2 Metadata & Provenance (FR-08, FR-09)

The `RecursiveCharacterTextSplitter` chunks the extracted documents based on configurable parameters (Size: 500, Overlap: 50). Every vector is upserted to the Qdrant Cloud collection (`kb_articles`) alongside a rich JSON payload containing the text chunk and its metadata (source type, source document, page number, language, and chunk type). This guarantees that the LangChain retrieval agent can correctly cite its sources during the incident generation phase.

## 5. Conclusion & Selection Rationale

While the Hybrid Local OCR (`ingest_pdf (1).py`) is cost-effective, its brittleness against complex ITSM layouts makes it unviable for production. The **Vision-Optimized LLM Pipeline (`ingest_pdf.py`)** is selected as the primary solution. It completely resolves the Arabic OCR corruption, preserves multi-span table structures, and successfully anchors the data to deterministic Qdrant payloads, cleanly fulfilling Sprint 3 Deliverables D-04 and D-05.