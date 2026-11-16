"""Jinja2 filters shared by the application factory and template context."""

import json

from markupsafe import Markup


def fromjson_filter(value, default=None):
    """
    Jinja2 filter to parse a JSON string.
    Returns default if parsing fails or value is None/empty.
    """
    if value is None:
        return default

    if isinstance(value, (list, dict)):
        return value

    if not isinstance(value, str):
        value = str(value)

    if value.strip() == "":
        return default

    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


def js_filter(value, default=""):
    """
    Jinja2 filter to safely emit a JavaScript literal using JSON encoding.
    """
    if value is None:
        value = default

    try:
        dumped = json.dumps(value, ensure_ascii=False)
    except TypeError:
        dumped = json.dumps(str(value), ensure_ascii=False)

    dumped = (
        dumped
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("'", "\\u0027")
    )
    return Markup(dumped)


def register_jinja_filters(app):
    """Register core Jinja2 filters on the application."""
    app.jinja_env.filters['fromjson'] = fromjson_filter
    app.jinja_env.filters['js'] = js_filter
