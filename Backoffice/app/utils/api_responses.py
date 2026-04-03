# -*- coding: utf-8 -*-
"""
Centralized JSON API response helpers for admin/AJAX and internal endpoints.

Use this module when:
- Building JSON responses in admin routes, form builder, notifications, etc.
- Response shape is fixed (success/error, known keys).

Prefer these helpers over inline jsonify() for consistency. GENERIC_ERROR_MESSAGE
is re-exported from api_helpers.

=============================================================================
api_responses vs api_helpers – When to use which
=============================================================================

Use api_responses (this module) for:
  - Admin UI routes (/admin/*, form builder, notifications, settings)
  - Internal AJAX endpoints called by the Backoffice frontend
  - Fixed response shapes: json_ok(), json_bad_request(), json_server_error()
  - Error handling via handle_json_view_exception (returns json_error)

Use api_helpers for:
  - External API routes (/api/v1/*) consumed by mobile, third-party clients
  - Responses that need error_id for tracking/support
  - api_error() when you need error_id, debug_message, or custom extra fields
  - json_response() for custom JSON serialization or raw data pass-through

When to keep jsonify: pass-through responses (jsonify(result) where result
comes from a service), raw arrays, or responses with custom headers.

=============================================================================
Exception handling in JSON routes
=============================================================================

Use handle_json_view_exception (from app.utils.error_handling) for JSON/AJAX
routes that catch Exception:

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)

It performs rollback, logging, and returns json_error. Avoid ad-hoc
try/except with current_app.logger.error + json_server_error.

Alternatively use @json_error_handler('Route name') decorator for routes that
need global exception handling without per-route try/except.

Use GENERIC_ERROR_MESSAGE for generic 500 errors (avoids leaking internal details).

=============================================================================
JSON parsing
=============================================================================

Use get_json_safe() (from api_helpers) when the route expects JSON body only.
Use get_json_or_form() (from request_utils) when the route accepts both JSON
and form-encoded bodies. Avoid request.get_json(silent=True) directly.
"""
from functools import wraps

from flask import current_app, jsonify

# Re-export for convenience (avoid importing from api_helpers in routes)
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE  # noqa: F401


def json_error(message, status=400, **extra):
    """
    Return a JSON error response.

    :param message: Error message string
    :param status: HTTP status code (default 400)
    :param extra: Additional keys to include in the response (e.g. success=False)
    :return: Flask response tuple (response, status_code)
    """
    body = {'error': message, **extra}
    return jsonify(body), status


def json_auth_required(message='Authentication required. Please log in.'):
    """Return 401 Unauthorized JSON response."""
    return json_error(message, 401)


def json_forbidden(message='Access denied.', **extra):
    """Return 403 Forbidden JSON response."""
    return json_error(message, 403, **extra)


def json_not_found(message='Not found.', **extra):
    """Return 404 Not Found JSON response."""
    return json_error(message, 404, **extra)


def json_bad_request(message='Invalid request.', **extra):
    """Return 400 Bad Request JSON response."""
    return json_error(message, 400, **extra)


def json_form_errors(form, message='Validation failed'):
    """
    Return 400 JSON response with form validation errors for AJAX form handlers.

    :param form: WTForms form instance with .errors dict
    :param message: Optional error message
    :return: Flask response tuple (response, status_code)
    """
    return json_bad_request(message, success=False, errors=getattr(form, 'errors', {}))


def json_server_error(message='Internal server error.', **extra):
    """Return 500 Internal Server Error JSON response."""
    return json_error(message, 500, **extra)


def json_ok(data=None, **extra):
    """Return 200 OK JSON response with optional data."""
    body = {'success': True, **(data if isinstance(data, dict) else {}), **extra}
    if data is not None and not isinstance(data, dict):
        body['data'] = data
    return jsonify(body), 200


def json_ok_result(result, **extra):
    """
    Return 200 OK JSON response from a result value.
    If result is a dict (without 'success'), merge its keys; otherwise use data=result.
    Use instead of: return json_ok(**result) if isinstance(result, dict) else json_ok(data=result)
    """
    if isinstance(result, dict) and 'success' not in result:
        return json_ok(**result, **extra)
    return json_ok(data=result, **extra)


def json_accepted(**extra):
    """Return 202 Accepted JSON response (e.g. for async job submission)."""
    body = {'success': True, **extra}
    return jsonify(body), 202


def json_created(**extra):
    """Return 201 Created JSON response (e.g. for resource creation)."""
    body = {'success': True, **extra}
    return jsonify(body), 201


def require_json_keys(data, keys, message=None):
    """
    Validate that data (dict) contains all required keys. Use with get_json_safe() or request.get_json().

    :param data: Dict (e.g. from request body)
    :param keys: Iterable of required key names
    :param message: Optional custom error message; default lists missing keys
    :return: None if valid, or (response, status_code) tuple to return immediately
    """
    if not isinstance(data, dict):
        return json_bad_request(message or 'Invalid request body.')
    missing = [k for k in keys if k not in data or data[k] is None]
    if missing:
        return json_bad_request(message or f"Missing required: {', '.join(missing)}")
    return None


def require_json_data(data, message=None):
    """
    Validate that data is a non-empty dict. Use when body is required but no specific keys.

    :param data: Parsed request body (from get_json_safe())
    :param message: Optional error message
    :return: None if valid, or (response, status_code) to return immediately
    """
    if not isinstance(data, dict) or not data:
        return json_bad_request(message or 'No data provided')
    return None


def require_json_content_type():
    """
    Ensure request Content-Type is application/json. Use at start of JSON-only handlers.

    :return: None if valid, or (response, status_code) tuple (415) to return immediately
    """
    from flask import request
    ct = request.headers.get('Content-Type') or ''
    if not ct.strip().lower().startswith('application/json'):
        return json_error('Content-Type must be application/json', 415)
    return None


def json_select_options(items, fields=('id', 'name')):
    """
    Return 200 JSON response with serialized select options for dropdowns.

    :param items: Iterable of model instances (e.g. NSBranch.query.all())
    :param fields: Attribute names to include (default: id, name)
    :return: Flask response tuple (jsonify(serialize_select_options(...)), 200)
    """
    from app.utils.api_formatting import serialize_select_options
    return jsonify(serialize_select_options(items, fields)), 200


def json_error_handler(log_prefix='Error'):
    """
    Decorator that catches Exception, logs with exc_info, rolls back the DB transaction,
    and returns json_server_error. Use for JSON-only routes that want consistent
    error handling without per-route try/except.

    Usage:
        @bp.route('/api/foo')
        @json_error_handler('API foo')
        def api_foo():
            # No try/except needed for generic errors
            ...
    """

    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except Exception as e:
                from app.utils.transactions import request_transaction_rollback
                request_transaction_rollback(reason='json_error_handler')
                current_app.logger.error(f"{log_prefix}: {e}", exc_info=True)
                return json_server_error(GENERIC_ERROR_MESSAGE)
        return wrapped
    return decorator


def flash_and_json(message, category='success', success=True, redirect_url=None, status=200):
    """
    Flash a message and return a JSON response.
    Import flash from flask in the caller, or use: from flask import flash
    """
    from flask import flash
    flash(message, category)
    body = {'success': success, 'message': message}
    if redirect_url is not None:
        body['redirect_url'] = redirect_url
    return jsonify(body), status
