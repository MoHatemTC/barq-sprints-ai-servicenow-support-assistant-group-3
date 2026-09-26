import hashlib
import uuid
from typing import List, Dict

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from barq_support.config import settings
from barq_support.ingestion.embedder import EMBEDDING_DIMENSION
 
COLLECTION_NAME = "kb_articles" 
VECTOR_SIZE = EMBEDDING_DIMENSION # 3072 for Gemini Embedding 2 
def get_client() -> QdrantClient: 
    """Creates a Qdrant client connected to the cloud cluster from .env.""" 
    return QdrantClient( 
             url=settings.qdrant_url, 
             api_key=settings.qdrant_api_key,
             timeout=120,) 
    
def ensure_collection( 
    client: QdrantClient, 
    vector_size: int = VECTOR_SIZE, 
    ) -> None: 
    """Creates the collection if it doesn't already exist.""" 
    
    existing = [c.name for c in client.get_collections().collections] 
    if COLLECTION_NAME in existing: 
        return 
    client.create_collection( 
        collection_name=COLLECTION_NAME, 
        vectors_config=VectorParams(
            size=vector_size, 
            distance=Distance.COSINE, 
            ), 
        ) 
    
def generate_point_id(
    article_id: str,
    section: str,
    chunk_index: int,
    chunk_text: str,
) -> str:
    """
    Deterministic ID from source (article_id + section + chunk_index)
    AND the chunk's own text. Same chunk on re-run -> same ID (overwrite,
    no duplicate). Different chunk text at the same index (e.g. after
    changing chunk_size/overlap) -> a different ID, so old points don't
    get silently overwritten by unrelated content.
    """
    raw_key = f"{article_id}::{section}::{chunk_index}::{chunk_text}"
    digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    return str(uuid.uuid5(uuid.NAMESPACE_URL, digest)) 
    
def build_point( 
  chunk: Dict, 
  vector: List[float], 
  ) -> PointStruct: 
    """Builds a single Qdrant point from a chunk and its embedding vector."""
    
    point_id = generate_point_id( 
      chunk["article_id"],
      chunk["section"], 
      chunk["chunk_index"], 
      chunk["text"],
    ) 
    
    payload = { 
      "text": chunk["text"], 
      "article_id": chunk["article_id"], 
      "section": chunk["section"], 
      "chunk_index": chunk["chunk_index"], 
      **chunk.get("metadata", {}), 
    } 
    
    return PointStruct( 
     id=point_id, 
     vector=vector,
     payload=payload, 
    ) 
    
def upsert_chunks( 
    client: QdrantClient, 
    chunks: List[Dict], 
    vectors: List[List[float]], 
    batch_size: int = 100,
) -> None: 
    """ Upserts chunks with their pre-computed vectors into Qdrant in batches. 
    Since point IDs are deterministic, re-running ingestion over the same 
    chunks overwrites the existing points instead of creating duplicates. 
    """ 
    
    points = [ 
      build_point(chunk, vector) 
      for chunk, vector in zip(chunks, vectors)
    ] 
    
    for i in range(0, len(points), batch_size): 
        batch = points[i:i + batch_size] 
        
        client.upsert( 
          collection_name=COLLECTION_NAME, 
          points=batch, 
        ) 
        
