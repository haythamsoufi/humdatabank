"""HTTP error handlers for the Flask application."""

import hashlib
import re
import sys
import traceback
import uuid
from contextlib import suppress

from flask import g, render_template, request, session, current_app, url_for, redirect, flash, jsonify
from flask_babel import _
from flask_login import current_user
from flask_wtf.csrf import CSRFError, generate_csrf

from app.utils.csp_nonce import get_style_nonce
from app.utils.logging_security import redact_url
from app.utils.redirect_utils import get_current_relative_url
from app.utils.request_utils import is_json_request
from app.utils.session_persistence import suppress_session_cookie_for_request

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_INBOUND_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
_MAX_TRACEBACK_FRAMES = 8


def get_request_id():
    """Correlation ID for the current request (reuses a well-formed inbound X-Request-ID)."""
    request_id = getattr(g, "request_id", None)
    if request_id:
        return request_id
    inbound = (request.headers.get(REQUEST_ID_HEADER) or "").strip()
    request_id = inbound if _VALID_INBOUND_REQUEST_ID.match(inbound) else uuid.uuid4().hex
    g.request_id = request_id
    return request_id


def _json_error_response(status, title, message, **extra):
    """Single JSON error envelope for every handler (detail stays server-side, keyed by request_id)."""
    body = {
        "success": False,
        "error": title,
        "message": message,
        "error_code": status,
        "request_id": get_request_id(),
    }
    body.update(extra)
    response = jsonify(body)
    response.status_code = status
    return response


def _html_error_response(app, error, status, title, message):
    return render_template(
        "errors/error.html",
        error_code=status,
        error_title=title,
        error_message=message,
        error_details=str(error) if app.config.get("DEBUG") else None,
        current_user=current_user,
        style_nonce=get_style_nonce(),
    ), status


def _current_user_id():
    if not getattr(current_user, "is_authenticated", False):
        return None
    user_id = None
    raw_user_id = session.get("_user_id")
    if raw_user_id is None:
        with suppress(Exception):
            raw_user_id = current_user.get_id()
    with suppress(Exception):
        user_id = int(raw_user_id) if raw_user_id is not None else None
    if user_id is None:
        with suppress(Exception):
            user_id = getattr(current_user, "id", None)
    return user_id


def _summarize_exception_for_storage(error):
    """
    Persistable description of a 500 that carries no exception text or local data.

    Exception messages routinely embed SQL parameters, file contents or user input, so only the
    exception type, a stable hash of the full traceback (to group recurrences) and the
    ``file:line function`` frames are stored. The full traceback goes to the application log only.
    """
    original = getattr(error, "original_exception", None) or error
    tb = getattr(original, "__traceback__", None)
    if tb is None:
        exc_type, exc_value, tb = sys.exc_info()
        original = exc_value or original
    frames = traceback.extract_tb(tb) if tb is not None else []
    rendered = "".join(traceback.format_list(frames))
    summary = {
        "exception_type": type(original).__name__,
        "traceback_hash": hashlib.sha256(rendered.encode("utf-8", "replace")).hexdigest()[:32] if rendered else None,
        "traceback_frames": [
            f"{frame.filename.replace(chr(92), '/').rsplit('/app/', 1)[-1]}:{frame.lineno} {frame.name}"
            for frame in frames[-_MAX_TRACEBACK_FRAMES:]
        ],
    }
    return summary


def _safe_csrf_reload_url():
    """Prefer the referring page so a failed POST returns to the form with a fresh token."""
    referrer = (request.referrer or "").strip()
    if referrer and referrer.startswith(request.host_url):
        return referrer
    with suppress(Exception):
        return url_for("main.dashboard")
    return "/"


def _is_context_switch_csrf_request():
    """True when CSRF failed on a country/entity navigation POST, not a data save."""
    values = request.values
    return "country_select" in values or "entity_select" in values


def _suppress_anonymous_session_cookie():
    """Do not emit a replacement session cookie for an unauthenticated CSRF failure."""
    suppress_session_cookie_for_request()


