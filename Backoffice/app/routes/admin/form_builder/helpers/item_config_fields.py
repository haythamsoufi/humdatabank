"""Declarative registry for item-modal config boolean fields.

Category B (preserve-existing): when a field is absent from the request the
stored config value is kept.  The frontend must send explicit ``"true"`` /
``"false"`` hidden inputs for these keys (see config-checkbox-serializer.js).

Keep ``PRESERVE_EXISTING_BOOL_FIELDS`` in sync with ``CONFIG_CHECKBOXES`` in
``app/static/js/form_builder/modules/modal/config-checkbox-serializer.js``.
Guardrail tests enforce that sync.
"""

from __future__ import annotations

import json
from typing import Any, Mapping, MutableMapping

# Keys parsed by _update_item_config with preserve-existing semantics.
PRESERVE_EXISTING_BOOL_FIELDS: tuple[str, ...] = (
    'allow_over_100',
    'unique_options_in_section',
    'use_as_repeat_entry_title',
    'exclude_from_completion_rate',
    'allow_other',
    'limit_entries_to_option_count',
)

# Category A: pre-bound in edit_item from request, then read via WTForms .data.
# Absent key → False (never preserves).  Listed here for guardrail tests only.
WT_FORMS_BOOL_FIELDS: frozenset[str] = frozenset({
    'is_required',
    'layout_break_after',
    'allow_data_not_available',
    'allow_not_applicable',
    'allow_disability_questions',
    'indirect_reach',
})

# Category C: presence-based in _update_item_config; absent → False + strip sub-keys.
PRESENCE_BASED_BOOL_FIELDS: frozenset[str] = frozenset({
    'carry_forward',
    'show_hint',
})

_TRUTHY = frozenset({'true', 'on', '1', True, 1})


def parse_request_bool(request_form: Mapping[str, Any], key: str, *, default: bool = False) -> bool:
    """Parse an explicit boolean from the request; absent keys use *default*."""
    if key not in request_form:
        return default
    return request_form.get(key) in _TRUTHY


def parse_preserve_existing_bool(
    existing_cfg: Mapping[str, Any],
    request_form: Mapping[str, Any],
    key: str,
    *,
    default: bool = False,
) -> bool:
    """Resolve a Category-B boolean from request data or keep the stored value."""
    value = bool(existing_cfg.get(key, default))
    if key in request_form:
        return request_form.get(key) in _TRUTHY
    for blob_key in ('config', 'matrix_config'):
        config_raw = request_form.get(blob_key)
        if config_raw:
            try:
                config_json = json.loads(config_raw)
                if isinstance(config_json, dict) and key in config_json:
                    return bool(config_json.get(key, False))
            except (json.JSONDecodeError, TypeError):
                pass
    return value


def apply_preserve_existing_bools(
    config: MutableMapping[str, Any],
    request_form: Mapping[str, Any],
) -> None:
    """Write all Category-B booleans into *config* in place."""
    for key in PRESERVE_EXISTING_BOOL_FIELDS:
        config[key] = parse_preserve_existing_bool(config, request_form, key)


def apply_wtforms_bools_from_request(
    config: MutableMapping[str, Any],
    request_form: Mapping[str, Any],
) -> None:
    """Apply Category-A booleans from the raw request (create path)."""
    for key in WT_FORMS_BOOL_FIELDS:
        if key in request_form:
            config[key] = parse_request_bool(request_form, key)


def parse_layout_column_width(request_form: Mapping[str, Any], *, default: str = '12') -> str:
    raw = request_form.get('layout_column_width')
    if raw is None or str(raw).strip() == '':
        return default
    return str(raw)


def parse_privacy(request_form: Mapping[str, Any], *, default: str = 'ifrc_network') -> str:
    raw = (request_form.get('privacy') or '').strip().lower()
    return raw if raw in ('public', 'ifrc_network') else default


def parse_max_other_entries(request_form: Mapping[str, Any]) -> int:
    try:
        return max(0, int(request_form.get('max_other_entries', 0)))
    except (ValueError, TypeError):
        return 0


def build_create_config_base(request_form: Mapping[str, Any]) -> dict[str, Any]:
    """Shared config keys for the create-item path (mirrors _update_item_config core)."""
    config: dict[str, Any] = {
        'is_required': parse_request_bool(request_form, 'is_required'),
        'layout_column_width': parse_layout_column_width(request_form),
        'layout_break_after': parse_request_bool(request_form, 'layout_break_after'),
        'allow_data_not_available': parse_request_bool(request_form, 'allow_data_not_available'),
        'allow_not_applicable': parse_request_bool(request_form, 'allow_not_applicable'),
        'allow_disability_questions': parse_request_bool(request_form, 'allow_disability_questions'),
        'indirect_reach': parse_request_bool(request_form, 'indirect_reach'),
        'privacy': parse_privacy(request_form),
        'max_other_entries': parse_max_other_entries(request_form),
    }
    apply_preserve_existing_bools(config, request_form)
    return config
