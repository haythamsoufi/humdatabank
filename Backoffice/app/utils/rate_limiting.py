# Backoffice/app/utils/rate_limiting.py

import time
from functools import wraps
from flask import request, current_app, flash, redirect, url_for

from app.utils.api_responses import json_error
from app.utils.request_utils import is_json_request
from collections import defaultdict, deque
import threading
from app.services.user_analytics_service import get_client_ip

# In-memory rate limiting storage.
# SECURITY NOTE: This storage is per-process. In multi-worker deployments (e.g.
# Gunicorn with multiple workers), each worker maintains its own counters,
# effectively multiplying the allowed rate by the number of workers. For
# production, configure RATELIMIT_STORAGE_URI to a shared Redis instance so
# Flask-Limiter (used on other routes) shares state. The custom deque-based
# limiter below would also need a Redis backend for cross-worker enforcement.
_rate_limit_storage = defaultdict(lambda: deque(maxlen=100))
_rate_limit_lock = threading.Lock()

def rate_limit(requests_per_minute=10, key_func=None, flash_message=None, redirect_to=None, methods=None):
    """
    Rate limiting decorator for Flask routes.

    Args:
        requests_per_minute: Maximum requests allowed per minute
        key_func: Function to generate rate limit key (defaults to IP address)
        flash_message: Optional custom flash message for web requests (defaults to standard message)
        redirect_to: Optional route name to redirect to on rate limit (for web requests)
        methods: HTTP methods to apply the limit to (e.g. ['POST']). None means all methods.

    Returns:
        Decorator function
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Skip rate limiting only when RATE_LIMIT_SKIP_DEBUG is explicitly
            # enabled and DEBUG is on (local development convenience).
            # In staging/production DEBUG should be False, so this never fires.
            if current_app.config.get('DEBUG') and current_app.config.get('RATE_LIMIT_SKIP_DEBUG', True):
                return f(*args, **kwargs)

            # Only count specified methods (e.g. skip GET for login page loads)
            if methods and request.method not in methods:
                return f(*args, **kwargs)

            # Generate rate limit key
            if key_func:
                key = key_func()
            else:
                # Use get_client_ip() to properly handle proxies
                key = get_client_ip()

            # Get current timestamp
            now = time.time()

            with _rate_limit_lock:
                # Clean old entries (older than 1 minute)
                while _rate_limit_storage[key] and _rate_limit_storage[key][0] < now - 60:
                    _rate_limit_storage[key].popleft()

                # Check if rate limit exceeded
                if len(_rate_limit_storage[key]) >= requests_per_minute:
                    current_app.logger.warning(f"Rate limit exceeded for {key} on {request.endpoint}")

                    # Check if this is a JSON/API request
                    if is_json_request():
                        # Return JSON response for API requests
                        return json_error(
                            'Rate limit exceeded. Please try again later.',
                            429,
                            success=False,
                            error='Rate limit exceeded. Please try again later.',
                            retry_after=60,
                        )
                    else:
                        # Flash message and redirect for web requests
                        message = flash_message or f'Rate limit exceeded. Please wait {60} seconds before trying again.'
                        flash(message, 'warning')

                        # Redirect to specified route or back to the same endpoint
                        if redirect_to:
                            # For POST requests, redirect to GET the same page to show flash message
                            return redirect(url_for(redirect_to))
                        elif request.endpoint:
                            # For POST requests, redirect to GET the same endpoint
                            # Extract just the path without query params to avoid redirect loops
                            return redirect(request.path)
                        else:
                            # Fallback: redirect to main page
                            try:
                                return redirect(url_for('main.index'))
                            except Exception as e:
                                current_app.logger.debug("Rate limit redirect fallback failed; redirecting to '/': %s", e, exc_info=True)
                                return redirect('/')

                # Add current request timestamp
                _rate_limit_storage[key].append(now)

            return f(*args, **kwargs)
        return decorated_function
    return decorator

def plugin_management_rate_limit():
    """Rate limiting specifically for plugin management operations."""
    return rate_limit(requests_per_minute=5, key_func=lambda: f"plugin_mgmt_{get_client_ip()}")

def plugin_install_rate_limit():
    """Rate limiting specifically for plugin installation operations."""
    return rate_limit(requests_per_minute=2, key_func=lambda: f"plugin_install_{get_client_ip()}")

def auth_rate_limit():
    """Rate limiting for authentication endpoints (login, password reset, etc.).

    Only counts POST requests — GET (page loads/refreshes) are not limited.
    Uses get_client_ip() to properly handle requests behind proxies/load balancers.

    For web requests, shows a flash message and redirects back to the login page.
    For API requests, returns a JSON error response.
    """
    return rate_limit(
        requests_per_minute=5,
        key_func=lambda: f"auth_{get_client_ip()}",
        flash_message='Too many login attempts. Please wait 60 seconds before trying again.',
        redirect_to='auth.login',
        methods=['POST'],
    )

def password_reset_rate_limit():
    """Rate limiting specifically for password reset requests (forgot password endpoint).

    Only counts POST requests. More restrictive than general auth rate limit to prevent abuse.
    """
    return rate_limit(
        requests_per_minute=3,
        key_func=lambda: f"password_reset_{get_client_ip()}",
        flash_message='Too many password reset requests. Please wait 60 seconds before trying again.',
        redirect_to='auth.login',
        methods=['POST'],
    )

def api_rate_limit():
    """Rate limiting for API endpoints."""
    return rate_limit(requests_per_minute=60, key_func=lambda: f"api_{get_client_ip()}")


def mobile_rate_limit(requests_per_minute=10):
    """Rate limiting for mobile API endpoints (JSON-only, no flash/redirect)."""
    return rate_limit(
        requests_per_minute=requests_per_minute,
        key_func=lambda: f"mobile_{get_client_ip()}",
        methods=['POST', 'PUT', 'PATCH', 'DELETE'],
    )


def mobile_destructive_rate_limit():
    """Rate limiting for destructive mobile operations (delete, archive, etc.)."""
    return rate_limit(
        requests_per_minute=10,
        key_func=lambda: f"mobile_destructive_{get_client_ip()}",
        methods=['POST'],
    )
