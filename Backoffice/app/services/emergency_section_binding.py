"""Emergency-section identity binding (Direction A).

Anchors the dynamic "Emergency Appeal N" sections (labelled with [EO1]/[EO2]/[EO3]) to a
stable appeal code per assignment instead of a volatile positional slot.

Why this exists
---------------
EO1/EO2/EO3 are otherwise just the first three items of the GO API result in raw order.
If the API reorders results, or the field's filters/timeframe change the membership, the
section label silently re-associates to a different appeal while the saved dynamic-indicator
data stays pinned to the same section. This module makes the server the source of truth:

- It deterministically orders the operations and honours any existing binding first, so a
  slot keeps showing the same appeal across reloads.
- On save it freezes the binding (appeal code + label snapshot) in ``dynamic_section_context``.
- If a bound appeal later drops out of the filtered set, its binding/data is preserved and
  flagged ``dropped`` rather than reused for a different appeal.

The binding table is provider-generic; this module is the Emergency Operations implementer.
"""

import hashlib
import json
import logging
import re
from typing import Dict, List, Optional

from app.extensions import db
from app.models.forms import DynamicSectionContext
from app.models.form_items import FormItem
from app.utils.datetime_helpers import utcnow

logger = logging.getLogger(__name__)

PROVIDER_ID = 'emergency_operations'
MAX_SLOTS = 3

# Matches the [EOn] placeholder used in emergency section names (n = 1..N).
_EO_SLOT_RE = re.compile(r'\[EO(\d+)\]', re.IGNORECASE)


def slot_for_section(section) -> Optional[int]:
    """Return the EO slot number (1/2/3) a section references, or None.

    Looks at the raw section name and any name translations so the binding works regardless
    of the active locale.
    """
    candidates = []
    name = getattr(section, 'name', None)
    if name:
        candidates.append(name)
    translations = getattr(section, 'name_translations', None)
    if isinstance(translations, dict):
        candidates.extend(v for v in translations.values() if v)
    for text in candidates:
        m = _EO_SLOT_RE.search(str(text))
        if m:
            try:
                return int(m.group(1))
            except (TypeError, ValueError):
                continue
    return None


def _country_iso_for_aes(aes) -> Optional[str]:
    try:
        from app.utils.api_serialization import _country_for_aes
        country = _country_for_aes(aes)
    except Exception:
        country = None
    if not country:
        return None
    iso = (getattr(country, 'iso3', None) or getattr(country, 'iso2', None) or '').strip().upper()
    return iso or None


def _assignment_period_for_aes(aes) -> Optional[str]:
    try:
        period = getattr(getattr(aes, 'assigned_form', None), 'period_name', None)
        return str(period).strip() if period else None
    except Exception:
        return None


def _eo_field_config(version_id) -> Dict:
    """Return Emergency Operations filter config for a template version (filters/timeframe).

    Supports both native ``emergency_operations`` plugin fields (``plugin_config``) and
    calculated-list questions that use ``lookup_list_id='emergency_operations'``
    (``question_plugin_config``).
    """
    if not version_id:
        return {}
    try:
        item = FormItem.query.filter(
            FormItem.version_id == version_id,
            db.or_(
                FormItem.item_type == 'emergency_operations',
                FormItem.item_type.like('plugin_emergency_operations%'),
            ),
        ).first()
        if not item:
            item = FormItem.query.filter(
                FormItem.version_id == version_id,
                FormItem.lookup_list_id == 'emergency_operations',
            ).first()
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Could not load EO field config for version %s: %s", version_id, exc)
        return {}
    if not item:
        return {}
    cfg = item.config if isinstance(getattr(item, 'config', None), dict) else {}
    if item.lookup_list_id == 'emergency_operations':
        qpc = cfg.get('question_plugin_config') if isinstance(cfg.get('question_plugin_config'), dict) else {}
        return qpc or {}
    plugin_cfg = cfg.get('plugin_config') if isinstance(cfg.get('plugin_config'), dict) else {}
    return plugin_cfg or {}


