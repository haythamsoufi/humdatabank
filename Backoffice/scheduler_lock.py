"""Scheduler ownership lock for multi-worker Gunicorn deployments.

This module lives at the repository top level (not inside the ``app``
package) so the Gunicorn master process can import it from the hooks in
``config/gunicorn.conf.py`` without executing ``app/__init__`` (Flask,
SQLAlchemy, config) — the master never serves requests and should stay
light. Application code imports the same objects through the
``app.scheduler_lock`` compatibility shim. Besides the lock itself it hosts
the worker-teardown helpers used by the hooks: bounded scheduler shutdown
and the lingering-thread hard-exit escape hatch.

Locking strategy
----------------
POSIX (production): ``flock(LOCK_EX | LOCK_NB)`` on a per-master lock file,
with the fd held open for the lifetime of the owning worker. The kernel
releases the lock automatically when the process dies — including SIGKILL —
which eliminates stale-lock reclaim logic, PID-reuse false positives, and
the read/remove/recreate races of the historical PID-file scheme. The owner
PID is still written into the file, but purely as diagnostics for log lines
and worker-investigation tooling. The lock file of a *live* master is never
unlinked (unlinking a file another process may already have open would let
two flocks succeed on different inodes); ``sweep_stale_scheduler_locks``
removes files left behind by dead masters.

Windows (development only; Gunicorn does not run on Windows): a hardened
variant of the PID-file scheme — atomic create-with-content via ``os.link``,
verify-after-reclaim, and liveness probing via ``OpenProcess``. Never probe
with ``os.kill(pid, 0)`` on Windows: any signal other than the two CTRL
events is delivered through ``TerminateProcess``, i.e. the probe would kill
the target process.

Filesystem errors fail *closed* (no scheduler in this worker) unless
``SCHEDULER_LOCK_FAIL_OPEN=true``: failing open means every worker whose
lock call errors starts its own scheduler, and duplicate scheduler jobs
(duplicate digest emails) were a real production incident.
"""

from __future__ import annotations

import errno
import logging
import os
import sys
import tempfile
import threading
import time as _time
from enum import Enum
from typing import Callable, Dict, Optional, Tuple

try:
    import fcntl  # POSIX only
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Upper bound for waiting on running jobs during scheduler shutdown.
#
# Invariant (enforced by choice of defaults, keep in sync with
# config/gunicorn.conf.py): GUNICORN_GRACEFUL_TIMEOUT (15s) + this bound
# (10s) must stay comfortably below GUNICORN_TIMEOUT (60s). During a
# max_requests recycle the worker stops heartbeating while it first drains
# in-flight requests (up to graceful_timeout) and then shuts down the
# scheduler (up to this bound); if the sum reaches the heartbeat timeout the
# master SIGKILLs the worker mid-teardown (WORKER TIMEOUT).
SCHEDULER_SHUTDOWN_WAIT_SECONDS = 10.0

_FAIL_OPEN_ENV = 'SCHEDULER_LOCK_FAIL_OPEN'

_LOCK_PREFIX = 'hdb_scheduler_'
_LOCK_SUFFIX = '.lock'

# flocks held by this process: lock_path -> (fd, owner_pid). POSIX only.
_held_locks: Dict[str, Tuple[int, int]] = {}
_held_locks_guard = threading.Lock()


class SchedulerLockResult(str, Enum):
    """Outcome of attempting to acquire the per-master scheduler lock."""

    ACQUIRED = 'acquired'
    RECLAIMED_STALE = 'reclaimed_stale'
    HELD_BY_LIVE_OWNER = 'held_by_live_owner'
    FILESYSTEM_FALLBACK = 'filesystem_fallback'


def scheduler_lock_path(master_pid: int) -> str:
    """Return the lock file path for a Gunicorn master process."""
    return os.path.join(tempfile.gettempdir(), f'{_LOCK_PREFIX}{master_pid}{_LOCK_SUFFIX}')


def _read_lock_raw(lock_path: str) -> str:
    try:
        with open(lock_path, 'r', encoding='utf-8', errors='replace') as fh:
            return fh.read().strip()
    except OSError:
        return ''


def read_lock_owner(lock_path: str) -> Optional[int]:
    """Read the worker PID stored in a lock file, if valid."""
    raw = _read_lock_raw(lock_path)
    return int(raw) if raw.isdigit() else None


# ---------------------------------------------------------------------------
# Process liveness
# ---------------------------------------------------------------------------

