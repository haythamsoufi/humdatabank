"""
Presence store for live assignment collaborators.

Backend selection:

- **Redis** (when ``REDIS_URL`` is set and reachable): presence is shared
  across Gunicorn workers and App Service instances, so co-editors reliably
  see each other. One sorted set per assignment (member = user id, score =
  epoch seconds), pruned by score on write and expired server-side so
  abandoned assignments leave no keys behind.
- **In-memory fallback** (no Redis): per-process dict. Users served by
  different Gunicorn workers may not see each other; accepted degradation
  for this UX-only feature.

Redis errors never propagate: any failure falls back to the in-memory store
for that call, and presence self-heals on the next client sync (~30-60 s).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Dict, Optional

from app.utils.datetime_helpers import utcnow

logger = logging.getLogger(__name__)

# Must match PRESENCE_TTL_MS in presence.js (120_000 ms).
PRESENCE_TTL_SECONDS = 120

_REDIS_KEY_PREFIX = 'humdb:presence:aes:'

_presence_lock = RLock()
_presence_memory: Dict[int, Dict[int, datetime]] = {}

# Lazy Redis client — same pattern as app.services.monitoring.request_pressure.
_redis_client = None
_redis_init_lock = threading.Lock()
_redis_available: Optional[bool] = None  # None = not yet tried


def _get_redis():
    """Return a shared Redis client, or None if unconfigured/unavailable.

    Never used under TESTING config so the suite exercises deterministic
    in-memory behavior regardless of the developer's local REDIS_URL.
    """
    global _redis_client, _redis_available
    try:
        from flask import current_app, has_app_context
        if has_app_context() and current_app.config.get('TESTING'):
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
        url = os.environ.get('REDIS_URL', '').strip()
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
            logger.info("Presence store: using Redis backend (cross-worker)")
        except Exception as e:
            logger.warning(
                "Presence store: Redis unavailable, using per-process memory: %s", e
            )
            _redis_available = False
            _redis_client = None
    return _redis_client


def _redis_key(aes_id: int) -> str:
    return f'{_REDIS_KEY_PREFIX}{int(aes_id)}'


def _dt_from_epoch(score: float) -> datetime:
    return datetime.fromtimestamp(float(score), tz=timezone.utc)


# ── In-memory backend ──────────────────────────────────────────────────────────

def _prune_memory_bucket(aes_id: int, cutoff: datetime) -> None:
    """Remove stale users from one AES bucket."""
    bucket = _presence_memory.get(aes_id, {})
    stale_user_ids = [uid for uid, seen_at in bucket.items() if seen_at < cutoff]
    for uid in stale_user_ids:
        bucket.pop(uid, None)
    if not bucket:
        _presence_memory.pop(aes_id, None)


def _memory_record(aes_id: int, user_id: int) -> None:
    now = utcnow()
    cutoff_dt = now - timedelta(seconds=PRESENCE_TTL_SECONDS)
    with _presence_lock:
        bucket = _presence_memory.setdefault(int(aes_id), {})
        bucket[int(user_id)] = now
        _prune_memory_bucket(int(aes_id), cutoff_dt)


def _memory_get(aes_id: int) -> Dict[int, datetime]:
    now = utcnow()
    cutoff_dt = now - timedelta(seconds=PRESENCE_TTL_SECONDS)
    with _presence_lock:
        _prune_memory_bucket(int(aes_id), cutoff_dt)
        bucket = _presence_memory.get(int(aes_id), {})
        return dict(bucket)


def _memory_remove(aes_id: int, user_id: int) -> None:
    with _presence_lock:
        bucket = _presence_memory.get(int(aes_id))
        if not bucket:
            return
        bucket.pop(int(user_id), None)
        if not bucket:
            _presence_memory.pop(int(aes_id), None)


# ── Public API ─────────────────────────────────────────────────────────────────

def record_presence(aes_id: int, user_id: int) -> None:
    """Record/refresh a user's presence heartbeat for an assignment."""
    rc = _get_redis()
    if rc is not None:
        try:
            now_ts = time.time()
            key = _redis_key(aes_id)
            pipe = rc.pipeline(transaction=False)
            pipe.zadd(key, {str(int(user_id)): now_ts})
            pipe.zremrangebyscore(key, '-inf', now_ts - PRESENCE_TTL_SECONDS)
            pipe.expire(key, PRESENCE_TTL_SECONDS * 2)
            pipe.execute()
            return
        except Exception as e:
            logger.debug("Presence store: Redis record failed, using memory: %s", e)
    _memory_record(aes_id, user_id)


def get_active_presence(aes_id: int) -> Dict[int, datetime]:
    """Return active users for an assignment as {user_id: last_seen_utc_datetime}."""
    rc = _get_redis()
    if rc is not None:
        try:
            now_ts = time.time()
            pairs = rc.zrangebyscore(
                _redis_key(aes_id),
                now_ts - PRESENCE_TTL_SECONDS,
                '+inf',
                withscores=True,
            )
            return {int(member): _dt_from_epoch(score) for member, score in pairs}
        except Exception as e:
            logger.debug("Presence store: Redis read failed, using memory: %s", e)
    return _memory_get(aes_id)


def remove_presence(aes_id: int, user_id: int) -> None:
    """Immediately remove a user from presence (e.g. on tab close)."""
    rc = _get_redis()
    if rc is not None:
        try:
            rc.zrem(_redis_key(aes_id), str(int(user_id)))
            return
        except Exception as e:
            logger.debug("Presence store: Redis remove failed, using memory: %s", e)
    _memory_remove(aes_id, user_id)
