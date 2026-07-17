"""Process-local request pressure tracking for platform 5xx diagnostics.

Tracks in-flight HTTP work and recent traffic on each Gunicorn worker. Snapshots
are attached to platform-error security events to explain worker saturation.

Cross-worker visibility (optional)
-----------------------------------
1. **Redis** (``REDIS_URL``): mirrors in-flight to ``humdb:pressure:iflt:<pid>``.
   Best for multi-instance / shared view across containers.
2. **Shared filesystem** (same container, no Redis required): each worker writes
   ``<PRESSURE_FS_DIR>/<pid>.json`` so SSH diagnostics and sibling workers can
   see in-flight/WS pressure without Redis. Default dirs tried in order:
   ``/home/LogFiles/humdb-pressure``, ``/tmp/humdb-pressure``.
   Disable with ``PRESSURE_FS_MIRROR=0``.

All Redis / FS operations are fire-and-forget with full exception suppression.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from contextlib import suppress
from glob import glob
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
_REDIS_ABORT_KEY = f'{_REDIS_KEY_PREFIX}:aborted_workers'
_REDIS_ABORT_MAX = 10       # last N worker aborts stored
_REDIS_ABORT_TTL = 600      # 10 min — long enough to appear in subsequent 504 events

_redis_client: Any = None   # lazy-initialised; None = unavailable
_redis_init_lock = threading.Lock()
_redis_available: Optional[bool] = None  # None = not yet tried

# ── Shared-filesystem mirror (same-container cross-worker, no Redis) ───────────

_FS_DEFAULT_CANDIDATES = (
    '/home/LogFiles/humdb-pressure',
    '/tmp/humdb-pressure',
)
_FS_STALE_FILE_S = 120.0
_FS_MIN_WRITE_INTERVAL_S = 0.25
_FS_ABORT_KEEP = 10

_fs_dir_resolved: Optional[str] = None  # set only after a successful resolve
_fs_mirror_disabled: bool = False
_fs_dir_lock = threading.Lock()
_fs_write_lock = threading.Lock()
_fs_last_write_mono = 0.0
_fs_dirty = False


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


def _fs_mirror_enabled() -> bool:
    raw = (os.environ.get('PRESSURE_FS_MIRROR') or '1').strip().lower()
    return raw not in {'0', 'false', 'no', 'off'}


def resolve_pressure_fs_dir(*, create: bool = False) -> Optional[str]:
    """Return the directory used for per-worker pressure JSON files, or None."""
    global _fs_dir_resolved, _fs_mirror_disabled
    if _fs_mirror_disabled:
        return None
    if _fs_dir_resolved:
        return _fs_dir_resolved
    with _fs_dir_lock:
        if _fs_mirror_disabled:
            return None
        if _fs_dir_resolved:
            return _fs_dir_resolved
        if not _fs_mirror_enabled():
            _fs_mirror_disabled = True
            return None
        explicit = (os.environ.get('PRESSURE_FS_DIR') or '').strip()
        candidates = [p for p in ((explicit,) if explicit else _FS_DEFAULT_CANDIDATES) if p]
        if create and '/tmp/humdb-pressure' not in candidates:
            candidates.append('/tmp/humdb-pressure')
        for path in candidates:
            try:
                if create:
                    os.makedirs(path, mode=0o755, exist_ok=True)
                if not os.path.isdir(path):
                    continue
                need = os.W_OK if create else os.R_OK
                if os.access(path, need):
                    _fs_dir_resolved = path
                    return path
            except OSError:
                continue
        # Do not cache failure when create=False — writers may create the dir later.
        return None


def _fs_worker_path(pid: int) -> Optional[str]:
    base = resolve_pressure_fs_dir(create=True)
    if not base:
        return None
    return os.path.join(base, f'{pid}.json')


def _fs_build_payload(pid: int) -> Dict[str, Any]:
    now = time.time()
    with _lock:
        inflight_entries = list(_inflight.values())
        last_60s, last_5m = _traffic_counts(now)
        recent_slow = list(_recent_slow_completions)[-8:]

    inflight_rows: List[Dict[str, Any]] = []
    for entry in inflight_entries:
        started = float(entry.get('started_at', now))
        inflight_rows.append({
            'method': entry.get('method'),
            'path': entry.get('path'),
            'endpoint': entry.get('endpoint'),
            'started_at': started,
            'elapsed_s': round(now - started, 1),
            'pid': entry.get('pid', pid),
        })
    inflight_rows.sort(key=lambda r: -r['elapsed_s'])

    ws_pool: Dict[str, Any] = {}
    with suppress(Exception):
        from app.utils.ws_manager import ws_manager
        ws_pool = ws_manager.snapshot()

    db_pool: Dict[str, Any] = {}
    with suppress(Exception):
        from app import db
        pool = db.engine.pool
        db_pool = {
            'size': pool.size(),
            'checked_out': pool.checkedout(),
            'checked_in': pool.checkedin(),
            'overflow': pool.overflow(),
        }

    return {
        'pid': pid,
        'updated_at': now,
        'in_flight_count': len(inflight_rows),
        'in_flight': inflight_rows[:20],
        'traffic_last_60s': last_60s,
        'traffic_last_5m': last_5m,
        'recent_slow_completions': recent_slow,
        'ws_pool': ws_pool,
        'db_pool': db_pool,
        'active_threads': threading.active_count(),
    }


def _fs_write_snapshot(*, force: bool = False) -> None:
    """Mirror this worker's pressure state to a shared JSON file (throttled)."""
    global _fs_last_write_mono, _fs_dirty
    if not _fs_mirror_enabled():
        return
    pid = os.getpid()
    path = _fs_worker_path(pid)
    if not path:
        return
    now_mono = time.monotonic()
    with _fs_write_lock:
        if not force and (now_mono - _fs_last_write_mono) < _FS_MIN_WRITE_INTERVAL_S:
            _fs_dirty = True
            return
        _fs_dirty = False
        _fs_last_write_mono = now_mono
        payload = _fs_build_payload(pid)
        tmp_path = f'{path}.{os.getpid()}.tmp'
        try:
            with open(tmp_path, 'w', encoding='utf-8') as fh:
                json.dump(payload, fh, separators=(',', ':'))
            os.replace(tmp_path, path)
        except OSError:
            with suppress(OSError):
                os.unlink(tmp_path)


