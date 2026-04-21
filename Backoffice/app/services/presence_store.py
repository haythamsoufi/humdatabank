"""
Presence store for live assignment collaborators.

Uses Redis when configured, with an in-memory fallback for local/dev setups.
"""

from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from typing import Dict

from flask import current_app

from app.utils.datetime_helpers import utcnow


_presence_lock = RLock()
_presence_memory: Dict[int, Dict[int, datetime]] = {}

_redis_client = None
_redis_initialized = False


def _presence_key(aes_id: int) -> str:
    return f"presence:aes:{aes_id}"


def _get_redis_client():
    """Return a cached Redis client when REDIS_URL is configured, else None."""
    global _redis_client, _redis_initialized
    if _redis_initialized:
        return _redis_client

    _redis_initialized = True
    redis_url = current_app.config.get("REDIS_URL")
    if not redis_url:
        return None

    try:
        import redis  # optional dependency

        _redis_client = redis.from_url(redis_url, decode_responses=True)
    except Exception as e:
        current_app.logger.warning("Presence store Redis init failed, using memory fallback: %s", e)
        _redis_client = None

    return _redis_client


def _prune_memory_bucket(aes_id: int, cutoff: datetime) -> None:
    """Remove stale users from one AES bucket."""
    bucket = _presence_memory.get(aes_id, {})
    stale_user_ids = [uid for uid, seen_at in bucket.items() if seen_at < cutoff]
    for uid in stale_user_ids:
        bucket.pop(uid, None)
    if not bucket:
        _presence_memory.pop(aes_id, None)


def record_presence(aes_id: int, user_id: int, ttl_seconds: int = 75) -> None:
    """
    Record/refresh a user's presence heartbeat for an assignment.
    """
    now = utcnow()
    cutoff_ts = now.timestamp() - ttl_seconds
    redis_client = _get_redis_client()

    if redis_client is not None:
        key = _presence_key(aes_id)
        try:
            p = redis_client.pipeline()
            p.zadd(key, {str(int(user_id)): float(now.timestamp())})
            p.zremrangebyscore(key, 0, cutoff_ts)
            p.expire(key, max(ttl_seconds * 2, 120))
            p.execute()
            return
        except Exception as e:
            current_app.logger.warning("Presence Redis write failed, using memory fallback: %s", e)

    cutoff_dt = datetime.fromtimestamp(cutoff_ts, tz=timezone.utc)
    with _presence_lock:
        bucket = _presence_memory.setdefault(int(aes_id), {})
        bucket[int(user_id)] = now
        _prune_memory_bucket(int(aes_id), cutoff_dt)


def get_active_presence(aes_id: int, ttl_seconds: int = 75) -> Dict[int, datetime]:
    """
    Return active users for an assignment as {user_id: last_seen_utc_datetime}.
    """
    now = utcnow()
    cutoff_ts = now.timestamp() - ttl_seconds
    redis_client = _get_redis_client()

    if redis_client is not None:
        try:
            rows = redis_client.zrangebyscore(
                _presence_key(aes_id),
                min=float(cutoff_ts),
                max="+inf",
                withscores=True,
            )
            return {
                int(user_id): datetime.fromtimestamp(float(last_seen_ts), tz=timezone.utc)
                for user_id, last_seen_ts in rows
            }
        except Exception as e:
            current_app.logger.warning("Presence Redis read failed, using memory fallback: %s", e)

    cutoff_dt = datetime.fromtimestamp(cutoff_ts, tz=timezone.utc)
    with _presence_lock:
        _prune_memory_bucket(int(aes_id), cutoff_dt)
        bucket = _presence_memory.get(int(aes_id), {})
        return dict(bucket)
