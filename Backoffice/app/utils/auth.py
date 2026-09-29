from functools import wraps
from flask import request, g, current_app, redirect, url_for
from flask_login import current_user
from app.services.security.api_authentication import authenticate_db_api_key_only
from app.utils.redirect_utils import get_current_relative_url


def _stamp_capability(view, capability, scope_aware):
    """Record the declared capability where the enforcement point and the route scan read it."""
    view._ep_capability = capability
    view._ep_scope_aware = bool(scope_aware)
    return view


def api_capability(capability, *, scope_aware=False):
    """
    Declare the API-key capability a route needs, without adding an auth wrapper.

    For routes that authenticate inside the view with ``authenticate_api_request()``
    (API key *or* user session/Basic auth). Enforcement happens in that call; this only
    declares what it must enforce. ``scope_aware=True`` asserts the view filters every
    query with the key's data scope (``get_api_key_data_scope()``); otherwise data-scoped
    keys are refused.
    """
    def decorator(view):
        _stamp_capability(view, capability, scope_aware)
        if getattr(view, '_ep_auth', None) is None:
            view._ep_auth = 'api_key_or_session'
        return view
    return decorator


def require_api_key(f=None, *, capability=None, scope_aware=False):
    """
    Require an API key that holds ``capability``.

    Usage: ``@require_api_key(capability=DATA_READ, scope_aware=True)``. Keys are read from
    ``Authorization: Bearer`` or ``X-API-Key``; ``?api_key=`` only works for keys that opted
    in (see ``allow_query_api_key``). A route that declares no capability is denied.
    """
    def decorator(view):
        @wraps(view)
        def decorated_function(*args, **kwargs):
            auth_result = authenticate_db_api_key_only(capability=capability, scope_aware=scope_aware)
            if hasattr(auth_result, "status_code"):
                return auth_result

            # Skip user authentication for API routes
            g.skip_auth = True

            # Log successful API key usage (optional, can be disabled in production)
            if current_app.config.get('LOG_API_KEY_USAGE', False):
                current_app.logger.info(
                    f"API key authenticated from {request.remote_addr} "
                    f"(endpoint: {request.endpoint})"
                )

            return view(*args, **kwargs)

        # Endpoint-registry metadata — read by scan_flask_routes()
        decorated_function._ep_auth = 'api_key'
        _stamp_capability(decorated_function, capability, scope_aware)
        return decorated_function

    if f is None:
        return decorator
    return decorator(f)


def _is_browser_navigation_without_api_key() -> bool:
    """True for an HTML document request with no attempted API credentials."""
    if request.method not in {"GET", "HEAD"}:
        return False
    if request.headers.get("Authorization", "").strip():
        return False
    if (
        request.headers.get("X-API-Key", "").strip()
        or request.headers.get("X-API-KEY", "").strip()
    ):
        return False
    if (request.args.get("api_key") or "").strip():
        return False
    return "text/html" in request.headers.get("Accept", "").lower()


def require_api_key_or_session(f=None, *, capability=None, scope_aware=False, browser_login_redirect: bool = False):
    """
    Decorator that allows authentication via either:
    1. Active session (logged-in user): governed by the user's RBAC, not key capabilities
    2. API key holding ``capability`` (Bearer or X-API-Key; ``?api_key=`` only for keys
       that opted in)

    Routes intended for direct browser navigation may opt into
    ``browser_login_redirect=True``. Anonymous HTML requests without an API key
    are then redirected to login, while API clients and invalid-key attempts retain
    the normal JSON 401 response.

    SECURITY: Use for endpoints that are accessed from both external API clients
    and the admin web interface. A route that declares no capability is denied to keys.
    """
    def decorator(view):
        @wraps(view)
        def decorated_function(*args, **kwargs):
            # First check if user is logged in via session
            if current_user and current_user.is_authenticated:
                g.skip_auth = True
                return view(*args, **kwargs)

            if browser_login_redirect and _is_browser_navigation_without_api_key():
                return redirect(
                    url_for("auth.login", next=get_current_relative_url())
                )

            auth_result = authenticate_db_api_key_only(capability=capability, scope_aware=scope_aware)
            if hasattr(auth_result, "status_code"):
                return auth_result

            g.skip_auth = True
            return view(*args, **kwargs)

        # Endpoint-registry metadata — read by scan_flask_routes()
        decorated_function._ep_auth = 'api_key_or_session'
        _stamp_capability(decorated_function, capability, scope_aware)
        return decorated_function

    if f is None:
        return decorator
    return decorator(f)
