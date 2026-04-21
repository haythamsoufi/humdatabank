# File: Backoffice/app/routes/admin/shared.py
"""
Shared utilities and decorators for admin modules
"""

from flask import current_app, flash, redirect, url_for, session, request
from flask_login import current_user, login_user
from functools import wraps
from app.models import User
from app.utils.redirect_utils import get_current_relative_url
from app.utils.api_responses import json_auth_required, json_error, json_forbidden
from app.utils.request_utils import is_json_request


def _is_json_request():
    """Alias for is_json_request; prefer importing from app.utils.request_utils."""
    return is_json_request()


def _apply_rbac_metadata(decorated_fn, source_fn, **overrides):
    """
    Apply RBAC metadata to decorated_fn: set overrides, then copy any _rbac_* attrs
    not overridden from source_fn. Wraps in try/except to avoid decorator failures.
    """
    try:
        for key, value in overrides.items():
            setattr(decorated_fn, key, value)
        defaults = {"_rbac_permissions_required": [], "_rbac_permissions_any_required": []}
        for key in ("_rbac_admin_required", "_rbac_permissions_required", "_rbac_permissions_any_required", "_rbac_system_manager_required", "_rbac_guard_audit_exempt", "_rbac_guard_audit_exempt_reason"):
            if key not in overrides:
                val = getattr(source_fn, key, None)
                if val is not None:
                    setattr(decorated_fn, key, list(val) if isinstance(val, (list, tuple)) else val)
                elif key in defaults:
                    setattr(decorated_fn, key, defaults[key])
                elif key in ("_rbac_admin_required", "_rbac_system_manager_required", "_rbac_guard_audit_exempt"):
                    setattr(decorated_fn, key, False)
                elif key == "_rbac_guard_audit_exempt_reason":
                    setattr(decorated_fn, key, "")
    except Exception as e:
        current_app.logger.debug("RBAC metadata setup failed: %s", e)


def _auto_login_system_manager_if_debug():
    """
    When DEBUG_SKIP_LOGIN is set and user is not authenticated,
    try to log in as a system manager. No-op otherwise.

    Security: only allowed when DEBUG is also True (enforced at startup)
    and the request originates from a loopback address.
    """
    if not current_app.config.get("DEBUG_SKIP_LOGIN"):
        return
    if current_user.is_authenticated:
        return

    remote_addr = request.remote_addr or ""
    if remote_addr not in ("127.0.0.1", "::1", "localhost"):
        current_app.logger.warning(
            "DEBUG_SKIP_LOGIN: rejected auto-login from non-loopback address %s",
            remote_addr,
        )
        return

    try:
        from app.models.rbac import RbacUserRole, RbacRole
        sys_mgr = (
            User.query.join(RbacUserRole, User.id == RbacUserRole.user_id)
            .join(RbacRole, RbacUserRole.role_id == RbacRole.id)
            .filter(RbacRole.code == "system_manager")
            .first()
        )
    except Exception as e:
        current_app.logger.debug("DEBUG_SKIP_LOGIN: could not find system manager: %s", e)
        sys_mgr = None
    if sys_mgr:
        current_app.logger.info("DEBUG_SKIP_LOGIN: auto-login as %s from %s", sys_mgr.email, remote_addr)
        login_user(sys_mgr)


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_app.config.get('DEBUG_SKIP_LOGIN'):
            if not current_user.is_authenticated:
                flash("Access denied. Please log in.", "warning")
                return redirect(url_for("auth.login", next=get_current_relative_url()))
            # RBAC-only: allow into /admin only if the user is a system manager,
            # or has at least one admin permission (routes still gate specifics).
            from app.services.authorization_service import AuthorizationService

            if not AuthorizationService.is_admin(current_user):
                flash("Access denied. Admin privileges required.", "warning")
                return redirect(url_for("main.dashboard"))
        else:  # pragma: no cover -- DEBUG_SKIP_LOGIN
            if current_user.is_authenticated:
                from app.services.authorization_service import AuthorizationService
                if not AuthorizationService.is_admin(current_user):
                    flash("Access denied. Admin privileges required even with DEBUG_SKIP_LOGIN if logged in as non-admin.", "warning")
                    return redirect(url_for("main.dashboard"))
            else:
                _auto_login_system_manager_if_debug()
        return f(*args, **kwargs)
    _apply_rbac_metadata(decorated_function, f, _rbac_admin_required=True)
    return decorated_function


def permission_required(permission_name):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            is_json_request = _is_json_request()

            if not current_app.config.get('DEBUG_SKIP_LOGIN'):
                if not current_user.is_authenticated:
                    if is_json_request:
                        return json_auth_required()
                    flash("Access denied. Please log in.", "warning")
                    return redirect(url_for("auth.login", next=get_current_relative_url()))
                if not user_has_permission(permission_name):
                    if is_json_request:
                        return json_forbidden(f'{permission_name.replace("_", " ").title()} permission required.')
                    flash(f"Access denied. {permission_name.replace('_', ' ').title()} permission required.", "warning")
                    return redirect(url_for("main.dashboard"))
            else:  # DEBUG_SKIP_LOGIN
                if current_user.is_authenticated and not user_has_permission(permission_name):
                    if is_json_request:
                        return json_forbidden(
                            f'{permission_name.replace("_", " ").title()} permission required even with DEBUG_SKIP_LOGIN.'
                        )
                    flash(f"Access denied. {permission_name.replace('_', ' ').title()} permission required even with DEBUG_SKIP_LOGIN.", "warning")
                    return redirect(url_for("main.dashboard"))
                elif not current_user.is_authenticated:
                    _auto_login_system_manager_if_debug()
            return f(*args, **kwargs)
        # Metadata for startup-time guard auditing
        existing = set(getattr(f, "_rbac_permissions_required", []) or [])
        if isinstance(permission_name, str) and permission_name.strip():
            existing.add(permission_name.strip())
        _apply_rbac_metadata(decorated_function, f, _rbac_permissions_required=sorted(existing))
        return decorated_function
    return decorator