def _normalize_emops_config(raw_cfg: Optional[Dict], assignment_period: Optional[str] = None) -> Dict:
    """Map emops_* / plugin_config keys to ``get_emergency_operations_data`` config."""
    raw = raw_cfg if isinstance(raw_cfg, dict) else {}

    show_closed = raw.get('show_closed_operations')
    if show_closed is None:
        show_closed = raw.get('emops_show_closed_operations')
    if isinstance(show_closed, list):
        show_closed = len(show_closed) > 0
    elif isinstance(show_closed, str):
        show_closed = show_closed.lower() in ('1', 'true', 'yes', 'on')
    elif show_closed is None:
        show_closed = True
    else:
        show_closed = bool(show_closed)

    operation_types = raw.get('operation_types') or raw.get('emops_operation_types') or ['All']
    if not isinstance(operation_types, list):
        operation_types = [operation_types] if operation_types else ['All']
    operation_types = [t for t in operation_types if t]
    if not operation_types:
        operation_types = ['All']
    if 'All' in operation_types and len(operation_types) > 1:
        operation_types = [t for t in operation_types if t != 'All']

    config: Dict = {
        'operation_types': operation_types,
        'show_closed_operations': show_closed,
    }

    timeframe_mode = raw.get('emops_timeframe_mode') or raw.get('timeframe_mode') or 'static'
    start_date = raw.get('start_date') or raw.get('emops_start_date')
    end_date_gt = raw.get('end_date_gt') or raw.get('emops_end_date_gt')

    if timeframe_mode == 'assignment_period' and assignment_period:
        year_match = re.search(r'\b(20\d{2})\b', str(assignment_period))
        if year_match:
            end_date_gt = f"{year_match.group(1)}-01-01"

    if start_date:
        config['start_date'] = start_date
    if end_date_gt:
        config['end_date_gt'] = end_date_gt

    return config


def _filters_hash(country_iso: Optional[str], eo_cfg: Dict, assignment_period: Optional[str] = None) -> str:
    normalized = _normalize_emops_config(eo_cfg, assignment_period)
    payload = {
        'iso': country_iso or '',
        'operation_types': normalized.get('operation_types'),
        'show_closed_operations': normalized.get('show_closed_operations'),
        'end_date_gt': normalized.get('end_date_gt'),
        'start_date': normalized.get('start_date'),
    }
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode('utf-8')).hexdigest()[:32]


def _fetch_ordered_operations(
    country_iso: Optional[str],
    eo_cfg: Dict,
    assignment_period: Optional[str] = None,
) -> List[Dict]:
    """Fetch operations for the country with the field's filters, de-duplicated and deterministically sorted.

    Sort: newest start_date first (missing dates last), tie-break appeal code ascending. This makes the
    "fill remaining slots" step reproducible regardless of raw API ordering.

    Worker-saturation guard: if the EmOps file cache is cold this function returns [] immediately
    and triggers a background refresh instead of blocking the Gunicorn thread on an external HTTP
    call (which can take up to the plugin's 10 s timeout). The client-side EmOps widget will fetch
    the live data via its own AJAX call once the form is loaded.
    """
    if not country_iso:
        return []

    # Pre-check: only proceed if the file cache is warm. A cold cache means we would otherwise
    # block this worker on a requests.get() to the GO API for up to ~10 s.
    try:
        from plugins.emergency_operations.data_store import get_data_store, trigger_background_refresh
        from plugins.emergency_operations.routes import GO_APPEALS_URL, plugin_config as _eo_plugin_config
        _store = get_data_store()
        if _store.load_cached() is None:
            logger.info(
                "[EmOps] Cache cold during form render (iso=%s); "
                "triggering background refresh — skipping blocking server-side EO binding.",
                country_iso,
            )
            try:
                _cfg = _eo_plugin_config.get_all_config()
                _qd = _cfg.get('query_defaults', {})
                _fetch_params = {
                    'end_date__gte': _qd.get('end_date_gt', '2022-12-31'),
                    'format': 'json',
                    'limit': str(_qd.get('limit', 1000)),
                }
                trigger_background_refresh(GO_APPEALS_URL, _fetch_params)
            except Exception as _exc:
                logger.debug("[EmOps] Background refresh trigger failed: %s", _exc)
            return []
    except Exception as exc:
        logger.debug("EmOps cache pre-check unavailable: %s", exc)

    try:
        from plugins.emergency_operations.routes import get_emergency_operations_data
    except Exception as exc:
        logger.debug("Emergency Operations plugin unavailable: %s", exc)
        return []

    config = _normalize_emops_config(eo_cfg, assignment_period)

    try:
        ops = get_emergency_operations_data(country_iso=country_iso, config=config) or []
    except Exception as exc:
        logger.debug("Emergency Operations fetch failed for iso=%s: %s", country_iso, exc)
        return []

    # De-duplicate by appeal code (keep first occurrence).
    seen = set()
    deduped = []
    for op in ops:
        code = (op.get('code') or '').strip()
        if code and code in seen:
            continue
        if code:
            seen.add(code)
        deduped.append(op)

    # Two-stage stable sort -> code asc, then start_date desc (missing dates sort last).
    deduped.sort(key=lambda op: (op.get('code') or ''))
    deduped.sort(key=lambda op: (str(op.get('start_date') or '')[:10]), reverse=True)
    return deduped


def _op_label(op: Dict) -> str:
    name = (op.get('name') or '').strip()
    code = (op.get('code') or '').strip()
    return f"{name} ({code})" if code else name


