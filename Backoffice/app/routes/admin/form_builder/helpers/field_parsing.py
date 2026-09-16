"""Shared helpers for reading prefixed multipart form fields in form_builder."""

from __future__ import annotations

import csv
import io
import json
from typing import Any, Callable, Dict, Iterable, Optional

_FIELD_PREFIX_DEFAULT = object()


def coerce_single_text(value: Any) -> Optional[str]:
    """Flatten a scalar text field that JSON form encoding turned into a list.

    Duplicate ``<textarea name>`` + hidden ``input[name]`` fields become
    ``["msg", "msg"]`` in ``formDataToJson``. Assigned to a Text column,
    psycopg2 stores that as a Postgres array literal
    ``{"msg","msg"}``.
    """
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        last = None
        for item in value:
            coerced = coerce_single_text(item)
            if coerced:
                last = coerced
        return last
    if not isinstance(value, str):
        value = str(value)
    stripped = value.strip()
    if not stripped:
        return None
    unwrapped = _unwrap_duplicate_pg_text_array(stripped)
    return unwrapped if unwrapped is not None else stripped


def _unwrap_duplicate_pg_text_array(raw: str) -> Optional[str]:
    """If *raw* is a PG text-array of identical quoted strings, return that string."""
    if not (raw.startswith('{') and raw.endswith('}')):
        return None
    if ':' in raw:
        return None
    inner = raw[1:-1].strip()
    if not inner:
        return None
    try:
        parts = next(
            csv.reader(io.StringIO(inner), delimiter=',', quotechar='"', escapechar='\\'),
            [],
        )
    except csv.Error:
        return None
    parts = [p.strip() for p in parts if p is not None and str(p).strip()]
    if len(parts) < 2:
        return None
    if len(set(parts)) == 1:
        return parts[0]
    return None


def _scalar_form_value(value: Any, default: Any = None) -> Any:
    """Take the last non-empty entry when JSON form encoding produced a list."""
    if not isinstance(value, (list, tuple)):
        return value
    last = None
    for item in value:
        if item is None:
            continue
        text = item if isinstance(item, str) else str(item)
        if text.strip():
            last = item
    return last if last is not None else default


def get_field_value(form_data, field_name: str, prefix: str = '', default: Any = None) -> Any:
    """
    Read a field from multipart form data, trying ``{prefix}{field_name}`` first.

    Falls back to the unprefixed ``field_name`` when the prefixed value is missing
    or empty. Returns ``default`` when neither key is present.
    Duplicate JSON keys (arrays) are flattened to the last non-empty value.
    """
    if prefix:
        prefixed_name = f"{prefix}{field_name}"
        value = form_data.get(prefixed_name)
        if value is not None and value != '':
            return _scalar_form_value(value, default)
    if field_name in form_data or hasattr(form_data, 'getlist'):
        value = form_data.get(field_name, default)
        return _scalar_form_value(value, default)
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
