# Safe redirect utilities to prevent open redirect vulnerabilities
"""
Security utilities for safely handling redirect URLs to prevent open redirect attacks.

Open redirect vulnerabilities occur when an application redirects to a URL specified
by the user without proper validation, allowing attackers to redirect users to
malicious sites.
"""

import unicodedata
from urllib.parse import unquote, urlparse
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


_MAX_DECODE_ROUNDS = 4
_ALLOWED_ABSOLUTE_SCHEMES = ("http", "https")


def _has_control_chars(value: str) -> bool:
    return any((ord(c) < 32) or (ord(c) == 127) for c in value)


def _log_blocked_redirect(reason: str, target_url: str) -> None:
    current_app.logger.warning("Blocked unsafe redirect (%s): %.200r", reason, target_url)


def _decoded_variants(value: str) -> Optional[list[str]]:
    """
    Return the value plus each successive percent-decoded / NFKC-normalised form.

    Returns None when the value is still changing after ``_MAX_DECODE_ROUNDS``
    (deliberate multi-encoding) so callers can reject it outright.
    """
    variants = [value]
    current = value
    for _ in range(_MAX_DECODE_ROUNDS):
        decoded = unicodedata.normalize("NFKC", unquote(current))
        if decoded == current:
            return variants
        variants.append(decoded)
        current = decoded
    return None


def _is_dangerous_path_form(candidate: str) -> Optional[str]:
    """Return a reason string when a (decoded) URL form can escape the origin."""
    if _has_control_chars(candidate):
        return "control characters"
    if "\\" in candidate:
        return "backslash"
    if candidate != candidate.strip():
        return "leading/trailing whitespace"
    return None


def is_safe_redirect_url(target_url: str) -> bool:
    """
    Validate that a redirect URL is safe (internal only, no external redirects).

    Returns True only for:
    - a root-relative path (``/x``) whose path component contains no ``//``, or
    - an absolute http(s) URL whose host matches the current origin (same rule
      applied to its path).

    Everything else is rejected, including (after repeated percent-decoding and
    NFKC normalisation): protocol-relative ``//host``, ``/\\host`` and other
    backslash forms, ``/%2f/host``, control characters / tab / newline anywhere,
    leading or trailing whitespace, ``javascript:`` / ``data:`` / ``vbscript:``
    or any other scheme, user-info tricks (``http://good@evil``), and values
    that are still changing after several decode rounds.

    Args:
        target_url: The URL to validate

    Returns:
        True if the URL is safe to redirect to, False otherwise
    """
    if not target_url or not isinstance(target_url, str):
        return False

    if not target_url.strip():
        return False

    variants = _decoded_variants(target_url)
    if variants is None:
        _log_blocked_redirect("excessive encoding", target_url)
        return False

    for form in variants:
        reason = _is_dangerous_path_form(form)
        if reason:
            _log_blocked_redirect(reason, target_url)
            return False
        if form.startswith("//"):
            _log_blocked_redirect("protocol-relative", target_url)
            return False

    parsed = urlparse(target_url)
    scheme = (parsed.scheme or "").lower()

    if scheme and scheme not in _ALLOWED_ABSOLUTE_SCHEMES:
        _log_blocked_redirect(f"scheme {scheme}", target_url)
        return False

    if target_url.startswith("/"):
        if parsed.netloc or scheme:
            _log_blocked_redirect("unexpected authority", target_url)
            return False
    else:
        if not parsed.netloc or scheme not in _ALLOWED_ABSOLUTE_SCHEMES:
            _log_blocked_redirect("non-relative", target_url)
            return False
        if "@" in parsed.netloc:
            _log_blocked_redirect("userinfo in authority", target_url)
            return False
        if not _is_same_origin_netloc(parsed.netloc):
            _log_blocked_redirect("external host", target_url)
            return False
        if parsed.path and not parsed.path.startswith("/"):
            _log_blocked_redirect("invalid path", target_url)
            return False

    for form in variants:
        if "//" in urlparse(form).path:
            _log_blocked_redirect("double slash in path", target_url)
            return False

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
