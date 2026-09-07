"""Keep Flask cookie sessions small and persist them after cross-site OAuth.

The Backoffice uses Flask's signed cookie session (not Redis). Browsers cap a
single cookie at ~4093 bytes and silently drop anything larger. Azure B2C ID
tokens used to be stored in that cookie and routinely exceeded the limit —
especially on mobile Safari / Chrome, which are stricter. Those browsers also
often refuse to persist a cookie that was first set on a 302 following a
cross-site IdP redirect.

This module:
- keeps the B2C ID token out of the cookie (server-side logout hint instead)
- strips leftover ``b2c_id_token`` values from already-issued cookies
- returns a first-party HTML continue page after OAuth so Set-Cookie lands
  on a document response, not a redirect hop
- logs when a session Set-Cookie is still approaching the browser limit
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Optional

from flask import current_app, has_app_context, make_response, render_template, request, session

from app.utils.redirect_utils import get_safe_redirect_url

logger = logging.getLogger(__name__)

B2C_ID_TOKEN_SESSION_KEY = "b2c_id_token"
# Browser per-cookie limit is 4096 including the name and attributes.
BROWSER_COOKIE_MAX_BYTES = 4093
SESSION_COOKIE_WARN_BYTES = 3500
_HINT_KEY_PREFIX = "humdb:oauth:id_hint:"

_hint_lock = threading.Lock()
_hint_memory: dict[str, tuple[str, float]] = {}

_redis_client = None
_redis_init_lock = threading.Lock()
_redis_available: Optional[bool] = None


def _hint_ttl_seconds() -> int:
    lifetime = current_app.permanent_session_lifetime
    return max(60, int(lifetime.total_seconds()))


def _get_redis():
    """Optional Redis client for cross-worker logout hints. Never used in tests."""
    global _redis_client, _redis_available
    try:
        if has_app_context() and current_app.config.get("TESTING"):
            return None
    except Exception:
        pass
    if _redis_available is False:
        return None
    if _redis_client is not None:
        return _redis_client
    with _redis_init_lock:
        if _redis_client is not None:
            return _redis_client
        url = (os.environ.get("REDIS_URL") or "").strip()
        if not url:
            _redis_available = False
            return None
        try:
            import redis as _redis_lib

            client = _redis_lib.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=1,
                socket_timeout=0.5,
                health_check_interval=30,
            )
            client.ping()
            _redis_client = client
            _redis_available = True
        except Exception as e:
            logger.debug("OAuth logout-hint Redis unavailable: %s", e)
            _redis_available = False
            _redis_client = None
    return _redis_client


def _prune_expired_hints(now: float) -> None:
    expired = [sid for sid, (_token, exp) in _hint_memory.items() if exp <= now]
    for sid in expired:
        _hint_memory.pop(sid, None)


def store_oauth_logout_hint(session_id: str | None, id_token: str | None) -> None:
    """Store the B2C ID token server-side for ``id_token_hint`` on logout."""
    if not session_id or not id_token:
        return
    ttl = _hint_ttl_seconds()
    redis_client = _get_redis()
    if redis_client is not None:
        try:
            redis_client.setex(f"{_HINT_KEY_PREFIX}{session_id}", ttl, id_token)
            return
        except Exception as e:
            logger.debug("OAuth logout-hint Redis set failed: %s", e)
    now = time.time()
    with _hint_lock:
        _prune_expired_hints(now)
        _hint_memory[session_id] = (id_token, now + ttl)


def pop_oauth_logout_hint(session_id: str | None) -> str | None:
    """Return and clear a stored B2C ID token for this Flask session id."""
    if not session_id:
        return None
    redis_client = _get_redis()
    if redis_client is not None:
        try:
            key = f"{_HINT_KEY_PREFIX}{session_id}"
            token = redis_client.get(key)
            redis_client.delete(key)
            if token:
                return token
        except Exception as e:
            logger.debug("OAuth logout-hint Redis get failed: %s", e)
    now = time.time()
    with _hint_lock:
        _prune_expired_hints(now)
        item = _hint_memory.pop(session_id, None)
    if not item:
        return None
    token, exp = item
    if exp <= now:
        return None
    return token


def migrate_oauth_logout_hint_from_session() -> bool:
    """Move a leftover cookie-stored B2C ID token into server-side storage.

    Existing sessions issued before this fix still carry ``b2c_id_token``.
    Removing it shrinks the cookie so mobile browsers stop dropping it.
    Returns True when the session was modified.
    """
    token = session.get(B2C_ID_TOKEN_SESSION_KEY)
    if not token:
        return False
    sid = session.get("session_id")
    if not sid:
        # Cannot key the server-side hint; leave the value so logout can still
        # read it. After a normal login ``session_id`` is always present.
        return False
    store_oauth_logout_hint(sid, token)
    session.pop(B2C_ID_TOKEN_SESSION_KEY, None)
    session.modified = True
    return True


def first_party_post_login_response(next_url: str | None, default_route: str = "main.dashboard"):
    """Return a 200 HTML page that then navigates to the post-login destination.

    iOS Safari and some Android browsers drop cookies set on a 302 that follows
    a cross-site Azure/B2C redirect. A same-origin document response persists
    the session cookie; the subsequent navigation is first-party.
    """
    safe_url = get_safe_redirect_url(next_url, default_route)
    response = make_response(
        render_template("auth/oauth_continue.html", next_url=safe_url)
    )
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    return response


def session_set_cookie_bytes(response) -> int:
    """Return the largest session Set-Cookie header size on *response*, or 0."""
    cookie_name = current_app.config.get("SESSION_COOKIE_NAME", "session")
    prefix = f"{cookie_name}="
    sizes = [
        len(header)
        for header in response.headers.getlist("Set-Cookie")
        if header.startswith(prefix)
    ]
    return max(sizes) if sizes else 0


def log_oversized_session_cookie(response):
    """Warn when the outgoing session cookie is close to the browser limit."""
    size = session_set_cookie_bytes(response)
    if size < SESSION_COOKIE_WARN_BYTES:
        return response
    keys = []
    try:
        keys = sorted(str(k) for k in session.keys())
    except Exception:
        pass
    level = logger.error if size >= BROWSER_COOKIE_MAX_BYTES else logger.warning
    path = None
    try:
        path = request.path
    except Exception:
        pass
    level(
        "Session cookie is %s bytes (browser limit ~%s). keys=%s path=%s",
        size,
        BROWSER_COOKIE_MAX_BYTES,
        keys,
        path,
    )
    return response


def reset_oauth_logout_hint_cache_for_tests() -> None:
    """Clear in-process logout hints (tests only)."""
    with _hint_lock:
        _hint_memory.clear()
