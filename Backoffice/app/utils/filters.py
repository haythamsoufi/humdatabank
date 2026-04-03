import json
from markupsafe import Markup, escape

def normalize_type(type_str):
    """Normalize field type strings for consistent comparison."""
    if not type_str:
        return ''
    return str(type_str).lower()

def escapejs(value):
    """Escape a string to be safe for use in JavaScript strings."""
    if value is None:
        return ''
    # Use JSON encoding to properly escape the string for JavaScript
    return Markup(json.dumps(str(value))[1:-1])  # Remove surrounding quotes

def safe_json_attr(value):
    """Convert a value to JSON and make it safe for HTML attributes."""
    if value is None:
        return '{}'
    try:
        # Convert to JSON string
        json_str = json.dumps(value, ensure_ascii=False)
        # HTML escape the JSON string for safe use in attributes
        return Markup(json_str.replace('"', '&quot;').replace("'", '&#39;'))
    except (TypeError, ValueError):
        return '{}'

def strip_commas(value):
    """
    Strip commas and other grouping separators from numeric values to prevent browser parsing errors.
    Used for input value attributes that contain formatted numbers.
    Handles comma (e.g. en), apostrophe (e.g. de-CH), and spaces.
    """
    if value is None or value == '':
        return ''
    # Convert to string and remove commas, apostrophes, spaces, and other group separators
    str_value = str(value).replace(',', '').replace("'", '').replace(' ', '').replace('\u00A0', '').replace('\u202F', '')
    # If the result is 'None' or 'null' or 'undefined', return empty string
    if str_value.lower() in ('none', 'null', 'undefined'):
        return ''
    return str_value


def format_number(value):
    """
    Format a number with thousands separators (e.g. 1234567 -> 1,234,567).
    Used in PDF export for number fields and matrix cells.
    Non-numeric values are returned unchanged.
    """
    if value is None:
        return ''
    if isinstance(value, str) and value.strip() == '':
        return ''
    s = str(value).strip().replace(',', '').replace("'", '').replace('\u00A0', '').replace('\u202F', '')
    try:
        n = float(s)
    except ValueError:
        return value
    if n == int(n):
        return format(int(n), ',')
    return format(n, ',')


def to_number(value):
    """
    Parse a value to float, stripping commas and apostrophes (thousands separators).
    Returns 0 for None, empty, or invalid input. Used in PDF matrix totals.
    """
    if value is None:
        return 0.0
    s = str(value).strip().replace(',', '').replace("'", '').replace(' ', '').replace('\u00A0', '').replace('\u202F', '')
    if not s or s.lower() in ('none', 'null', 'undefined'):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def nl2br(value):
    """
    Convert newlines to <br> tags safely by escaping HTML first.

    Security: This filter escapes HTML entities BEFORE converting newlines,
    preventing XSS attacks when rendering user-controlled content.

    Usage in templates: {{ field.description|nl2br }}
    """
    if value is None:
        return ''
    # First escape HTML to prevent XSS, then convert newlines to <br>
    escaped = escape(str(value))
    return Markup(str(escaped).replace('\n', '<br>'))


def register_filters(app):
    """Register custom Jinja filters."""
    app.jinja_env.filters['normalize_type'] = normalize_type
    app.jinja_env.filters['escapejs'] = escapejs
    app.jinja_env.filters['safe_json_attr'] = safe_json_attr
    app.jinja_env.filters['strip_commas'] = strip_commas
    app.jinja_env.filters['format_number'] = format_number
    app.jinja_env.filters['to_number'] = to_number
    app.jinja_env.filters['nl2br'] = nl2br
