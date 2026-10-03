import pytest

from app.services.chunker import Chunker
from tests.conftest import make_article

PARAGRAPH = "Reset your password from the portal. Then restart the VPN client. "


def test_short_article_is_single_chunk():
    spans = Chunker(500, 50).split("Short article body.")
    assert len(spans) == 1
    assert spans[0].text == "Short article body."
    assert spans[0].index == 0


def test_empty_content_yields_no_chunks():
    chunker = Chunker(500, 50)
    assert chunker.split("") == []
    assert chunker.split("   \n\n  ") == []
    assert chunker.split(None) == []  # type: ignore[arg-type]
    assert chunker.chunk_article(make_article(), "") == []


def test_long_article_respects_chunk_size_and_indexes():
    text = PARAGRAPH * 40
    spans = Chunker(500, 50).split(text)
    assert len(spans) > 3
    assert [s.index for s in spans] == list(range(len(spans)))
    assert all(len(s.text) <= 500 for s in spans)


def test_consecutive_chunks_overlap_without_gaps():
    text = PARAGRAPH * 40
    spans = Chunker(500, 50).split(text)
    overlaps = []
    for prev, nxt in zip(spans, spans[1:], strict=False):
        assert nxt.start <= prev.end, "gap between chunks would lose content"
        overlaps.append(prev.end - nxt.start)
    assert all(0 <= o <= 50 for o in overlaps)
    assert any(o > 0 for o in overlaps)


def test_no_content_is_lost():
    text = " ".join(f"word{i}" for i in range(400))
    spans = Chunker(120, 15).split(text)
    covered = set()
    for s in spans:
        covered.update(range(s.start, s.end))
    assert all(i in covered for i, ch in enumerate(text) if not ch.isspace())
    joined = " ".join(s.text for s in spans)
    assert all(f"word{i}" in joined for i in range(400))


def test_prefers_paragraph_boundaries():
    text = ("A" * 150 + " end.\n\n") + ("B" * 150 + " end.")
    spans = Chunker(200, 20).split(text)
    assert spans[0].text.endswith("end.")
    assert "B" not in spans[0].text


def test_deterministic():
    text = PARAGRAPH * 30
    assert Chunker(300, 30).split(text) == Chunker(300, 30).split(text)


def test_unbroken_string_hard_splits():
    spans = Chunker(100, 10).split("x" * 450)
    assert all(len(s.text) <= 100 for s in spans)
    assert sum(len(s.text) for s in spans) >= 450


def test_metadata():
    article = make_article(sys_id="abc123", number="KB001500")
    chunks = Chunker(100, 10).chunk_article(article, PARAGRAPH * 5)
    assert chunks[0].metadata == {
        "sys_id": "abc123",
        "number": "KB001500",
        "title": "VPN Authentication Issue",
        "chunk_index": 0,
        "source": "servicenow",
        "section": "Body",
    }
    assert [c.metadata["chunk_index"] for c in chunks] == list(range(len(chunks)))


@pytest.mark.parametrize("size,overlap", [(0, 0), (100, 100), (100, 150), (100, -1)])
def test_invalid_configuration(size, overlap):
    with pytest.raises(ValueError):
        Chunker(size, overlap)