def resolve_slot_map(aes, max_slots: int = MAX_SLOTS) -> List[Optional[Dict]]:
    """Resolve which appeal occupies each EO slot for an assignment, honouring existing bindings.

    Returns a list of length ``max_slots``; each entry is None (empty slot) or a dict with keys
    ``code``, ``name``, ``label``, ``status`` ('active'|'dropped') and ``op`` (raw operation or None).
    """
    slots: List[Optional[Dict]] = [None] * max_slots

    version_id = None
    try:
        version_id = aes.assigned_form.template.published_version_id
    except Exception:
        version_id = None

    country_iso = _country_iso_for_aes(aes)
    assignment_period = _assignment_period_for_aes(aes)
    eo_cfg = _eo_field_config(version_id)
    ops = _fetch_ordered_operations(country_iso, eo_cfg, assignment_period)
    ops_by_code = {(op.get('code') or '').strip(): op for op in ops if (op.get('code') or '').strip()}

    # Load existing bindings for this assignment.
    bindings = {}
    try:
        rows = DynamicSectionContext.query.filter_by(
            assignment_entity_status_id=aes.id,
            provider_id=PROVIDER_ID,
        ).all()
        for row in rows:
            if row.slot:
                bindings[row.slot] = row
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Could not load section-context bindings for aes %s: %s", getattr(aes, 'id', None), exc)

    used_codes = set()
    for slot, row in bindings.items():
        if not (1 <= slot <= max_slots):
            continue
        code = (row.context_key or '').strip()
        if not code:
            continue
        op = ops_by_code.get(code)
        if op is not None:
            slots[slot - 1] = {
                'code': code,
                'name': (op.get('name') or '').strip(),
                'label': _op_label(op),
                'status': 'active',
                'op': op,
            }
        else:
            # Bound appeal no longer in the filtered set: keep identity, flag as dropped.
            slots[slot - 1] = {
                'code': code,
                'name': row.label_snapshot or code,
                'label': row.label_snapshot or code,
                'status': 'dropped',
                'op': None,
            }
        used_codes.add(code)

    # Fill remaining empty slots with remaining operations in deterministic order.
    remaining = [op for op in ops if (op.get('code') or '').strip() not in used_codes]
    for i in range(max_slots):
        if slots[i] is None and remaining:
            op = remaining.pop(0)
            slots[i] = {
                'code': (op.get('code') or '').strip(),
                'name': (op.get('name') or '').strip(),
                'label': _op_label(op),
                'status': 'active',
                'op': op,
            }
    return slots


def resolve_eo_variables(aes, max_slots: int = MAX_SLOTS) -> Dict[str, str]:
    """Return {'EO1': label, 'EO2': label, 'EO3': label} resolved server-side (binding-aware)."""
    slots = resolve_slot_map(aes, max_slots)
    out: Dict[str, str] = {}
    for i in range(max_slots):
        s = slots[i]
        out[f'EO{i + 1}'] = (s.get('label') if s else '') or ''
    return out


def persist_section_binding(section, aes, user_id=None) -> Optional[DynamicSectionContext]:
    """Freeze (or refresh) the emergency binding for a dynamic section after its data is saved.

    The binding is captured the first time data is saved into the slot and then kept stable
    (the appeal code is not overwritten on later saves). Returns the binding row, or None when
    the section is not an emergency section or no appeal can be resolved.
    """
    slot = slot_for_section(section)
    if not slot:
        return None

    version_id = None
    try:
        version_id = aes.assigned_form.template.published_version_id
    except Exception:
        version_id = None
    country_iso = _country_iso_for_aes(aes)
    assignment_period = _assignment_period_for_aes(aes)
    eo_cfg = _eo_field_config(version_id)

    slots = resolve_slot_map(aes)
    s = slots[slot - 1] if 1 <= slot <= len(slots) else None
    if not s or not s.get('code'):
        return None

    binding = DynamicSectionContext.query.filter_by(
        assignment_entity_status_id=aes.id,
        section_id=section.id,
        provider_id=PROVIDER_ID,
    ).first()

    now = utcnow()
    if binding is None:
        binding = DynamicSectionContext(
            assignment_entity_status_id=aes.id,
            section_id=section.id,
            provider_id=PROVIDER_ID,
            slot=slot,
            context_key=s['code'],
            created_by_user_id=user_id,
        )
        db.session.add(binding)
    binding.slot = slot
    # Freeze the appeal code on first bind; keep it stable afterwards.
    if not binding.context_key:
        binding.context_key = s['code']
    binding.label_snapshot = s.get('label') or s.get('name') or binding.context_key
    binding.status = s.get('status', 'active')
    binding.filters_hash = _filters_hash(country_iso, eo_cfg, assignment_period)
    binding.resolved_at = now
    return binding
