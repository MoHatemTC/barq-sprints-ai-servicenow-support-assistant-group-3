import pytest

from barq_support.ingestion.chunker import chunk_article, extract_sections, split_by_length


class TestSplitByLength:
    def test_empty_text_returns_no_chunks(self):
        assert split_by_length("   ", chunk_size=100, overlap=10) == []

    def test_short_text_returns_a_single_chunk(self):
        text = "short article body"
        assert split_by_length(text, chunk_size=100, overlap=10) == [text]

    def test_consecutive_chunks_overlap_by_the_requested_amount(self):
        text = "a" * 30
        chunks = split_by_length(text, chunk_size=10, overlap=3)
        for prev, nxt in zip(chunks, chunks[1:]):
            assert prev[-3:] == nxt[:3]

    def test_last_chunk_reaches_the_end_of_the_text(self):
        text = "0123456789" * 5  # 50 chars
        chunks = split_by_length(text, chunk_size=12, overlap=4)
        assert chunks[-1].endswith(text[-1])

    def test_zero_or_negative_chunk_size_raises(self):
        with pytest.raises(ValueError):
            split_by_length("some text", chunk_size=0, overlap=0)

    def test_overlap_greater_or_equal_to_chunk_size_raises(self):
        with pytest.raises(ValueError):
            split_by_length("some text", chunk_size=10, overlap=10)


class TestExtractSections:
    def test_no_recognized_heading_falls_back_to_body(self):
        html = "<p>Just a plain paragraph with no headings.</p>"
        sections = extract_sections(html)
        assert len(sections) == 1
        assert sections[0]["section"] == "Body"

    def test_recognized_headings_split_the_article_into_sections(self):
        html = (
            "<p><strong>Problem:</strong> The login page times out.</p>"
            "<p><strong>Resolution:</strong> Restart the auth service.</p>"
        )
        sections = extract_sections(html)
        assert [s["section"] for s in sections] == ["Problem", "Resolution"]
        assert "login page" in sections[0]["text"]
        assert "auth service" in sections[1]["text"]

    def test_unrecognized_bold_text_is_not_treated_as_a_heading(self):
        html = "<p><strong>Note</strong> this label isn't in our known list.</p>"
        sections = extract_sections(html)
        assert sections[0]["section"] == "Body"

    def test_empty_or_blank_html_returns_no_sections(self):
        assert extract_sections("") == []
        assert extract_sections("   ") == []


class TestChunkArticle:
    def test_metadata_is_attached_to_every_resulting_chunk(self):
        html = "<p>Some reasonably short body text.</p>"
        metadata = {"workflow_state": "published", "category": "network"}

        chunks = chunk_article(
            "KB0001", html, metadata=metadata, chunk_size=500, overlap=50
        )

        assert len(chunks) == 1
        assert chunks[0]["metadata"] == metadata
        assert chunks[0]["article_id"] == "KB0001"

    def test_chunk_index_increments_sequentially_across_sections(self):
        html = (
            "<p><strong>Problem:</strong> " + ("x " * 20) + "</p>"
            "<p><strong>Resolution:</strong> " + ("y " * 20) + "</p>"
        )
        chunks = chunk_article("KB0002", html, chunk_size=20, overlap=5)
        assert [c["chunk_index"] for c in chunks] == list(range(len(chunks)))

    def test_missing_metadata_defaults_to_an_empty_dict(self):
        chunks = chunk_article("KB0003", "<p>text</p>")
        assert chunks[0]["metadata"] == {}

    def test_empty_article_text_produces_no_chunks(self):
        assert chunk_article("KB0004", "") == []
