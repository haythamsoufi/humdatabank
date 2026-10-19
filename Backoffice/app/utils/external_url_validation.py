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


# Hosts a Manage Resources row may point at instead of an uploaded file.
# YouTube is not on ``IFRC_DOCUMENT_ALLOWED_HOSTS``: that list is also used to
# fetch documents server-side, and a video link must never be downloaded as a file.
_RESOURCE_LINK_HOSTS = (
    "youtube.com",
    "youtu.be",
    "youtube-nocookie.com",
)


def resource_link_hosts() -> list[str]:
    """YouTube plus the configured IFRC document hosts."""
    configured = current_app.config.get("IFRC_DOCUMENT_ALLOWED_HOSTS") or []
    hosts: list[str] = list(_RESOURCE_LINK_HOSTS)
    for host in configured:
        text = str(host or "").strip().lower().strip(".")
        if text and text not in hosts:
            hosts.append(text)
    return hosts


def resource_external_url_error(url: str | None) -> str:
    """Empty string when *url* is blank or an allowed https link; otherwise the reason."""
    candidate = (url or "").strip()
    if not candidate:
        return ""
    if any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in candidate):
        return "Invalid URL"
    result = validate_outbound_url(
        candidate,
        allowed_hosts=resource_link_hosts(),
        allowed_ports=(443,),
        resolve_dns=False,
    )
    if result.ok:
        return ""
    if result.reason == "Outbound host allow-list is not configured":
        return "This link host is not allowed"
    return result.reason or "Invalid URL"


def safe_resource_external_url(url: str | None) -> str | None:
    """Return a stored resource link when it is safe to show or redirect to."""
    candidate = (url or "").strip()
    if not candidate or not isinstance(url, str):
        return None
    if resource_external_url_error(candidate):
        return None
    return candidate


def is_youtube_url(url: str | None) -> bool:
    """True when *url* is an allowlisted YouTube link."""
    candidate = safe_resource_external_url(url)
    if not candidate:
        return False
    from urllib.parse import urlparse

    host = (urlparse(candidate).hostname or "").lower()
    return host == "youtu.be" or host.endswith(".youtu.be") or host == "youtube.com" or host.endswith(".youtube.com") or host.endswith(".youtube-nocookie.com")
