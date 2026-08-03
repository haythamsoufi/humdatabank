"""Shared helpers for reading prefixed multipart form fields in form_builder."""

from __future__ import annotations

from typing import Any, Callable

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


def make_field_reader(form_data, default_prefix: str = '') -> Callable[..., Any]:
    """Return a ``get_field_value(field_name, prefix=...)`` closure for one form payload."""

    def read(field_name: str, prefix: Any = _FIELD_PREFIX_DEFAULT) -> Any:
        effective_prefix = default_prefix if prefix is _FIELD_PREFIX_DEFAULT else prefix
        return get_field_value(form_data, field_name, effective_prefix)

    return read
