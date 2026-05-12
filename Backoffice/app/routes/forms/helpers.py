"""Shared helper functions for the forms blueprint.

Extracted from the monolithic forms.py for maintainability.
"""
from __future__ import annotations

from contextlib import suppress
import json
import logging

from flask import current_app
from sqlalchemy.orm import joinedload

from app.models import (
    FormData, FormItem, DynamicIndicatorData,
    SubmittedDocument,
)
from app.services.form_processing_service import get_form_items_for_section


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

    dynamic_data_entries = DynamicIndicatorData.query.filter(
        DynamicIndicatorData.assignment_entity_status_id == assignment_entity_status.id
    ).all()
    for dynamic_data_entry in dynamic_data_entries:
        dynamic_key = f'field_value[dynamic_{dynamic_data_entry.id}]'
        if dynamic_data_entry.disagg_data:
            existing_data_processed[dynamic_key] = dynamic_data_entry.disagg_data
        else:
            existing_data_processed[dynamic_key] = dynamic_data_entry.value
        if dynamic_data_entry.data_not_available:
            existing_data_processed[f'dynamic_{dynamic_data_entry.id}_data_not_available'] = True
        if dynamic_data_entry.not_applicable:
            existing_data_processed[f'dynamic_{dynamic_data_entry.id}_not_applicable'] = True

    return existing_data_processed


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


def calculate_section_completion_status(all_sections, existing_data_processed, existing_submitted_documents_dict):
    """Calculate completion status for sections - returns dict format expected by template."""
    section_statuses = {}
    for section in all_sections:
        total_items_in_section = 0
        filled_items_count = 0
        if hasattr(section, 'fields_ordered'):
            for field in section.fields_ordered:
                if hasattr(field, 'field_type_for_js') and field.field_type_for_js.lower() == 'blank':
                    continue

                total_items_in_section +=1

                if hasattr(field, 'dynamic_assignment_id'):
                    item_key = f"field_value[dynamic_{field.dynamic_assignment_id}]"
                    not_applicable_key = f"dynamic_{field.dynamic_assignment_id}_not_applicable"
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
            section_statuses[section.name] = 'In Progress'
        else:
            section_statuses[section.name] = 'Completed'

    return section_statuses
