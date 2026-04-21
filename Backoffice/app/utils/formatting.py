# ========== Formatting Utilities ==========
"""
Utilities for formatting data for display.
Extracted from routes/main.py for better organization and reusability.
"""

import json
from typing import Any, Dict, Optional, Callable


def format_age_group_breakdown(age_groups: Dict[str, int], fmt_number_func: Callable[[Any], str]) -> str:
    """
    Format age group breakdown with visual hierarchy and clear labels.

    Args:
        age_groups: Dictionary of age group keys to counts
        fmt_number_func: Function to format numbers (e.g., with commas)

    Returns:
        HTML-formatted string with age group breakdown
    """
    def _format_age_group_label(age_group: str) -> str:
        """Convert age group codes to more readable labels."""
        age_group_mapping = {
            '_5': '>5',
            '5_17': '5-17',
            '18_49': '18-49',
            '50_': '50+',
            'unknown': 'Unknown',
            'male': 'Male',
            'female': 'Female',
            'total': 'Total'
        }
        return age_group_mapping.get(age_group, age_group.replace('_', '-'))

    # Filter out zero values
    non_zero_groups = [(age_group, count) for age_group, count in age_groups.items()
                      if count and count != 0]

    if not non_zero_groups:
        return "0"

    # Sort by logical order: total first, then by age ranges
    def sort_key(item):
        age_group, _ = item
        if age_group == 'total':
            return (0, age_group)
        elif age_group == 'unknown':
            return (999, age_group)
        elif age_group == '_5':
            return (1, age_group)
        elif age_group == '5_17':
            return (2, age_group)
        elif age_group == '18_49':
            return (3, age_group)
        elif age_group == '50_':
            return (4, age_group)
        else:
            return (100, age_group)

    non_zero_groups.sort(key=sort_key)

    # Format with HTML for better visual hierarchy
    parts = []
    for age_group, count in non_zero_groups:
        label = _format_age_group_label(age_group)
        formatted_count = fmt_number_func(count)
        parts.append(f'<span class="text-gray-600">{label}:</span> <span class="font-semibold text-green-600">{formatted_count}</span>')

    return " • ".join(parts)


def parse_field_value_for_display(
    value: Any,
    data_not_available: Optional[bool] = None,
    not_applicable: Optional[bool] = None
) -> str:
    """
    Parse field value to extract meaningful information for display in activity summaries.

    Args:
        value: Field value (can be string, dict, number, etc.)
        data_not_available: Data not available flag
        not_applicable: Not applicable flag

    Returns:
        Human-readable string representation
    """
    # Handle data availability flags first
    if data_not_available:
        return "Data not available"
    if not_applicable:
        return "Not applicable"

    if value is None:
        return "N/A"

    # Helper for number formatting
    def _fmt_number(n):
        try:
            return f"{int(n):,}"
        except Exception as e1:
            try:
                return f"{float(n):,}"
            except Exception as e2:
                import logging
                logging.getLogger(__name__).debug("format_value number failed: %s, %s", e1, e2)
                return str(n)

    # If value is a string that looks like a dict, try to parse it
    if isinstance(value, str) and value.strip().startswith('{'):
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            parsed = None
        if isinstance(parsed, dict):
            value = parsed

    # Handle dict values (disaggregated data)
    if isinstance(value, dict):
        if 'mode' in value and 'values' in value:
            # This is disaggregation data
            mode = value.get('mode', 'unknown')
            values = value.get('values', {})

            if mode == 'total':
                total_val = values.get('total') or values.get('direct')
                if total_val is not None:
                    return _fmt_number(total_val)

            elif mode == 'sex':
                if isinstance(values, dict):
                    sex_breakdown = ", ".join([f"{k}: {_fmt_number(v)}" for k, v in values.items() if v])
                    return sex_breakdown or "N/A"

            elif mode == 'age':
                return format_age_group_breakdown(values, _fmt_number)

            elif mode == 'sex_age':
                # Complex breakdown
                return f"Sex/Age breakdown ({len(values)} categories)"

        # Generic dict display
        return json.dumps(value)

    # Handle simple values
    try:
        # Try to format as number
        return _fmt_number(value)
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug("format_value failed: %s", e)
        return str(value)


def format_number(value: Any) -> str:
    """
    Format a number with thousands separators.

    Args:
        value: Number to format

    Returns:
        Formatted string
    """
    try:
        return f"{int(value):,}"
    except Exception as e1:
        try:
            return f"{float(value):,}"
        except Exception as e2:
            import logging
            logging.getLogger(__name__).debug("format_number failed: %s, %s", e1, e2)
            return str(value)


def format_currency(value: Any, currency_code: str = 'USD') -> str:
    """
    Format a number as currency.

    Args:
        value: Number to format
        currency_code: Currency code (e.g., 'USD', 'EUR')

    Returns:
        Formatted currency string
    """
    try:
        formatted = format_number(value)
        return f"{currency_code} {formatted}"
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug("format_currency failed: %s", e)
        return str(value)
