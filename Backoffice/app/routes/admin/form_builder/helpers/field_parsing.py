"""Shared helpers for reading prefixed multipart form fields in form_builder."""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, Iterable, Optional

_FIELD_PREFIX_DEFAULT = object()


def get_field_value(form_data, field_name: str, prefix: str = '', default: Any = None) -> Any:
    """
    Read a field from multipart form data, trying ``{prefix}{field_name}`` first.

    Falls back to the unprefixed ``field_name`` when the prefixed value is missing
    or empty. Returns ``default`` when neither key is present.
    """
    if prefix:
        prefixed_name = f"{prefix}{field_name}"
        value = form_data.get(prefixed_name)
        if value is not None and value != '':
            return value
    if field_name in form_data or hasattr(form_data, 'getlist'):
        value = form_data.get(field_name, default)
        return value
    return default


def parse_translations_json(raw: Any, supported_codes: Iterable[str]) -> Optional[Dict[str, str]]:
    """Parse a JSON translations object and keep only supported language codes."""
    if not raw:
        return None
    data = raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
    if not isinstance(data, dict):
        return None
    codes = set(supported_codes)
    filtered: Dict[str, str] = {}
    for key, value in data.items():
        if not (isinstance(key, str) and isinstance(value, str) and value.strip()):
            continue
        code = key.strip().lower().split('_', 1)[0]
        if code in codes:
            filtered[code] = value.strip()
    return filtered or None


def make_field_reader(form_data, default_prefix: str = '') -> Callable[..., Any]:
    """Return a ``get_field_value(field_name, prefix=...)`` closure for one form payload."""

    def read(field_name: str, prefix: Any = _FIELD_PREFIX_DEFAULT) -> Any:
        effective_prefix = default_prefix if prefix is _FIELD_PREFIX_DEFAULT else prefix
        return get_field_value(form_data, field_name, effective_prefix)

    return read
