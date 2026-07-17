"""Log slow and stuck HTTP requests to stdout (Azure Log Stream).

Unlike SYSTEM_MONITORING (file-based CPU/disk metrics), this module is lightweight
and enabled by default. In-flight timers emit warnings before Gunicorn kills a worker
at GUNICORN_TIMEOUT.
"""

from __future__ import annotations

import os
import threading
import time
from contextlib import suppress
from typing import List, Optional

from flask import Flask, current_app, g, request

from app.services.monitoring.system import _is_long_lived_connection_request
from app.utils.request_utils import is_static_asset_request

_enabled = False
_threshold_seconds = 30.0
# Defaults match config.py so [STUCK_REQUEST] fires before GUNICORN_TIMEOUT=25s even if
# configure() is somehow not called (e.g. very early startup or test isolation edge cases).
_stuck_warning_seconds = 15.0
_stuck_critical_seconds = 23.0


def configure(app: Flask) -> None:
    """Load slow-request settings from app config."""
    global _enabled, _threshold_seconds, _stuck_warning_seconds, _stuck_critical_seconds
    _enabled = bool(app.config.get('SLOW_REQUEST_LOG_ENABLED', True))
    _threshold_seconds = float(app.config.get('SLOW_REQUEST_THRESHOLD_SECONDS', 30))
    _stuck_warning_seconds = float(app.config.get('SLOW_REQUEST_STUCK_WARNING_SECONDS', 15))
    _stuck_critical_seconds = float(app.config.get('SLOW_REQUEST_STUCK_CRITICAL_SECONDS', 23))


def _should_track() -> bool:
    if not _enabled:
        return False
    if is_static_asset_request():
        return False
    path = (request.path or '').lower()
    if path in {'/health', '/favicon.ico'}:
        return False
    return not _is_long_lived_connection_request()


def _format_request_context(
    *,
    method: Optional[str] = None,
    path: Optional[str] = None,
    query: Optional[str] = None,
    endpoint: Optional[str] = None,
) -> str:
    if method is None:
        method = getattr(g, 'slow_request_method', None) or request.method
    if path is None:
        path = getattr(g, 'slow_request_path', None) or request.path
    if query is None:
        query = getattr(g, 'slow_request_query', '')
    if endpoint is None:
        endpoint = getattr(g, 'slow_request_endpoint', None)
    parts = [f'pid={os.getpid()}', f'method={method}', f'path={path}']
    if query:
        parts.append(f'query={query!r}')
    if endpoint:
        parts.append(f'endpoint={endpoint}')
    return ' '.join(parts)


def _append_pool_stats(message: str) -> str:
    with suppress(Exception):
        from app import db

        pool = db.engine.pool
        message += f' | db_pool_out={pool.checkedout()}/{pool.size()}'
    return message


def _append_pressure_context(message: str, *, exclude_request_id: Optional[int] = None) -> str:
    """Append active-thread count and concurrent in-flight requests to a slow/stuck log line.

    Answers "was this process doing something else at the time?" directly in the
    log, instead of requiring a separate investigation after the fact — the
    request's own duration alone can't distinguish "this code is slow" from
    "this thread was waiting behind other concurrent work on the same process".
    """
    with suppress(Exception):
        from app.services.monitoring.request_pressure import sibling_snapshot

        snap = sibling_snapshot(exclude_request_id=exclude_request_id)
        message += (
            f' | active_threads={snap["active_threads"]} '
            f'concurrent_requests={snap["sibling_count"]}'
        )
        if snap['siblings']:
            sibling_desc = ', '.join(
                f'{s["method"]} {s["path"]} ({s["elapsed_s"]}s)' for s in snap['siblings']
            )
            message += f' | concurrent=[{sibling_desc}]'
    return message


def _log_inflight(
    level: str,
    tag: str,
    elapsed: float,
    *,
    method: str,
    path: str,
    query: str = '',
    endpoint: Optional[str] = None,
    pressure_request_id: Optional[int] = None,
) -> None:
    logger = current_app.logger
    message = (
        f'[{tag}] Request still in progress after {elapsed:.1f}s | '
        f'{_format_request_context(method=method, path=path, query=query, endpoint=endpoint)}'
    )
    message = _append_pool_stats(message)
    message = _append_pressure_context(message, exclude_request_id=pressure_request_id)
    log_fn = getattr(logger, level, logger.warning)
    log_fn(message)


