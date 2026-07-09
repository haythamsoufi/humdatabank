"""Deferred worker-availability investigation for 504 gateway timeout events.

When the platform-error endpoint receives a client-reported 504 it calls
``schedule_504_investigation`` which spawns a short-lived daemon thread.
The thread sleeps for ``_DELAY_SECONDS`` (enough for the stuck worker to be
killed and a new one to start), then takes a fresh snapshot and logs a single
``[WORKER_INVESTIGATION]`` line that answers the question:

    "Why was no Gunicorn worker free to handle the request that timed out?"

Log entries use structured key=value pairs so they can be queried in
Azure Log Analytics or Log Stream without post-processing.

Recovery probes
---------------
The JS client also sends a follow-up beacon at T+5 s and T+15 s.  When
``log_platform_error`` receives one of these (identified by the
``probe_delay_s`` field) it calls ``log_worker_recovery`` instead of
starting another investigation, providing a "worker available now"
confirmation that completes the incident timeline.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DELAY_SECONDS = 3.0  # pause before snapshotting — lets stuck workers die / recycle


# ── Public API ─────────────────────────────────────────────────────────────────

def schedule_504_investigation(
    app,
    *,
    url: Optional[str] = None,
    reported_at: Optional[float] = None,
) -> None:
    """Spawn a daemon thread to explain why no worker served the failing request.

    Args:
        app:         Flask application object (*not* the proxy) — pass
                     ``current_app._get_current_object()`` from the request handler.
        url:         The URL that returned 504 (from the client report).
        reported_at: ``time.time()`` when the 504 report arrived; defaults to now.
    """
    t0 = reported_at or time.time()
    thread = threading.Thread(
        target=_investigate,
        args=(app, url, t0),
        daemon=True,
        name='humdb-worker-investigation',
    )
    thread.start()


def log_worker_recovery(
    app,
    *,
    url: Optional[str] = None,
    probe_delay_s: float = 0.0,
    reported_at: Optional[float] = None,
) -> None:
    """Log a recovery confirmation beacon sent by the JS client.

    Called from ``log_platform_error`` when the request payload contains
    ``probe_delay_s``.  Runs synchronously in the request thread — it is
    cheap (just a snapshot + one log line).

    Args:
        app:           Flask application object.
        url:           The URL that originally returned 504.
        probe_delay_s: The client-side delay before this beacon was sent (s).
        reported_at:   When the *original* 504 was first reported.
    """
    try:
        with app.app_context():
            _log_recovery(app, url=url, probe_delay_s=probe_delay_s, reported_at=reported_at)
    except Exception as exc:
        logger.error('[WORKER_RECOVERY] Failed to log recovery snapshot: %s', exc)


# ── Internal helpers ───────────────────────────────────────────────────────────

def _investigate(app, url: Optional[str], reported_at: float) -> None:
    time.sleep(_DELAY_SECONDS)
    try:
        with app.app_context():
            _analyse_and_log(app, url=url, reported_at=reported_at)
    except Exception as exc:
        logger.error('[WORKER_INVESTIGATION] Investigation thread error: %s', exc, exc_info=True)


def _analyse_and_log(app, *, url: Optional[str], reported_at: float) -> None:
    from app.services.monitoring.request_pressure import snapshot_inflight
    from app.scheduler_lock import scheduler_lock_path, read_lock_owner, pid_alive

    now = time.time()
    elapsed = now - reported_at
    snap = snapshot_inflight()

    # ── Capacity ──────────────────────────────────────────────────────────────
    n_workers = max(1, int(os.environ.get('GUNICORN_WORKERS', '3')))
    threads_per_worker = snap.get('gunicorn_threads') or 4
    total_capacity = n_workers * threads_per_worker

    in_flight_this = snap.get('in_flight_count', 0)
    stale_this = snap.get('stale_in_flight_count', 0)
    other_workers = snap.get('other_workers_in_flight') or []
    in_flight_total = in_flight_this + len(other_workers)
    stale_total = stale_this + sum(1 for r in other_workers if r.get('stale'))
    cross_worker = snap.get('redis_cross_worker', False)
    timeout_s = snap.get('gunicorn_timeout_s', 25.0)

    capacity_pct = round(100 * in_flight_total / total_capacity) if total_capacity else 0

    # ── Scheduler state ───────────────────────────────────────────────────────
    sched_info = ''
    try:
        master_pid = os.getppid()
        owner_pid = read_lock_owner(scheduler_lock_path(master_pid))
        if owner_pid:
            alive = pid_alive(owner_pid)
            state = 'alive' if alive else 'DEAD'
            sched_info = f'scheduler_owner=pid:{owner_pid}({state})'
            if not alive:
                sched_info += ':stale-lock-likely-recycle-hang'
    except Exception:
        pass

    # ── Recent worker aborts ──────────────────────────────────────────────────
    recent_aborts = snap.get('recent_worker_aborts') or []
    abort_note = ''
    if recent_aborts:
        ab = recent_aborts[0]
        age_s = round(now - float(ab.get('aborted_at', now)))
        abort_note = (
            f"recent_abort=pid:{ab.get('pid')}"
            f"/{ab.get('stale_count', 0)}-stuck/{age_s}s-ago"
        )

    # ── DB pool ───────────────────────────────────────────────────────────────
    db_pool = snap.get('db_pool') or {}
    pool_note = ''
    checked_out = db_pool.get('checked_out')
    pool_size = db_pool.get('size')
    if isinstance(checked_out, int) and isinstance(pool_size, int) and pool_size > 0:
        overflow = db_pool.get('overflow') or 0
        pool_note = f'db_pool={checked_out}/{pool_size}+overflow:{overflow}'

    # ── Verdict ───────────────────────────────────────────────────────────────
    verdicts: List[str] = []
    if stale_total > 0:
        verdicts.append(f'STALE_WORKERS({stale_total})')
    if recent_aborts and (now - float(recent_aborts[0].get('aborted_at', 0))) < 120:
        verdicts.append('RECENT_WORKER_KILL')
    if isinstance(checked_out, int) and isinstance(pool_size, int) and checked_out >= pool_size:
        verdicts.append('DB_POOL_EXHAUSTED')
    if capacity_pct >= 80:
        verdicts.append(f'HIGH_CAPACITY({capacity_pct}pct)')
    if not verdicts:
        verdicts.append('QUEUE_OVERFLOW_OR_TRANSIENT')

    # ── Assemble log line ─────────────────────────────────────────────────────
    parts = [
        f'verdict={"+".join(verdicts)}',
        f'threads={in_flight_total}/{total_capacity}({capacity_pct}%)'
        + ('' if cross_worker else '[this-worker-only:no-redis]'),
        f'stale>={timeout_s:.0f}s:{stale_total}',
        f'probe_delay={_DELAY_SECONDS:.0f}s elapsed={elapsed:.1f}s',
        f"traffic={snap.get('traffic_last_60s')}/min",
    ]
    if sched_info:
        parts.append(sched_info)
    if abort_note:
        parts.append(abort_note)
    if pool_note:
        parts.append(pool_note)

    app.logger.warning(
        '[WORKER_INVESTIGATION] 504 url=%s | %s',
        url or 'unknown',
        ' | '.join(parts),
    )


def _log_recovery(
    app,
    *,
    url: Optional[str],
    probe_delay_s: float,
    reported_at: Optional[float],
) -> None:
    from app.services.monitoring.request_pressure import snapshot_inflight

    now = time.time()
    snap = snapshot_inflight()
    in_flight = snap.get('in_flight_count', 0)
    stale = snap.get('stale_in_flight_count', 0)
    pid = snap.get('worker_pid')

    elapsed_since_report = (now - reported_at) if reported_at else None
    elapsed_str = f'{elapsed_since_report:.1f}s' if elapsed_since_report else 'unknown'

    app.logger.info(
        '[WORKER_RECOVERY] probe_delay=%.0fs elapsed_since_504=%s '
        'url=%s pid=%s in_flight=%s stale=%s traffic=%s/min',
        probe_delay_s,
        elapsed_str,
        url or 'unknown',
        pid,
        in_flight,
        stale,
        snap.get('traffic_last_60s'),
    )