def _fs_schedule_write() -> None:
    """Write soon; force a flush if a previous write was throttled away."""
    global _fs_dirty
    _fs_write_snapshot(force=False)
    if _fs_dirty:
        _fs_write_snapshot(force=True)


def _fs_push_aborted_worker(pid: int, entries: List[Dict[str, Any]], stale_count: int) -> None:
    base = resolve_pressure_fs_dir(create=True)
    if not base:
        return
    with suppress(Exception):
        record = {
            'pid': pid,
            'aborted_at': time.time(),
            'stale_count': stale_count,
            'in_flight': entries,
        }
        path = os.path.join(base, f'abort-{pid}-{int(record["aborted_at"])}.json')
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(record, fh, separators=(',', ':'))
        # Keep only the newest abort dumps
        aborts = sorted(glob(os.path.join(base, 'abort-*.json')), reverse=True)
        for old in aborts[_FS_ABORT_KEEP:]:
            with suppress(OSError):
                os.unlink(old)
    _fs_write_snapshot(force=True)
    # Remove live worker file so readers do not treat a dead pid as active
    with suppress(OSError):
        live = os.path.join(base, f'{pid}.json')
        if os.path.isfile(live):
            os.unlink(live)


def _fs_get_cross_worker_inflight(
    current_pid: int, stale_threshold: float
) -> List[Dict[str, Any]]:
    """Read in-flight entries from sibling workers' FS mirror files."""
    base = resolve_pressure_fs_dir(create=False)
    if not base:
        # Still try creating so first writer path is visible; readers may only need read
        base = resolve_pressure_fs_dir(create=True)
    if not base or not os.path.isdir(base):
        return []
    results: List[Dict[str, Any]] = []
    now = time.time()
    with suppress(OSError):
        for name in os.listdir(base):
            if not name.endswith('.json') or name.startswith('abort-'):
                continue
            path = os.path.join(base, name)
            with suppress(Exception):
                try:
                    pid = int(name[:-5])
                except ValueError:
                    continue
                if pid == current_pid:
                    continue
                with open(path, encoding='utf-8') as fh:
                    data = json.load(fh)
                updated = float(data.get('updated_at') or 0)
                if updated and (now - updated) > _FS_STALE_FILE_S:
                    continue
                for entry in data.get('in_flight') or []:
                    started = float(entry.get('started_at', now))
                    elapsed = now - started
                    if 'elapsed_s' in entry and updated:
                        # Prefer wall-clock from started_at when present
                        elapsed = now - started
                    results.append({
                        'method': entry.get('method'),
                        'path': entry.get('path'),
                        'endpoint': entry.get('endpoint'),
                        'elapsed_s': round(elapsed, 1),
                        'stale': elapsed >= stale_threshold,
                        'pid': entry.get('pid', pid),
                        'source': 'fs',
                    })
    return results


