from __future__ import annotations

import hmac
import os
from typing import Optional, Iterable

from flask import current_app, request

from app.utils.api_responses import json_bad_request
from werkzeug.exceptions import Forbidden
from flask_wtf.csrf import CSRFError

from app.extensions import csrf


UNSAFE_HTTP_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def enforce_csrf_json(*, methods: Optional[Iterable[str]] = None):
    """
    Enforce CSRF for JSON/AJAX endpoints and return a JSON response on failure.

    This is intended for session-cookie (Flask-Login) routes that accept JSON
    and use unsafe HTTP methods. It returns a (json, status) tuple on failure,
    or None when CSRF validation passes / is not required.
    """
    allowed_methods = {m.upper() for m in (methods or UNSAFE_HTTP_METHODS)}
    if request.method.upper() not in allowed_methods:
        return None

    try:
        csrf.protect()
        return None
    except CSRFError as exc:
        # Log without leaking token contents
        current_app.logger.warning(
            "CSRF validation failed for %s (%s): %s",
            request.path,
            request.method,
            getattr(exc, "description", "CSRF validation failed"),
        )
        return json_bad_request(
            getattr(exc, "description", None) or "CSRF token missing or invalid",
            success=False,
            error="CSRF validation failed",
            message=getattr(exc, "description", None) or "CSRF token missing or invalid",
        )


def enforce_api_or_csrf_protection(
    *,
    header_name: Optional[str] = None,
    config_key: Optional[str] = None
) -> None:
    """
    Require a valid CSRF token for browser requests while still allowing
    trusted native clients (e.g., the Flutter mobile app) to authenticate via
    a shared secret header.
    """
    # Allow mobile/native requests that send the shared secret header.
    # Read directly from environment since these may not be in Flask config
    config_key_name = config_key or "MOBILE_NOTIFICATION_API_KEY"
    expected_secret = (
        os.environ.get(config_key_name)
        or os.environ.get("MOBILE_API_KEY")
        or current_app.config.get(config_key_name)
        or current_app.config.get("MOBILE_API_KEY")
    )
    incoming_token = request.headers.get(header_name or "X-Mobile-Auth")

    if incoming_token:
        if expected_secret and hmac.compare_digest(str(incoming_token), str(expected_secret)):
            return
        # Log more detailed warning to help diagnose the issue
        if not expected_secret:
            current_app.logger.warning(
                "Rejected mobile notification request: X-Mobile-Auth header present but "
                "MOBILE_NOTIFICATION_API_KEY not configured on server (from %s)",
                request.remote_addr,
            )
        else:
            # Debug: Log lengths and first/last chars to help diagnose without exposing secrets
            incoming_len = len(str(incoming_token))
            expected_len = len(str(expected_secret))
            incoming_preview = f"{str(incoming_token)[:2]}...{str(incoming_token)[-2:]}" if incoming_len > 4 else "***"
            expected_preview = f"{str(expected_secret)[:2]}...{str(expected_secret)[-2:]}" if expected_len > 4 else "***"
            current_app.logger.warning(
                "Rejected mobile notification request with invalid auth header from %s "
                "(header present but value does not match configured secret). "
                "Incoming length: %d, Expected length: %d, Incoming preview: %s, Expected preview: %s",
                request.remote_addr,
                incoming_len,
                expected_len,
                incoming_preview,
                expected_preview,
            )
        raise Forbidden("Invalid mobile authentication token.")

    # Fallback to the standard CSRF protection for browser-based requests.
    try:
        csrf.protect()
    except CSRFError as exc:
        current_app.logger.warning(
            "CSRF validation failed for notifications endpoint: %s", exc.description
        )
        raise
