"""
Site lock middleware.

When COMING_SOON_LOCK or MAINTENANCE_LOCK is true, all routes except health
checks and static assets return a lock page. Maintenance takes precedence when
both flags are enabled. Team bypass via *_BYPASS_SECRET query/cookie params.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from typing import Optional

from flask import current_app, g, make_response, render_template, request

from app.utils.api_responses import json_error
from app.utils.request_utils import is_json_request, is_static_asset_request

_HEALTH_PATHS = frozenset({"/health"})


@dataclass(frozen=True)
class _LockMode:
    key: str
    bypass_cookie: str
    bypass_query: str
    bypass_secret_config: str
    bypass_flag: str
    template: str
    api_message: str
    api_code: str


_MODES = {
    "maintenance": _LockMode(
        key="maintenance",
        bypass_cookie="maintenance_bypass",
        bypass_query="maintenance_bypass",
        bypass_secret_config="MAINTENANCE_BYPASS_SECRET",
        bypass_flag="set_maintenance_bypass_cookie",
        template="public/maintenance.html",
        api_message="The platform is temporarily unavailable for maintenance. Please try again later.",
        api_code="maintenance",
    ),
    "coming_soon": _LockMode(
        key="coming_soon",
        bypass_cookie="coming_soon_bypass",
        bypass_query="coming_soon_bypass",
        bypass_secret_config="COMING_SOON_BYPASS_SECRET",
        bypass_flag="set_coming_soon_bypass_cookie",
        template="public/coming_soon.html",
        api_message="The platform is not open yet. Please check back soon.",
        api_code="coming_soon",
    ),
}


def _active_mode() -> Optional[_LockMode]:
    if current_app.config.get("MAINTENANCE_LOCK"):
        return _MODES["maintenance"]
    if current_app.config.get("COMING_SOON_LOCK"):
        return _MODES["coming_soon"]
    return None


def _bypass_secret(mode: _LockMode) -> str:
    return str(current_app.config.get(mode.bypass_secret_config) or "").strip()


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


def _token_matches(value: Optional[str], secret: str) -> bool:
    if not secret or not value:
        return False
    return hmac.compare_digest(str(value), secret)


def _has_bypass(mode: _LockMode) -> bool:
    secret = _bypass_secret(mode)
    if _token_matches(request.cookies.get(mode.bypass_cookie), secret):
        return True
    if _token_matches(request.args.get(mode.bypass_query), secret):
        setattr(g, mode.bypass_flag, True)
        return True
    return False


def _lock_response(mode: _LockMode):
    if is_json_request() or request.path.startswith("/api/"):
        return json_error(
            mode.api_message,
            status=503,
            code=mode.api_code,
        )

    response = make_response(render_template(mode.template), 200)
    response.headers["Cache-Control"] = "no-store"
    return response


def register_site_lock_middleware(app):
    """Register before/after hooks for coming-soon and maintenance site locks."""

    @app.before_request
    def _enforce_site_lock():
        mode = _active_mode()
        if mode is None or _is_exempt_path() or _has_bypass(mode):
            return None
        return _lock_response(mode)

    @app.after_request
    def _persist_site_lock_bypass_cookie(response):
        for mode in _MODES.values():
            if not getattr(g, mode.bypass_flag, False):
                continue

            secret = _bypass_secret(mode)
            if not secret:
                continue

            response.set_cookie(
                mode.bypass_cookie,
                secret,
                httponly=True,
                secure=not current_app.debug,
                samesite="Lax",
                max_age=7 * 24 * 60 * 60,
            )
        return response


# Backward-compatible alias used during rollout of the renamed middleware.
register_coming_soon_lock_middleware = register_site_lock_middleware
