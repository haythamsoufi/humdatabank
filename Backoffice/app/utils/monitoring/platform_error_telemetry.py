"""Sanitize ajax-save / WAF 403 telemetry for platform-error security events.

Kept free of Flask imports so unit tests can load this module without the
app stack. The WAF blocks ``?ajax=1`` before Flask sees the body; the
browser reporter is the only place that saw the payload and which
``ajax-save.js`` actually ran. These helpers turn that untrusted JSON into
``SecurityEvent.context_data`` keys and description fragments.
"""

from __future__ import annotations

from typing import Optional

_VERSION_TOKEN_ALLOWED = frozenset(
    'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-+'
)
_FIELD_NAME_ALLOWED = frozenset(
    'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789[]_.-'
)
_SCRIPT_DELIVERY_ALLOWED = frozenset({'disk_cache', 'network'})
_MAX_UNWRAPPED_FIELD_NAMES = 15

_INT_FIELDS = (
    ('request_field_count', 100_000),
    ('request_approx_bytes', 500_000_000),
    ('request_b64_field_count', 100_000),
    ('request_unwrapped_field_count', 100_000),
    ('request_longest_field_bytes', 500_000_000),
    ('ajax_save_script_transfer_size', 50_000_000),
)


def strip_control_chars(value, *, max_len: int) -> Optional[str]:
    """Remove control characters to reduce log-forging risk."""
    if not value:
        return None
    s = str(value).replace('\r', ' ').replace('\n', ' ').replace('\t', ' ').strip()
    if not s:
        return None
    return s[:max_len]


def clamp_optional_int(value, *, max_value: int) -> Optional[int]:
    """Coerce untrusted numeric telemetry to a bounded non-negative int."""
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed < 0:
        return None
    return min(parsed, max_value)


def _sanitize_token(value, *, allowed: frozenset, max_len: int) -> Optional[str]:
    text = strip_control_chars(value, max_len=max_len)
    if not text:
        return None
    cleaned = ''.join(ch for ch in text if ch in allowed)
    return cleaned[:max_len] or None


def sanitize_version_token(value) -> Optional[str]:
    """Sanitize deploy / content-hash tokens like ``abc123.deadbeef0123``."""
    return _sanitize_token(value, allowed=_VERSION_TOKEN_ALLOWED, max_len=128)


def sanitize_form_field_name(value) -> Optional[str]:
    """Sanitize a FormData field name (never a value) for security-event context."""
    return _sanitize_token(value, allowed=_FIELD_NAME_ALLOWED, max_len=200)


def sanitize_script_delivery(value) -> Optional[str]:
    """Allow only the cache-vs-network labels the reporter emits."""
    text = strip_control_chars(value, max_len=40)
    if not text:
        return None
    return text if text in _SCRIPT_DELIVERY_ALLOWED else None


def sanitize_field_name_list(value) -> Optional[list]:
    """Sanitize a short list of FormData field names (no values)."""
    if not isinstance(value, list):
        return None
    names = []
    for item in value[:_MAX_UNWRAPPED_FIELD_NAMES]:
        cleaned = sanitize_form_field_name(item)
        if cleaned:
            names.append(cleaned)
    return names or None


def sanitize_ajax_save_telemetry(data: dict) -> dict:
    """Return sanitized non-URL telemetry keys present on a platform-error body.

    URL fields (``page_url``, ``ajax_save_script_url``) are left to the
    caller — they need the existing ``sanitize_url()`` (scheme allow-list).
    """
    if not isinstance(data, dict):
        return {}

    out: dict = {}
    for key, max_value in _INT_FIELDS:
        parsed = clamp_optional_int(data.get(key), max_value=max_value)
        if parsed is not None:
            out[key] = parsed

    longest_name = sanitize_form_field_name(data.get('request_longest_field_name'))
    if longest_name:
        out['request_longest_field_name'] = longest_name

    unwrapped_names = sanitize_field_name_list(data.get('request_unwrapped_field_names'))
    if unwrapped_names:
        out['request_unwrapped_field_names'] = unwrapped_names

    asset_version = sanitize_version_token(data.get('asset_version'))
    if asset_version:
        out['asset_version'] = asset_version

    script_version = sanitize_version_token(data.get('ajax_save_script_version'))
    if script_version:
        out['ajax_save_script_version'] = script_version

    delivery = sanitize_script_delivery(data.get('ajax_save_script_delivery'))
    if delivery:
        out['ajax_save_script_delivery'] = delivery

    response_server = strip_control_chars(data.get('response_server'), max_len=200)
    if response_server:
        out['response_server'] = response_server

    return out


def format_platform_error_description_extras(telemetry: dict) -> list[str]:
    """Human-readable fragments for the ``platform_*`` security-event description."""
    extras: list[str] = []
    if not isinstance(telemetry, dict):
        return extras

    field_count = telemetry.get('request_field_count')
    approx_bytes = telemetry.get('request_approx_bytes')
    if field_count is not None or approx_bytes is not None:
        size_kb = f'{approx_bytes / 1024:.1f}KB' if approx_bytes is not None else 'unknown size'
        fields = f'{field_count} fields' if field_count is not None else 'unknown field count'
        extras.append(f'request body: ~{size_kb}, {fields}')

    asset_version = telemetry.get('asset_version')
    if asset_version:
        extras.append(f'asset v={asset_version}')

    script_version = telemetry.get('ajax_save_script_version')
    if script_version:
        extras.append(f'ajax-save.js v={script_version}')

    b64_count = telemetry.get('request_b64_field_count')
    unwrapped_count = telemetry.get('request_unwrapped_field_count')
    if b64_count is not None or unwrapped_count is not None:
        wrapped = b64_count if b64_count is not None else '?'
        unwrapped = unwrapped_count if unwrapped_count is not None else '?'
        extras.append(f'{wrapped} b64-wrapped, {unwrapped} unwrapped wrap-candidates')

    return extras
