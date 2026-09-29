# Backoffice/app/utils/rate_limiting.py

import logging
import threading
import time
from collections import defaultdict, deque
from functools import wraps

from flask import request, current_app, flash, redirect, url_for

from app.utils.api_responses import json_error
from app.utils.client_ip import get_client_ip
from app.utils.request_utils import is_json_request

_rl_logger = logging.getLogger(__name__)

# In-memory limiter storage (per process). Used for high-volume, low-risk limits and as
# the degraded mode when the shared store is unreachable. Security-critical limiters
# (login, password reset, mobile token endpoints) opt in with ``shared=True`` and then
# count in the shared auth-state store (Redis, or the auth_state_entry table) so the
# limit holds across Gunicorn workers.
_rate_limit_storage = defaultdict(lambda: deque(maxlen=100))
_rate_limit_lock = threading.Lock()

_WINDOW_SECONDS = 60


def _use_shared_store() -> bool:
    from app.utils.security_startup import redis_configured

    if redis_configured(current_app):
        return True
    return str(current_app.config.get("RATE_LIMIT_SHARED_FALLBACK") or "memory").lower() == "db"


def _shared_limit_exceeded(key: str, limit: int, now: float) -> bool | None:
    """Count one hit in the shared store. ``None`` means the store is unavailable."""
    from app.utils.auth_state import NS_RATE_LIMIT, AuthStateUnavailable, get_auth_state

    window = int(now // _WINDOW_SECONDS)
    try:
        count = get_auth_state().incr(NS_RATE_LIMIT, f"{key}:{window}", _WINDOW_SECONDS * 2)
    except AuthStateUnavailable:
        _rl_logger.error("Shared rate-limit store unavailable; using per-process limiter for %s", key)
        return None
    return count > limit


def _memory_limit_exceeded(key: str, limit: int, now: float) -> bool:
    with _rate_limit_lock:
        bucket = _rate_limit_storage[key]
        while bucket and bucket[0] < now - _WINDOW_SECONDS:
            bucket.popleft()
        if len(bucket) >= limit:
            return True
        bucket.append(now)
        return False


def hit_rate_limit(key: str, limit: int, *, shared: bool = False) -> bool:
    """Record one hit for ``key``; True when the per-minute ``limit`` is exceeded."""
    now = time.time()
    if shared and _use_shared_store():
        exceeded = _shared_limit_exceeded(key, limit, now)
        if exceeded is not None:
            return exceeded
    return _memory_limit_exceeded(key, limit, now)


def rate_limit(requests_per_minute=10, key_func=None, flash_message=None, redirect_to=None, methods=None, on_limit=None, shared=False):
    """
    Rate limiting decorator for Flask routes.

    Args:
        requests_per_minute: Maximum requests allowed per minute
        key_func: Function to generate rate limit key (defaults to IP address)
        flash_message: Optional custom flash message for web requests (defaults to standard message)
        redirect_to: Optional route name to redirect to on rate limit (for web requests)
        methods: HTTP methods to apply the limit to (e.g. ['POST']). None means all methods.
        on_limit: Optional callable() invoked when the rate limit is exceeded.
            If it returns a non-None Flask response, that response is returned to the
            client instead of 429.  If it returns None, the normal 429 / redirect
            behaviour applies.  Use this for graceful degradation (e.g. serving a
            stale cache entry rather than an error).
        shared: Count in the shared auth-state store (cross-worker) instead of process
            memory. Use for login/reset/token endpoints.

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

            # Skip rate limiting for trusted IPs (e.g. load-test runners, internal services).
            # Configure RATE_LIMIT_EXEMPT_IPS as a comma-separated list or Python list in config.
            client_ip = get_client_ip()
            exempt_ips_cfg = current_app.config.get('RATE_LIMIT_EXEMPT_IPS', [])
            if isinstance(exempt_ips_cfg, str):
                exempt_ips_cfg = [ip.strip() for ip in exempt_ips_cfg.split(',') if ip.strip()]
            if client_ip in exempt_ips_cfg:
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

            if hit_rate_limit(key, requests_per_minute, shared=shared):
                current_app.logger.warning(f"Rate limit exceeded for {key} on {request.endpoint}")

                # Give the caller a chance to return a graceful fallback response
                # (e.g. a stale cache entry) instead of the hard 429 / redirect.
                if on_limit is not None:
                    fallback_response = on_limit()
                    if fallback_response is not None:
                        return fallback_response

                if is_json_request():
                    return json_error(
                        'Rate limit exceeded. Please try again later.',
                        429,
                        success=False,
                        error='Rate limit exceeded. Please try again later.',
                        retry_after=60,
                    )

                message = flash_message or f'Rate limit exceeded. Please wait {60} seconds before trying again.'
                flash(message, 'warning')

                if redirect_to:
                    return redirect(url_for(redirect_to))
                elif request.endpoint:
                    # Path only (no query string) to avoid redirect loops.
                    return redirect(request.path)
                else:
                    try:
                        return redirect(url_for('main.dashboard'))
                    except Exception as e:
                        current_app.logger.debug("Rate limit redirect fallback failed; redirecting to '/': %s", e, exc_info=True)
                        return redirect('/')

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
        shared=True,
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
        shared=True,
    )

def _api_rate_limit_identity_key() -> str:
    """
    Bucket API rate limits by API key when present, falling back to client IP.

    Runs before ``authenticate_api_request()`` (that happens inside the view), so
    this only peeks at the raw ``Authorization`` header — no DB lookup — to avoid
    duplicating auth work on every request, including ones that get rejected.
    The key itself is never stored: only a truncated SHA-256 hash is kept in the
    in-memory rate-limit buckets.

    Without this, every request sharing a NAT/proxy IP (or a request without a
    forwarded-for header at all) shares one bucket regardless of which API key —
    if any — it authenticates with, letting one noisy caller throttle unrelated
    integrators, while a trusted key gets no benefit from being a distinct, known
    caller.
    """
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header[len('Bearer '):].strip()
        if token:
            import hashlib
            return f"key_{hashlib.sha256(token.encode('utf-8')).hexdigest()[:16]}"
    return f"api_{get_client_ip()}"


def api_rate_limit(requests_per_minute=60):
    """Rate limiting for API endpoints. Keys by API key when authenticated, else client IP."""
    return rate_limit(requests_per_minute=requests_per_minute, key_func=_api_rate_limit_identity_key)


def mobile_rate_limit(requests_per_minute=30, shared=False):
    """Rate limiting for mobile API endpoints (JSON-only, no flash/redirect).

    Applies to **all** HTTP methods (GET, POST, PUT, PATCH, DELETE).
    Returns a ``mobile_error`` envelope on 429 — not the generic ``json_error``
    — so Flutter clients always receive ``{success: false, error_code: ...}``.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if current_app.config.get('DEBUG') and current_app.config.get('RATE_LIMIT_SKIP_DEBUG', True):
                return f(*args, **kwargs)

            client_ip = get_client_ip()
            exempt_ips_cfg = current_app.config.get('RATE_LIMIT_EXEMPT_IPS', [])
            if isinstance(exempt_ips_cfg, str):
                exempt_ips_cfg = [ip.strip() for ip in exempt_ips_cfg.split(',') if ip.strip()]
            if client_ip in exempt_ips_cfg:
                return f(*args, **kwargs)

            key = f"mobile_{client_ip}:{request.endpoint}" if shared else f"mobile_{client_ip}"
            if hit_rate_limit(key, requests_per_minute, shared=shared):
                _rl_logger.warning(
                    "Mobile rate limit exceeded for %s on %s",
                    key, request.endpoint,
                )
                from app.utils.mobile_responses import mobile_error
                return mobile_error(
                    'Rate limit exceeded. Please try again later.',
                    429,
                    error_code='RATE_LIMIT_EXCEEDED',
                    retry_after=60,
                )

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def mobile_destructive_rate_limit():
    """Rate limiting for destructive mobile operations (delete, archive, etc.)."""
    return mobile_rate_limit(requests_per_minute=10)
