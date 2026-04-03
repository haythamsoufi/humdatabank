"""Secure rendering of admin-provided email templates.

Admin-authored Jinja2 templates are rendered with Jinja2's
``SandboxedEnvironment`` to block Server-Side Template Injection (SSTI).
The rendered HTML is then passed through ``bleach`` to strip any remaining
dangerous constructs (``<script>``, event-handler attributes, ``javascript:``
URLs) before the message is delivered.

Usage::

    from app.utils.email_rendering import render_admin_email_template

    html = render_admin_email_template(
        template_str,
        user_name="Alice",
        org_name="Your organization",
    )
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

import bleach
from jinja2.sandbox import SandboxedEnvironment

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Jinja2 sandbox
# ---------------------------------------------------------------------------
# autoescape=True: {{ variable }} values are HTML-escaped by default.
# SandboxedEnvironment: blocks __class__, __mro__, __subclasses__ and similar
# dunder/SSTI chains while still allowing standard template features (loops,
# conditionals, filters, the |safe filter for server-generated markup, etc.).
_sandbox = SandboxedEnvironment(autoescape=True)


def _datetimeformat_filter(value: Any) -> str:
    """Format datetimes for DB-stored email templates (Flask-Babel filter is not available here)."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        try:
            from app.utils.datetime_helpers import ensure_utc

            dt = ensure_utc(value)
            return dt.strftime("%Y-%m-%d %H:%M:%S UTC") if dt else ""
        except Exception:
            return str(value)
    if isinstance(value, date):
        try:
            return value.strftime("%Y-%m-%d")
        except Exception:
            return str(value)
    if hasattr(value, "strftime"):
        try:
            return value.strftime("%Y-%m-%d %H:%M:%S UTC")
        except Exception:
            return str(value)
    return str(value)


_sandbox.filters["datetimeformat"] = _datetimeformat_filter

# ---------------------------------------------------------------------------
# bleach allowlist – all tags acceptable in outbound email HTML, minus the
# dangerous ones (script, iframe, object, embed, form, input, button are
# intentionally absent).
# ---------------------------------------------------------------------------
_ALLOWED_TAGS = list({
    'a', 'abbr', 'acronym', 'address', 'article', 'aside',
    'b', 'bdi', 'bdo', 'blockquote', 'body', 'br',
    'caption', 'center', 'cite', 'code', 'col', 'colgroup',
    'data', 'dd', 'del', 'details', 'dfn', 'div', 'dl', 'dt',
    'em', 'figcaption', 'figure', 'font', 'footer',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'head', 'header', 'hr', 'html',
    'i', 'img', 'ins',
    'kbd',
    'li',
    'main', 'mark', 'meta',
    'nav',
    'ol',
    'p', 'pre',
    'q',
    'rp', 'rt', 'ruby',
    's', 'samp', 'section', 'small', 'span', 'strong', 'style',
    'sub', 'summary', 'sup',
    'table', 'tbody', 'td', 'tfoot', 'th', 'thead', 'time', 'title', 'tr',
    'u', 'ul',
    'var',
    'wbr',
})

# Protocols permitted in href / src attributes.
_SAFE_PROTOCOLS = {'http', 'https', 'mailto', 'tel'}

# Attribute names that carry URLs and must be protocol-checked.
_URL_ATTRS = frozenset({'href', 'src', 'action', 'formaction', 'data'})


def _allow_attr(tag: str, name: str, value: str) -> bool:
    """Bleach attribute callback – blocks event handlers and unsafe URLs."""
    name_lower = name.lower()

    # Block all event-handler attributes (onclick, onload, onmouseover …)
    if name_lower.startswith('on'):
        return False

    # Block javascript: / vbscript: / data: URLs in link/resource attributes.
    if name_lower in _URL_ATTRS:
        stripped = (value or '').strip().lower().lstrip('\x00\t\n\r\x0c ')
        if stripped.startswith(('javascript:', 'vbscript:', 'data:')):
            return False

    return True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_admin_email_template(template_str: str, **context: Any) -> str:
    """Render an admin-provided Jinja2 email template safely.

    Steps:
    1. Compile and render the template string inside ``SandboxedEnvironment``
       (prevents SSTI – attribute traversal to builtins is blocked).
    2. Pass the rendered HTML through ``bleach`` to strip ``<script>`` tags,
       event-handler attributes, and ``javascript:`` URLs.

    Args:
        template_str: Raw Jinja2 template string stored in the settings DB.
        **context: Variables exposed to the template (org_name, user_name, …).

    Returns:
        Sanitised HTML string safe to use as an email body.
        Returns an empty string if the template is blank or fails to render.
    """
    if not template_str or not template_str.strip():
        return ''

    # Step 1 – sandboxed render
    try:
        tmpl = _sandbox.from_string(template_str)
        rendered = tmpl.render(**context)
    except Exception as e:
        logger.error(
            "Admin email template rendering failed: %s",
            e,
            exc_info=True,
        )
        return ''

    # Step 2 – HTML sanitisation of the rendered output
    try:
        return bleach.clean(
            rendered,
            tags=_ALLOWED_TAGS,
            attributes=_allow_attr,
            strip=True,
            strip_comments=False,
        )
    except Exception:
        logger.warning(
            'Post-render HTML sanitisation failed; returning empty body.',
            exc_info=True,
        )
        return ''
