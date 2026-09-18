"""Skip Excel updates that would change locked section/page answers."""
from __future__ import annotations

from typing import Any

from flask_babel import gettext as _

from app.extensions import db
from app.models.form_items import FormItem
from app.models.forms import DynamicIndicatorData, FormData, FormPage, FormSection, RepeatGroupInstance
from app.services.assignments.page_submission_service import (
    is_page_submission_enabled,
    locked_section_ids as locked_page_section_ids,
    section_to_page_ids,
)
from app.services.assignments.section_submission_service import (
    is_section_submission_enabled,
    locked_section_ids,
    top_level_section_id,
)


def _locked_import_warning(scope_kind: str, name: str) -> str:
    return _(
        "Submitted %(scope)s '%(name)s' has different values in the Excel file and was skipped. "
        "Ask an administrator to reopen it if you need to import those values.",
        scope=scope_kind,
        name=name,
    )


def load_assignment_sections(assignment_entity_status) -> list:
    assigned = getattr(assignment_entity_status, 'assigned_form', None)
    template = getattr(assigned, 'template', None) if assigned else None
    if not template:
        return []
    try:
        template_id = int(getattr(template, 'id', None))
        version_id = int(getattr(template, 'published_version_id', None))
    except (TypeError, ValueError):
        return []
    return (
        FormSection.query.filter_by(
            template_id=template_id,
            version_id=version_id,
            archived=False,
        ).all()
    )


def locked_import_section_ids(assignment_entity_status, all_sections=None) -> set[int]:
    sections = all_sections if all_sections is not None else load_assignment_sections(assignment_entity_status)
    locked = set()
    if is_section_submission_enabled(assignment_entity_status):
        locked |= locked_section_ids(assignment_entity_status, sections)
    if is_page_submission_enabled(assignment_entity_status):
        locked |= locked_page_section_ids(assignment_entity_status, sections)
    return locked


def _normalize_value(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, dict):
        return {
            str(key): _normalize_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_normalize_value(item) for item in value]
    if isinstance(value, (int, float)):
        return float(value) if not isinstance(value, bool) else value
    text = str(value).strip()
    if text == '':
        return None
    try:
        number = float(text.replace(',', ''))
        return number
    except (TypeError, ValueError):
        return text.casefold()


def _incoming_payload(data_dict: dict | None) -> dict:
    data_dict = data_dict or {}
    if data_dict.get('disagg_data'):
        return {'kind': 'disagg', 'value': data_dict.get('disagg_data')}
    if data_dict.get('data_not_available'):
        return {'kind': 'flag', 'value': 'data_not_available'}
    if data_dict.get('not_applicable'):
        return {'kind': 'flag', 'value': 'not_applicable'}
    if 'value' in data_dict:
        return {'kind': 'value', 'value': data_dict.get('value')}
    if data_dict:
        return {'kind': 'matrix', 'value': data_dict}
    return {'kind': 'value', 'value': None}


def _existing_payload(entry: FormData | None) -> dict:
    if entry is None:
        return {'kind': 'value', 'value': None}
    if getattr(entry, 'data_not_available', False):
        return {'kind': 'flag', 'value': 'data_not_available'}
    if getattr(entry, 'not_applicable', False):
        return {'kind': 'flag', 'value': 'not_applicable'}
    if getattr(entry, 'disagg_data', None):
        if getattr(entry, 'disagg_type', None) == 'matrix':
            return {'kind': 'matrix', 'value': entry.disagg_data}
        return {'kind': 'disagg', 'value': entry.disagg_data}
    return {'kind': 'value', 'value': entry.value}


def values_differ(incoming: dict | None, existing_entry: FormData | None) -> bool:
    return _normalize_value(_incoming_payload(incoming)) != _normalize_value(_existing_payload(existing_entry))


def _scope_label(section, all_sections, assignment_entity_status) -> tuple[str, str]:
    if is_page_submission_enabled(assignment_entity_status):
        mapping = section_to_page_ids(all_sections)
        page_id = mapping.get(str(getattr(section, 'id', '')))
        if page_id:
            page = db.session.get(FormPage, page_id)
            return 'page', getattr(page, 'name', None) or f'Page {page_id}'
    top_id = top_level_section_id(section, all_sections)
    by_id = {getattr(item, 'id', None): item for item in all_sections or []}
    top = by_id.get(top_id) or section
    return 'section', getattr(top, 'display_name', None) or getattr(top, 'name', None) or str(top_id)


def _warning_for_scope(scope_kind: str, name: str) -> dict:
    return {'message': _locked_import_warning(scope_kind, name), 'scope': scope_kind, 'name': name}


def _repeat_slot_differs(assignment_entity_status, section_id: int, entry: dict) -> bool:
    """True when applying this locked repeat slot would change saved instances."""
    slot_num = entry.get('slot_num') or entry.get('repeat_instance_number')
    try:
        slot_num = int(slot_num)
    except (TypeError, ValueError):
        return True
    existing = RepeatGroupInstance.query.filter_by(
        assignment_entity_status_id=assignment_entity_status.id,
        section_id=section_id,
        instance_number=slot_num,
    ).first()
    if existing is None:
        return True
    incoming = (
        entry.get('display_value')
        or entry.get('mdr_code')
        or entry.get('appeal_name')
        or ''
    ).strip().casefold()
    existing_label = (existing.instance_label or '').strip().casefold()
    if not incoming or not existing_label:
        return False
    if incoming == existing_label:
        return False
    mdr_code = str(entry.get('mdr_code') or '').strip().casefold()
    if mdr_code and mdr_code in existing_label:
        return False
    return True


