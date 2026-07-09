"""Scheduler ownership lock file for multi-worker Gunicorn deployments."""

from __future__ import annotations

import logging
import os
import tempfile
import time as _time
from enum import Enum
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class SchedulerLockResult(str, Enum):
    """Outcome of attempting to acquire the per-master scheduler lock."""

    ACQUIRED = 'acquired'
    RECLAIMED_STALE = 'reclaimed_stale'
    HELD_BY_LIVE_OWNER = 'held_by_live_owner'
    FILESYSTEM_FALLBACK = 'filesystem_fallback'


def scheduler_lock_path(master_pid: int) -> str:
    """Return the lock file path for a Gunicorn master process."""
    return os.path.join(tempfile.gettempdir(), f'hdb_scheduler_{master_pid}.lock')


def read_lock_owner(lock_path: str) -> Optional[int]:
    """Read the worker PID stored in a lock file, if valid."""
    try:
        with open(lock_path, 'r', encoding='utf-8') as fh:
            raw = fh.read().strip()
        return int(raw) if raw.isdigit() else None
    except (OSError, ValueError):
        return None


def pid_alive(pid: int) -> bool:
    """Return True when ``pid`` is a running process."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    else:
        return True


def try_acquire_scheduler_lock(
    master_pid: int,
    owner_pid: Optional[int] = None,
) -> SchedulerLockResult:
    """
    Try to acquire scheduler ownership for ``owner_pid`` under ``master_pid``.

    Reclaims the lock when the stored owner PID is missing or no longer alive.
    """
    owner_pid = os.getpid() if owner_pid is None else owner_pid
    lock_path = scheduler_lock_path(master_pid)

    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return _handle_existing_lock(lock_path, owner_pid)
    except OSError:
        logger.warning(
            'Scheduler lock create failed (%s); allowing scheduler init',
            lock_path,
        )
        return SchedulerLockResult.FILESYSTEM_FALLBACK

    try:
        os.write(fd, str(owner_pid).encode())
    finally:
        os.close(fd)
    return SchedulerLockResult.ACQUIRED


def _handle_existing_lock(lock_path: str, owner_pid: int) -> SchedulerLockResult:
    existing_owner = read_lock_owner(lock_path)
    if existing_owner == owner_pid:
        return SchedulerLockResult.ACQUIRED
    if existing_owner is not None and pid_alive(existing_owner):
        return SchedulerLockResult.HELD_BY_LIVE_OWNER

    stale_owner = existing_owner
    try:
        os.remove(lock_path)
    except OSError:
        logger.warning('Could not remove stale scheduler lock %s', lock_path)
        return SchedulerLockResult.HELD_BY_LIVE_OWNER

    logger.warning(
        'Reclaimed stale scheduler lock %s (previous owner pid=%s)',
        lock_path,
        stale_owner if stale_owner is not None else 'unknown',
    )

    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except (FileExistsError, OSError):
        return SchedulerLockResult.HELD_BY_LIVE_OWNER

    try:
        os.write(fd, str(owner_pid).encode())
    finally:
        os.close(fd)
    return SchedulerLockResult.RECLAIMED_STALE


def release_scheduler_lock(master_pid: int, owner_pid: Optional[int] = None) -> bool:
    """
    Remove the scheduler lock when owned by ``owner_pid``.

    When ``owner_pid`` is omitted, remove the lock unconditionally if present.
    """
    lock_path = scheduler_lock_path(master_pid)
    if not os.path.exists(lock_path):
        return False

    if owner_pid is not None:
        existing_owner = read_lock_owner(lock_path)
        if existing_owner is not None and existing_owner != owner_pid:
            return False

    try:
        os.remove(lock_path)
        return True
    except OSError:
        return False


def clear_stale_scheduler_locks_for_master(master_pid: int) -> bool:
    """Remove a master lock file when its owner PID is dead or unreadable."""
    lock_path = scheduler_lock_path(master_pid)
    if not os.path.exists(lock_path):
        return False

    owner = read_lock_owner(lock_path)
    if owner is not None and pid_alive(owner):
        return False

    try:
        os.remove(lock_path)
    except OSError:
        logger.warning('Could not clear stale scheduler lock on master start: %s', lock_path)
        return False

    logger.warning(
        'Cleared stale scheduler lock on master start: %s (owner pid=%s)',
        lock_path,
        owner if owner is not None else 'unknown',
    )
    return True


def shutdown_worker_scheduler(
    wsgi,
    master_pid: int,
    worker_pid: int,
    *,
    wait: bool = True,
    log_fn: Optional[Callable[[str], None]] = None,
) -> None:
    """Stop APScheduler and release the lock for an exiting/aborted worker.

    Used from Gunicorn ``worker_exit`` and ``worker_abort`` hooks.

    Args:
        wait: Pass ``False`` during ``worker_abort`` so the shutdown call
              does *not* block waiting for the currently-running job —
              the process will be SIGKILLed immediately after, so waiting
              would just delay the abort handler without benefit.
        log_fn: Optional callable that accepts a plain string and emits it
                as a log line.  Falls back to the module logger when omitted.
    """
    _log = log_fn or (lambda msg: logger.info(msg))

    if wsgi is not None and hasattr(wsgi, 'scheduler'):
        sched = getattr(wsgi, 'scheduler', None)
        if sched is not None and sched.running:
            _log(
                f"[SCHED_SHUTDOWN] pid={worker_pid} scheduler shutdown starting"
                f" (wait={wait})"
            )
            t0 = _time.monotonic()
            try:
                sched.shutdown(wait=wait)
                elapsed = _time.monotonic() - t0
                _log(
                    f"[SCHED_SHUTDOWN] pid={worker_pid} scheduler shutdown complete"
                    f" in {elapsed:.2f}s (wait={wait})"
                )
            except Exception as exc:
                elapsed = _time.monotonic() - t0
                _log(
                    f"[SCHED_SHUTDOWN] pid={worker_pid} scheduler shutdown error"
                    f" after {elapsed:.2f}s: {exc}"
                )
            try:
                wsgi.scheduler = None
            except Exception:
                pass
        else:
            _log(
                f"[SCHED_SHUTDOWN] pid={worker_pid} scheduler not running — skip shutdown"
            )

    released = release_scheduler_lock(master_pid, owner_pid=worker_pid)
    if released:
        _log(
            f"[SCHED_SHUTDOWN] pid={worker_pid} scheduler lock released"
            f" (master_pid={master_pid})"
        )
