# ========== API Helper Utilities ==========
"""
Shared helpers for external API routes and error tracking.

Use api_helpers when:
- Building responses for external API consumers (e.g. /api/v1/*)
- You need error_id in responses for tracking/debugging
- You need json_response() for custom JSON serialization
- You need api_error() with debug_message or custom extra fields

For internal admin/AJAX routes with fixed response shapes, prefer
app.utils.api_responses (json_ok, json_bad_request, etc.) instead.

See api_responses module docstring for the full decision guide.
"""

import json
import uuid
import re
from typing import Dict

from flask import current_app, request
from contextlib import suppress

# Constants
MAX_PER_PAGE = 100000  # Maximum items per page for API requests
DEFAULT_PER_PAGE = 20
DEFAULT_PAGE = 1
PAST_ASSIGNMENT_DAYS = 30  # Days to consider an assignment as "past"

# SECURITY: Generic message for API/JSON error responses to avoid leaking internal details
GENERIC_ERROR_MESSAGE = "An internal error occurred."


def service_error(message: str, success: bool = False, **extra) -> Dict:
    """
    Return a standardized dict for service-layer error responses.

    Use in services that return {'success': False, 'error': str} to callers.
    Routes can pass the result to jsonify() or use api_responses helpers.

    Args:
        message: Error message
        success: Always False for errors
        **extra: Additional keys (e.g. code, details)

    Returns:
        Dict suitable for jsonify() or further processing.
    """
    return {'success': success, 'error': message, **extra}


def get_json_safe(default=None):
    """
    Safely parse JSON request body. Returns empty dict if request is not JSON or parsing fails.
    Use across routes instead of repeating request.get_json(silent=True) or {}.
    """
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else (default if default is not None else {})


def json_response(data, status_code=200, pretty=None):
    """Create JSON responses using Flask's JSON provider.
    - ensure_ascii=False for proper UTF-8
    - pretty print in debug by default (or override via pretty=True/False)
    - sort_keys=False to preserve dictionary insertion order
    """
    if pretty is None:
        # Pretty-print only in debug by default
        pretty = bool(getattr(current_app, 'debug', False))

    indent = 2 if pretty else None

    # Use standard json.dumps to ensure sort_keys=False and order preservation
    # Flask's JSON provider might not preserve order, so we use standard library
    json_data = json.dumps(data, ensure_ascii=False, indent=indent, sort_keys=False)

    return current_app.response_class(
        json_data,
        status=status_code,
        mimetype='application/json; charset=utf-8'
    )


def api_error(message, status_code=500, error_id=None, debug_message=None, extra: dict | None = None):
    """
    Create a standardized API error response.

    Args:
        message: User-friendly error message
        status_code: HTTP status code
        error_id: Optional error ID for tracking (generated if not provided)
        debug_message: Optional debug message (only shown in debug mode)
        extra: Optional dict of extra fields to include in the payload (e.g. hint codes).

    Returns:
        JSON response with error details
    """
    if not error_id:
        error_id = str(uuid.uuid4())

    error_data = {
        'error': message,
        'error_id': error_id
    }

    if extra and isinstance(extra, dict):
        # Do not allow overriding the core keys.
        for k, v in extra.items():
            if k in ("error", "error_id"):
                continue
            error_data[k] = v

    # SECURITY: Only include debug information in debug mode
    # Sanitize debug_message to prevent information leakage
    if current_app.debug and debug_message:
        # Remove potential path information and stack traces in production-like messages
        sanitized_debug = str(debug_message)
        # Don't expose full file paths - only show filename
        if '/' in sanitized_debug or '\\' in sanitized_debug:
            # Extract just the filename from paths
            sanitized_debug = re.sub(r'[^/\\]+[/\\]([^/\\]+)', r'\1', sanitized_debug)
        error_data['debug'] = sanitized_debug
    elif current_app.debug:
        # In debug mode, include error_id for tracking even without debug_message
        pass

    return json_response(error_data, status_code)


def extract_numeric_value(value):
    """Extract numeric value from a value that might be string, number, or None."""
    if value is None:
        return None
    with suppress(Exception):
        # If it's already a number, return it
        if isinstance(value, (int, float)):
            return float(value) if isinstance(value, float) else int(value)
        # If it's a string, try to parse it
        if isinstance(value, str):
            # Remove common formatting characters
            cleaned = value.strip().replace(',', '').replace(' ', '')
            # Try to parse as float first (handles decimals)
            try:
                return float(cleaned)
            except ValueError:
                # Try as int
                with suppress(ValueError):
                    return int(cleaned)
        # If it's a list or dict, try to find a numeric value
        if isinstance(value, list) and len(value) > 0:
            # Try first element
            return extract_numeric_value(value[0])
        if isinstance(value, dict):
            # Try common numeric keys
            for key in ['value', 'total', 'amount', 'count', 'number']:
                if key in value:
                    return extract_numeric_value(value[key])
    return None
