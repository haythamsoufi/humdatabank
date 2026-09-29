"""Allowlist validation for externally sourced document URLs.

Used both before fetching a remote document server-side (SSRF) and before sending a
browser to one (open redirect / phishing). Values such as ``SubmittedDocument.source_url``
are synced from third-party systems and must be treated as untrusted.
"""

from __future__ import annotations

from flask import current_app

from app.utils.outbound_url import validate_outbound_url


def validate_allowlisted_https_url(url: str) -> tuple[bool, str]:
    """Allow only ``https`` URLs on the default port whose host is in ``IFRC_DOCUMENT_ALLOWED_HOSTS``.

    Returns ``(ok, reason)``; ``reason`` is empty when ``ok`` is true. Fails closed when
    no hosts are configured. Built on :mod:`app.utils.outbound_url`; additionally rejects
    whitespace/control characters, which have no place in a URL emitted in a ``Location`` header.
    """
    u = (url or "").strip()
    if not u:
        return False, "URL is required"
    if any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in u):
        return False, "Invalid URL"

    allowed_hosts = current_app.config.get("IFRC_DOCUMENT_ALLOWED_HOSTS") or []
    result = validate_outbound_url(
        u,
        allowed_hosts=[str(h) for h in allowed_hosts],
        allowed_ports=(443,),
        resolve_dns=False,
    )
    if result.ok:
        return True, ""
    if result.reason == "Outbound host allow-list is not configured":
        return False, "External document import is not configured (no allowed hosts)"
    return False, result.reason


def safe_external_redirect_target(url: str | None) -> str | None:
    """Return *url* stripped when it passes :func:`validate_allowlisted_https_url`, else ``None``."""
    candidate = (url or "").strip()
    ok, _reason = validate_allowlisted_https_url(candidate)
    return candidate if ok else None
