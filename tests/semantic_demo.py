import os
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore

def main():
    load_dotenv()
    embeddings = OpenAIEmbeddings(
        api_key=os.getenv("LLM_API_KEY"),
        base_url=os.getenv("LLM_BASE_URL"),
        model=os.getenv("LLM_EMBEDDING_MODEL", "gemini/gemini-embedding-2"),
        check_embedding_ctx_length=False
    )
    
    vector_store = QdrantVectorStore.from_existing_collection(
        embedding=embeddings,
        collection_name=os.getenv("QDRANT_COLLECTION_NAME", "kb_articles"),
        url=os.getenv("QDRANT_URL"),
        api_key=os.getenv("QDRANT_API_KEY")
    )

    query = "What is the certificate rotation failure path?"
    print(f"\n[*] Executing Semantic Query: '{query}'\n")
    
    results = vector_store.similarity_search(query, k=1)
    if results:
        print("--- MATCH FOUND ---")
        print(f"Content: {results[0].page_content[:150]}...\n")
        print(f"Payload Metadata: {results[0].metadata}")

if __name__ == "__main__":
    main()