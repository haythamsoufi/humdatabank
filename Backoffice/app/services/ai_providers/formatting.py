"""
PII scrubbing and AI response formatting for chat routes and services.

Moved from app.services.ai_providers (legacy module) into the ai_providers package
so imports from app.services.ai_providers resolve correctly.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any, Dict, Optional

import bleach
import markdown
from markupsafe import escape

logger = logging.getLogger(__name__)


def scrub_pii_text(text: str) -> str:
    """
    Best-effort PII redaction for outbound LLM requests.
    Not a full DLP system; reduces accidental leakage of obvious identifiers.
    """
    if not text or not isinstance(text, str):
        return ""
    t = text
    t = re.sub(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[REDACTED_EMAIL]", t, flags=re.IGNORECASE)
    t = re.sub(
        r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)",
        lambda m: "[REDACTED_PHONE]" if sum(c.isdigit() for c in m.group(0)) >= 9 else m.group(0),
        t,
    )
    t = re.sub(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b", "[REDACTED_TOKEN]", t)
    t = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._-]{20,}\b", "Bearer [REDACTED_TOKEN]", t)
    t = re.sub(r"\b[A-Za-z0-9/_+=-]{64,}\b", "[REDACTED_SECRET]", t)
    return t


def scrub_pii_context(value: Any) -> Any:
    """Recursively scrub PII in page_context-like structures."""
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        if len(s) > 2000:
            s = s[:2000] + "…"
        return scrub_pii_text(s)
    if isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, list):
        return [scrub_pii_context(v) for v in value[:50]]
    if isinstance(value, dict):
        out = {}
        for i, (k, v) in enumerate(list(value.items())[:50]):
            out[str(k)[:100]] = scrub_pii_context(v)
        return out
    return scrub_pii_text(str(value))


def format_provenance_block(provenance_data: Optional[Dict[str, Any]]) -> str:
    """Format data provenance information as HTML block."""
    if not provenance_data:
        return ""

    def esc(v: Any) -> str:
        return str(escape("" if v is None else str(v)))

    details_id = f"provenance-details-{uuid.uuid4().hex}"
    html_parts = ['<div class="provenance-block mt-3 p-3 bg-gray-50 border-l-4 border-blue-400 text-sm">']
    html_parts.append('<div class="flex items-center mb-2">')
    html_parts.append('<span class="text-blue-600 font-medium">📊 Data Source</span>')
    html_parts.append(
        f'<button type="button" class="ml-auto text-xs text-gray-500 hover:text-gray-700" '
        f'data-action="ui:toggle-next" aria-expanded="false" aria-controls="{details_id}">'
        'Show Details'
        '</button>'
    )
    html_parts.append('</div>')
    html_parts.append(f'<div id="{details_id}" class="hidden text-xs text-gray-600 space-y-1">')

    if 'source' in provenance_data:
        html_parts.append(f'<div><strong>Source:</strong> {esc(provenance_data.get("source"))}</div>')
    if 'query_time' in provenance_data:
        html_parts.append(f'<div><strong>Query Time:</strong> {esc(provenance_data.get("query_time"))}</div>')
    if 'filters' in provenance_data and provenance_data['filters']:
        try:
            items = provenance_data.get("filters", {}).items()
        except Exception as e:
            logger.debug("format_provenance_block: filters items failed: %s", e)
            items = []
        filters_str = ', '.join([f"{esc(k)}: {esc(v)}" for k, v in items])
        html_parts.append(f'<div><strong>Filters Applied:</strong> {filters_str}</div>')
    if 'record_count' in provenance_data:
        html_parts.append(f'<div><strong>Records Found:</strong> {esc(provenance_data.get("record_count"))}</div>')
    if 'aggregation' in provenance_data:
        html_parts.append(f'<div><strong>Aggregation:</strong> {esc(provenance_data.get("aggregation"))}</div>')
    if 'time_period' in provenance_data:
        html_parts.append(f'<div><strong>Time Period:</strong> {esc(provenance_data.get("time_period"))}</div>')
    if 'exclusions' in provenance_data and provenance_data['exclusions']:
        html_parts.append(f'<div><strong>Excluded:</strong> {esc(provenance_data.get("exclusions"))}</div>')

    html_parts.append('</div>')
    html_parts.append('</div>')
    return ''.join(html_parts)


def format_ai_response_for_html(text: Optional[str], provenance_data: Optional[Dict[str, Any]] = None) -> str:
    """
    Convert AI response text to HTML for display. XSS-hardened; allows only
    safe tags and internal links. Optionally appends a provenance block.
    """
    if not text:
        return ""

    # Remove duplicate / code-like patterns
    try:
        t = str(text).strip()
        if len(t) > 200:
            prefix = t[:160]
            repeat_at = t.find(prefix, 160)
            if repeat_at != -1 and repeat_at > 200:
                candidate = t[:repeat_at].rstrip()
                if len(candidate) > int(len(t) * 0.4):
                    text = candidate
    except Exception as e:
        logger.debug("format_ai_response_for_html: duplicate pattern trim failed: %s", e)

    text = re.sub(r'```python\s*print\([^)]+\)\s*```', '', text or '', flags=re.IGNORECASE)
    text = re.sub(r'```python\s*get_[^)]+\)\s*```', '', text or '', flags=re.IGNORECASE)
    text = re.sub(r'```\s*print\([^)]+\)\s*```', '', text or '', flags=re.IGNORECASE)
    text = re.sub(r'(?im)^\s*i can help you with that\.\s*$', '', text or '')
    text = re.sub(r'(?im)^\s*please wait .*retrieve.*\s*$', '', text or '')
    text = re.sub(r'(?im)^\s*i\s*(?:am|\'m)?\s*calling\s*`?get_value_breakdown`?.*$', '', text or '')
    text = re.sub(r'(?im)^\s*i\s*(?:am|\'m)?\s*calling\s*`?get_[a-z_]+`?.*$', '', text or '')
    text = re.sub(r'I need to call the data function\.\s*```[^`]+```', 'I will retrieve that information for you.', text or '', flags=re.IGNORECASE)

    # Last-resort defense: strip leaked agent step traces (Thought/Action/Observation patterns)
    text = re.sub(r'(?m)^---\s*Step\s*\d+\s*---\s*$', '', text or '')
    text = re.sub(r'(?m)^Timestamp:\s+\d{4}-\d{2}-\d{2}T[\d:.+Z-]+\s*$', '', text or '')
    text = re.sub(r'(?m)^Action [Ii]nput:\s*$', '', text or '')
    text = re.sub(r'(?m)^Observation:\s*$', '', text or '')

    def esc(v: Any) -> str:
        return str(escape("" if v is None else str(v)))

    # NOTE: Historically we used regex-based "markdown-ish" formatting here.
    # That approach is brittle (e.g. years like "2024. " were mis-detected as list items).
    # We now parse Markdown with a real parser and sanitize the resulting HTML.
    sources_placeholder = "IFRC-AI-SOURCES-PLACEHOLDER"
    sources_block_raw = None
    stop_at = (
        r"(?=\n\s*\n\s*(?:If you want, I can|If you'd like|Which would you prefer\?|Which format do you prefer\?|\*\*Notes?\s*/\s*next steps\b)"
        r"|\n\s*(?:If you want, I can|If you'd like)"
        r"|\Z)"
    )
    sources_match = re.search(
        r"(?m)^(#{2,3}\s*Sources\s*)\s*$(.+?)" + stop_at,
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if sources_match:
        sources_block_raw = sources_match.group(2).strip()
        text = text[: sources_match.start()].rstrip() + "\n\n" + sources_placeholder + "\n"

    # Lightweight readability: promote standalone "section heading" lines to bold (markdown),
    # while avoiding list items ("- x", "* x", "1. x") which markdown will format as lists.
    try:
        text = re.sub(
            r"(?m)^(?!\s*(?:[-*]|\d{1,3}\.)\s)([A-Za-z][A-Za-z /(),–—-]{2,60})$",
            r"**\1**",
            text,
        )
    except Exception as e:
        logger.debug("format_ai_response_for_html: heading regex failed: %s", e)

    # Markdown → HTML (then sanitize). Prefer "chat-friendly" behavior where single newlines become <br>.
    try:
        md_input = str(esc(text))
        html = markdown.markdown(
            md_input,
            extensions=[
                "tables",
                "sane_lists",
                "nl2br",
            ],
            output_format="html5",
        )
    except Exception as e:
        logger.debug("markdown rendering failed: %s", e)
        html = esc(text).replace("\n", "<br>")

    # Sources block: build with our own link conversion so relative URLs survive.
    # Bleach with protocols=[] strips ALL href values (including relative); we inject
    # Sources after bleach with links we validate ourselves (only allow paths starting with /).
    sources_safe_html = None
    if sources_block_raw is not None:
        try:
            sources_escaped = str(esc(sources_block_raw))
            # Convert [label](url) to <a> only when url is a safe relative path; do this
            # before markdown/bleach so our links are never touched by bleach.
            def _safe_link(m: re.Match) -> str:
                label, url = m.group(1) or "", (m.group(2) or "").strip()
                path_part = url.split("#")[0].split("?")[0]
                if url.startswith("/") and "//" not in path_part:
                    return f'<a href="{escape(url)}" class="text-blue-600 hover:text-blue-800 underline" target="_blank" rel="noopener">{escape(label)}</a>'
                return escape(label)
            sources_with_links = re.sub(
                r"\[([^\]]*)\]\((https?://[^)\s]+|/[^)\s]*)\)",
                _safe_link,
                sources_escaped,
                flags=re.IGNORECASE,
            )
            # Strip markdown bold ** so the first source is not emphasized
            sources_with_links = sources_with_links.replace("**", "")
            sources_body_safe = sources_with_links.replace("\n", "<br>")
            sources_safe_html = (
                '<details class="chat-response-sources mt-2 border border-gray-200 rounded p-2 bg-gray-50">'
                '<summary class="cursor-pointer font-medium text-gray-700">Sources</summary>'
                f'<div class="chat-response-sources-body mt-2 text-sm text-gray-600">{sources_body_safe}</div>'
                "</details>"
            )
        except Exception as e:
            logger.debug("format_ai_response_for_html: sources block link conversion failed: %s", e)
            sources_body_esc = esc(sources_block_raw).replace("**", "").replace("\n", "<br>")
            sources_safe_html = (
                '<details class="chat-response-sources mt-2 border border-gray-200 rounded p-2 bg-gray-50">'
                '<summary class="cursor-pointer font-medium text-gray-700">Sources</summary>'
                f'<div class="chat-response-sources-body mt-2 text-sm text-gray-600">{sources_body_esc}</div>'
                "</details>"
            )
        # Use a marker that will survive bleach (no links inside)
        sources_marker = "IFRC-SOURCES-MARKER-REPLACE-AFTER-BLEACH"
        html = re.sub(
            rf"(?is)<p>\s*{re.escape(sources_placeholder)}\s*</p>",
            sources_marker,
            html,
        )
        html = html.replace(sources_placeholder, sources_marker)

    # Append provenance block (HTML) if present.
    if provenance_data:
        html = (html or "") + "<br><br>" + format_provenance_block(provenance_data)

    # Table links: bleach with protocols=[] strips all href values. Extract <a href="/path">content</a>
    # (safe relative paths only) and replace with placeholders; re-inject after bleach.
    table_link_placeholders = []

    def _replace_table_links(m: re.Match) -> str:
        url = (m.group(1) or "").strip()
        path_part = url.split("#")[0].split("?")[0]
        if url.startswith("/") and "//" not in path_part:
            inner = m.group(2) or ""
            idx = len(table_link_placeholders)
            table_link_placeholders.append((url, inner))
            return f"IFRC-TABLE-LINK-{idx}-END"
        return m.group(0)

    html = re.sub(
        r'<a\s+href="(/[^"]*)"[^>]*>([\s\S]*?)</a>',
        _replace_table_links,
        html or "",
        flags=re.IGNORECASE,
    )

    # Sanitize the final HTML. We intentionally allow only relative links (no schemes),
    # and keep a small allowlist of tags needed by the chat UI.
    allowed_tags = [
        "p",
        "br",
        "strong",
        "b",
        "em",
        "i",
        "u",
        "ul",
        "ol",
        "li",
        "div",
        "span",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "a",
        "table",
        "thead",
        "tbody",
        "tr",
        "th",
        "td",
        "details",
        "summary",
    ]
    allowed_attrs = {
        "*": ["class"],
        "a": ["href", "title", "class"],
        "th": ["colspan", "rowspan", "class"],
        "td": ["colspan", "rowspan", "class"],
        "table": ["class"],
        "details": ["class"],
        "summary": ["class"],
        "div": ["class"],
        "span": ["class"],
    }

    cleaned = bleach.clean(
        html or "",
        tags=allowed_tags,
        attributes=allowed_attrs,
        protocols=[],  # disallow absolute URL schemes like http(s):; allow relative links only
        strip=True,
    )

    # Extra-hardening: ensure any remaining href is relative / anchor / query only.
    # (Bleach with protocols=[] already removes scheme URLs, but keep this as defense-in-depth.)
    try:
        cleaned = re.sub(
            r'(?i)\s+href="(?!/|#|\?)[^"]*"',
            "",
            cleaned,
        )
    except Exception as e:
        logger.debug("format_ai_response_for_html: extra href hardening failed: %s", e)

    # Inject Sources block after bleach so our safe relative links are never stripped
    if sources_safe_html is not None:
        cleaned = cleaned.replace("IFRC-SOURCES-MARKER-REPLACE-AFTER-BLEACH", sources_safe_html)

    # Re-inject table links (placeholders survived bleach as plain text)
    for idx, (url, inner) in enumerate(table_link_placeholders):
        placeholder = f"IFRC-TABLE-LINK-{idx}-END"
        safe_url = escape(url)
        safe_inner = inner  # inner was captured from HTML; we re-inject as-is (originated from markdown)
        link_html = f'<a href="{safe_url}" class="text-blue-600 hover:text-blue-800 underline" target="_blank" rel="noopener">{safe_inner}</a>'
        cleaned = cleaned.replace(placeholder, link_html)

    return (cleaned or "").strip()
