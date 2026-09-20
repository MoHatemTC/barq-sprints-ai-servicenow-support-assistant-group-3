import os
import sys
from pathlib import Path

# Make chunker.py / embedder.py / qdrant_store.py / ingest.py / config.py /
# embedding_cache.py importable regardless of where pytest is invoked from.
# Put this conftest.py in the SAME folder as those source files.
sys.path.insert(0, str(Path(__file__).parent))

# Dummy credentials so importing config.py (pydantic-settings) and
# embedder.py (genai.Client) doesn't blow up just because a real .env isn't
# present in the test environment. No real network calls happen in these
# tests -- everything that would hit Gemini or Qdrant is mocked.
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
os.environ.setdefault("QDRANT_API_KEY", "test-key")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
