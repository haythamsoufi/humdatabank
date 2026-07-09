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


def _log_inflight(
    level: str,
    tag: str,
    elapsed: float,
    *,
    method: str,
    path: str,
    query: str = '',
    endpoint: Optional[str] = None,
) -> None:
    logger = current_app.logger
    message = (
        f'[{tag}] Request still in progress after {elapsed:.1f}s | '
        f'{_format_request_context(method=method, path=path, query=query, endpoint=endpoint)}'
    )
    message = _append_pool_stats(message)
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
    current_app.logger.warning(message)


def track_slow_request_teardown(_exc=None) -> None:
    """Ensure timers are cancelled even when after_request is skipped."""
    with suppress(Exception):
        _cancel_timers()
