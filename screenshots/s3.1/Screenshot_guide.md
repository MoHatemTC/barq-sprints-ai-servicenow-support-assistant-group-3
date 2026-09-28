## Sprint 3 (S3.1) - Multimodal PDF Ingestion, Governance, & Semantic Retrieval

### 1. ServiceNow Governance Layer & Evidence Index
The platform data model and incident workflow have been hardened with strict lifecycle controls[cite: 30]. All 24 pieces of evidence are located in the `Sprint3.1_screenshoots` directory and are mapped directly to their platform requirements below:

* **[1] Dictionary Fields & Security (FR-02):** Deployed 5 custom scoped AI fields (`ai_status`, `ai_processed`, `ai_confidence`, `ai_suggested_response`, `human_review_required`)[cite: 30].
  * 📸 *Reference:* `Screenshot 2026-09-23 230114.png`[cite: 11].
* **[2] Read-Only UI Policy:** Locked all AI-generated fields for standard fulfillers to enforce system-driven updates.
  * 📸 *References:* `Screenshot 2026-09-23 225424.jpg`[cite: 10], `Screenshot 2026-09-25 115037.jpg`[cite: 17], and `Screenshot 2026-09-25 115145.jpg`[cite: 18].
* **[3] 0-1 Confidence Data Policy:** Aborts operations if `ai_confidence` breaches the 0.0 - 1.0 boundary.
  * 📸 *References:* `Screenshot 2026-09-23 223928.png`[cite: 3] and `Screenshot 2026-09-25 120425.png`[cite: 25].
* **[4] Lifecycle Guard (Business Rule):** Automatically clears the review flag upon fulfiller comment or terminal state transition. Includes a strict caller exclusion so customer replies do not bypass the ITIL review gate.
  * 📸 *Conditions:* `Screenshot 2026-09-23 224302.png`[cite: 4] and `Screenshot 2026-09-25 120147.png`[cite: 23].
  * 📸 *Caller Exclusion Script:* `Screenshot 2026-09-23 224412.jpg`[cite: 5] and `Screenshot 2026-09-25 120223.jpg`[cite: 24].
* **[5] Actionable UI Scripts (Adopt, Edit, Reject):** Condition-gated actions. Validated that Adopt/Edit route to Comments without resolving the ticket, while Reject routes to Work Notes.
  * 📸 *List View:* `Screenshot 2026-09-23 224757.png`[cite: 6] and `Screenshot 2026-09-25 115339.png`[cite: 19].
  * 📸 *Approve (Adopt) Script:* `Screenshot 2026-09-23 225155.jpg`[cite: 9] and `Screenshot 2026-09-25 115837.png`[cite: 22].
  * 📸 *Edit Script:* `Screenshot 2026-09-23 224851.png`[cite: 7] and `Screenshot 2026-09-25 115432.png`[cite: 20].
  * 📸 *Reject Script:* `Screenshot 2026-09-23 225141.png`[cite: 8] and `Screenshot 2026-09-25 115652.png`[cite: 21].
* **[6] Behavioral Walkthrough (FR-16):** Form behavior rendering the AI fields and the three UI action buttons before and after processing[cite: 30].
  * 📸 *Before Action:* `Screenshot 2026-09-24 083608.png`[cite: 12].
  * 📸 *After Action:* `Screenshot 2026-09-24 083837.png`[cite: 13].

### 2. Multimodal Ingestion Pipeline (`ingest_pdf.py`)
* **Orientation Correction:** Added a pre-OCR step utilizing Tesseract OSD to detect and rotate sideways pages (90/270 degrees) upright, preventing garbled text artifacts.
  * 📸 *Ingestion Terminal Run:* `Screenshot 2026-09-24 215106.jpg`[cite: 14].
* **Vision LLM Workaround:** Leverages `Unstructured` (YOLOX) for high-resolution layout parsing alongside a custom vector-heuristic fallback that passes rasterized flowchart crops directly to `gemini-3.6-flash`.

### 3. Deterministic Ingestion & Provenance (FR-08, FR-09, NFR-10)
* **Idempotency (NFR-10):** Implemented `UUIDv5` deterministic point IDs derived from `filename + page_number + chunk_type + content_hash` to guarantee safe overwrites[cite: 30].
* **Provenance Stamping (FR-08, FR-09):** Stamped `source_type: "pdf"` explicitly onto every chunk prior to embedding, ensuring category, service, article status, and version are stored as payload metadata[cite: 30].

### 4. Semantic Retrieval Proof (D-05, FR-10)
The semantic search successfully retrieved the PDF-sourced chunk with the correct metadata payload and passed the Qdrant retrieval threshold gates[cite: 30].
* 📸 *REST API / Semantic Search Terminal Output:* `Screenshot 2026-09-25 080038.jpg`[cite: 16] and `Screenshot 2026-09-25 122207.png`[cite: 26].
* 📸 *Pytest Retrieval Pass:* `Screenshot 2026-09-24 221249.jpg`[cite: 15].