"""Process-local request pressure tracking for platform 5xx diagnostics.

Tracks in-flight HTTP work and recent traffic on each Gunicorn worker. Snapshots
are attached to platform-error security events to explain worker saturation.
"""

from __future__ import annotations

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
    entry = {
        'id': request_id,
        'pid': os.getpid(),
        'method': method,
        'path': path,
        'endpoint': endpoint,
        'query': (query or '')[:120],
        'started_at': time.time(),
    }
    with _lock:
        _inflight[request_id] = entry
    return request_id


def unregister_inflight(request_id: Optional[int], *, duration_seconds: float) -> None:
    """Remove an in-flight request; optionally remember slow completions."""
    if request_id is None:
        return
    with _lock:
        entry = _inflight.pop(request_id, None)
    if entry and duration_seconds >= _SLOW_COMPLETION_THRESHOLD_SECONDS:
        _remember_slow_completion(entry, duration_seconds)


def _remember_slow_completion(entry: Dict[str, Any], duration_seconds: float) -> None:
    with _lock:
        _recent_slow_completions.append({
            'method': entry.get('method'),
            'path': entry.get('path'),
            'endpoint': entry.get('endpoint'),
            'duration_s': round(duration_seconds, 2),
            'completed_at': time.time(),
        })


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
    """Return current worker pressure snapshot for security-event context."""
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

    return {
        'worker_pid': os.getpid(),
        'snapshot_at': now,
        'gunicorn_timeout_s': stale_threshold,
        'gunicorn_threads': _gunicorn_threads(),
        'active_threads': thread_count,
        'in_flight_count': len(inflight_requests),
        'stale_in_flight_count': stale_count,
        'in_flight_requests': inflight_requests[:12],
        'recent_slow_completions': recent_slow[-8:],
        'traffic_last_60s': last_60s,
        'traffic_last_5m': last_5m,
        'db_pool': pool_stats,
        'scope_note': 'Per-worker snapshot (Gunicorn multi-process); other workers not included.',
    }


def reset_for_tests() -> None:
    """Clear registry state (tests only)."""
    global _next_request_id
    with _lock:
        _next_request_id = 0
        _inflight.clear()
        _traffic_timestamps.clear()
        _recent_slow_completions.clear()