def filter_locked_field_updates(assignment_entity_status, field_data: dict[int, dict]) -> tuple[dict[int, dict], list[dict]]:
    """Return writable field_data plus one warning per locked section/page that differed."""
    if not field_data:
        return {}, []
    all_sections = load_assignment_sections(assignment_entity_status)
    locked_ids = locked_import_section_ids(assignment_entity_status, all_sections)
    if not locked_ids:
        return dict(field_data), []

    item_ids = [int(item_id) for item_id in field_data.keys()]
    items = FormItem.query.filter(FormItem.id.in_(item_ids)).all() if item_ids else []
    item_by_id = {int(item.id): item for item in items}
    existing = {
        int(row.form_item_id): row
        for row in FormData.query.filter(
            FormData.assignment_entity_status_id == assignment_entity_status.id,
            FormData.form_item_id.in_(item_ids),
        ).all()
    }
    by_id = {getattr(section, 'id', None): section for section in all_sections}
    writable = {}
    warned = {}
    for item_id, payload in field_data.items():
        item = item_by_id.get(int(item_id))
        section_id = getattr(item, 'section_id', None) if item is not None else None
        if section_id in locked_ids:
            if values_differ(payload, existing.get(int(item_id))):
                section = by_id.get(section_id)
                if section is not None and section_id not in warned:
                    scope_kind, name = _scope_label(section, all_sections, assignment_entity_status)
                    warned[section_id] = _warning_for_scope(scope_kind, name)
            continue
        writable[item_id] = payload
    return writable, list(warned.values())


def filter_staged_import_payload(assignment_entity_status, payload: dict[str, Any] | None) -> dict[str, Any]:
    """Remove differing locked values from a UPR/UCP stage payload and return warning metadata."""
    payload = payload or {}
    all_sections = load_assignment_sections(assignment_entity_status)
    locked_ids = locked_import_section_ids(assignment_entity_status, all_sections)
    warnings: list[dict] = []
    if not locked_ids:
        updated_count = (
            len(payload.get('fields') or {})
            + len(payload.get('matrices') or {})
            + len(payload.get('dynamic_indicators') or [])
            + len(payload.get('repeat_slots') or [])
        )
        return {'warnings': [], 'warning_items': [], 'updated_count': updated_count}

    field_map = {}
    for raw_id, value in (payload.get('fields') or {}).items():
        try:
            field_map[int(raw_id)] = value if isinstance(value, dict) else {'value': value}
        except (TypeError, ValueError):
            continue
    for raw_id, value in (payload.get('matrices') or {}).items():
        try:
            field_map[int(raw_id)] = value if isinstance(value, dict) else {'value': value}
        except (TypeError, ValueError):
            continue

    writable, field_warnings = filter_locked_field_updates(assignment_entity_status, field_map)
    writable_ids = {str(item_id) for item_id in writable}
    if 'fields' in payload:
        payload['fields'] = {
            key: value for key, value in (payload.get('fields') or {}).items() if str(key) in writable_ids
        }
    if 'matrices' in payload:
        payload['matrices'] = {
            key: value for key, value in (payload.get('matrices') or {}).items() if str(key) in writable_ids
        }
    warnings.extend(field_warnings)

    by_id = {getattr(section, 'id', None): section for section in all_sections}
    warned_sections = {warning.get('name') for warning in warnings}

    kept_dynamic = []
    for entry in payload.get('dynamic_indicators') or []:
        section_id = entry.get('section_id')
        try:
            section_id = int(section_id)
        except (TypeError, ValueError):
            kept_dynamic.append(entry)
            continue
        if section_id not in locked_ids:
            kept_dynamic.append(entry)
            continue
        existing = DynamicIndicatorData.query.filter_by(
            assignment_entity_status_id=assignment_entity_status.id,
            section_id=section_id,
            indicator_bank_id=entry.get('indicator_bank_id'),
            repeat_instance_number=entry.get('repeat_instance_number'),
        ).first()
        incoming = {
            'value': entry.get('value'),
            'disagg_data': entry.get('disagg_data'),
            'data_not_available': entry.get('data_not_available'),
            'not_applicable': entry.get('not_applicable'),
        }
        if not values_differ(incoming, existing):
            continue
        section = by_id.get(section_id)
        if section is None:
            continue
        scope_kind, name = _scope_label(section, all_sections, assignment_entity_status)
        if name not in warned_sections:
            warnings.append(_warning_for_scope(scope_kind, name))
            warned_sections.add(name)
    payload['dynamic_indicators'] = kept_dynamic

    kept_repeats = []
    for entry in payload.get('repeat_slots') or []:
        section_id = entry.get('repeat_section_id') or entry.get('section_id')
        try:
            section_id = int(section_id)
        except (TypeError, ValueError):
            kept_repeats.append(entry)
            continue
        if section_id not in locked_ids:
            kept_repeats.append(entry)
            continue
        if not _repeat_slot_differs(assignment_entity_status, section_id, entry):
            continue
        section = by_id.get(section_id)
        if section is None:
            continue
        scope_kind, name = _scope_label(section, all_sections, assignment_entity_status)
        if name not in warned_sections:
            warnings.append(_warning_for_scope(scope_kind, name))
            warned_sections.add(name)
    payload['repeat_slots'] = kept_repeats

    updated_count = (
        len(payload.get('fields') or {})
        + len(payload.get('matrices') or {})
        + len(payload.get('dynamic_indicators') or [])
        + len(payload.get('repeat_slots') or [])
    )
    return {
        'warnings': [item['message'] for item in warnings],
        'warning_items': warnings,
        'updated_count': updated_count,
    }
