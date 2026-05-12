# Safe redirect utilities to prevent open redirect vulnerabilities
"""
Security utilities for safely handling redirect URLs to prevent open redirect attacks.

Open redirect vulnerabilities occur when an application redirects to a URL specified
by the user without proper validation, allowing attackers to redirect users to
malicious sites.
"""

from urllib.parse import urlparse
from flask import request, url_for, current_app
from typing import Optional


def get_current_relative_url() -> str:
    """
    Return the current request URL as a relative path (path + optional query string).

    Using a relative URL for `next` avoids false positives in redirect safety checks
    and reduces risk from host/proxy mismatches.
    """
    try:
        qs = request.query_string.decode("utf-8", errors="ignore") if request.query_string else ""
    except Exception as e:
        current_app.logger.debug("query_string decode failed: %s", e)
        qs = ""
    if qs:
        return f"{request.path}?{qs}"
    return request.path


def _is_same_origin_netloc(target_netloc: str) -> bool:
    """
    Check whether an absolute URL netloc (host[:port]) matches the current app origin.
    """
    if not target_netloc:
        return False

    target = target_netloc.strip().lower()
    current = (request.host or "").strip().lower()  # includes port when present

    if target and current and target == current:
        return True

    # Optional fallback to SERVER_NAME if configured (can include port)
    server_name = (current_app.config.get("SERVER_NAME") or "").strip().lower()
    if server_name and target == server_name:
        return True

    # Dev convenience: treat localhost/127.0.0.1/::1 as same host when ports match.
    # This avoids blocking redirects during local dev when the hostname varies.
    def split_host_port(netloc: str) -> tuple[str, str]:
        # Handle IPv6 like [::1]:5000
        if netloc.startswith("["):
            end = netloc.find("]")
            host = netloc[1:end] if end != -1 else netloc
            port = ""
            rest = netloc[end + 1 :] if end != -1 else ""
            if rest.startswith(":"):
                port = rest[1:]
            return host, port
        if ":" in netloc:
            host, port = netloc.rsplit(":", 1)
            return host, port
        return netloc, ""

    target_host, target_port = split_host_port(target)
    current_host, current_port = split_host_port(current)
    localhost_set = {"localhost", "127.0.0.1", "::1"}
    if target_host in localhost_set and current_host in localhost_set and target_port == current_port:
        return True

    return False


def is_safe_redirect_url(target_url: str) -> bool:
    """
    Validate that a redirect URL is safe (internal only, no external redirects).

    Security checks:
    - Must be a relative URL (starts with /), OR an absolute http(s) URL to the same origin
    - No protocol-relative URLs (//evil.com)
    - No external domains
    - No javascript: or data: schemes
    - No null bytes or control characters

    Args:
        target_url: The URL to validate

    Returns:
        True if the URL is safe to redirect to, False otherwise
    """
    if not target_url or not isinstance(target_url, str):
        return False

    # Reject control characters (prevents header injection / request smuggling vectors)
    if any((ord(c) < 32) or (ord(c) == 127) for c in target_url):
        current_app.logger.warning(f"Unsafe redirect URL contains control characters: {target_url}")
        return False

    # Strip whitespace
    target_url = target_url.strip()

    # Reject empty URLs
    if not target_url:
        return False

    # Reject protocol-relative URLs (//evil.com) - these are external
    if target_url.startswith('//'):
        current_app.logger.warning(f"Blocked protocol-relative redirect URL: {target_url}")
        return False

    # Reject dangerous schemes (javascript:, data:, etc.)
    parsed = urlparse(target_url)
    if parsed.scheme and parsed.scheme.lower() not in ("http", "https", ""):
        current_app.logger.warning(f"Blocked redirect URL with dangerous scheme '{parsed.scheme}': {target_url}")
        return False

    # Allow relative URLs (must start with /)
    if target_url.startswith("/"):
        # Reject protocol-relative URLs (//evil.com) - these are external
        if target_url.startswith("//"):
            current_app.logger.warning(f"Blocked protocol-relative redirect URL: {target_url}")
            return False
    else:
        # For non-relative targets, allow only absolute same-origin http(s) URLs.
        parsed = urlparse(target_url)
        scheme = (parsed.scheme or "").lower()
        if parsed.netloc:
            if scheme not in ("http", "https"):
                current_app.logger.warning(f"Blocked redirect URL with non-http scheme '{parsed.scheme}': {target_url}")
                return False
            if not _is_same_origin_netloc(parsed.netloc):
                current_app.logger.warning(f"Blocked external redirect URL: {target_url}")
                return False
            # Ensure it has an internal path
            if parsed.path and not parsed.path.startswith("/"):
                current_app.logger.warning(f"Blocked redirect URL with invalid path: {target_url}")
                return False
        else:
            # Not relative and not a parseable absolute URL -> unsafe (e.g. "admin/page" or "localhost:5000/x")
            current_app.logger.warning(f"Blocked non-relative redirect URL: {target_url}")
            return False

    # Additional check: double slashes inside the PATH can be suspicious (avoid flagging "http://")
    check_path = parsed.path if parsed else target_url
    if isinstance(check_path, str) and "//" in check_path:
        current_app.logger.warning(f"Suspicious redirect URL path with double slashes: {target_url}")

    return True


def get_safe_redirect_url(target_url: Optional[str], default_route: str = 'main.dashboard') -> str:
    """
    Get a safe redirect URL, falling back to a default route if the target is unsafe.

    Args:
        target_url: The target URL to validate
        default_route: The Flask route name to redirect to if target is unsafe

    Returns:
        A safe redirect URL (either the validated target or the default route)
    """
    if target_url and is_safe_redirect_url(target_url):
        return target_url
    else:
        if target_url:
            # Log the blocked redirect attempt for security monitoring
            current_app.logger.warning(
                f"Unsafe redirect URL blocked: {target_url} from {request.remote_addr or 'unknown'}"
            )
        return url_for(default_route)


def safe_redirect(target_url: Optional[str], default_route: str = 'main.dashboard'):
    """
    Safely redirect to a URL, falling back to a default route if the target is unsafe.

    This is a convenience wrapper that validates the URL and creates a redirect response.

    Args:
        target_url: The target URL to validate and redirect to
        default_route: The Flask route name to redirect to if target is unsafe

    Returns:
        Flask redirect response
    """
    from flask import redirect
    safe_url = get_safe_redirect_url(target_url, default_route)
    return redirect(safe_url)
