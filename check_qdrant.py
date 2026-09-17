from qdrant_client import QdrantClient
from config import settings

client = QdrantClient(
    url=settings.qdrant_url,
    api_key=settings.qdrant_api_key,
)

collections = client.get_collections()

print("Collections:")
for collection in collections.collections:
    print("-", collection.name)

collection_name = collections.collections[0].name

points, _ = client.scroll(
    collection_name=collection_name,
    limit=1,
    with_payload=True,
    with_vectors=False,
)

if points:
    #print("\nSample point:")
    #print(points[0].payload)
    payload = points[0].payload

    print("\nPayload Verification: ")
    print("article_id:", payload.get("article_id"))
    print("section:", payload.get("section"))
    print("chunk_index:", payload.get("chunk_index"))
    print("workflow_state:", payload.get("workflow_state"))
    print("category:", payload.get("category"))
    print("kb_knowledge_base:", payload.get("kb_knowledge_base"))
    print("short_description:", payload.get("short_description"))
    print("text exists:", bool(payload.get("text")))
else:
    print("No points found.")