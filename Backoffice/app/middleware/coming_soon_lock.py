"""
Coming Soon lock middleware.

When COMING_SOON_LOCK=true, all routes except health checks and static assets
return a coming-soon page. Team members can bypass with COMING_SOON_BYPASS_SECRET.
"""

from __future__ import annotations

import hmac
from typing import Optional

from flask import current_app, g, make_response, render_template, request

from app.utils.api_responses import json_error
from app.utils.request_utils import is_json_request, is_static_asset_request

_BYPASS_COOKIE = "coming_soon_bypass"
_BYPASS_QUERY = "coming_soon_bypass"
_HEALTH_PATHS = frozenset({"/health"})


def _is_enabled() -> bool:
    return bool(current_app.config.get("COMING_SOON_LOCK"))


def _bypass_secret() -> str:
    return str(current_app.config.get("COMING_SOON_BYPASS_SECRET") or "").strip()


def _is_anonymous_root_health_probe() -> bool:
    """Match the root probe heuristic used by serve_root_health_probe_fast_path."""
    if request.path != "/" or request.method != "GET":
        return False

    user_agent = (request.headers.get("User-Agent") or "").strip()
    accept = (request.headers.get("Accept") or "").strip()
    has_cookies = bool((request.headers.get("Cookie") or "").strip())

    return not user_agent and (not accept or accept == "*/*") and not has_cookies


def _is_exempt_path() -> bool:
    if is_static_asset_request():
        return True
    if request.path in _HEALTH_PATHS:
        return True
    if request.path.startswith("/api/v1/uploads/branding/"):
        return True
    if _is_anonymous_root_health_probe():
        return True
    return False


def _token_matches(value: Optional[str]) -> bool:
    secret = _bypass_secret()
    if not secret or not value:
        return False
    return hmac.compare_digest(str(value), secret)


def _has_bypass() -> bool:
    if _token_matches(request.cookies.get(_BYPASS_COOKIE)):
        return True
    if _token_matches(request.args.get(_BYPASS_QUERY)):
        g.set_coming_soon_bypass_cookie = True
        return True
    return False


def _coming_soon_response():
    if is_json_request() or request.path.startswith("/api/"):
        return json_error(
            "The platform is not open yet. Please check back soon.",
            status=503,
            code="coming_soon",
        )

    response = make_response(
        render_template("public/coming_soon.html"),
        200,
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def register_coming_soon_lock_middleware(app):
    """Register before/after hooks for the coming-soon site lock."""

    @app.before_request
    def _enforce_coming_soon_lock():
        if not _is_enabled() or _is_exempt_path() or _has_bypass():
            return None
        return _coming_soon_response()

    @app.after_request
    def _persist_coming_soon_bypass_cookie(response):
        if not getattr(g, "set_coming_soon_bypass_cookie", False):
            return response

        secret = _bypass_secret()
        if not secret:
            return response

        response.set_cookie(
            _BYPASS_COOKIE,
            secret,
            httponly=True,
            secure=not current_app.debug,
            samesite="Lax",
            max_age=7 * 24 * 60 * 60,
        )
        return response
