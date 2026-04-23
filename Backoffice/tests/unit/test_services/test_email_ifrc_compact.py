"""Unit tests for IFRC email HTML compaction (gateway body size limits)."""

from app.services.email.client import _compact_ifrc_html_body


def test_compact_preserves_meaningful_content():
    html = "<div>\n  <p>Hello</p>\n  <!-- c -->\n  <p>World</p>\n</div>"
    out = _compact_ifrc_html_body(html)
    assert "<!--" not in out
    assert "Hello" in out and "World" in out
    assert out == "<div><p>Hello</p><p>World</p></div>"


def test_compact_squishes_style_block():
    html = (
        "<html><head><style>\n"
        "body { margin: 0; }\n"
        ".a { color: red; }\n"
        "</style></head><body><p>x</p></body></html>"
    )
    out = _compact_ifrc_html_body(html)
    assert "\n" not in out or out.count("\n") <= 0
    assert "body { margin: 0; }" in out
    assert ".a { color: red; }" in out


def test_compact_reduces_utf8_size_on_verbose_template():
    # Mimics pretty-printed email HTML with bulky CSS
    lines = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        "<style>",
        "    body { margin: 0; padding: 0; }",
        "    .email-outer { max-width: 960px; }",
        "</style>",
        "</head>",
        "<body>",
        "<div class='email-outer'>",
        "    <p>Line one</p>",
        "    <p>Line two</p>",
        "</div>",
        "</body>",
        "</html>",
    ]
    raw = "\n".join(lines)
    compact = _compact_ifrc_html_body(raw)
    assert len(compact.encode("utf-8")) < len(raw.encode("utf-8"))


def test_compact_empty_and_whitespace():
    assert _compact_ifrc_html_body("") == ""
    assert _compact_ifrc_html_body("   \n  ") == ""
