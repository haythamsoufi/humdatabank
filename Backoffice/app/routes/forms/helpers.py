"""Shared helper functions for the forms blueprint.

Extracted from the monolithic forms.py for maintainability.
"""
from __future__ import annotations

from contextlib import suppress
import json
import logging

from flask import current_app, render_template
from sqlalchemy.orm import joinedload

from app.models import (
    AssignmentEntityStatus,
    db,
    FormData, FormItem, DynamicIndicatorData, FormSection,
    SubmittedDocument,
)
from app.services.assignments.completion_service import AssignmentCompletionService
from app.services.forms.processing_service import (
    get_form_items_for_section,
    _create_dynamic_indicator_object,
    slugify_age_group,
)
from app.utils.form_localization import (
    get_localized_indicator_definition,
    get_localized_indicator_type,
    get_localized_indicator_unit,
    get_translation_key,
)
from config import Config as AppConfig


def debug_numeric_value(logger, context, field_id, field_type, value, processed_value):
    """Helper function to log numeric value processing"""
    logger.debug(f"[NUMERIC DEBUG] {context}")
    logger.debug(f"  Field ID: {field_id}")
    logger.debug(f"  Field Type: {field_type}")
    logger.debug(f"  Original Value: {value} (type: {type(value)})")
    logger.debug(f"  Processed Value: {processed_value} (type: {type(processed_value)})")


def process_numeric_value(value):
    """Process a numeric value, ensuring proper handling of None and invalid values"""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None

    if isinstance(value, str):
        value_str = value.strip()
        if value_str.lower() in ('none', 'null', 'undefined', ''):
            return None

        clean_value = value_str.replace(',', '').replace(' ', '').replace('\u00A0', '').replace('\u202F', '')
        if not clean_value:
            return None

        try:
            if '.' in clean_value or 'e' in clean_value.lower():
                return float(clean_value)
            else:
                return int(clean_value)
        except (ValueError, TypeError):
            return None

    with suppress((ValueError, TypeError)):
        if isinstance(value, (int, float)):
            return value

    return None


def process_existing_data_for_template(data_entry):
    """Process existing data entry for template rendering using the new structure.
    Be tolerant to lightweight placeholder objects (e.g., TempEntry) by using getattr with defaults.
    """
    if not data_entry:
        return ""

    data_not_available = getattr(data_entry, 'data_not_available', False)
    not_applicable = getattr(data_entry, 'not_applicable', False)

    if data_not_available:
        return "data_not_available"
    elif not_applicable:
        return "not_applicable"

    disagg_data = getattr(data_entry, 'disagg_data', None)
    if disagg_data is not None:
        return disagg_data
    prefilled_disagg_data = getattr(data_entry, 'prefilled_disagg_data', None)
    if prefilled_disagg_data is not None:
        return prefilled_disagg_data
    imputed_disagg_data = getattr(data_entry, 'imputed_disagg_data', None)
    if imputed_disagg_data is not None:
        return imputed_disagg_data

    value = getattr(data_entry, 'value', None)
    if value:
        return value

    prefilled_value = getattr(data_entry, 'prefilled_value', None)
    if prefilled_value is not None:
        return prefilled_value

    imputed_value = getattr(data_entry, 'imputed_value', None)
    if imputed_value is not None:
        if isinstance(imputed_value, str):
            s = imputed_value.strip()
            if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
                try:
                    imputed_value = json.loads(s)
                except (json.JSONDecodeError, ValueError, TypeError):
                    imputed_value = s[1:-1]
            elif len(s) >= 2 and s[0] == "'" and s[-1] == "'":
                imputed_value = s[1:-1]
        return imputed_value

    return ""


