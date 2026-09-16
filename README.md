# Sprint 2 (S2.1) — Chunking, Embedding & Vector Storage

Part of the AI ServiceNow Support Assistant (BARQ G3) project. This service turns
ServiceNow KB articles into a searchable vector corpus in Qdrant, which Sprint 3's
retrieval logic will query against.

## Pipeline
ServiceNow KB Articles (from Task 1 FastAPI service)

↓

Chunking (heading-aware, configurable size/overlap)

↓

Embedding (local sentence-transformers model)

↓

Qdrant (deterministic upsert, workflow_state in payload)


## Setup

1. Create and activate a virtual environment:
python -m venv .venv
.venv\Scripts\Activate.ps1

2. Install dependencies:

  pip install qdrant-client sentence-transformers pydantic-settings python-dotenv beautifulsoup4 httpx


3. Copy `.env.example` to `.env` and fill in your Qdrant Cloud credentials:

QDRANT_URL=your-cluster-url

QDRANT_API_KEY=your-api-key

CHUNK_SIZE=500

CHUNK_OVERLAP=50

HF_TOKEN=


4. Make sure the Task 1 FastAPI service is running (ingestion fetches articles
   from it live):

uv run uvicorn main:app --port 8000


## Run
python ingest.py


This loads articles from the Task 1 (S1.3) `/kb-articles` endpoint, chunks them, generates
embeddings, and upserts the resulting points into Qdrant. Console output reports the
number of articles, chunks, and final point count at each stage.

## Configuration

`chunk_size` and `chunk_overlap` are read from `.env` (via `config.py`), so they can
be changed without touching any code:

CHUNK_SIZE=500

CHUNK_OVERLAP=50


## Project structure

config.py # Settings loaded from .env (Qdrant credentials, chunk params)

chunker.py # Heading-aware chunking with character-length fallback

embedder.py # Local embedding model (all-MiniLM-L6-v2, 384-dim)

qdrant_store.py # Collection setup, deterministic point IDs, batched upsert

ingest.py # Entry point: fetch → chunk → embed → upsert

.env.example # Template for required environment variables


## Chunking logic

- Article HTML is parsed and split first on recognized section headings
  (`Problem`, `Diagnostic Steps`, `Resolution`, etc.), so numbered steps stay
  grouped with their parent section.
- Any section with no recognizable heading — or a section longer than
  `chunk_size` — falls back to character-length splitting with the configured
  overlap.
- Every chunk keeps full provenance: `text`, `article_id`, `section`,
  `chunk_index`, plus all original article metadata (`workflow_state`,
  `category`, `kb_knowledge_base`, `short_description`) passed through
  untouched.

## Idempotency

Point IDs are generated deterministically from
`article_id + section + chunk_index` (SHA-256 hash, converted to a UUID via
`uuid5`). Re-running `ingest.py` against unchanged articles upserts the same
points instead of creating duplicates.

Verified by running ingestion twice in a row against the same 50 articles:

Run 1: Produced 144 chunks → Collection now has 144 points.
Run 2: Produced 144 chunks → Collection now has 144 points.
