import os
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from retriever import retrieve_relevant_chunks

# Load environment variables from .env file
load_dotenv()

print("=== Starting Retrieval Gate Tests ===")

qdrant_url = os.getenv("QDRANT_URL")
qdrant_api_key = os.getenv("QDRANT_API_KEY")

if not qdrant_url:
    print("Error: QDRANT_URL environment variable is missing. Check your .env file.")
    exit(1)

client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)

# 1. Fetch sample point
points, _ = client.scroll(
    collection_name="kb_articles",
    limit=1,
    with_payload=True,
    with_vectors=True
)

if not points:
    print("No points found in collection.")
    exit()

sample_point = points[0]
sample_vector = sample_point.vector
sample_text = sample_point.payload.get("text", "")[:60]

# Test 1: Successful retrieval
print("\n--- Test 1: Query Meeting Threshold (Success) ---")
result_success = retrieve_relevant_chunks(
    query_vector=sample_vector,
    query_text=sample_text,
    collection_name="kb_articles",
    top_k=2,
    threshold=0.70,
    client=client
)
print("Status:", result_success["status"])
print("Top Score:", result_success["top_score"])
print("Retrieved Chunks Count:", len(result_success["results"]))
if result_success["results"]:
    print("Top Article ID:", result_success["results"][0]["article_id"])

# Test 2: Refusal Gate
print("\n--- Test 2: Threshold Gate Triggered (Refusal) ---")
result_refused = retrieve_relevant_chunks(
    query_vector=sample_vector,
    query_text=sample_text,
    collection_name="kb_articles",
    top_k=2,
    threshold=1.05,
    client=client
)
print("Status:", result_refused["status"])
print("Message:", result_refused["message"])
print("Searched Query:", result_refused["searched_query"])
print("Top Score:", result_refused["top_score"])
print("Threshold:", result_refused["threshold"])

# Test 3: Category Filtering
print("\n--- Test 3: Category Filtering ---")
result_category = retrieve_relevant_chunks(
    query_vector=sample_vector,
    query_text=sample_text,
    collection_name="kb_articles",
    top_k=2,
    category="NonExistingCategory123",
    threshold=0.50,
    client=client
)
print("Status:", result_category["status"])
print("Message:", result_category["message"])