def _process_form_data_entry(entry, form_item):
    """Process a single FormData/PublicFormData entry into existing_data_processed updates.
    Shared logic for _load_existing_data_for_assignment and _load_existing_data_for_public_submission.
    Returns dict of key-value pairs to merge into existing_data_processed.
    """
    key = f'field_value[{entry.form_item_id}]'
    data_not_available = entry.data_not_available if entry.data_not_available is not None else False
    not_applicable = entry.not_applicable if entry.not_applicable is not None else False

    result = {}

    def _checkbox_key(suffix):
        if form_item.is_indicator:
            return f'indicator_{entry.form_item_id}_{suffix}'
        if form_item.item_type == 'matrix':
            return f'matrix_{entry.form_item_id}_{suffix}'
        return f'question_{entry.form_item_id}_{suffix}'

    if data_not_available:
        result[_checkbox_key('data_not_available')] = True
    if not_applicable:
        result[_checkbox_key('not_applicable')] = True

    if not data_not_available and not not_applicable:
        has_reported = (
            (entry.value is not None and str(entry.value).strip() != "")
            or (getattr(entry, "disagg_data", None) is not None)
        )
        has_prefilled = (
            (getattr(entry, "prefilled_value", None) is not None)
            or (getattr(entry, "prefilled_disagg_data", None) is not None)
        )
        has_imputed = (
            (getattr(entry, "imputed_value", None) is not None)
            or (getattr(entry, "imputed_disagg_data", None) is not None)
        )
        if form_item.item_type == 'matrix' or form_item.item_type.startswith('plugin_'):
            dd = getattr(entry, "disagg_data", None)
            dd_source = "reported"
            if dd is None:
                dd = getattr(entry, "prefilled_disagg_data", None)
                dd_source = "prefilled"
            if dd is None:
                dd = getattr(entry, "imputed_disagg_data", None)
                dd_source = "imputed"
            if dd is not None:
                result[key] = dd
                if dd_source == "prefilled":
                    result[f'{key}_is_prefilled'] = True
                elif dd_source == "imputed":
                    result[f'{key}_is_imputed'] = True
            else:
                result[key] = {}
        else:
            if has_reported or has_prefilled or has_imputed:
                result[key] = process_existing_data_for_template(entry)
                if (not has_reported) and has_prefilled:
                    result[f'{key}_is_prefilled'] = True
                elif (not has_reported) and (not has_prefilled) and has_imputed:
                    result[f'{key}_is_imputed'] = True

    return result


def _load_existing_data_for_assignment(assignment_entity_status, form_template):
    """Load and process existing FormData and DynamicIndicatorData for an assignment.
    Returns existing_data_processed dict keyed by field_value[<id>].
    Matrix fields are handled inline during the FormData loop (item_type == 'matrix').
    """
    existing_data_entries = (
        FormData.query
        .filter_by(assignment_entity_status_id=assignment_entity_status.id)
        .options(joinedload(FormData.form_item))
        .all()
    )
    existing_data_processed = {}
    for entry in existing_data_entries:
        if entry.form_item_id:
            form_item = entry.form_item
            if not form_item:
                current_app.logger.warning(
                    f"[DATA_LOADING] FormItem not found for form_item_id={entry.form_item_id}"
                )
                continue
            existing_data_processed.update(_process_form_data_entry(entry, form_item))

    dynamic_data_entries = (
        DynamicIndicatorData.query
        .filter_by(assignment_entity_status_id=assignment_entity_status.id)
        .options(joinedload(DynamicIndicatorData.indicator_bank))
        .all()
    )
    for dynamic_data_entry in dynamic_data_entries:
        existing_data_processed.update(existing_data_for_dynamic_assignment(dynamic_data_entry))

    return existing_data_processed


def existing_data_for_dynamic_assignment(dynamic_assignment) -> dict:
    """Build existing_data entries for rendering one saved dynamic indicator."""
    existing_data = {}
    dynamic_key = f'field_value[dynamic_{dynamic_assignment.id}]'
    if dynamic_assignment.disagg_data:
        existing_data[dynamic_key] = dynamic_assignment.disagg_data
    else:
        existing_data[dynamic_key] = dynamic_assignment.value
    if dynamic_assignment.data_not_available:
        existing_data[f'dynamic_{dynamic_assignment.id}_data_not_available'] = True
    if dynamic_assignment.not_applicable:
        existing_data[f'dynamic_{dynamic_assignment.id}_not_applicable'] = True
    return existing_data


def render_dynamic_indicator_item_html(
    dynamic_assignment,
    section,
    assignment_entity_status,
    *,
    can_edit: bool = True,
) -> str:
    """Render the HTML partial for one saved dynamic indicator assignment."""
    dynamic_field = _create_dynamic_indicator_object(dynamic_assignment, section)

    template_structure = None
    if assignment_entity_status and getattr(assignment_entity_status, 'assigned_form', None):
        template_structure = assignment_entity_status.assigned_form.template
    if not template_structure and getattr(section, 'template', None):
        template_structure = section.template
    if not template_structure:
        template_structure = type('TemplateStructure', (), {'display_order_visible': True})()

    return render_template(
        'forms/entry_form/partials/dynamic_indicator_item.html',
        field=dynamic_field,
        section=section,
        existing_data=existing_data_for_dynamic_assignment(dynamic_assignment),
        template_structure=template_structure,
        config=AppConfig,
        can_edit=can_edit,
        translation_key=get_translation_key(),
        get_localized_indicator_definition=get_localized_indicator_definition,
        get_localized_indicator_type=get_localized_indicator_type,
        get_localized_indicator_unit=get_localized_indicator_unit,
        isinstance=isinstance,
        json=json,
        hasattr=hasattr,
        slugify_age_group=slugify_age_group,
    )


