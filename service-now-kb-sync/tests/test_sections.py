from app.services.chunker import Chunker
from app.services.sections import extract_sections
from tests.conftest import make_article


def _names(html):
    return [s.name for s in extract_sections(html)]


def test_no_headings_is_single_body_section():
    sections = extract_sections("<p>Just some text.</p><p>More text.</p>")
    assert [s.name for s in sections] == ["Body"]
    assert "Just some text." in sections[0].text and "More text." in sections[0].text


def test_bold_labels_start_sections_in_order():
    html = (
        "<p>Intro line.</p>"
        "<p><strong>Problem:</strong> VPN will not connect.</p>"
        "<p><strong>Symptoms</strong></p><p>Timeout shown.</p>"
        "<p><strong>Cause:</strong> Expired token.</p>"
        "<p><b>Resolution:</b> Reset the token.</p>"
    )
    sections = extract_sections(html)
    assert [s.name for s in sections] == ["Body", "Problem", "Symptoms", "Cause", "Resolution"]
    assert sections[1].text == "VPN will not connect."
    assert sections[4].text == "Reset the token."


def test_list_content_under_a_heading_is_not_lost():
    html = (
        "<p><strong>Diagnostic Steps:</strong></p><ul><li>Check VPN</li><li>Check token</li></ul>"
    )
    sections = extract_sections(html)
    assert [s.name for s in sections] == ["Diagnostic Steps"]
    assert "Check VPN" in sections[0].text and "Check token" in sections[0].text


def test_bold_word_inside_a_sentence_is_not_a_heading():
    assert _names("<p>The <strong>cause</strong> is unknown.</p>") == ["Body"]


def test_colon_outside_the_bold_tag_is_tolerated():
    sections = extract_sections("<p><strong>Resolution</strong>: restart it</p>")
    assert (sections[0].name, sections[0].text) == ("Resolution", "restart it")


def test_empty_and_whitespace():
    assert extract_sections("") == []
    assert extract_sections(None) == []
    assert extract_sections("<p>&nbsp;</p>") == []
    assert extract_sections("<p><strong>Problem:</strong></p>") == []  # heading with no content


def test_plain_text_body_still_works():
    assert _names("Plain text without any tags") == ["Body"]


def test_chunk_index_runs_across_sections_and_carries_section_name():
    html = (
        "<p><strong>Problem:</strong> " + "problem text. " * 40 + "</p>"
        "<p><strong>Resolution:</strong> " + "fix text. " * 40 + "</p>"
    )
    chunks = Chunker(200, 20).chunk_sections(make_article(), extract_sections(html))
    assert [c.index for c in chunks] == list(range(len(chunks)))
    names = [c.metadata["section"] for c in chunks]
    assert names[0] == "Problem" and names[-1] == "Resolution"
    assert names == sorted(names, key=["Problem", "Resolution"].index)  # no interleaving
