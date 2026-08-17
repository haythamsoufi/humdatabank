"""Server-side (metadata-only) evaluation of ``relevance_condition`` rules.

``FormSection.relevance_condition`` / ``FormItem.relevance_condition`` store the
same JSON rule shape evaluated client-side in
``app/static/js/forms/modules/conditions.js``::

    {"logic": "AND"|"OR", "conditions": [{"item_id": ..., "condition_type": ..., "value": ...}, ...]}

The client can evaluate ANY such rule because it has live DOM state (other
question answers on the page) and plugin-published variables
(``window.__ifrcPluginVariables``). The server only reliably knows the
built-in *metadata* tokens exposed to the client as ``window.metadataContext``
(see ``entry_form.html``'s ``metadata-context-data`` block): entity/period/
template identifiers that are fixed for the lifetime of an assignment.

A condition whose ``item_id`` is anything else (a numeric ``FormItem`` id, a
``plugin_*`` measure, or a ``[VAR]``/``var:`` plugin token) depends on state we
cannot reproduce here, so evaluation deliberately returns ``None`` ("unknown")
rather than guessing. Callers must treat ``None`` the same as "still relevant"
(i.e. keep counting the item) — that matches the pre-existing behavior for all
relevance conditions, so this module can only ever make completion counts more
accurate, never less.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Keys resolvable server-side without any client/session state — mirrors
# `entry_form.html`'s `metadata-context-data` block and
# `VariableResolutionService._BUILTIN_METADATA_TYPES`.
METADATA_KEYS = frozenset({
    'entity_name',
    'entity_name_hierarchy',
    'entity_id',
    'entity_type',
    'national_society_name',
    'template_name',
    'assignment_period',
    'assignment_year',
    'country_iso',
    'country_iso2',
    'template_id',
})


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ''
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return False


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        text = str(value).strip().replace(',', '')
        if not text:
            return None
        return float(text)
    except (TypeError, ValueError):
        return None


def _parse_condition_payload(raw: Any) -> Optional[dict]:
    """Normalize a stored condition (object, JSON string, or double-encoded JSON) to a dict."""
    value = raw
    for _ in range(3):
        if isinstance(value, dict):
            return value
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return None
    return value if isinstance(value, dict) else None


def referenced_metadata_keys(raw_condition: Any) -> set[str]:
    """Return the subset of ``METADATA_KEYS`` this condition's sub-conditions target."""
    parsed = _parse_condition_payload(raw_condition)
    if not parsed:
        return set()
    conditions = parsed.get('conditions')
    if not isinstance(conditions, list):
        return set()
    keys = set()
    for c in conditions:
        if not isinstance(c, dict):
            continue
        key = str(c.get('item_id') or '').strip()
        if key in METADATA_KEYS:
            keys.add(key)
    return keys


def condition_references_metadata_keys(raw_condition: Any) -> bool:
    """True when at least one sub-condition targets a server-known metadata token.

    Cheap pre-check used to skip building a metadata context entirely for the
    (overwhelmingly common) rules that only reference other form questions or
    plugin data — ``evaluate_relevance_condition`` would return ``None`` for
    those anyway.
    """
    return bool(referenced_metadata_keys(raw_condition))


def _evaluate_single_condition(condition: dict, metadata: dict) -> Optional[bool]:
    """Return True/False when resolvable purely from ``metadata``, else None (unknown)."""
    item_id = condition.get('item_id')
    key = str(item_id).strip() if item_id is not None else ''
    if key not in METADATA_KEYS:
        return None  # references a form question / plugin value we can't see server-side

    condition_type = condition.get('condition_type')
    actual = metadata.get(key)
    expected = condition.get('value')

    if condition_type == 'is_empty':
        return _is_empty(actual)
    if condition_type == 'is_not_empty':
        return not _is_empty(actual)
    if condition_type in ('equals', 'equal_to'):
        return str(actual or '').strip() == str(expected or '').strip()
    if condition_type in ('not_equals', 'not_equal_to'):
        return str(actual or '').strip() != str(expected or '').strip()
    if condition_type == 'is_yes':
        return actual is not None and str(actual).strip().lower() == 'yes'
    if condition_type == 'is_no':
        return actual is not None and str(actual).strip().lower() == 'no'
    if condition_type in (
        'greater_than', 'less_than', 'greater_than_or_equal_to', 'less_than_or_equal_to',
    ):
        a, e = _as_float(actual), _as_float(expected)
        if a is None or e is None:
            return False
        if condition_type == 'greater_than':
            return a > e
        if condition_type == 'less_than':
            return a < e
        if condition_type == 'greater_than_or_equal_to':
            return a >= e
        return a <= e

    logger.debug("relevance_evaluator: unknown condition_type %r", condition_type)
    return None


def evaluate_relevance_condition(raw_condition: Any, metadata: dict) -> Optional[bool]:
    """
    Evaluate a stored ``relevance_condition`` against server-known ``metadata``.

    Returns:
        True  -> definitely relevant/visible.
        False -> definitely NOT relevant (hidden); safe to exclude from completion counts.
        None  -> cannot be determined server-side; callers must treat this as visible.

    Uses three-valued (Kleene) AND/OR so a rule mixing a resolvable and an
    unresolvable condition can still short-circuit to a definite answer
    (e.g. an OR rule is True as soon as one resolvable branch is True).
    """
    parsed = _parse_condition_payload(raw_condition)
    if not parsed:
        return True  # no condition (or malformed) => always relevant, matches conditions.js

    conditions = parsed.get('conditions')
    if not isinstance(conditions, list):
        return True

    results = [
        _evaluate_single_condition(c, metadata) if isinstance(c, dict) else None
        for c in conditions
    ]

    if parsed.get('logic') == 'OR':
        if any(r is True for r in results):
            return True
        if any(r is None for r in results):
            return None
        return False
    # Default logic is AND (matches conditions.js `results.every(...)`).
    if any(r is False for r in results):
        return False
    if any(r is None for r in results):
        return None
    return True


def build_metadata_context(assignment_entity_status, template_version=None, needed_keys=None) -> dict:
    """Build the same metadata dict exposed to the client as ``window.metadataContext``
    (see ``entry_form.html``'s ``metadata-context-data`` block), for relevance
    conditions that only need server-known assignment/template identifiers.

    When ``needed_keys`` is given, only those built-in tokens are resolved —
    this keeps the common case (e.g. period-gated sections only need
    ``assignment_period``) cheap and avoids locale-dependent entity-name/
    national-society-name lookups that require an active HTTP request (they'd
    otherwise fail from CLI/maintenance contexts such as the completion-rate
    backfill command).
    """
    if assignment_entity_status is None:
        return {}

    from app.services.forms.variable_resolution_service import VariableResolutionService

    builtin_keys = needed_keys - {'country_iso', 'country_iso2', 'template_id'} if needed_keys is not None else None
    metadata = dict(
        VariableResolutionService.get_builtin_metadata_context(
            assignment_entity_status, template_version, keys=builtin_keys
        ) or {}
    )

    if needed_keys is None or needed_keys & {'country_iso', 'country_iso2'}:
        country = getattr(assignment_entity_status, 'country', None)
        metadata['country_iso'] = getattr(country, 'iso3', None) or ''
        metadata['country_iso2'] = getattr(country, 'iso2', None) or ''

    if needed_keys is None or 'template_id' in needed_keys:
        assigned_form = getattr(assignment_entity_status, 'assigned_form', None)
        template = getattr(assigned_form, 'template', None) if assigned_form else None
        metadata['template_id'] = template.id if template else getattr(template_version, 'template_id', None)

    return metadata
