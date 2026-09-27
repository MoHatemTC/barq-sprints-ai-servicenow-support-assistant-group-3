"""One-off utility: wipe and recreate the kb_articles Qdrant collection.

Run this once, right before re-ingesting an updated corpus, so no
orphaned points from earlier ingestion runs or schema versions linger
alongside the fresh data (this is what caused the "Unknown" hit in
the benchmark results).

Usage (from the project root, with your venv active):
    python scripts/wipe_collection.py
"""

from barq_support.ingestion.qdrant_store import (
    get_client,
    ensure_collection,
    COLLECTION_NAME,
)


def main() -> None:
    client = get_client()

    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME in existing:
        client.delete_collection(COLLECTION_NAME)
        print(f"Deleted collection '{COLLECTION_NAME}'.")
    else:
        print(f"Collection '{COLLECTION_NAME}' did not exist yet — nothing to delete.")

    ensure_collection(client)
    print(f"Recreated empty collection '{COLLECTION_NAME}'.")


if __name__ == "__main__":
    main()