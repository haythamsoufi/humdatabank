import sys
from unittest.mock import patch

from app.services.reports.sanitize_service import sanitize_definition, sanitize_html

PAYLOAD = '<p>ok</p><script>alert(1)</script><img src=x onerror=alert(1)><a href="javascript:alert(1)">x</a>'


def test_sanitize_html_strips_active_content_and_keeps_allowed_tags():
    out = sanitize_html(PAYLOAD)
    assert "<p>ok</p>" in out
    assert "<script" not in out and "onerror" not in out and "javascript:" not in out


def test_sanitize_html_fallback_without_bleach_escapes_everything():
    with patch.dict(sys.modules, {"bleach": None}):
        out = sanitize_html(PAYLOAD)
    assert "<" not in out
    assert "&lt;script&gt;" in out


def test_definition_sanitizes_text_content_translations_and_embed_html():
    definition = {
        "sections": [
            {
                "widgets": [
                    {"type": "text", "content": PAYLOAD, "content_translations": {"fr": PAYLOAD}},
                    {"type": "embed", "embed_html": '<iframe src="https://evil.example"></iframe>' + PAYLOAD},
                    {"type": "kpi"},
                ]
            }
        ]
    }
    result = sanitize_definition(definition)
    widgets = result["sections"][0]["widgets"]
    for text in (widgets[0]["content"], widgets[0]["content_translations"]["fr"], widgets[1]["embed_html"]):
        assert "<script" not in text and "onerror" not in text and "javascript:" not in text
    assert "<iframe" not in widgets[1]["embed_html"]
