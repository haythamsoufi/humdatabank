# ========== Route Helper Utilities ==========
"""
Helper functions for route handlers.
Extracted from route files to improve code organization and reusability.
"""

import logging
from flask import url_for

logger = logging.getLogger(__name__)


def normalize_value_for_display(value):
    """
    Simplify verbose labels like 'Total: 123' to '123' for summaries.

    Args:
        value: The value to normalize

    Returns:
        Normalized value suitable for display
    """
    try:
        if isinstance(value, str):
            parts = value.split(':', 1)
            if len(parts) == 2:
                candidate = parts[1].strip()
                # Strip thousands separators and validate numeric
                candidate_digits = candidate.replace(',', '').replace(' ', '')
                if candidate_digits.isdigit():
                    return candidate
        return value
    except Exception as e:
        logger.debug("normalize_value_for_display failed: %s", e)
        return value


def get_unified_form_url(form_type, form_id, action=None):
    """
    Convert old form URLs to new unified URLs.

    Args:
        form_type: 'assignment' or 'public-submission'
        form_id: The ID of the form/submission
        action: Optional action like 'edit', 'view', 'approve', etc.

    Returns:
        URL for the unified forms system

    Examples:
        get_unified_form_url('assignment', 123) -> '/forms/assignment/123'
        get_unified_form_url('public-submission', 456, 'edit') -> '/forms/public-submission/456/edit'
    """
    if action:
        return url_for(f'forms.{action}_{form_type.replace("-", "_")}', **{f'{form_type.replace("-", "_")}_id' if 'submission' in form_type else 'form_id': form_id})
    else:
        return url_for('forms.view_edit_form', form_type=form_type, form_id=form_id)


def get_unified_form_item_id(field):
    """
    Get the unified form_item_id for a field object.

    Args:
        field: A FormItem object

    Returns:
        int or None: The unified form_item_id, or None if not available
    """
    # If it's a FormItem, return its id
    if hasattr(field, 'item_type') and hasattr(field, 'id'):
        return field.id

    # If it's not a FormItem, we can't determine the ID
    return None