def register_error_handlers(app):
    """Register all HTTP error handlers on the Flask app."""

    @app.before_request
    def _assign_request_id():
        get_request_id()

    @app.after_request
    def _echo_request_id(response):
        with suppress(Exception):
            response.headers[REQUEST_ID_HEADER] = get_request_id()
        return response

    @app.errorhandler(CSRFError)
    def csrf_error(error):
        desc = getattr(error, "description", None) or "CSRF token missing or invalid"
        current_app.logger.warning(
            "CSRF validation failed: %s | %s %s | request_id=%s",
            desc,
            request.method,
            request.path,
            get_request_id(),
        )

        if is_json_request():
            # NOTE: deliberately not using json_bad_request()/json_error() here.
            # Both take the human message as their first positional arg named
            # `message` and build body = {'error': <that message>, **extra} — so
            # there is no way to pass both a fixed 'error' type string (which
            # responseIndicatesCsrfFailure() in csrf.js matches on) *and* a
            # distinct human-readable 'message' through that helper without one
            # silently clobbering the other or a duplicate-argument TypeError.
            if not getattr(current_user, "is_authenticated", False):
                _suppress_anonymous_session_cookie()
            response = jsonify({
                "success": False,
                "error": "CSRF validation failed",
                "message": "Your session needed a refresh. Please try again.",
                "error_code": 400,
                "request_id": get_request_id(),
                "csrf_refresh_required": True,
            })
            response.status_code = 400
            return response

        # No usable login session on this request. Do not flash() or mint a
        # CSRF token — that would write a new anonymous session cookie and
        # overwrite a login cookie the browser still has but omitted from this
        # POST (common on phones after OAuth / oversized cookies). Sending no
        # cookie gives the browser one more chance to present the real one: if
        # it does, /login sees an authenticated user and bounces straight back.
        if not getattr(current_user, "is_authenticated", False):
            _suppress_anonymous_session_cookie()
            with suppress(Exception):
                return redirect(
                    url_for(
                        "auth.login",
                        next=get_current_relative_url(),
                        session_expired=1,
                    )
                )
            return redirect("/login?session_expired=1")

        # Still logged in: token/referer mismatch. Refresh the token and return
        # to the page they came from. Country/entity switching is navigation,
        # not a data save — do not claim their submission was discarded.
        if _is_context_switch_csrf_request():
            flash_message = _("We could not switch your selection. Please try again.")
        else:
            flash_message = _(
                "Your session needed a refresh, so your last submission was not saved. Please try again."
            )
        with suppress(Exception):
            flash(flash_message, "warning")
        with suppress(Exception):
            generate_csrf()
        return redirect(_safe_csrf_reload_url())

    @app.errorhandler(400)
    def bad_request(error):
        detail = str(getattr(error, "description", None) or error or "").strip()
        with suppress(Exception):
            current_app.logger.warning(
                "HTTP 400: %s | %s %s | request_id=%s",
                detail[:500],
                request.method,
                request.path,
                get_request_id(),
            )
        message = "The request was invalid or malformed."
        if is_json_request():
            extra = {"detail": detail} if app.config.get("DEBUG") and detail else {}
            return _json_error_response(400, "Bad Request", message, **extra)
        return _html_error_response(
            app, error, 400, "Bad Request",
            "The request was invalid or malformed. Please check your input and try again.",
        )

    @app.errorhandler(401)
    def unauthorized(error):
        if is_json_request():
            return _json_error_response(
                401, "Unauthorized", "Authentication required to access this resource.",
            )
        # For browser requests, redirect to login so the user can continue
        # their session rather than seeing a dead-end error page.
        next_url = request.full_path.rstrip('?') or '/'
        return redirect(url_for('auth.login', next=next_url))

    @app.errorhandler(403)
    def forbidden(error):
        if not app.config.get('DEBUG'):
            try:
                from app.services.security.monitoring import SecurityMonitor

                SecurityMonitor.log_security_event(
                    event_type='http_403_forbidden',
                    severity='medium',
                    description=f'Access forbidden: {request.method} {request.path}'[:500],
                    context_data={
                        'url': (redact_url(request.url) or '')[:2000] if request else None,
                        'endpoint': request.endpoint if request else None,
                        'method': request.method if request else None,
                        'request_id': get_request_id(),
                    },
                    user_id=_current_user_id(),
                )
            except Exception:
                app.logger.debug('Failed to log 403 security event', exc_info=True)

        if is_json_request():
            return _json_error_response(
                403, "Forbidden",
                "You do not have permission to access this resource. If you have been on this page a long time, refresh the page and try again.",
            )
        return _html_error_response(
            app, error, 403, "Access Forbidden",
            "You do not have permission to access this resource. Please contact an administrator if you believe this is an error.",
        )

    @app.errorhandler(404)
    def not_found(error):
        if is_json_request():
            return _json_error_response(404, "Not Found", "The requested resource could not be found.")
        return _html_error_response(
            app, error, 404, "Page Not Found",
            "The page you are looking for does not exist. It may have been moved or deleted.",
        )

    @app.errorhandler(405)
    def method_not_allowed(error):
        allowed = ", ".join(sorted(getattr(error, "valid_methods", None) or []))
        if is_json_request():
            response = _json_error_response(
                405, "Method Not Allowed", "This resource does not support the requested method.",
            )
        else:
            response, _ = _html_error_response(
                app, error, 405, "Method Not Allowed",
                "This page does not support the requested action.",
            )
            response = current_app.make_response((response, 405))
        if allowed:
            response.headers["Allow"] = allowed
        return response

    @app.errorhandler(413)
    def payload_too_large(error):
        if is_json_request():
            return _json_error_response(413, "Payload Too Large", "The submitted content is too large.")
        return _html_error_response(
            app, error, 413, "Payload Too Large",
            "The submitted content is too large. Please reduce its size and try again.",
        )

    @app.errorhandler(429)
    def too_many_requests(error):
        retry_after = getattr(error, "retry_after", None)
        if is_json_request():
            extra = {"retry_after": int(retry_after)} if retry_after else {}
            response = _json_error_response(
                429, "Too Many Requests", "Too many requests. Please wait a moment and try again.", **extra,
            )
        else:
            response, _ = _html_error_response(
                app, error, 429, "Too Many Requests",
                "Too many requests. Please wait a moment and try again.",
            )
            response = current_app.make_response((response, 429))
        if retry_after:
            response.headers["Retry-After"] = str(int(retry_after))
        return response

    @app.errorhandler(500)
    def internal_error(error):
        request_id = get_request_id()
        app.logger.error(
            'Server Error [request_id=%s] %s %s: %s',
            request_id, request.method, request.path, error, exc_info=True,
        )

        if not app.config.get('DEBUG'):
            try:
                from app.services.security.monitoring import SecurityMonitor

                context_data = {
                    'url': redact_url(request.url) if request else 'Unknown URL',
                    'endpoint': request.endpoint if request else None,
                    'method': request.method if request else None,
                    'request_id': request_id,
                }
                context_data.update(_summarize_exception_for_storage(error))
                SecurityMonitor.log_security_event(
                    event_type='internal_server_error',
                    severity='critical',
                    description=f'Internal Server Error: {request.method} {request.path}'[:200],
                    context_data=context_data,
                    user_id=_current_user_id(),
                )

            except Exception as notify_error:
                app.logger.error(f"Failed to notify system managers of error: {notify_error}")

        if is_json_request():
            return _json_error_response(
                500, "Internal Server Error", "An unexpected error occurred. Please try again later.",
            )
        return _html_error_response(
            app, error, 500, "Internal Server Error",
            f"An unexpected error occurred on our end. We have been notified and are working to fix it. "
            f"Please try again later. Reference: {request_id}",
        )

    @app.errorhandler(502)
    def bad_gateway(error):
        if is_json_request():
            return _json_error_response(
                502, "Bad Gateway", "The server received an invalid response from an upstream server.",
            )
        return _html_error_response(
            app, error, 502, "Bad Gateway",
            "The server received an invalid response. Please try again in a few moments.",
        )

    @app.errorhandler(503)
    def service_unavailable(error):
        if is_json_request():
            return _json_error_response(
                503, "Service Unavailable", "The service is temporarily unavailable. Please try again later.",
            )
        return _html_error_response(
            app, error, 503, "Service Unavailable",
            "The service is temporarily unavailable due to maintenance or high load. Please try again later.",
        )
