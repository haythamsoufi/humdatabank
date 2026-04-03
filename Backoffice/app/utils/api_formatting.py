# ========== API Formatting Utilities ==========
"""
Utilities for formatting data for API responses.
Extracted from routes/api.py for better organization and reusability.
"""

import json
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union
from contextlib import suppress


def choices_from_query(query, value_attr='id', label_attr='name', label_func=None, empty_option=None):
    """
    Build WTForms SelectField.choices from a SQLAlchemy query.

    Args:
        query: SQLAlchemy query (e.g. Country.query.order_by(Country.name))
        value_attr: Attribute for option value (default: 'id')
        label_attr: Attribute for option label when label_func is None (default: 'name')
        label_func: Optional callable(item) -> str for custom labels
        empty_option: Optional (value, label) for empty/placeholder (e.g. ('', 'None'))

    Returns:
        List of (value, label) tuples for form.field.choices

    Example:
        form.country_id.choices = choices_from_query(Country.query.order_by(Country.name))
        form.branch_id.choices = choices_from_query(
            NSBranch.query.join(Country).order_by(Country.name, NSBranch.name),
            label_func=lambda b: f"{b.country.name} - {b.name}"
        )
        form.subbranch_id.choices = choices_from_query(..., empty_option=('', 'None (Direct to Branch)'))
    """
    items = query.all()
    result = []
    if empty_option is not None:
        result.append(empty_option)
    for item in items:
        val = getattr(item, value_attr)
        label = label_func(item) if label_func else getattr(item, label_attr)
        result.append((val, str(label)))
    return result


def serialize_select_options(
    items: Iterable[Any],
    fields: Union[Tuple[str, ...], List[str]] = ('id', 'name'),
) -> List[Dict[str, Any]]:
    """
    Serialize iterable of model instances into [{field: value, ...}, ...] for select/options.

    Args:
        items: Queryset or list of model instances (e.g. Country, NSBranch)
        fields: Attribute names to include (default: id, name)

    Returns:
        List of dicts suitable for API responses. Prefer json_select_options from
        app.utils.api_responses for 200 responses.

    Example:
        from app.utils.api_responses import json_select_options
        return json_select_options(clusters)  # [{'id': 1, 'name': 'Cluster A'}, ...]
        return json_select_options(branches, ('id', 'name', 'code'))
    """
    result = []
    for item in items:
        row = {}
        for attr in fields:
            if hasattr(item, attr):
                row[attr] = getattr(item, attr)
        result.append(row)
    return result


def format_answer_value(value: Any) -> Any:
    """
    Format answer value as JSON-serializable (optimized for performance).

    Args:
        value: Raw value from database

    Returns:
        JSON-serializable value
    """
    # Fast path for common types
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, dict)):
        # Already JSON-serializable, return as-is
        return value

    # Only parse JSON strings if they look like JSON (starts with { or [)
    if isinstance(value, str):
        value_stripped = value.strip()
        if value_stripped.startswith(('{', '[')):
            with suppress(json.JSONDecodeError):
                return json.loads(value)
        return value

    # For other types, try JSON round-trip only if necessary
    try:
        # Check if it's already JSON-serializable by attempting serialization
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        # If not serializable, convert to string
        return str(value)


def format_form_data_response(data_item) -> Dict[str, Any]:
    """
    Format form data item with the new three-field structure for API responses (optimized).

    Args:
        data_item: FormData or similar model instance

    Returns:
        Dictionary with formatted data
    """
    # Direct field access instead of properties for better performance
    data_not_available = data_item.data_not_available
    not_applicable = data_item.not_applicable
    has_flags = data_not_available is not None or not_applicable is not None

    # Determine the effective value based on data availability flags
    if has_flags:
        if data_not_available:
            answer_value = None
            data_status = "data_not_available"
        elif not_applicable:
            answer_value = None
            data_status = "not_applicable"
        else:
            answer_value = format_answer_value(data_item.value)
            data_status = "available"
    else:
        answer_value = format_answer_value(data_item.value)
        data_status = "available"

    # Format disaggregation data (direct access to disagg_data)
    disaggregation_data = None
    disagg_data = data_item.disagg_data
    if disagg_data:
        disaggregation_data = {
            'mode': disagg_data.get('mode') if isinstance(disagg_data, dict) else None,
            'values': disagg_data.get('values', {}) if isinstance(disagg_data, dict) else {}
        }

    return {
        'answer_value': answer_value,
        'disaggregation_data': disaggregation_data,
        'data_status': data_status,
        'data_not_available': data_not_available,
        'not_applicable': not_applicable
    }


def serialize_form_data_item(data_item, submission_type: str) -> Dict[str, Any]:
    """
    Serialize a form data item into the API response format.
    Handles both 'assigned' and 'public' submission types.

    Args:
        data_item: FormData model instance
        submission_type: 'assigned' or 'public'

    Returns:
        Dictionary with serialized form data item
    """
    from app.utils.api_serialization import format_country_info, format_form_item_info

    form_data_info = format_form_data_response(data_item)

    base_data = {
        'id': data_item.id,
        'form_item_id': data_item.form_item_id,
        'answer_value': form_data_info['answer_value'],
        'disaggregation_data': form_data_info['disaggregation_data'],
        'data_status': form_data_info['data_status'],
        'data_not_available': form_data_info['data_not_available'],
        'not_applicable': form_data_info['not_applicable'],
        'start_date': None,
        'end_date': None,
        'updated_at': None
    }

    if submission_type == 'assigned':
        status_info = data_item.assignment_entity_status
        assigned_form = status_info.assigned_form if status_info else None
        country = status_info.country if status_info else None
        submitted_at = data_item.submitted_at.isoformat() if data_item.submitted_at is not None else None

        # Build form_item_info safely
        form_item = data_item.form_item
        form_item_info = None
        if form_item:
            section = getattr(form_item, 'form_section', None)
            template = getattr(form_item, 'template', None)
            form_item_info = format_form_item_info(
                form_item,
                section=section,
                template=template,
                assignment=assigned_form
            )

        base_data.update({
            'submission_id': status_info.id if status_info else None,
            'submission_type': 'assigned',
            'period_name': assigned_form.period_name if assigned_form else None,
            'country_info': format_country_info(country),
            'form_item_info': form_item_info,
            'date_collected': submitted_at,
            'submitted_at': submitted_at,
            'created_at': submitted_at
        })
    else:  # public
        submission = data_item.public_submission
        public_assignment = submission.assigned_form if submission else None
        country = submission.country if submission else None
        submitted_at = submission.submitted_at.isoformat() if submission and submission.submitted_at is not None else None

        # Build form_item_info safely
        form_item = data_item.form_item
        form_item_info = None
        if form_item:
            section = getattr(form_item, 'form_section', None)
            template = getattr(form_item, 'template', None)
            form_item_info = format_form_item_info(
                form_item,
                section=section,
                template=template,
                public_assignment=public_assignment
            )

        base_data.update({
            'submission_id': submission.id if submission else None,
            'submission_type': 'public',
            'assignment_id': public_assignment.id if public_assignment else None,
            'assignment_name': public_assignment.period_name if public_assignment else None,
            'period_name': public_assignment.period_name if public_assignment else None,
            'template_id': public_assignment.template_id if public_assignment else None,
            'template_name': public_assignment.template.name if public_assignment and public_assignment.template else None,
            'country_info': format_country_info(country),
            'form_item_info': form_item_info,
            'date_collected': submitted_at,
            'submitted_at': submitted_at,
            'created_at': submitted_at
        })

    return base_data
