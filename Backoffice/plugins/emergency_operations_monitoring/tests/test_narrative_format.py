"""Chapters are stored as a closed subset of HTML, and older plain text still reads."""

from __future__ import annotations

import pytest

from plugins.emergency_operations_monitoring.services import narrative_format as nf

pytestmark = pytest.mark.unit


def test_plain_text_becomes_paragraphs_and_lists():
    html = nf.to_html("First paragraph.\n\nSecond line one\nline two\n\n- one\n- two\n\n1. first\n2. second")
    assert html == (
        "<p>First paragraph.</p>"
        "<p>Second line one<br>line two</p>"
        "<ul><li>one</li><li>two</li></ul>"
        "<ol><li>first</li><li>second</li></ol>"
    )


def test_only_the_allowed_tags_survive():
    html = nf.to_html(
        '<p onclick="x()">Hello <strong>bold</strong> <em>it</em> <a href="javascript:alert(1)">link</a></p>'
        "<script>alert(1)</script><img src=x onerror=alert(1)>"
        '<p><span style="font-weight: bold; color: red">B</span>&nbsp;& <z></p>'
    )
    assert html == (
        "<p>Hello <strong>bold</strong> <em>it</em> link</p>"
        '<p><span style="color:#ff0000"><strong>B</strong></span> &amp;</p>'
    )
    assert "script" not in html and "onclick" not in html and "javascript" not in html


def test_links_colour_highlight_and_strike_round_trip_and_unsafe_links_do_not():
    html = nf.to_html(
        '<p>See <a href="https://example.org/a?b=1&c=2" onclick="x()">the update</a>, '
        '<span style="color: rgb(224, 62, 45); background-color: #ff0">this</span> '
        "and <s>the old line</s>.</p>"
        '<p><a href="javascript:alert(1)">no</a> <a href="mailto:desk@example.org">mail</a></p>'
    )
    assert html == (
        '<p>See <a href="https://example.org/a?b=1&amp;c=2" target="_blank" rel="noopener noreferrer">the update</a>, '
        '<span style="color:#e03e2d;background-color:#ffff00">this</span> '
        "and <s>the old line</s>.</p>"
        "<p>no "
        '<a href="mailto:desk@example.org" target="_blank" rel="noopener noreferrer">mail</a></p>'
    )
    assert nf.to_html(html) == html
    assert "javascript" not in html and "onclick" not in html


def test_marks_nest_in_a_fixed_order_and_empty_paragraphs_go():
    assert nf.to_html("<p><u><strong>x</strong></u></p><p><br data-mce-bogus='1'></p><p>   </p>") == (
        "<p><u><strong>x</strong></u></p>"
    )


def test_a_nested_list_is_flattened_into_one_list():
    assert nf.to_html("<ol><li>a<ul><li>b</li></ul></li><li>c</li></ol>") == (
        "<ol><li>a</li><li>b</li><li>c</li></ol>"
    )


def test_plain_text_for_go_and_the_model_keeps_list_markers():
    html = "<p>Intro</p><ul><li>one</li><li>two</li></ul><ol><li>x</li><li>y</li></ol>"
    assert nf.to_plain(html) == "Intro\n\n- one\n- two\n\n1. x\n2. y"
    assert nf.word_count(html) == 5


def test_the_stored_form_is_stable_so_a_round_trip_changes_nothing():
    original = "Water reached the clinic.\n\n- Beds lost\n- Stock lost"
    once = nf.to_html(original)
    assert nf.to_html(once) == once
    assert nf.same(original, once)
    assert nf.same("", None) and not nf.same("a", "b")


def test_a_long_chapter_is_clipped_on_a_paragraph_edge_when_asked():
    text = "\n\n".join(f"Paragraph number {index} with enough words to count." for index in range(40))
    clipped = nf.to_plain(nf.to_html(text, limit=300))
    assert len(clipped) <= 300
    assert clipped.startswith("Paragraph number 0")
    assert nf.too_long("x" * (nf.CHAPTER_LIMIT + 1)) and not nf.too_long("short")
