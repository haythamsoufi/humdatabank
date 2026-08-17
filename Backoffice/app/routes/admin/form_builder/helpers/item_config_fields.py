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
    config_raw = request_form.get('config')
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
