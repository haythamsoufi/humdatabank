"""
Unified mobile authentication decorator.

Replaces the scattered pattern of @login_required + @csrf.exempt +
enforce_api_or_csrf_protection() with a single decorator for all
mobile-facing routes.

Supports two authentication methods:
1. Flask session cookie (existing) -- for backward compatibility.
2. JWT Bearer token (Phase 3) -- stateless auth for mobile.
"""
from __future__ import annotations

from functools import wraps

from flask import current_app, g, request
from flask_login import current_user, login_user

from app.utils.mobile_responses import mobile_auth_error, mobile_forbidden
from app.utils.request_validation import enforce_api_or_csrf_protection


def _try_jwt_auth() -> bool:
    """
    Attempt to authenticate via ``Authorization: Bearer <mobile_jwt>``.
    Returns True if a valid mobile JWT was found and the user was loaded
    into ``current_user``.  Returns False if no Bearer header or the token
    is not a valid mobile JWT (so the caller can fall back to session auth).
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return False

    token = auth_header[7:].strip()
    if not token:
        return False

    try:
        from app.utils.mobile_jwt import decode_mobile_token
        claims = decode_mobile_token(token, expected_type="access")
    except Exception:
        return False

    from app import db
    from app.models import User
    user = db.session.get(User, claims.user_id)
    if not user or not user.is_active:
        return False

    # Honour admin force-logout: if the session embedded in this token has been
    # blacklisted (e.g. by an admin via the sessions UI), reject the token.
    if claims.sid:
        from app.services.user_analytics_service import is_session_blacklisted
        if is_session_blacklisted(claims.sid):
            return False

    login_user(user, remember=False)
    g._mobile_jwt_auth = True
    g._mobile_jwt_sid = claims.sid  # expose for downstream use if needed
    return True


def mobile_auth_required(f=None, *, permission: str | None = None):
    """
    Authentication decorator for mobile API routes.

    Enforces:
    1. User must be authenticated via either:
       - Flask-Login session cookie, OR
       - ``Authorization: Bearer <mobile_jwt>`` (JWT issued by the mobile
         token endpoint).
    2. For session-based auth on unsafe HTTP methods, requires either a valid
       ``X-Mobile-Auth`` header or a valid CSRF token.  JWT-based requests
       skip CSRF entirely (tokens are not cookie-based).
    3. Optionally checks an RBAC permission string.

    Usage::

        @mobile_bp.route('/foo', methods=['POST'])
        @mobile_auth_required
        def foo():
            ...

        @mobile_bp.route('/bar', methods=['POST'])
        @mobile_auth_required(permission='admin.users.edit')
        def bar():
            ...
    """
    def decorator(fn):
        @wraps(fn)
        def decorated_view(*args, **kwargs):
            # Always prefer JWT when a Bearer token is present — even if a
            # session cookie has already authenticated the user.  Without this,
            # mobile clients that send both a Cookie and a Bearer header end up
            # skipping `_try_jwt_auth()`, leaving `jwt_authenticated = False`,
            # and then triggering the CSRF / Referer check which mobile clients
            # never pass.
            bearer_presented = request.headers.get("Authorization", "").startswith("Bearer ")
            if bearer_presented:
                jwt_authenticated = _try_jwt_auth()
                # If the client explicitly sent a Bearer token but it failed
                # (e.g. expired access token), return 401 immediately so the
                # mobile app uses its refresh-token flow.  Do NOT fall through
                # to session/CSRF auth — that path would cause a confusing CSRF
                # 400 for POST requests even though the blueprint is exempt,
                # forcing an unnecessary CSRF retry round-trip.
                if not jwt_authenticated:
                    return mobile_auth_error(
                        "Access token invalid or expired. Please refresh."
                    )
            else:
                jwt_authenticated = getattr(g, '_mobile_jwt_auth', False)

            if not current_user.is_authenticated:
                return mobile_auth_error()

            if not jwt_authenticated and request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
                enforce_api_or_csrf_protection()

            if permission:
                from app.routes.admin.shared import user_has_permission
                if not user_has_permission(permission):
                    return mobile_forbidden(
                        f'{permission.replace("_", " ").title()} permission required.'
                    )

            # Track session activity for JWT-authenticated mobile requests so that
            # UserSessionLog.last_activity stays current.  Without this,
            # cookie-based update_session_activity() is a no-op for JWT clients and
            # the sessions page shows stale activity for mobile sessions.
            if jwt_authenticated:
                sid = getattr(g, '_mobile_jwt_sid', None)
                if sid:
                    try:
                        from app.services.user_analytics_service import _update_session_activity_explicit
                        # Use 'action' (touch-only): refreshes last_activity without
                        # incrementing actions_performed. Screen navigations are tracked
                        # via POST /analytics/screen-view; we avoid counting every API
                        # call as page_view or as a semantic "activity".
                        _update_session_activity_explicit(sid, 'action')
                    except Exception:
                        pass  # Never let tracking errors break the auth flow

            return fn(*args, **kwargs)

        # ── Endpoint-registry metadata ────────────────────────────────────
        # These attributes are read by scan_flask_routes() in api_management.py
        # to detect auth policy from live Flask routes without manual registry upkeep.
        decorated_view._ep_auth = 'rbac' if permission else 'user'
        if permission:
            decorated_view._ep_permission = permission
        return decorated_view

    if f is not None:
        return decorator(f)
    return decorator
