"""
Redaction and trimming for activity log ``context_data['form_data']``.

Policy: drop sensitive keys and truncate string values so large payloads are not
stored verbatim. Which keys are sensitive is decided by the shared policy in
``app.utils.logging_security`` (case-, separator- and camelCase-insensitive, e.g.
``password_confirm``, ``newPassword``, ``X-Api-Key``), so activity logs, API usage
rows and error/security events all redact the same way.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from app.utils.logging_security import is_sensitive_key, sanitize_for_logging

_DEFAULT_MAX_LEN = 100


def _is_sensitive_key(key: str) -> bool:
    return is_sensitive_key(key)


def _clip(value: Any, cap: int) -> str:
    text = sanitize_for_logging(value, max_length=10**9) if isinstance(value, str) else str(value)
    return text[:cap] + ("..." if len(text) > cap else "")


def redact_activity_form_data(
    form_items: Iterable[tuple[str, Any]],
    *,
    max_value_len: int = _DEFAULT_MAX_LEN,
) -> Dict[str, Any]:
    """
    Build a safe ``form_data`` dict from Werkzeug form pairs (or any key/value iterable).

    - Drops sensitive keys (see module docstring).
    - Masks inline credentials (bearer tokens, JWTs, ``password=...``) inside values.
    - Truncates string values to ``max_value_len``; non-strings are stringified then truncated.
    """
    out: Dict[str, Any] = {}
    if not form_items:
        return out
    cap = max(1, int(max_value_len))
    for key, value in form_items:
        if not key or _is_sensitive_key(key):
            continue
        out[key] = _clip(value, cap)
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