def _fs_get_aborted_workers() -> List[Dict[str, Any]]:
    base = resolve_pressure_fs_dir(create=False)
    if not base:
        return []
    results: List[Dict[str, Any]] = []
    with suppress(OSError):
        paths = sorted(glob(os.path.join(base, 'abort-*.json')), reverse=True)
        for path in paths[:_FS_ABORT_KEEP]:
            with suppress(Exception):
                with open(path, encoding='utf-8') as fh:
                    results.append(json.load(fh))
    return results


def clear_fs_mirror(pid: Optional[int] = None) -> None:
    """Remove this worker's FS mirror file (call from worker_exit if desired)."""
    target = pid if pid is not None else os.getpid()
    base = resolve_pressure_fs_dir(create=False)
    if not base:
        return
    with suppress(OSError):
        os.unlink(os.path.join(base, f'{target}.json'))


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


def _redis_get_aborted_workers() -> List[Dict[str, Any]]:
    """Return recent worker-abort dumps from Redis (last N, newest first)."""
    rc = _get_redis()
    if rc is None:
        return []
    results: List[Dict[str, Any]] = []
    with suppress(Exception):
        for raw in rc.lrange(_REDIS_ABORT_KEY, 0, _REDIS_ABORT_MAX - 1):
            with suppress(Exception):
                results.append(json.loads(raw))
    return results


def _redis_push_aborted_worker(pid: int, entries: List[Dict[str, Any]], stale_count: int) -> None:
    """Push an abort-dump record to the cross-worker abort ring in Redis."""
    rc = _get_redis()
    if rc is None:
        return
    with suppress(Exception):
        payload = json.dumps({
            'pid': pid,
            'aborted_at': time.time(),
            'stale_count': stale_count,
            'in_flight': entries,
        })
        rc.lpush(_REDIS_ABORT_KEY, payload)
        rc.ltrim(_REDIS_ABORT_KEY, 0, _REDIS_ABORT_MAX - 1)
        rc.expire(_REDIS_ABORT_KEY, _REDIS_ABORT_TTL)
        # Clean up this worker's in-flight hash so stale entries don't linger
        rc.delete(f'{_REDIS_KEY_PREFIX}:iflt:{pid}')


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
    with suppress(Exception):
        _fs_schedule_write()
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
        with suppress(Exception):
            _fs_schedule_write()


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
        return float(os.environ.get('GUNICORN_TIMEOUT', '60'))
    except (TypeError, ValueError):
        return 60.0


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

    # Cross-worker: prefer Redis; fall back to shared FS mirror (same container).
    cross_worker = _redis_get_cross_worker_inflight(current_pid, stale_threshold)
    fs_cross = False
    if not cross_worker:
        cross_worker = _fs_get_cross_worker_inflight(current_pid, stale_threshold)
        fs_cross = bool(cross_worker)
    cross_worker.sort(key=lambda row: (-int(row['stale']), -row['elapsed_s']))
    cross_worker_stale = sum(1 for r in cross_worker if r.get('stale'))

    recent_aborts = _redis_get_aborted_workers()
    if not recent_aborts:
        recent_aborts = _fs_get_aborted_workers()

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

    ws_pool_snapshot: Dict[str, Any] = {}
    try:
        from app.utils.ws_manager import ws_manager
        ws_pool_snapshot = ws_manager.snapshot()
    except Exception:
        ws_pool_snapshot = {'error': 'unavailable'}

    redis_active = _redis_available is True
    fs_dir = resolve_pressure_fs_dir(create=False)
    if redis_active:
        scope_note = 'Cross-worker snapshot via Redis (other workers included).'
    elif fs_cross or fs_dir:
        scope_note = (
            'Cross-worker snapshot via shared filesystem mirror '
            f'({fs_dir or "humdb-pressure"}); Redis not configured.'
        )
    else:
        scope_note = (
            'Per-worker snapshot (Gunicorn multi-process); other workers not included. '
            'FS mirror inactive and REDIS_URL unset.'
        )

    # Keep FS mirror fresh for SSH diagnostics even when only snapshot is called.
    with suppress(Exception):
        _fs_write_snapshot(force=False)

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
        'recent_worker_aborts': recent_aborts[:5],
        'traffic_last_60s': last_60s,
        'traffic_last_5m': last_5m,
        'db_pool': pool_stats,
        'ws_pool': ws_pool_snapshot,
        'redis_cross_worker': redis_active,
        'fs_cross_worker': bool(fs_cross or (fs_dir and not redis_active)),
        'fs_pressure_dir': fs_dir,
        'scope_note': scope_note,
    }


