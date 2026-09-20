import uuid
from unittest.mock import MagicMock

import qdrant_store


def make_chunk(article_id="KB01", section="Problem", chunk_index=0, text="hello", metadata=None):
    return {
        "article_id": article_id,
        "section": section,
        "chunk_index": chunk_index,
        "text": text,
        "metadata": metadata or {},
    }


class TestGeneratePointId:
    def test_same_inputs_produce_the_same_id(self):
        id_a = qdrant_store.generate_point_id("KB01", "Problem", 0, "hello")
        id_b = qdrant_store.generate_point_id("KB01", "Problem", 0, "hello")
        assert id_a == id_b

    def test_different_text_produces_a_different_id(self):
        id_a = qdrant_store.generate_point_id("KB01", "Problem", 0, "version one")
        id_b = qdrant_store.generate_point_id("KB01", "Problem", 0, "version two")
        assert id_a != id_b

    def test_different_article_or_section_produces_a_different_id(self):
        base = qdrant_store.generate_point_id("KB01", "Problem", 0, "same text")
        other_article = qdrant_store.generate_point_id("KB02", "Problem", 0, "same text")
        other_section = qdrant_store.generate_point_id("KB01", "Resolution", 0, "same text")
        assert base != other_article
        assert base != other_section

    def test_id_is_a_valid_uuid_string(self):
        point_id = qdrant_store.generate_point_id("KB01", "Problem", 0, "text")
        uuid.UUID(point_id)  # raises if not a valid UUID


class TestBuildPoint:
    def test_payload_contains_core_fields_plus_passed_through_metadata(self):
        chunk = make_chunk(metadata={"workflow_state": "published", "category": "network"})
        point = qdrant_store.build_point(chunk, vector=[0.1, 0.2])

        assert point.payload["text"] == chunk["text"]
        assert point.payload["article_id"] == chunk["article_id"]
        assert point.payload["section"] == chunk["section"]
        assert point.payload["workflow_state"] == "published"
        assert point.payload["category"] == "network"
        assert point.vector == [0.1, 0.2]

    def test_point_id_depends_on_chunk_identity_not_on_the_vector(self):
        chunk = make_chunk()
        point_1 = qdrant_store.build_point(chunk, vector=[0.1])
        point_2 = qdrant_store.build_point(chunk, vector=[0.9])
        assert point_1.id == point_2.id


class TestEnsureCollection:
    def test_does_not_recreate_an_already_existing_collection(self):
        client = MagicMock()
        existing = MagicMock()
        existing.name = qdrant_store.COLLECTION_NAME
        client.get_collections.return_value.collections = [existing]

        qdrant_store.ensure_collection(client)

        client.create_collection.assert_not_called()

    def test_creates_the_collection_with_the_right_vector_size_when_missing(self):
        client = MagicMock()
        client.get_collections.return_value.collections = []

        qdrant_store.ensure_collection(client, vector_size=3072)

        client.create_collection.assert_called_once()
        _, kwargs = client.create_collection.call_args
        assert kwargs["collection_name"] == qdrant_store.COLLECTION_NAME
        assert kwargs["vectors_config"].size == 3072


class TestUpsertChunks:
    def test_upserts_in_batches_of_the_requested_size(self):
        client = MagicMock()
        chunks = [make_chunk(chunk_index=i, text=f"chunk {i}") for i in range(5)]
        vectors = [[float(i)] for i in range(5)]

        qdrant_store.upsert_chunks(client, chunks, vectors, batch_size=2)

        assert client.upsert.call_count == 3  # 2 + 2 + 1
        batch_sizes = [len(call.kwargs["points"]) for call in client.upsert.call_args_list]
        assert batch_sizes == [2, 2, 1]
