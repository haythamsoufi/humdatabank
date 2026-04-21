from functools import wraps
from flask import request, g, current_app
from flask_login import current_user
from app.services.security.api_authentication import authenticate_db_api_key_only


def _extract_api_key():
    """
    Extract API key from request.
    Standard method: Authorization header only (Bearer token).
    Query parameters are not accepted for security (keys must not appear in URLs/logs).

    Returns:
        tuple: (api_key: str or None, source: str) where source is 'header'
    """
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        api_key = auth_header[7:].strip()  # Remove 'Bearer ' prefix
        return api_key, 'header'
    return None, None

def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_result = authenticate_db_api_key_only()
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

        return f(*args, **kwargs)

    # Endpoint-registry metadata — read by scan_flask_routes()
    decorated_function._ep_auth = 'api_key'
    return decorated_function


def require_api_key_or_session(f):
    """
    Decorator that allows authentication via either:
    1. Valid API key in Authorization header (Bearer token)
    2. Active session (logged-in user)

    SECURITY: Use for endpoints that are accessed from both external API clients
    and the admin web interface.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # First check if user is logged in via session
        if current_user and current_user.is_authenticated:
            g.skip_auth = True
            return f(*args, **kwargs)

        # Otherwise, require Bearer API key (DB api_keys or MOBILE_APP_API_KEY env fallback)
        auth_result = authenticate_db_api_key_only()
        if hasattr(auth_result, "status_code"):
            return auth_result

        g.skip_auth = True
        return f(*args, **kwargs)

    # Endpoint-registry metadata — read by scan_flask_routes()
    decorated_function._ep_auth = 'api_key_or_session'
    return decorated_function