def sibling_snapshot(*, exclude_request_id: Optional[int] = None, limit: int = 5) -> Dict[str, Any]:
    """Lightweight same-process concurrency snapshot for slow/stuck request logs.

    Unlike ``snapshot_inflight`` (Redis + DB-pool + ws-pool lookups, meant for
    platform-5xx security events), this only reads the process-local in-flight
    registry and thread count — cheap enough to call on every ``[SLOW_REQUEST]``/
    ``[STUCK_REQUEST]`` log line so "what else was this process doing?" doesn't
    require a separate investigation after the fact.
    """
    now = time.time()
    with _lock:
        entries = [e for e in _inflight.values() if e.get('id') != exclude_request_id]

    entries.sort(key=lambda e: float(e.get('started_at', now)))
    siblings: List[Dict[str, Any]] = []
    for entry in entries[:limit]:
        siblings.append({
            'method': entry.get('method'),
            'path': entry.get('path'),
            'endpoint': entry.get('endpoint'),
            'elapsed_s': round(now - float(entry.get('started_at', now)), 1),
        })

    try:
        active_threads: Optional[int] = threading.active_count()
    except Exception:
        active_threads = None

    return {
        'active_threads': active_threads,
        'sibling_count': len(entries),
        'siblings': siblings,
    }


def dump_inflight_on_abort(pid: int, log_fn=None) -> None:
    """Called from the Gunicorn worker_abort hook — no Flask app context available.

    Logs every in-flight request tracked on this worker to stderr (or the
    supplied log_fn), then pushes the dump to the Redis abort ring so subsequent
    platform-504 security events can surface what was running when this worker
    was killed.  Safe to call when Redis is unavailable: all Redis operations
    are fire-and-forget with full exception suppression.
    """
    import sys

    if log_fn is None:
        def log_fn(msg: str) -> None:
            print(msg, file=sys.stderr, flush=True)

    now = time.time()
    stale_threshold = _gunicorn_timeout_seconds()

    # Use a non-blocking lock acquire so we never deadlock if SIGABRT
    # interrupted a thread that was already holding _lock.  In CPython the GIL
    # makes a bare dict read safe enough for this diagnostic purpose.
    acquired = _lock.acquire(blocking=False)
    try:
        entries = list(_inflight.values())
    finally:
        if acquired:
            _lock.release()

    if not entries:
        log_fn(f'[WORKER_ABORT] pid={pid} no in-flight requests tracked on this worker')
        return

    serialised: List[Dict[str, Any]] = []
    stale_count = 0
    for entry in sorted(entries, key=lambda e: float(e['started_at'])):
        elapsed = now - float(entry['started_at'])
        is_stale = elapsed >= stale_threshold
        if is_stale:
            stale_count += 1
        tag = 'STUCK' if is_stale else 'ACTIVE'
        log_fn(
            f'[WORKER_ABORT] pid={pid} [{tag}] '
            f'{entry.get("method")} {entry.get("path")}'
            + (f'?{entry.get("query")}' if entry.get('query') else '')
            + f' elapsed={elapsed:.1f}s endpoint={entry.get("endpoint")}'
        )
        serialised.append({
            'method': entry.get('method'),
            'path': entry.get('path'),
            'elapsed_s': round(elapsed, 1),
            'stale': is_stale,
        })

    log_fn(
        f'[WORKER_ABORT] pid={pid} summary: '
        f'{len(entries)} in-flight, {stale_count} stale (>={stale_threshold:.0f}s)'
    )
    _redis_push_aborted_worker(pid, serialised, stale_count)
    with suppress(Exception):
        _fs_push_aborted_worker(pid, serialised, stale_count)


def reset_for_tests() -> None:
    """Clear registry state (tests only)."""
    global _next_request_id, _fs_dir_resolved, _fs_mirror_disabled
    global _fs_last_write_mono, _fs_dirty, _redis_available, _redis_client
    with _lock:
        _next_request_id = 0
        _inflight.clear()
        _traffic_timestamps.clear()
        _recent_slow_completions.clear()
    _fs_dir_resolved = None
    _fs_mirror_disabled = False
    _fs_last_write_mono = 0.0
    _fs_dirty = False
    _redis_available = None
    _redis_client = None
