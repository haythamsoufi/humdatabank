"""
Presence store for live assignment collaborators.

In-memory per-process store. Users on different Gunicorn workers or instances
will not see each other; acceptable for this UX-only feature with sticky sessions.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from threading import RLock
from typing import Dict

from app.utils.datetime_helpers import utcnow

# Must match PRESENCE_TTL_MS in presence.js (120_000 ms).
PRESENCE_TTL_SECONDS = 120

_presence_lock = RLock()
_presence_memory: Dict[int, Dict[int, datetime]] = {}


def _prune_memory_bucket(aes_id: int, cutoff: datetime) -> None:
    """Remove stale users from one AES bucket."""
    bucket = _presence_memory.get(aes_id, {})
    stale_user_ids = [uid for uid, seen_at in bucket.items() if seen_at < cutoff]
    for uid in stale_user_ids:
        bucket.pop(uid, None)
    if not bucket:
        _presence_memory.pop(aes_id, None)


def record_presence(aes_id: int, user_id: int) -> None:
    """Record/refresh a user's presence heartbeat for an assignment."""
    now = utcnow()
    cutoff_dt = now - timedelta(seconds=PRESENCE_TTL_SECONDS)
    with _presence_lock:
        bucket = _presence_memory.setdefault(int(aes_id), {})
        bucket[int(user_id)] = now
        _prune_memory_bucket(int(aes_id), cutoff_dt)


def get_active_presence(aes_id: int) -> Dict[int, datetime]:
    """Return active users for an assignment as {user_id: last_seen_utc_datetime}."""
    now = utcnow()
    cutoff_dt = now - timedelta(seconds=PRESENCE_TTL_SECONDS)
    with _presence_lock:
        _prune_memory_bucket(int(aes_id), cutoff_dt)
        bucket = _presence_memory.get(int(aes_id), {})
        return dict(bucket)


def remove_presence(aes_id: int, user_id: int) -> None:
    """Immediately remove a user from presence (e.g. on tab close)."""
    with _presence_lock:
        bucket = _presence_memory.get(int(aes_id))
        if not bucket:
            return
        bucket.pop(int(user_id), None)
        if not bucket:
            _presence_memory.pop(int(aes_id), None)
