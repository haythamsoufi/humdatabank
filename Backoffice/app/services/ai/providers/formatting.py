"""
PII scrubbing and AI response formatting for chat routes and services.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any, Dict, List, Optional

import bleach
import markdown
from markupsafe import escape

logger = logging.getLogger(__name__)


_RE_LONG_OPAQUE_TOKEN = re.compile(r"\b[A-Za-z0-9/_+=-]{64,}\b")


def scrub_pii_text(text: str) -> str:
    """
    Best-effort PII redaction for outbound LLM requests.

    Masks everything the AI chat DLP guard detects (same patterns, so the two cannot
    drift apart), plus long opaque tokens that DLP does not flag on their own.
    Not a full DLP system; reduces accidental leakage of obvious identifiers.
    """
    if not text or not isinstance(text, str):
        return ""
    from app.services.ai.chat.dlp import mask_sensitive_text

    return _RE_LONG_OPAQUE_TOKEN.sub("[REDACTED_SECRET]", mask_sensitive_text(text))


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


def _ensure_markdown_list_spacing(text: str) -> str:
    """Insert a blank line before list items so Markdown parsers emit <ul>/<li>."""
    if not text:
        return text
    lines = text.split("\n")
    out: List[str] = []
    for line in lines:
        if re.match(r"^\s*[-*]\s+", line) and out and out[-1].strip() and not re.match(r"^\s*[-*]\s+", out[-1]):
            out.append("")
        out.append(line)
    return "\n".join(out)


def _linkify_indicator_bank_paths(text: str) -> str:
    """Turn bare view/edit paths into markdown links (before HTML escape)."""
    if not text:
        return text
    text = re.sub(
        r'(?<!\]\()(?<![\w"/])/admin/indicator_bank/view/(\d+)\b',
        r"[View indicator](/admin/indicator_bank/view/\1)",
        text,
    )
    text = re.sub(
        r'(?<!\]\()(?<![\w"/])/admin/indicator_bank/edit/(\d+)\b',
        r"[Edit indicator](/admin/indicator_bank/edit/\1)",
        text,
    )
    return text


def _finalize_indicator_action_links(html: str) -> str:
    """Style view/edit links as CTA buttons that open in a new tab."""
    if not html:
        return html

    def _patch_tag(match: re.Match) -> str:
        href = match.group(1)
        return (
            f'<a href="{href}" class="chatbot-show-me" target="_blank" rel="noopener">'
        )

    return re.sub(
        r'<a href="(/admin/indicator_bank/(?:view|edit)/\d+)"[^>]*>',
        _patch_tag,
        html,
        flags=re.IGNORECASE,
    )


_DEFAULT_CHAT_DOCUMENT_HOSTS = (
    "api.ifrc.org",
    "go.ifrc.org",
    "go-api.ifrc.org",
    "ifrc.org",
    "prddsgolocstor01.blob.core.windows.net",
)


def _chat_document_allowed_hosts() -> List[str]:
    """Hosts whose https document links may survive chat HTML sanitization."""
    try:
        from flask import current_app, has_app_context

        if has_app_context():
            configured = current_app.config.get("IFRC_DOCUMENT_ALLOWED_HOSTS") or []
            hosts = [str(h).strip().lower().strip(".") for h in configured if str(h).strip()]
            if hosts:
                return hosts
    except Exception as e:
        logger.debug("chat document allowed hosts: app config unavailable: %s", e)
    return list(_DEFAULT_CHAT_DOCUMENT_HOSTS)


def _is_preserved_chat_href(url: str) -> bool:
    """True for relative app paths or allowlisted https document hosts."""
    u = (url or "").strip()
    if not u:
        return False
    path_part = u.split("#")[0].split("?")[0]
    if u.startswith("/") and "//" not in path_part:
        return True
    if not u.lower().startswith("https://"):
        return False
    try:
        from urllib.parse import urlparse

        parsed = urlparse(u)
        if (parsed.scheme or "").lower() != "https":
            return False
        if parsed.port not in (None, 443):
            return False
        host = (parsed.hostname or "").lower().strip(".")
        if not host:
            return False
        for allowed in _chat_document_allowed_hosts():
            if host == allowed or host.endswith("." + allowed):
                return True
    except Exception as e:
        logger.debug("preserved chat href parse failed: %s", e)
    return False


def _render_structured_sources_block(sources: Optional[List[Dict[str, Any]]]) -> Optional[str]:
    """Sources HTML is always a structured list. The client renders only the chip."""
    if not sources:
        return None
    try:
        from app.utils.ai_sources_parser import render_sources_body_html
        body = render_sources_body_html(sources)
    except Exception as e:
        logger.debug("format_ai_response_for_html: structured sources render failed: %s", e)
        return None
    if not body:
        return None
    return (
        '<div class="chat-response-sources">'
        f'<div class="chat-response-sources-body">{body}</div>'
        "</div>"
    )


def format_ai_response_for_html(
    text: Optional[str],
    provenance_data: Optional[Dict[str, Any]] = None,
    sources: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Convert AI response text to HTML for display. XSS-hardened; allows only
    safe tags and internal links. Optionally appends a provenance block.

    When ``sources`` is a structured list (title/detail/url/page), the Sources
    block is rendered with data-* attributes for reliable client chip/modal UI.
    """
    if not text and not sources:
        return ""
    if not text:
        text = ""

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

    text = _linkify_indicator_bank_paths(text or "")
    text = _ensure_markdown_list_spacing(text or "")

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

    # Sources are always structured rows with data-* attributes. Bleach strips
    # hrefs, so this block is injected after bleach. There is no prose <details> fallback.
    structured_sources = sources if isinstance(sources, list) and sources else None
    sources_safe_html = _render_structured_sources_block(structured_sources)
    if sources_safe_html is None and sources_block_raw is not None:
        try:
            from app.utils.ai_sources_parser import merge_structured_sources
            sources_safe_html = _render_structured_sources_block(
                merge_structured_sources(answer="## Sources\n\n" + sources_block_raw)
            )
        except Exception as e:
            logger.debug("format_ai_response_for_html: structured sources parse failed: %s", e)
            sources_safe_html = None

    if sources_safe_html is not None:
        # Use a marker that will survive bleach (no links inside)
        sources_marker = "IFRC-SOURCES-MARKER-REPLACE-AFTER-BLEACH"
        if sources_placeholder in (html or "") or sources_block_raw is not None:
            html = re.sub(
                rf"(?is)<p>\s*{re.escape(sources_placeholder)}\s*</p>",
                sources_marker,
                html or "",
            )
            html = html.replace(sources_placeholder, sources_marker)
        else:
            # Structured sources without a ## Sources section in the text
            html = (html or "") + sources_marker

    # Append provenance block (HTML) if present.
    if provenance_data:
        html = (html or "") + "<br><br>" + format_provenance_block(provenance_data)

    # Table/download links: bleach with protocols=[] strips all href values.
    # Extract safe relative paths and allowlisted IFRC document https URLs, then
    # re-inject after bleach so emergency-document Download cells stay clickable
    # on web and mobile.
    table_link_placeholders: List[tuple[str, str]] = []

    def _replace_table_links(m: re.Match) -> str:
        url = (m.group(1) or "").strip()
        if not _is_preserved_chat_href(url):
            return m.group(0)
        inner = m.group(2) or ""
        idx = len(table_link_placeholders)
        table_link_placeholders.append((url, inner))
        return f"IFRC-TABLE-LINK-{idx}-END"

    html = re.sub(
        r'<a\s+href="((?:/|https://)[^"]*)"[^>]*>([\s\S]*?)</a>',
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
        path_part = url.split("#")[0].split("?")[0]
        if re.match(r"/admin/indicator_bank/(?:view|edit)/\d+", path_part, re.IGNORECASE):
            link_html = (
                f'<a href="{safe_url}" class="chatbot-show-me" target="_blank" rel="noopener">'
                f"{safe_inner}</a>"
            )
        else:
            link_html = (
                f'<a href="{safe_url}" class="text-blue-600 hover:text-blue-800 underline" '
                f'target="_blank" rel="noopener">{safe_inner}</a>'
            )
        cleaned = cleaned.replace(placeholder, link_html)

    cleaned = _finalize_indicator_action_links(cleaned)
    cleaned = re.sub(
        r'<a href="/admin/indicator_bank(?:[?#][^"]*)?"[^>]*>.*?</a>\s*',
        "",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )

    return (cleaned or "").strip()
