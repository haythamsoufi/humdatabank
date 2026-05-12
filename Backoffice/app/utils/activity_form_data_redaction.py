"""
Redaction and trimming for activity log ``context_data['form_data']``.

Policy: drop known-sensitive keys (passwords, tokens, secrets, CSRF) and
truncate string values so large payloads are not stored verbatim. Keys are
matched case-insensitively for substrings (e.g. ``password_confirm``).
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

# Substrings; if any appears in the lowercased key, the field is omitted.
_SENSITIVE_KEY_SUBSTRINGS: tuple[str, ...] = (
    "password",
    "passwd",
    "secret",
    "token",
    "csrf",
    "api_key",
    "apikey",
    "authorization",
    "credit_card",
    "creditcard",
    "cvv",
    "ssn",
    "otp",
    "recovery_code",
    "private_key",
)

_DEFAULT_MAX_LEN = 100


def _is_sensitive_key(key: str) -> bool:
    k = (key or "").lower()
    return any(s in k for s in _SENSITIVE_KEY_SUBSTRINGS)


def redact_activity_form_data(
    form_items: Iterable[tuple[str, Any]],
    *,
    max_value_len: int = _DEFAULT_MAX_LEN,
) -> Dict[str, Any]:
    """
    Build a safe ``form_data`` dict from Werkzeug form pairs (or any key/value iterable).

    - Drops sensitive keys (see module docstring).
    - Truncates string values to ``max_value_len``; non-strings are stringified then truncated.
    """
    out: Dict[str, Any] = {}
    if not form_items:
        return out
    cap = max(1, int(max_value_len))
    for key, value in form_items:
        if not key or _is_sensitive_key(key):
            continue
        if isinstance(value, str):
            out[key] = value[:cap] + ("..." if len(value) > cap else "")
        else:
            s = str(value)
            out[key] = s[:cap] + ("..." if len(s) > cap else "")
    return out


def redact_activity_form_dict(
    data: Optional[Dict[str, Any]],
    *,
    max_value_len: int = _DEFAULT_MAX_LEN,
) -> Dict[str, Any]:
    """Redact an existing dict (e.g. from JSON); values are copied, not mutated."""
    if not data:
        return {}
    return redact_activity_form_data(data.items(), max_value_len=max_value_len)