class _InflightTimer:
    """Fire once after delay if the request is still active."""

    def __init__(
        self,
        app,
        start_time: float,
        delay_seconds: float,
        level: str,
        tag: str,
        *,
        method: str,
        path: str,
        query: str = '',
        endpoint: Optional[str] = None,
        pressure_request_id: Optional[int] = None,
    ):
        self._app = app
        self._start_time = start_time
        self._delay_seconds = delay_seconds
        self._level = level
        self._tag = tag
        self._method = method
        self._path = path
        self._query = query
        self._endpoint = endpoint
        self._pressure_request_id = pressure_request_id
        self._cancelled = False
        self._timer: Optional[threading.Timer] = None

    def start(self) -> None:
        if self._delay_seconds <= 0:
            return
        self._timer = threading.Timer(self._delay_seconds, self._fire)
        self._timer.daemon = True
        self._timer.start()

    def _fire(self) -> None:
        if self._cancelled:
            return
        with self._app.app_context():
            elapsed = time.time() - self._start_time
            _log_inflight(
                self._level,
                self._tag,
                elapsed,
                method=self._method,
                path=self._path,
                query=self._query,
                endpoint=self._endpoint,
                pressure_request_id=self._pressure_request_id,
            )

    def cancel(self) -> None:
        self._cancelled = True
        if self._timer is not None:
            self._timer.cancel()


def _cancel_timers() -> None:
    timers: List[_InflightTimer] = getattr(g, 'slow_request_timers', None) or []
    for timer in timers:
        timer.cancel()
    if timers:
        g.slow_request_timers = []


def track_slow_request_start() -> None:
    """Start slow/stuck tracking for the current request (Flask before_request hook)."""
    if not _should_track():
        return

    app = current_app._get_current_object()
    start_time = time.time()
    g.slow_request_start = start_time
    g.slow_request_path = request.path
    g.slow_request_method = request.method
    g.slow_request_endpoint = request.endpoint
    g.slow_request_query = request.query_string.decode('utf-8', errors='replace')[:200]
    g.slow_request_timers = []
    # Captured now (not read from `g` inside the timer callback) because the timer
    # fires on a background thread under a fresh app_context that doesn't carry
    # this request's `g` — see request_pressure.track_pressure_start, which runs
    # earlier in the before_request chain and sets this on the *request's* g.
    pressure_request_id = getattr(g, 'pressure_request_id', None)

    schedule = (
        (_stuck_warning_seconds, 'warning', 'STUCK_REQUEST'),
        (_stuck_critical_seconds, 'error', 'STUCK_REQUEST_CRITICAL'),
    )
    for delay_seconds, level, tag in schedule:
        if delay_seconds <= 0:
            continue
        timer = _InflightTimer(
            app,
            start_time,
            delay_seconds,
            level,
            tag,
            method=g.slow_request_method,
            path=g.slow_request_path,
            query=g.slow_request_query,
            endpoint=g.slow_request_endpoint,
            pressure_request_id=pressure_request_id,
        )
        g.slow_request_timers.append(timer)
        timer.start()


def track_slow_request_end() -> None:
    """Log completed slow requests and cancel in-flight timers (Flask after_request hook)."""
    _cancel_timers()
    if not _enabled or not hasattr(g, 'slow_request_start'):
        return

    duration = time.time() - g.slow_request_start
    if duration < _threshold_seconds:
        return

    message = (
        f'[SLOW_REQUEST] Completed in {duration:.2f}s '
        f'(threshold={_threshold_seconds:.0f}s) | {_format_request_context()}'
    )
    message = _append_pool_stats(message)
    message = _append_pressure_context(message, exclude_request_id=getattr(g, 'pressure_request_id', None))
    current_app.logger.warning(message)


def track_slow_request_teardown(_exc=None) -> None:
    """Ensure timers are cancelled even when after_request is skipped."""
    with suppress(Exception):
        _cancel_timers()