def _load_existing_data_for_public_submission(submission):
    """Load and process existing form data entries for a public submission.
    Returns existing_data_processed dict.
    """
    existing_data_processed = {}
    for entry in submission.data_entries.all():
        if not entry.form_item_id:
            continue
        form_item = FormItem.query.get(entry.form_item_id)
        if not form_item:
            current_app.logger.warning(
                f"FormItem {entry.form_item_id} not found for public submission {submission.id}"
            )
            continue
        existing_data_processed.update(_process_form_data_entry(entry, form_item))
    return existing_data_processed


def _prepare_submitted_documents_for_template(submission):
    """Prepare submitted documents dict for entry_form.html.
    Returns dict mapping field keys to single doc or list of docs (most recent first).
    """
    result = {}
    for doc in submission.submitted_documents.order_by(SubmittedDocument.uploaded_at.desc()).all():
        if not doc.form_item_id:
            continue
        doc_key = f"field_value[{doc.form_item_id}]"
        if doc_key not in result:
            result[doc_key] = doc
        else:
            current = result[doc_key]
            if isinstance(current, list):
                current.append(doc)
            else:
                result[doc_key] = [current, doc]
    return result


def map_unified_item_to_original(item_id, item_type):
    """Map a unified item ID to the FormItem.

    Args:
        item_id: The unified item ID from FormItem
        item_type: The FormItemType (indicator, question, document_field)

    Returns:
        tuple: (FormItem instance, item_id) or (None, None) if not found
    """
    if item_id is None:
        return (None, None)

    try:
        if isinstance(item_id, str):
            item_id = int(item_id)
        elif not isinstance(item_id, int):
            return (None, None)
    except (ValueError, TypeError):
        return (None, None)

    if not item_type:
        return (None, None)

    try:
        form_item = FormItem.query.filter_by(id=item_id, item_type=item_type).first()
        return (form_item, item_id) if form_item else (None, None)
    except Exception as e:  # SQLAlchemy/DB errors - keep broad for DB layer
        current_app.logger.warning("_resolve_form_item_from_request DB error: %s", e, exc_info=True)
        return (None, None)


def calculate_assignment_completion_rate(assignment_entity_status_id, template_id, version_id):
    """Return persisted assignment completion rate (refreshes when not yet stored)."""
    del template_id, version_id  # kept for call-site compatibility
    aes = db.session.get(AssignmentEntityStatus, assignment_entity_status_id)
    if not aes:
        return 0.0
    return AssignmentCompletionService.stored_rate_for(aes)


def build_entry_form_features(all_sections, form_template=None):
    """Build ``window.__formFeatures`` flags for conditional JS module loading.

    Section-level features (repeat, dynamic indicators) are detected via
    ``section_type``. Field-level features (matrix, documents, calculated lists)
    are detected by scanning ``fields_ordered`` on each section.

    Matrix list-library items carry ``lookup_list_id`` but are handled by
    ``matrix-handler.js``, so they are excluded from ``calculatedLists``.
    """
    section_types = {getattr(s, 'section_type', None) for s in (all_sections or [])}

    def _iter_fields():
        for section in (all_sections or []):
            for field in getattr(section, 'fields_ordered', []) or []:
                if field:
                    yield field

    fields = list(_iter_fields())

    has_matrix_fields = any(getattr(f, 'item_type', None) == 'matrix' for f in fields)
    has_document_fields = any(getattr(f, 'item_type', None) == 'document_field' for f in fields)
    has_calculated_list_fields = any(
        getattr(f, 'lookup_list_id', None) and getattr(f, 'item_type', None) != 'matrix'
        for f in fields
    )

    enable_export_excel = bool(getattr(form_template, 'enable_export_excel', False)) if form_template else False
    enable_import_excel = bool(getattr(form_template, 'enable_import_excel', False)) if form_template else False
    has_discussion_section = 'discussion' in section_types
    enable_discussion = bool(getattr(form_template, 'enable_discussion', False)) if form_template else False
    template_id = int(getattr(form_template, 'id', 0) or 0)
    upr_country_reporting_excel = template_id == 33

    return {
        'matrix': has_matrix_fields,
        'repeat': 'repeat' in section_types,
        'dynamicIndicators': 'dynamic_indicators' in section_types,
        'documents': has_document_fields,
        'calculatedLists': has_calculated_list_fields,
        'pdfExport': True,
        'excelExport': enable_export_excel or enable_import_excel or upr_country_reporting_excel,
        'discussion': enable_discussion or has_discussion_section,
    }


