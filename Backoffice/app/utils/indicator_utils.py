"""
Utility functions for indicator-related operations.
"""

from config import Config


def supports_disaggregation(unit, indicator_type=None):
    """
    Check if an indicator supports disaggregation based on its unit and type.

    Args:
        unit (str): The unit of the indicator (e.g., 'People', 'Staff', 'Volunteers', '%', etc.)
        indicator_type (str, optional): The type of the indicator (e.g., 'Number', 'Percentage')
                                       If not provided, only unit is checked for backward compatibility.

    Returns:
        bool: True if the indicator supports disaggregation, False otherwise.
    """
    if not unit:
        return False

    # Check if unit is in the allowed units for disaggregation
    unit_supports_disagg = unit in Config.DISAGGREGATION_ALLOWED_UNITS

    # If indicator_type is provided, also check that it's 'Number'
    if indicator_type is not None:
        type_supports_disagg = indicator_type and indicator_type.lower() == 'number'
        return unit_supports_disagg and type_supports_disagg

    # Backward compatibility: if no type provided, only check unit
    return unit_supports_disagg


def get_allowed_disaggregation_modes(unit, indicator_type=None, allowed_options=None):
    """
    Get the allowed disaggregation modes for an indicator.

    Args:
        unit (str): The unit of the indicator
        indicator_type (str, optional): The type of the indicator
        allowed_options (list, optional): Pre-configured allowed options for this indicator

    Returns:
        list: List of allowed disaggregation mode keys (e.g., ['total', 'sex', 'age'])
    """
    if not supports_disaggregation(unit, indicator_type):
        return ['total']

    if allowed_options:
        return allowed_options

    return ['total']  # Default fallback


def slugify_age_group(age_group):
    """
    Convert an age group string into a valid slug for use in form field names.

    Delegates to the canonical implementation in form_processing.
    Use app.utils.form_processing.slugify_age_group for direct imports.

    Args:
        age_group (str): The age group string (e.g., '0-4', '5-17', '18+')

    Returns:
        str: A slugified version (e.g., '0_4', '5_17', '18_')
    """
    from app.services.form_processing_service import slugify_age_group as _canonical_slugify
    return _canonical_slugify(age_group)
