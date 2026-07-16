"""Compatibility shim for the top-level ``scheduler_lock`` module.

The implementation lives in ``Backoffice/scheduler_lock.py`` (repository top
level) so the Gunicorn master process can import it from the hooks in
``config/gunicorn.conf.py`` without executing ``app/__init__`` (Flask,
SQLAlchemy, config). Application code keeps importing from
``app.scheduler_lock``; both names resolve to the same module objects and
share the same in-process lock state.
"""

from scheduler_lock import (  # noqa: F401
    SCHEDULER_SHUTDOWN_WAIT_SECONDS,
    SchedulerLockResult,
    pid_alive,
    read_lock_owner,
    release_scheduler_lock,
    scheduler_lock_path,
    shutdown_scheduler_bounded,
    shutdown_worker_scheduler,
    sweep_stale_scheduler_locks,
    try_acquire_scheduler_lock,
)

__all__ = [
    'SCHEDULER_SHUTDOWN_WAIT_SECONDS',
    'SchedulerLockResult',
    'pid_alive',
    'read_lock_owner',
    'release_scheduler_lock',
    'scheduler_lock_path',
    'shutdown_scheduler_bounded',
    'shutdown_worker_scheduler',
    'sweep_stale_scheduler_locks',
    'try_acquire_scheduler_lock',
]