def calculate_section_completion_status(all_sections, existing_data_processed, existing_submitted_documents_dict):
    """Calculate completion status for sections - returns dict format expected by template."""
    section_statuses = {}
    for section in all_sections:
        if getattr(section, 'section_type', None) == 'discussion':
            section_statuses[section.name] = 'N/A'
            continue
        total_items_in_section = 0
        filled_items_count = 0
        if hasattr(section, 'fields_ordered'):
            for field in section.fields_ordered:
                if hasattr(field, 'field_type_for_js') and field.field_type_for_js.lower() in ('blank', 'image'):
                    continue
                if getattr(field, 'is_image', False):
                    continue
                field_config = getattr(field, 'config', None) or {}
                if field_config.get('exclude_from_completion_rate'):
                    continue

                total_items_in_section +=1

                dynamic_id = getattr(field, 'dynamic_assignment_id', None)
                if dynamic_id is not None:
                    item_key = f"field_value[dynamic_{dynamic_id}]"
                    not_applicable_key = f"dynamic_{dynamic_id}_not_applicable"
                else:
                    item_key = f"field_value[{field.id}]"
                    if field.is_indicator:
                        not_applicable_key = f"indicator_{field.id}_not_applicable"
                    elif field.is_question:
                        not_applicable_key = f"question_{field.id}_not_applicable"
                    else:
                        not_applicable_key = f"field_{field.id}_not_applicable"

                if existing_data_processed.get(not_applicable_key):
                    filled_items_count += 1
                elif field.is_document_field:
                    if field.is_required_for_js and item_key in existing_submitted_documents_dict:
                        filled_items_count +=1
                    elif not field.is_required_for_js and item_key in existing_submitted_documents_dict:
                        filled_items_count +=1
                else:
                    entry_data = existing_data_processed.get(item_key)
                    if entry_data is not None:
                        if isinstance(entry_data, dict) and 'values' in entry_data:
                             if any(str(v).strip() for v in entry_data['values'].values() if v is not None):
                                  filled_items_count += 1
                        elif hasattr(field, 'is_matrix') and field.is_matrix and isinstance(entry_data, dict):
                            if any(
                                v is not None and str(v).strip() != ''
                                for k, v in entry_data.items()
                                if not k.startswith('_')
                            ):
                                filled_items_count += 1
                        elif field.field_type_for_js == 'CHECKBOX':
                            if entry_data == 'true' or entry_data is True:
                                filled_items_count += 1
                        elif entry_data is not None and str(entry_data).strip():
                             filled_items_count += 1

        if total_items_in_section == 0:
            section_statuses[section.name] = 'N/A'
        elif filled_items_count == 0:
            section_statuses[section.name] = 'Not Started'
        elif filled_items_count < total_items_in_section:
            section_statuses[section.name] = 'in_progress'
        else:
            section_statuses[section.name] = 'Completed'

    return section_statuses


def build_submitted_documents_dict(assignment_entity_status_id):
    """Build the field_value-keyed submitted-documents map used by section status logic."""
    submitted_docs = (
        SubmittedDocument.query.filter_by(assignment_entity_status_id=assignment_entity_status_id)
        .order_by(SubmittedDocument.uploaded_at.desc())
        .all()
    )
    existing_submitted_documents_dict = {}
    for doc in submitted_docs:
        if not doc.form_item_id:
            continue
        key = f'field_value[{doc.form_item_id}]'
        if key not in existing_submitted_documents_dict:
            existing_submitted_documents_dict[key] = doc
        elif isinstance(existing_submitted_documents_dict[key], list):
            existing_submitted_documents_dict[key].append(doc)
        else:
            existing_submitted_documents_dict[key] = [
                existing_submitted_documents_dict[key], doc
            ]
    return existing_submitted_documents_dict


def parse_csv_id_set(raw: str | None) -> set[int]:
    """Parse comma-separated numeric ids (FormItem / FormSection ids from the client)."""
    if not raw or not str(raw).strip():
        return set()
    out: set[int] = set()
    for part in str(raw).split(','):
        part = part.strip()
        if part.isdigit():
            with suppress(Exception):
                out.add(int(part))
    return out


def compute_entry_form_progress_metrics(
    assignment_entity_status,
    form_template,
    all_sections,
    *,
    hidden_field_ids: set[int] | None = None,
    hidden_section_ids: set[int] | None = None,
):
    """Reload saved assignment data and return completion rate + section statuses for the UI."""
    existing_data_processed = _load_existing_data_for_assignment(
        assignment_entity_status, form_template
    )
    existing_submitted_documents_dict = build_submitted_documents_dict(
        assignment_entity_status.id
    )
    section_statuses_by_name = calculate_section_completion_status(
        all_sections, existing_data_processed, existing_submitted_documents_dict
    )
    section_statuses = {
        str(section.id): section_statuses_by_name.get(section.name, 'Not Started')
        for section in (all_sections or [])
    }

    completion_rate = 0.0
    if getattr(assignment_entity_status, 'id', None):
        completion_rate = AssignmentCompletionService.refresh_and_persist(
            assignment_entity_status.id
        )

    return {
        'completion_rate': completion_rate,
        'section_statuses': section_statuses,
    }
