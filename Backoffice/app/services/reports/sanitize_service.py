"""Sanitize rich text content for report widgets."""

from __future__ import annotations

import re
from typing import Any


_ALLOWED_TAGS = {
    "p", "br", "strong", "em", "b", "i", "u", "ul", "ol", "li", "a", "span", "div",
    "h1", "h2", "h3", "h4", "table", "thead", "tbody", "tr", "th", "td", "blockquote",
}


def sanitize_html(html: str | None) -> str:
    text = (html or "").strip()
    if not text:
        return ""
    try:
        import bleach

        return bleach.clean(
            text,
            tags=sorted(_ALLOWED_TAGS),
            attributes={"a": ["href", "title", "target", "rel"], "*": ["class", "dir"]},
            protocols=["http", "https", "mailto"],
            strip=True,
        )
    except ImportError:
        return re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.I | re.S)


def sanitize_definition(definition: dict[str, Any]) -> dict[str, Any]:
    for section in definition.get("sections") or []:
        for widget in section.get("widgets") or []:
            if widget.get("type") != "text":
                continue
            translations = widget.get("content_translations") or {}
            if isinstance(translations, dict):
                widget["content_translations"] = {
                    lang: sanitize_html(value) for lang, value in translations.items()
                }
            if widget.get("content"):
                widget["content"] = sanitize_html(widget.get("content"))
            if widget.get("embed_html"):
                widget["embed_html"] = sanitize_html(widget.get("embed_html"))
    return definition
