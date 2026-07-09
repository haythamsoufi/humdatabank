"""Process-local request pressure tracking for platform 5xx diagnostics.

Tracks in-flight HTTP work and recent traffic on each Gunicorn worker. Snapshots
are attached to platform-error security events to explain worker saturation.

Cross-worker visibility (optional)
-----------------------------------
When ``REDIS_URL`` is set the module also mirrors in-flight registrations to a
Redis hash keyed by worker PID (``humdb:pressure:iflt:<pid>``).  ``snapshot_inflight``
then reads *other* workers' hashes to expose the full-cluster picture in platform
502/503/504 security events.  This fixes the "0 stale in-flight on the reporting
worker" blind spot: the stuck request may be on a different worker that this one
has no direct visibility into.

All Redis operations are fire-and-forget with full exception suppression.  If Redis
is unavailable, behaviour is identical to the original per-worker-only mode.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from contextlib import suppress
from typing import Any, Deque, Dict, List, Optional, Tuple

from flask import g, request

from app.services.monitoring.system import _is_long_lived_connection_request
from app.utils.request_utils import is_static_asset_request

_lock = threading.Lock()
_next_request_id = 0
_inflight: Dict[int, Dict[str, Any]] = {}
_traffic_timestamps: Deque[float] = deque()
_recent_slow_completions: Deque[Dict[str, Any]] = deque(maxlen=15)

_TRAFFIC_WINDOW_SECONDS = 300.0
_SLOW_COMPLETION_THRESHOLD_SECONDS = 5.0

# ── Redis cross-worker ring buffer ─────────────────────────────────────────────

_REDIS_KEY_PREFIX = 'humdb:pressure'
_REDIS_INFLIGHT_TTL = 120   # auto-expire if a worker dies (> GUNICORN_TIMEOUT)
_REDIS_SLOW_MAX = 50        # entries kept in the global slow-completions ring

_redis_client: Any = None   # lazy-initialised; None = unavailable
_redis_init_lock = threading.Lock()
_redis_available: Optional[bool] = None  # None = not yet tried


def _get_redis() -> Any:
    """Return a shared Redis client, or None if Redis is unconfigured/unavailable."""
    global _redis_client, _redis_available
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
        except Exception:
            _redis_available = False
            _redis_client = None
    return _redis_client


def _redis_push_inflight(pid: int, request_id: int, entry: Dict[str, Any]) -> None:
    rc = _get_redis()
    if rc is None:
        return
    with suppress(Exception):
        key = f'{_REDIS_KEY_PREFIX}:iflt:{pid}'
        payload = json.dumps({
            'method': entry.get('method'),
            'path': entry.get('path'),
            'endpoint': entry.get('endpoint'),
            'started_at': entry.get('started_at'),
            'pid': pid,
        })
        rc.hset(key, request_id, payload)
        rc.expire(key, _REDIS_INFLIGHT_TTL)


def _redis_remove_inflight(pid: int, request_id: int) -> None:
    rc = _get_redis()
    if rc is None:
        return
    with suppress(Exception):
        rc.hdel(f'{_REDIS_KEY_PREFIX}:iflt:{pid}', request_id)


def _redis_push_slow_completion(completion: Dict[str, Any]) -> None:
    rc = _get_redis()
    if rc is None:
        return
    with suppress(Exception):
        key = f'{_REDIS_KEY_PREFIX}:slow'
        rc.lpush(key, json.dumps(completion))
        rc.ltrim(key, 0, _REDIS_SLOW_MAX - 1)
        rc.expire(key, 3600)


def _redis_get_cross_worker_inflight(
    current_pid: int, stale_threshold: float
) -> List[Dict[str, Any]]:
    """Read in-flight entries from all OTHER worker PIDs stored in Redis."""
    rc = _get_redis()
    if rc is None:
        return []
    results: List[Dict[str, Any]] = []
    now = time.time()
    pattern = f'{_REDIS_KEY_PREFIX}:iflt:*'
    with suppress(Exception):
        for key in rc.scan_iter(pattern, count=20):
            with suppress(Exception):
                pid_str = key.rsplit(':', 1)[-1]
                pid = int(pid_str)
                if pid == current_pid:
                    continue
                entries = rc.hgetall(key)
                for _, raw in entries.items():
                    with suppress(Exception):
                        entry = json.loads(raw)
                        elapsed = now - float(entry.get('started_at', now))
                        results.append({
                            'method': entry.get('method'),
                            'path': entry.get('path'),
                            'endpoint': entry.get('endpoint'),
                            'elapsed_s': round(elapsed, 1),
                            'stale': elapsed >= stale_threshold,
                            'pid': pid,
                        })
    return results


def _should_track_pressure() -> bool:
    if is_static_asset_request():
        return False
    path = (request.path or '').lower()
    if path in {'/health', '/favicon.ico', '/api/v1/platform-error'}:
        return False
    return not _is_long_lived_connection_request()


def track_pressure_start() -> None:
    """Register in-flight work for platform 5xx diagnostics (before_request)."""
    if not _should_track_pressure():
        return
    g.pressure_request_start = time.time()
    g.pressure_request_id = register_inflight(
        method=request.method,
        path=request.path,
        endpoint=request.endpoint,
        query=request.query_string.decode('utf-8', errors='replace')[:200],
    )


def track_pressure_end() -> None:
    """Unregister in-flight work (after_request / teardown)."""
    with suppress(Exception):
        request_id = getattr(g, 'pressure_request_id', None)
        if request_id is None:
            return
        start = getattr(g, 'pressure_request_start', None)
        duration = (time.time() - start) if start is not None else 0.0
        unregister_inflight(request_id, duration_seconds=duration)
        g.pressure_request_id = None
        g.pressure_request_start = None


def _next_id() -> int:
    global _next_request_id
    _next_request_id += 1
    return _next_request_id


def record_traffic() -> None:
    """Record one incoming request timestamp (call from before_request)."""
    now = time.time()
    cutoff = now - _TRAFFIC_WINDOW_SECONDS
    with _lock:
        _traffic_timestamps.append(now)
        while _traffic_timestamps and _traffic_timestamps[0] < cutoff:
            _traffic_timestamps.popleft()


def register_inflight(
    *,
    method: str,
    path: str,
    endpoint: Optional[str] = None,
    query: str = '',
) -> int:
    """Register an in-flight request; returns a handle for unregister."""
    request_id = _next_id()
    pid = os.getpid()
    entry = {
        'id': request_id,
        'pid': pid,
        'method': method,
        'path': path,
        'endpoint': endpoint,
        'query': (query or '')[:120],
        'started_at': time.time(),
    }
    with _lock:
        _inflight[request_id] = entry
    _redis_push_inflight(pid, request_id, entry)
    return request_id


def unregister_inflight(request_id: Optional[int], *, duration_seconds: float) -> None:
    """Remove an in-flight request; optionally remember slow completions."""
    if request_id is None:
        return
    with _lock:
        entry = _inflight.pop(request_id, None)
    if entry:
        _redis_remove_inflight(entry.get('pid', os.getpid()), request_id)
        if duration_seconds >= _SLOW_COMPLETION_THRESHOLD_SECONDS:
            _remember_slow_completion(entry, duration_seconds)


def _remember_slow_completion(entry: Dict[str, Any], duration_seconds: float) -> None:
    completion = {
        'method': entry.get('method'),
        'path': entry.get('path'),
        'endpoint': entry.get('endpoint'),
        'duration_s': round(duration_seconds, 2),
        'completed_at': time.time(),
        'pid': entry.get('pid', os.getpid()),
    }
    with _lock:
        _recent_slow_completions.append(completion)
    _redis_push_slow_completion(completion)


def _traffic_counts(now: float) -> Tuple[int, int]:
    cutoff_60 = now - 60.0
    cutoff_5m = now - _TRAFFIC_WINDOW_SECONDS
    last_60s = 0
    last_5m = 0
    for ts in _traffic_timestamps:
        if ts >= cutoff_5m:
            last_5m += 1
        if ts >= cutoff_60:
            last_60s += 1
    return last_60s, last_5m


def _gunicorn_timeout_seconds() -> float:
    try:
        return float(os.environ.get('GUNICORN_TIMEOUT', '25'))
    except (TypeError, ValueError):
        return 25.0


def _gunicorn_threads() -> Optional[int]:
    raw = os.environ.get('GUNICORN_THREADS', '').strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def snapshot_inflight(*, stale_after_seconds: Optional[float] = None) -> Dict[str, Any]:
    """Return current worker pressure snapshot for security-event context.

    When Redis is configured, ``other_workers_in_flight`` contains in-flight
    requests from all other Gunicorn workers so the caller can detect saturation
    even when the reporting worker is idle.
    """
    current_pid = os.getpid()
    now = time.time()
    stale_threshold = stale_after_seconds if stale_after_seconds is not None else _gunicorn_timeout_seconds()

    with _lock:
        inflight_entries = list(_inflight.values())
        last_60s, last_5m = _traffic_counts(now)
        recent_slow = list(_recent_slow_completions)

    inflight_requests: List[Dict[str, Any]] = []
    stale_count = 0
    for entry in inflight_entries:
        elapsed = now - float(entry['started_at'])
        is_stale = elapsed >= stale_threshold
        if is_stale:
            stale_count += 1
        inflight_requests.append({
            'method': entry.get('method'),
            'path': entry.get('path'),
            'endpoint': entry.get('endpoint'),
            'elapsed_s': round(elapsed, 1),
            'stale': is_stale,
            'pid': entry.get('pid'),
        })

    # Stale / longest-running first so truncation keeps the most useful rows.
    inflight_requests.sort(key=lambda row: (-int(row['stale']), -row['elapsed_s']))

    # Cross-worker in-flight data from Redis (empty list if Redis is unavailable).
    cross_worker = _redis_get_cross_worker_inflight(current_pid, stale_threshold)
    cross_worker.sort(key=lambda row: (-int(row['stale']), -row['elapsed_s']))
    cross_worker_stale = sum(1 for r in cross_worker if r.get('stale'))

    pool_stats: Dict[str, Any] = {}
    try:
        from app import db

        pool = db.engine.pool
        pool_stats = {
            'size': pool.size(),
            'checked_out': pool.checkedout(),
            'checked_in': pool.checkedin(),
            'overflow': pool.overflow(),
        }
    except Exception:
        pool_stats = {'error': 'unavailable'}

    thread_count = None
    try:
        thread_count = threading.active_count()
    except Exception:
        pass

    redis_active = _redis_available is True
    scope_note = (
        'Cross-worker snapshot via Redis (other workers included).'
        if redis_active
        else 'Per-worker snapshot (Gunicorn multi-process); other workers not included.'
    )

    return {
        'worker_pid': current_pid,
        'snapshot_at': now,
        'gunicorn_timeout_s': stale_threshold,
        'gunicorn_threads': _gunicorn_threads(),
        'active_threads': thread_count,
        'in_flight_count': len(inflight_requests),
        'stale_in_flight_count': stale_count,
        'in_flight_requests': inflight_requests[:12],
        'other_workers_in_flight': cross_worker[:12],
        'other_workers_stale_count': cross_worker_stale,
        'recent_slow_completions': recent_slow[-8:],
        'traffic_last_60s': last_60s,
        'traffic_last_5m': last_5m,
        'db_pool': pool_stats,
        'redis_cross_worker': redis_active,
        'scope_note': scope_note,
    }


def reset_for_tests() -> None:
    """Clear registry state (tests only)."""
    global _next_request_id
    with _lock:
        _next_request_id = 0
        _inflight.clear()
        _traffic_timestamps.clear()
        _recent_slow_completions.clear()
