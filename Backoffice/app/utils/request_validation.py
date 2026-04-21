"""
Mobile ↔ Backend Authentication Contract
=========================================

The mobile app (Flutter) and the Backoffice (Flask) share the following auth model:

**Authentication mechanisms (in order of preference):**

1. **JSON API login** (``POST /api/v1/auth/login``)
   Returns a Flask session cookie and CSRF token as JSON. The mobile app stores
   the session cookie in FlutterSecureStorage and sends it as a ``Cookie`` header
   on subsequent requests. No HTML scraping required.

2. **Azure B2C / IFRC login** (WebView to ``/login/azure``)
   The mobile app opens a WebView, the user authenticates with Azure, and the
   backend sets a session cookie which the app extracts from the WebView cookies.

**Request authentication headers (sent by mobile on each request):**

- ``Cookie: session=<value>`` — Flask-Login session identity (required for all
  authenticated routes).
- ``X-Mobile-Auth: <MOBILE_APP_API_KEY>`` — shared API key (``api_keys`` table or
  optional ``MOBILE_APP_API_KEY`` env when no DB row matches) that proves the
  request originates from the mobile app. Used by
  ``enforce_api_or_csrf_protection()`` to skip CSRF for non-browser clients.
- ``Authorization: Bearer <MOBILE_APP_API_KEY>`` — same key, sent only on
  ``/api/v1/...`` routes for unauthenticated public data reads.
- ``X-CSRFToken: <token>`` — CSRF token for session-backed unsafe methods on
  routes that do *not* use ``enforce_api_or_csrf_protection``.

**CSRF handling for mobile-facing POST/PUT/PATCH/DELETE routes:**

All mobile-facing mutation endpoints MUST use one of:

  a) ``@csrf.exempt`` + ``enforce_api_or_csrf_protection()`` at the top of the
     view.  This accepts either a valid ``X-Mobile-Auth`` header OR a valid CSRF
     token, so both mobile and browser clients work.

  b) Normal Flask-WTF CSRF (the mobile app sends ``X-CSRFToken`` obtained from
     ``GET /api/v1/csrf-token``).  This is acceptable but less reliable than (a).

Option (a) is the standard pattern for all new mobile-facing routes.

**Dedicated JSON API endpoints (Phase 1 -- no HTML scraping):**

- ``POST /api/v1/auth/login`` — JSON login
- ``POST /api/v1/auth/change-password`` — JSON password change
- ``GET  /api/v1/auth/profile`` — JSON profile read
- ``PUT  /api/v1/auth/profile`` — JSON profile update
- ``GET  /api/v1/csrf-token`` — issue CSRF token for session

**AI chat uses a separate JWT** issued by ``GET /api/ai/v2/token`` (session
required); it is independent of ``X-Mobile-Auth``.
"""
from __future__ import annotations

from typing import Iterable, Optional

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


def enforce_api_or_csrf_protection() -> None:
    """
    Require CSRF for browser session requests, or accept ``X-Mobile-Auth`` when it
    matches an active DB ``api_keys`` row or the optional ``MOBILE_APP_API_KEY``
    env value (same plaintext as ``Authorization: Bearer`` for /api/v1).
    """
    from app.services.security.api_authentication import validate_plaintext_db_api_key_for_mobile_auth

    incoming_token = (request.headers.get("X-Mobile-Auth") or "").strip() or None

    if incoming_token:
        if validate_plaintext_db_api_key_for_mobile_auth(incoming_token):
            return

        current_app.logger.warning(
            "Rejected X-Mobile-Auth from %s for %s: not a valid DB API key",
            request.remote_addr,
            request.path,
        )
        raise Forbidden("Invalid mobile authentication token.")

    try:
        csrf.protect()
    except CSRFError as exc:
        current_app.logger.warning(
            "CSRF validation failed for notifications endpoint: %s", exc.description
        )
        raise