def _pid_alive_posix(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # EPERM: the process exists but belongs to another user.
        return True
    except OSError:
        return False
    return True


def _pid_alive_windows(pid: int) -> bool:
    import ctypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    ERROR_ACCESS_DENIED = 5

    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        # Access denied: the process exists but is protected.
        return ctypes.get_last_error() == ERROR_ACCESS_DENIED
    try:
        exit_code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return True  # handle opened; assume alive
        return exit_code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def pid_alive(pid: int) -> bool:
    """Return True when ``pid`` is a running process.

    On Windows this must never use ``os.kill(pid, 0)``: signals other than
    the CTRL events are delivered via ``TerminateProcess``, so the "probe"
    would kill the target — and Windows recycles PIDs aggressively, meaning
    a stale lock file could point at an unrelated live process.
    """
    if pid <= 0:
        return False
    if os.name == 'nt':
        return _pid_alive_windows(pid)
    return _pid_alive_posix(pid)


# ---------------------------------------------------------------------------
# Acquire / release
# ---------------------------------------------------------------------------

def _fail_open_enabled() -> bool:
    return os.environ.get(_FAIL_OPEN_ENV, '').strip().lower() in ('1', 'true', 'yes')


def _filesystem_error_result(lock_path: str, op: str) -> SchedulerLockResult:
    """Map a lock filesystem error to a result — fail closed by default.

    HELD_BY_LIVE_OWNER is returned (although no owner exists) because every
    caller treats it as "do not start the scheduler in this worker".
    """
    if _fail_open_enabled():
        logger.warning(
            'Scheduler lock %s failed (%s); %s=true — allowing scheduler without lock',
            op, lock_path, _FAIL_OPEN_ENV,
        )
        return SchedulerLockResult.FILESYSTEM_FALLBACK
    logger.error(
        'Scheduler lock %s failed (%s); failing closed — scheduler disabled in this '
        'worker. Set %s=true to run the scheduler without cross-worker locking.',
        op, lock_path, _FAIL_OPEN_ENV,
    )
    return SchedulerLockResult.HELD_BY_LIVE_OWNER


def try_acquire_scheduler_lock(
    master_pid: int,
    owner_pid: Optional[int] = None,
) -> SchedulerLockResult:
    """
    Try to acquire scheduler ownership for ``owner_pid`` under ``master_pid``.

    POSIX: non-blocking flock held for the process lifetime (auto-released by
    the kernel on process death). Windows: hardened PID-file fallback.
    """
    owner_pid = os.getpid() if owner_pid is None else owner_pid
    lock_path = scheduler_lock_path(master_pid)
    if fcntl is not None:
        return _acquire_flock(lock_path, owner_pid)
    return _acquire_pidfile(lock_path, owner_pid)


def _acquire_flock(lock_path: str, owner_pid: int) -> SchedulerLockResult:
    with _held_locks_guard:
        held = _held_locks.get(lock_path)
        if held is not None:
            # A second flock on a new fd would contend with our own lock
            # (flock is per open-file-description), so answer from state.
            return (
                SchedulerLockResult.ACQUIRED
                if held[1] == owner_pid
                else SchedulerLockResult.HELD_BY_LIVE_OWNER
            )

        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
        except OSError:
            return _filesystem_error_result(lock_path, 'create')

        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(fd)
            if exc.errno in (errno.EAGAIN, errno.EACCES, errno.EWOULDBLOCK):
                return SchedulerLockResult.HELD_BY_LIVE_OWNER
            return _filesystem_error_result(lock_path, 'flock')

        # The lock is ours. Any leftover content belongs to a previous owner
        # whose flock the kernel already released (crash / SIGKILL).
        previous_raw = _read_lock_raw(lock_path)
        try:
            os.ftruncate(fd, 0)
            os.write(fd, str(owner_pid).encode())
        except OSError:
            # Diagnostics only — the flock itself is what guarantees mutual
            # exclusion, so a failed owner-pid write must not fail the acquire.
            logger.warning('Could not write owner pid to scheduler lock %s', lock_path)

        _held_locks[lock_path] = (fd, owner_pid)

    if previous_raw and previous_raw != str(owner_pid):
        logger.warning(
            'Reclaimed scheduler lock %s (previous owner pid=%s no longer holds it)',
            lock_path,
            previous_raw if previous_raw.isdigit() else 'unknown',
        )
        return SchedulerLockResult.RECLAIMED_STALE
    return SchedulerLockResult.ACQUIRED


def _create_pidfile_atomically(lock_path: str, owner_pid: int) -> Optional[bool]:
    """Create ``lock_path`` containing ``owner_pid`` in one atomic step.

    Returns True on success, False when the lock already exists, None on
    filesystem errors. Writing to a temp file and hard-linking it into place
    means the lock file never exists in an empty, half-written state (a
    reader seeing an empty file would classify it as stale and remove it).
    """
    tmp_path = f'{lock_path}.{os.getpid()}.tmp'
    try:
        fd = os.open(tmp_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            os.write(fd, str(owner_pid).encode())
        finally:
            os.close(fd)

        try:
            os.link(tmp_path, lock_path)
            return True
        except FileExistsError:
            return False
        except OSError:
            # Filesystem without hard-link support: two-step create is the
            # best remaining option.
            try:
                fd2 = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                return False
            except OSError:
                return None
            try:
                os.write(fd2, str(owner_pid).encode())
            finally:
                os.close(fd2)
            return True
    except OSError:
        return None
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def _acquire_pidfile(lock_path: str, owner_pid: int) -> SchedulerLockResult:
    created = _create_pidfile_atomically(lock_path, owner_pid)
    if created is True:
        return SchedulerLockResult.ACQUIRED
    if created is None:
        return _filesystem_error_result(lock_path, 'create')

    existing_owner = read_lock_owner(lock_path)
    if existing_owner == owner_pid:
        return SchedulerLockResult.ACQUIRED
    if existing_owner is not None and pid_alive(existing_owner):
        return SchedulerLockResult.HELD_BY_LIVE_OWNER

    # Stale: dead or unreadable owner. Reclaim.
    try:
        os.remove(lock_path)
    except FileNotFoundError:
        pass
    except OSError:
        logger.warning('Could not remove stale scheduler lock %s', lock_path)
        return SchedulerLockResult.HELD_BY_LIVE_OWNER

    if _create_pidfile_atomically(lock_path, owner_pid) is not True:
        return SchedulerLockResult.HELD_BY_LIVE_OWNER

    # Verify after reclaiming: another worker may have raced the
    # read -> remove -> recreate sequence.
    if read_lock_owner(lock_path) != owner_pid:
        return SchedulerLockResult.HELD_BY_LIVE_OWNER

    logger.warning(
        'Reclaimed stale scheduler lock %s (previous owner pid=%s)',
        lock_path,
        existing_owner if existing_owner is not None else 'unknown',
    )
    return SchedulerLockResult.RECLAIMED_STALE


def release_scheduler_lock(master_pid: int, owner_pid: Optional[int] = None) -> bool:
    """
    Release the scheduler lock when owned by ``owner_pid``.

    POSIX: only this process's own held flock can be released (a dead
    worker's flock is released by the kernel, so e.g. the master reaping a
    SIGKILLed worker has nothing to do). Windows fallback: removes the PID
    file after an owner check; ``owner_pid=None`` removes it unconditionally.
    """
    lock_path = scheduler_lock_path(master_pid)
    if fcntl is not None:
        return _release_flock(lock_path, owner_pid)
    return _release_pidfile(lock_path, owner_pid)


def _release_flock(lock_path: str, owner_pid: Optional[int]) -> bool:
    with _held_locks_guard:
        held = _held_locks.get(lock_path)
        if held is None:
            return False
        fd, held_owner = held
        if owner_pid is not None and held_owner != owner_pid:
            return False
        del _held_locks[lock_path]

    try:
        os.ftruncate(fd, 0)  # clear the diagnostic owner pid
    except OSError:
        pass
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        os.close(fd)
    except OSError:
        pass
    # Deliberately do NOT unlink: another process may already have the file
    # open; removing it would let its flock and a later acquirer's flock
    # succeed on different inodes (two schedulers). Dead masters' files are
    # removed by sweep_stale_scheduler_locks().
    return True


def _release_pidfile(lock_path: str, owner_pid: Optional[int]) -> bool:
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


def sweep_stale_scheduler_locks(current_master_pid: Optional[int] = None) -> int:
    """Remove lock files whose *master* PID is dead. Returns the count removed.

    Housekeeping for the temp dir: live masters' lock files are never
    unlinked (see _release_flock), so each master leaves one small file
    behind. Removing a dead master's file is safe — no process can hold or
    acquire a lock keyed to a dead master. The current master's own file is
    skipped; with flock, leftover content in it is harmless.
    """
    removed = 0
    tmpdir = tempfile.gettempdir()
    try:
        names = os.listdir(tmpdir)
    except OSError:
        return 0

    for name in names:
        if not (name.startswith(_LOCK_PREFIX) and name.endswith(_LOCK_SUFFIX)):
            continue
        raw = name[len(_LOCK_PREFIX):-len(_LOCK_SUFFIX)]
        if not raw.isdigit():
            continue
        master_pid = int(raw)
        if current_master_pid is not None and master_pid == current_master_pid:
            continue
        if pid_alive(master_pid):
            continue

        path = os.path.join(tmpdir, name)
        owner = read_lock_owner(path)
        try:
            os.remove(path)
        except OSError:
            continue
        removed += 1
        logger.warning(
            'Removed stale scheduler lock %s (master pid=%s dead, owner pid=%s)',
            path, master_pid, owner if owner is not None else 'unknown',
        )
    return removed


# ---------------------------------------------------------------------------
# Scheduler shutdown helpers (used by app/scheduler.py and gunicorn hooks)
# ---------------------------------------------------------------------------

def shutdown_scheduler_bounded(
    sched,
    *,
    timeout_s: float = SCHEDULER_SHUTDOWN_WAIT_SECONDS,
    log_fn: Optional[Callable[[str], None]] = None,
) -> bool:
    """Shut down APScheduler, waiting for running jobs at most ``timeout_s``.

    ``scheduler.shutdown(wait=True)`` blocks until all running jobs finish.
    When a job hangs (external call without a timeout, DB lock), a recycling
    Gunicorn worker goes silent past GUNICORN_TIMEOUT and gets SIGKILLed —
    the ``WORKER TIMEOUT`` bursts seen in production. Bounding the wait
    releases the scheduler lock promptly so a fresh worker can take over.

    Note this alone does not bound the *process* exit time: the abandoned
    job keeps running on a non-daemon executor thread which the interpreter
    joins during finalization. The gunicorn worker_exit hook escapes that via
    ``shutdown_worker_scheduler(hard_exit_on_timeout=True)``.

    Returns True when shutdown completed within the deadline.
    """
    _log = log_fn or (lambda msg: logger.info(msg))
    done = threading.Event()

    def _run() -> None:
        try:
            sched.shutdown(wait=True)
        except Exception as exc:
            _log(f"[SCHED_SHUTDOWN] shutdown(wait=True) error: {exc}")
        finally:
            done.set()

    threading.Thread(target=_run, name='sched-shutdown', daemon=True).start()
    if done.wait(timeout_s):
        return True

    _log(
        f"[SCHED_SHUTDOWN] shutdown did not finish within {timeout_s:.0f}s "
        f"— abandoning wait so the worker can exit before the master kills it"
    )
    try:
        sched.shutdown(wait=False)
    except Exception:
        pass
    return False


def _flush_logging_and_stdio() -> None:
    """Flush log handlers and stdio; ``os._exit`` skips all buffered teardown."""
    for name in (None, 'gunicorn.error', 'gunicorn.access'):
        try:
            target = logging.getLogger(name) if name else logging.getLogger()
            for handler in list(target.handlers):
                try:
                    handler.flush()
                except Exception:
                    pass
        except Exception:
            pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except Exception:
            pass


def shutdown_worker_scheduler(
    wsgi,
    master_pid: int,
    worker_pid: int,
    *,
    wait: bool = True,
    hard_exit_on_timeout: bool = False,
    log_fn: Optional[Callable[[str], None]] = None,
) -> None:
    """Stop APScheduler and release the lock for an exiting/aborted worker.

    Used from Gunicorn ``worker_exit`` and ``worker_abort`` hooks.

    Args:
        wait: Pass ``False`` during ``worker_abort`` so the shutdown call
              does *not* block waiting for the currently-running job —
              the process will be SIGKILLed immediately after, so waiting
              would just delay the abort handler without benefit.
        hard_exit_on_timeout: When True and the bounded shutdown wait times
              out *in the exiting worker itself*, release the lock, flush
              logs, and ``os._exit(0)``. Since Python 3.9 the APScheduler
              executor threads are non-daemon and ``threading._shutdown()``
              joins them unboundedly during interpreter finalization (before
              atexit handlers), so returning normally with a stuck job would
              leave the worker silent until the master SIGKILLs it (WORKER
              TIMEOUT). Only honoured when ``os.getpid() == worker_pid`` —
              the master's reap-path call can never hard-exit the master.
        log_fn: Optional callable that accepts a plain string and emits it
                as a log line.  Falls back to the module logger when omitted.
    """
    _log = log_fn or (lambda msg: logger.info(msg))

    shutdown_timed_out = False
    if wsgi is not None and hasattr(wsgi, 'scheduler'):
        sched = getattr(wsgi, 'scheduler', None)
        if sched is not None and sched.running:
            _log(
                f"[SCHED_SHUTDOWN] pid={worker_pid} scheduler shutdown starting"
                f" (wait={wait})"
            )
            t0 = _time.monotonic()
            try:
                if wait:
                    completed = shutdown_scheduler_bounded(sched, log_fn=_log)
                    shutdown_timed_out = not completed
                else:
                    sched.shutdown(wait=False)
                elapsed = _time.monotonic() - t0
                _log(
                    f"[SCHED_SHUTDOWN] pid={worker_pid} scheduler shutdown complete"
                    f" in {elapsed:.2f}s (wait={wait}, timed_out={shutdown_timed_out})"
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

    if shutdown_timed_out and hard_exit_on_timeout and os.getpid() == worker_pid:
        _log(
            f"[SCHED_SHUTDOWN] pid={worker_pid} scheduler job still running after the"
            f" bounded wait — hard-exiting (os._exit(0)) so the master replaces this"
            f" worker cleanly instead of SIGKILLing it after WORKER TIMEOUT"
        )
        _flush_logging_and_stdio()
        os._exit(0)


# ---------------------------------------------------------------------------
# Worker exit: interpreter-shutdown hang escape hatch
# ---------------------------------------------------------------------------

# How long a graceful worker exit waits for remaining non-daemon threads to
# finish on their own before abandoning interpreter finalization. Idle gthread
# pool threads exit within milliseconds of the pool shutdown; anything still
# alive after this grace period is wedged for good (typically a pool thread
# pinned by a live WebSocket connection, blocked in ws.receive(), plus
# simple_websocket's own non-daemon reader thread per connection).
WORKER_EXIT_THREAD_JOIN_GRACE_SECONDS = 1.0


def lingering_nondaemon_threads(
    grace_seconds: float = WORKER_EXIT_THREAD_JOIN_GRACE_SECONDS,
) -> list[threading.Thread]:
    """Join other non-daemon threads for at most ``grace_seconds`` total.

    Returns the survivors — exactly the threads ``threading._shutdown()``
    (and ``concurrent.futures``' registered atexit join) would then wait on
    *without* a timeout during interpreter finalization.
    """
    current = threading.current_thread()
    candidates = [
        t for t in threading.enumerate()
        if t is not current and t is not threading.main_thread()
        and t.is_alive() and not t.daemon
    ]
    deadline = _time.monotonic() + max(0.0, grace_seconds)
    for t in candidates:
        remaining = deadline - _time.monotonic()
        if remaining <= 0:
            break
        try:
            t.join(remaining)
        except Exception:
            pass
    return [t for t in candidates if t.is_alive()]


def hard_exit_if_lingering_threads(
    worker_pid: int,
    *,
    grace_seconds: float = WORKER_EXIT_THREAD_JOIN_GRACE_SECONDS,
    exit_code: int = 0,
    log_fn: Optional[Callable[[str], None]] = None,
) -> bool:
    """``os._exit`` a finished worker whose interpreter shutdown would hang.

    Called at the very end of the Gunicorn ``worker_exit``/``worker_abort``
    hooks, after all teardown. gthread's ThreadPoolExecutor threads are
    non-daemon (Python 3.9+), and a thread pinned by a live WebSocket
    connection never finishes: ``threading._shutdown()`` joins it forever,
    the worker stops heartbeating, and the master SIGKILLs it after
    GUNICORN_TIMEOUT — the recurring post-incident ``WORKER TIMEOUT`` +
    "Perhaps out of memory?" pattern on recycles of workers holding
    notification WebSockets. Exiting via ``os._exit`` merely skips that
    doomed finalization: the pinned connections die with the process either
    way (clients auto-reconnect to a fresh worker), and the master replaces
    the worker immediately instead of after the timeout.

    No-op returning False in the master's reap path (``worker_pid`` is not
    this process) and when every non-daemon thread finishes within
    ``grace_seconds``. Returns True only in tests where ``os._exit`` is
    mocked.
    """
    if os.getpid() != worker_pid:
        return False
    lingering = lingering_nondaemon_threads(grace_seconds)
    if not lingering:
        return False

    _log = log_fn or (lambda msg: logger.info(msg))
    names = ', '.join(t.name for t in lingering[:8])
    if len(lingering) > 8:
        names += f', +{len(lingering) - 8} more'
    _log(
        f"[WORKER_EXIT] pid={worker_pid} hard exit (os._exit({exit_code})):"
        f" {len(lingering)} non-daemon thread(s) still alive after"
        f" {grace_seconds:.1f}s grace ({names}) — interpreter shutdown would"
        f" join them unboundedly and the master would SIGKILL this worker"
        f" after WORKER TIMEOUT"
    )
    _flush_logging_and_stdio()
    os._exit(exit_code)
    return True