def system_manager_required(f):
    """
    Restrict a route to System Managers only.

    Use in addition to @admin_required for admin routes.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from app.services.authorization_service import AuthorizationService

        is_json_request = _is_json_request()

        # Authentication is handled by admin_required / permission_required.
        if not current_user.is_authenticated:
            if is_json_request:
                return json_auth_required()
            flash("Access denied. Please log in.", "warning")
            return redirect(url_for("auth.login", next=get_current_relative_url()))

        if not AuthorizationService.is_system_manager(current_user):
            if is_json_request:
                return json_forbidden('System manager privileges required.')
            flash("Access denied. System manager privileges required.", "warning")
            return redirect(url_for("admin.admin_dashboard"))

        return f(*args, **kwargs)
    _apply_rbac_metadata(decorated_function, f, _rbac_system_manager_required=True)
    return decorated_function


def permission_required_any(*permission_names):
    """
    Require that the current user has at least one of the provided RBAC permissions.

    Usage:
        @permission_required_any('admin.templates.edit', 'admin.translations.manage')
    """
    # Allow passing a single iterable
    if len(permission_names) == 1 and isinstance(permission_names[0], (list, tuple, set)):
        permission_names = tuple(permission_names[0])

    # Normalize / filter invalid entries early
    permission_names = tuple(
        p.strip() for p in permission_names
        if isinstance(p, str) and "." in p and p.strip()
    )

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            is_json_request = _is_json_request()

            if not current_app.config.get('DEBUG_SKIP_LOGIN'):
                if not current_user.is_authenticated:
                    if is_json_request:
                        return json_auth_required()
                    flash("Access denied. Please log in.", "warning")
                    return redirect(url_for("auth.login", next=get_current_relative_url()))

                allowed = any(user_has_permission(p) for p in permission_names)
                if not allowed:
                    if is_json_request:
                        return json_error('Permission required.', 403, required_permissions=list(permission_names))
                    flash("Access denied. Permission required.", "warning")
                    return redirect(url_for("main.dashboard"))

            else:  # pragma: no cover
                if current_user.is_authenticated:
                    allowed = any(user_has_permission(p) for p in permission_names)
                    if not allowed:
                        if is_json_request:
                            return json_error(
                                'Permission required even with DEBUG_SKIP_LOGIN.',
                                403,
                                required_permissions=list(permission_names)
                            )
                        flash("Access denied. Permission required even with DEBUG_SKIP_LOGIN.", "warning")
                        return redirect(url_for("main.dashboard"))
                else:
                    _auto_login_system_manager_if_debug()

            return f(*args, **kwargs)
        # Metadata for startup-time guard auditing
        existing = set(getattr(f, "_rbac_permissions_any_required", []) or [])
        for p in permission_names:
            if isinstance(p, str) and p.strip():
                existing.add(p.strip())
        _apply_rbac_metadata(decorated_function, f, _rbac_permissions_any_required=sorted(existing))
        return decorated_function
    return decorator


def rbac_guard_audit_exempt(reason: str = ""):
    """
    Mark an /admin route as intentionally unguarded for startup RBAC audits.

    Use this only for endpoints that are explicitly meant to be public or are
    protected by non-standard controls.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            return f(*args, **kwargs)

        _apply_rbac_metadata(
            decorated_function, f,
            _rbac_guard_audit_exempt=True,
            _rbac_guard_audit_exempt_reason=str(reason or "").strip()
        )
        return decorated_function
    return decorator


def admin_permission_required(permission_name):
    """
    Apply admin_required + permission_required in one decorator.
    Reduces boilerplate where both are stacked.
    """
    def decorator(f):
        return admin_required(permission_required(permission_name)(f))
    return decorator


def admin_permission_required_any(*permission_names):
    """
    Apply admin_required + permission_required_any in one decorator.
    Reduces boilerplate where both are stacked.
    """
    def decorator(f):
        return admin_required(permission_required_any(*permission_names)(f))
    return decorator


def user_has_permission(permission_name):
    """Check if the current user has the specified permission.

    RBAC-only: `permission_name` must be an RBAC permission code (e.g. 'admin.users.view').
    """
    if not current_user.is_authenticated:
        return False

    if not isinstance(permission_name, str) or "." not in permission_name:
        return False
    from app.services.authorization_service import AuthorizationService
    return AuthorizationService.has_rbac_permission(current_user, permission_name.strip())

def check_template_access(template_id, user_id):
    """
    Check if a user has access to a template (owner or shared with).

    Args:
        template_id: ID of the template to check
        user_id: ID of the user to check access for

    Returns:
        bool: True if user has access, False otherwise
    """
    # Delegate to the centralized authorization service to avoid drift and
    # correctly evaluate system-manager access for the provided user_id.
    from app.services.authorization_service import AuthorizationService
    return bool(AuthorizationService.check_template_access(int(template_id), int(user_id)))


# Re-export from form_localization for backward compatibility
from app.utils.form_localization import (
    get_localized_sector_name,
    get_localized_subsector_name,
)
