from barq_support.settings import get_settings
from barq_support.retrieval.retriever import get_qdrant_client, search_kb

s = get_settings()
client = get_qdrant_client(s.qdrant_url, s.qdrant_api_key)

results = search_kb(
    query="laptop screen physically cracked broken hardware replacement",
    client=client,
    top_k=5,
)

print("=" * 70)
print("RUN B - KB RETRIEVAL")
print("=" * 70)

for i, result in enumerate(results, 1):
    print(f"\nResult {i}")
    print(f"Score:   {result['score']:.4f}")
    print(f"Article: {result['article_id']}")
    print(f"Section: {result['section']}")
    print(f"Chunk:   {result['chunk_index']}")
    print(f"Text:    {result['text'][:400]}")
    print("-" * 70)