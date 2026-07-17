"""
Gunicorn configuration file for production deployment.

This configuration optimizes for WebSocket support and prevents blocking.

The hooks below import only the top-level ``scheduler_lock`` and
``org_logging`` modules (stdlib-only) — never ``app.*`` — so the master
process stays light and no Flask/SQLAlchemy import graph is loaded outside
the workers.
"""

import multiprocessing
import os
import sys
import logging

# Make the repository root importable regardless of how gunicorn was launched
# (the hooks import the top-level scheduler_lock / org_logging modules).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Server socket
bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"
backlog = 2048

# Worker processes
# Default 3 on Azure P1v3 (2 vCPU, ~3.5 GB RAM): avoids auto (2×CPU+1) over-provisioning
# that exhausts memory and DB pool. Scale out App Service instances instead of workers.
# Override via GUNICORN_WORKERS; auto-detect only when GUNICORN_WORKERS=auto.
_workers_env = os.environ.get('GUNICORN_WORKERS', '3').strip()
workers = (
    multiprocessing.cpu_count() * 2 + 1
    if _workers_env.lower() == 'auto'
    else int(_workers_env)
)

# Worker class - use gthread for WebSocket support
# gthread provides threading support needed for non-blocking WebSocket operations
worker_class = os.environ.get('GUNICORN_WORKER_CLASS', 'gthread')

# Threads per worker (this app is I/O-bound: DB, external APIs, WebSockets).
# Total concurrent request slots = workers x threads (3 x 8 = 24). WebSocket
# connections pin a thread each for their whole lifetime; ws_manager budgets
# them as GUNICORN_THREADS - WS_RESERVED_HTTP_THREADS (8 - 2 = 6 per worker).
# DB pool math per worker: pool_size 5 + max_overflow 10 = 15 connections vs
# 8 request threads + up to 6 concurrent scheduler jobs (scheduler-owner
# worker only) — jobs release their connection when each run's app context
# exits, so the pool covers the practical worst case.
threads = int(os.environ.get('GUNICORN_THREADS', '8'))

# ws_manager derives its per-worker WebSocket budget from GUNICORN_THREADS.
# Write the *effective* value back so workers always see the real thread
# count (previously an unset env var silently meant "assume 100").
os.environ['GUNICORN_THREADS'] = str(threads)

# Worker connections
# Maximum number of simultaneous clients per worker (for gthread this caps
# accepted/keepalive sockets held in the poller, not the thread pool).
worker_connections = int(os.environ.get('GUNICORN_WORKER_CONNECTIONS', '1000'))

# Timeout (heartbeat murder threshold — NOT a request timeout under gthread).
# gthread workers heartbeat from the main accept loop while requests run in
# the thread pool, so a stuck/slow REQUEST never trips this: slow requests are
# the App Gateway's problem (it 504s clients at ~30s) and are surfaced by the
# [SLOW_REQUEST]/[STUCK_REQUEST] monitors. What this timeout really catches is
# a worker whose main loop stopped (recycle teardown, GIL-hogging C call), so
# it must comfortably exceed the worst-case recycle teardown:
#   graceful_timeout (15s) + SCHEDULER_SHUTDOWN_WAIT_SECONDS (10s) = 25s.
# The old default of 25s made that exact case a coin-flip and produced the
# WORKER TIMEOUT bursts of the 2026-07-16 incident (workers SIGKILLed while
# draining a stuck translation_services request during recycle).
timeout = int(os.environ.get('GUNICORN_TIMEOUT', '60'))

# Keep-alive
# Seconds to keep idle Keep-Alive connections open. Behind Azure Application
# Gateway the backend keepalive should outlive the gateway's connection reuse,
# otherwise gunicorn closes an idle connection just as the gateway sends a new
# request on it (sporadic 502s). Idle keepalive sockets sit in the gthread
# poller (bounded by worker_connections), not on worker threads, so a long
# value costs nothing.
keepalive = int(os.environ.get('GUNICORN_KEEPALIVE', '75'))

# Logging
# Configure logging to route by level:
# - INFO logs go to stdout (normal color in Azure Log Stream)
# - WARNING/ERROR logs go to stderr (red in Azure Log Stream)
accesslog = os.environ.get('GUNICORN_ACCESS_LOG', '-')  # '-' means stdout
errorlog = os.environ.get('GUNICORN_ERROR_LOG', '-')  # '-' means stderr, but we'll route by level
loglevel = os.environ.get('GUNICORN_LOG_LEVEL', 'info')
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = 'hum-databank-backoffice'

# Server mechanics
daemon = False
pidfile = os.environ.get('GUNICORN_PIDFILE', None)
umask = 0
user = os.environ.get('GUNICORN_USER', None)
group = os.environ.get('GUNICORN_GROUP', None)
tmp_upload_dir = None

# SSL (if needed)
# keyfile = None
# certfile = None

# Preload app for better performance
# Loads application code before forking workers.
#
# IMPORTANT (Azure/Postgres/SSL):
# This app performs some database work during Flask app creation (startup settings load,
# background cleanup checks, etc.). If Gunicorn preloads the app in the master process,
# those DB connections can be inherited by forked workers, which can manifest as sporadic
# psycopg2 TLS errors like: "SSL error: ssl/tls alert bad record mac".
#
# Default to False for safety; enable explicitly via GUNICORN_PRELOAD=true if desired.
preload_app = os.environ.get('GUNICORN_PRELOAD', 'false').lower() == 'true'

# Max requests per worker before restart (prevents memory leaks)
max_requests = int(os.environ.get('GUNICORN_MAX_REQUESTS', '500'))
max_requests_jitter = int(os.environ.get('GUNICORN_MAX_REQUESTS_JITTER', '100'))

# Graceful timeout for worker shutdown.
# Invariant: graceful_timeout + SCHEDULER_SHUTDOWN_WAIT_SECONDS (10s) must
# stay comfortably below `timeout` (60s). During a max_requests recycle the
# worker stops heartbeating while it waits (up to graceful_timeout) for
# in-flight work — long-lived WebSocket connections, stuck requests — and
# then shuts down the scheduler (bounded at 10s). With the pre-incident
# default (30s > timeout 25s) the master's heartbeat check always fired
# first, so every recycle with lingering work ended in WORKER TIMEOUT +
# SIGKILL ("Perhaps out of memory?") instead of a clean exit — observed
# repeatedly in prod on 2026-07-16.
graceful_timeout = int(os.environ.get('GUNICORN_GRACEFUL_TIMEOUT', '15'))

# Enable statsd (if configured)
# statsd_host = None
# statsd_prefix = 'gunicorn'

def on_starting(server):
    """Called just before the master process is initialized."""
    # Top-level module (stdlib-only) — keeps Flask/SQLAlchemy out of the master.
    from org_logging import configure_process_org_timezone, create_app_log_formatter

    configure_process_org_timezone()

    # Configure Gunicorn's logger to route by level
    # INFO and below -> stdout (normal color in Azure Log Stream)
    # WARNING and above -> stderr (red in Azure Log Stream)
    gunicorn_logger = logging.getLogger('gunicorn.error')

    # Remove existing handlers
    gunicorn_logger.handlers = []

    # Create handler for INFO and below -> stdout
    info_handler = logging.StreamHandler(sys.stdout)
    info_handler.setLevel(logging.DEBUG)
    info_handler.addFilter(lambda record: record.levelno <= logging.INFO)

    # Create handler for WARNING and above -> stderr
    error_handler = logging.StreamHandler(sys.stderr)
    error_handler.setLevel(logging.WARNING)

    # Use Gunicorn's default formatter style
    formatter = create_app_log_formatter('[%(asctime)s] [%(levelname)s] %(message)s')
    info_handler.setFormatter(formatter)
    error_handler.setFormatter(formatter)

    # Add handlers
    gunicorn_logger.addHandler(info_handler)
    gunicorn_logger.addHandler(error_handler)

    server.log.info("Starting Gunicorn server...")
    server.log.info(f"Workers: {workers}, Threads: {threads}, Worker Class: {worker_class}")

def when_ready(server):
    """Called just after the server is started."""
    try:
        from scheduler_lock import sweep_stale_scheduler_locks
        removed = sweep_stale_scheduler_locks(current_master_pid=server.pid)
        if removed:
            server.log.warning(
                "Removed %s stale scheduler lock file(s) from dead masters (master pid=%s)",
                removed,
                server.pid,
            )
    except Exception:
        pass
    server.log.info("Gunicorn server is ready. Spawning workers...")

def on_exit(server):
    """Called just before exiting Gunicorn."""
    server.log.info("Shutting down Gunicorn server...")

def worker_int(worker):
    """Called when a worker receives INT or QUIT signal.

    This fires for every worker on every graceful restart/deploy, so keep it
    at INFO; only the scheduler-owner worker is interesting enough to WARN.
    """
    is_scheduler_worker = False
    try:
        from scheduler_lock import scheduler_lock_path, read_lock_owner
        is_scheduler_worker = read_lock_owner(scheduler_lock_path(os.getppid())) == worker.pid
    except Exception:
        pass
    log = worker.log.warning if is_scheduler_worker else worker.log.info
    log(
        "[WORKER_INT] pid=%s scheduler_owner=%s — INT/QUIT received; in-flight requests may be interrupted",
        worker.pid, is_scheduler_worker,
    )

def pre_fork(server, worker):
    """Called just before a worker is forked."""
    server.log.info(
        "Forking worker (master pid=%s, active workers=%s)",
        server.pid,
        len(server.WORKERS),
    )

def post_fork(server, worker):
    """Called just after a worker has been forked."""
    try:
        from app.logging_config import _apply_access_log_filters
        _apply_access_log_filters()
    except Exception:
        pass
    server.log.info("Worker spawned (pid: %s)", worker.pid)

def pre_exec(server):
    """Called just before a new master process is forked."""
    server.log.info("Forking new master process")

def worker_exit(server, worker):
    """Called when a worker exits — in the *worker* process for graceful exits
    (max_requests recycle, SIGTERM) and in the *master* when reaping a dead
    worker (SIGKILL). shutdown_worker_scheduler handles both: in the master,
    worker.wsgi is None and the flock was already released by the kernel.

    Distinguishes voluntary recycle (max_requests) from other exits and times
    the scheduler-shutdown + lock-release so slow teardown is visible in logs.
    """
    import time as _wtime
    _t0 = _wtime.monotonic()

    # worker.alive is False when the worker initiated its own recycle (max_requests).
    is_recycle = not getattr(worker, 'alive', True)
    reason = 'recycle(max_requests)' if is_recycle else 'exit'

    # Check whether this worker owned the scheduler lock BEFORE releasing it.
    is_scheduler_worker = False
    try:
        from scheduler_lock import scheduler_lock_path, read_lock_owner
        lock_path = scheduler_lock_path(server.pid)
        is_scheduler_worker = read_lock_owner(lock_path) == worker.pid
    except Exception:
        pass

    server.log.info(
        "[WORKER_EXIT] pid=%s reason=%s scheduler_owner=%s",
        worker.pid, reason, is_scheduler_worker,
    )

    try:
        from scheduler_lock import shutdown_worker_scheduler
        # hard_exit_on_timeout: if a scheduler job is still stuck when the
        # bounded shutdown wait expires, os._exit(0) instead of returning —
        # the interpreter would otherwise join the stuck non-daemon executor
        # thread unboundedly during finalization and the master would SIGKILL
        # this worker after WORKER TIMEOUT. Only takes effect in the exiting
        # worker's own call (this hook also runs in the master when reaping).
        shutdown_worker_scheduler(
            getattr(worker, "wsgi", None), server.pid, worker.pid,
            hard_exit_on_timeout=True,
            log_fn=lambda msg: server.log.info(msg),
        )
    except Exception as exc:
        server.log.warning(
            "[WORKER_EXIT] scheduler shutdown error (pid=%s): %s",
            worker.pid, exc,
        )

    elapsed = _wtime.monotonic() - _t0
    level = 'warning' if elapsed > 5 else 'info'
    getattr(server.log, level)(
        "[WORKER_EXIT] pid=%s teardown complete in %.2fs",
        worker.pid, elapsed,
    )

    # Teardown is done — nothing useful remains for this process. If non-daemon
    # threads linger (gthread pool threads pinned by live WebSocket connections),
    # interpreter finalization would join them forever and the master would
    # SIGKILL this worker after WORKER TIMEOUT — the residual post-2026-07-16
    # kill pattern on recycles of workers holding notification WebSockets.
    # Skip the doomed finalization and exit cleanly now. No-op in the master's
    # reap path and when all threads finish within the grace period.
    try:
        from scheduler_lock import hard_exit_if_lingering_threads
        hard_exit_if_lingering_threads(
            worker.pid,
            log_fn=lambda msg: server.log.info(msg),
        )
    except Exception as exc:
        server.log.warning(
            "[WORKER_EXIT] lingering-thread check failed (pid=%s): %s",
            worker.pid, exc,
        )


def worker_abort(worker):
    """Called (in the worker process) when Gunicorn kills a worker that exceeded GUNICORN_TIMEOUT.

    This fires *before* SIGKILL, so we have a short window to emit diagnostics.
    """
    import time as _wtime
    _t0 = _wtime.monotonic()

    # worker.alive is False when the worker was already in recycle (max_requests) when killed.
    # A blocked recycle has two possible culprits: in-flight requests draining in
    # futures.wait(graceful_timeout) — e.g. a stuck request, the actual cause in the
    # 2026-07-16 incident — or the scheduler shutdown wait. Don't presume the scheduler.
    is_recycle = not getattr(worker, 'alive', True)
    recycle_hint = (
        ' [was in recycle — blocked by in-flight request drain or scheduler shutdown;'
        ' check [STUCK_REQUEST] and [SCHED_SHUTDOWN] lines]'
        if is_recycle else ''
    )

    # Check whether this worker owned the scheduler lock.
    is_scheduler_worker = False
    try:
        from scheduler_lock import scheduler_lock_path, read_lock_owner
        lock_path = scheduler_lock_path(os.getppid())
        is_scheduler_worker = read_lock_owner(lock_path) == worker.pid
    except Exception:
        pass

    worker.log.error(
        "[WORKER_ABORT] pid=%s timeout=%ss scheduler_owner=%s%s — "
        "worker was silent for >%ss; check [STUCK_REQUEST]/[SLOW_REQUEST] above",
        worker.pid, timeout, is_scheduler_worker, recycle_hint, timeout,
    )

    # Dump every in-flight request tracked on this worker before the process dies.
    # This runs without a Flask app context; request_pressure handles that constraint.
    try:
        from app.services.monitoring.request_pressure import dump_inflight_on_abort
        dump_inflight_on_abort(
            worker.pid,
            log_fn=lambda msg: worker.log.error(msg),
        )
    except Exception as exc:
        worker.log.warning(
            "[WORKER_ABORT] Could not dump in-flight requests (pid=%s): %s",
            worker.pid, exc,
        )

    # Shut down scheduler without waiting — process is about to be SIGKILLed anyway.
    try:
        from scheduler_lock import shutdown_worker_scheduler
        shutdown_worker_scheduler(
            getattr(worker, "wsgi", None), os.getppid(), worker.pid,
            wait=False,
            log_fn=lambda msg: worker.log.error(msg),
        )
    except Exception as exc:
        worker.log.warning(
            "[WORKER_ABORT] Scheduler shutdown error (pid=%s): %s",
            worker.pid, exc,
        )

    elapsed = _wtime.monotonic() - _t0
    worker.log.error(
        "[WORKER_ABORT] pid=%s abort handler finished in %.3fs",
        worker.pid, elapsed,
    )

    # After this hook gunicorn calls sys.exit(1), which hangs in interpreter
    # finalization when non-daemon threads are wedged (the usual reason the
    # heartbeat stopped) — producing the "Exception ignored in threading
    # _shutdown" traceback and a second SIGKILL from the master. The process
    # is condemned either way; exit immediately instead. grace_seconds=0:
    # the worker was already silent for >GUNICORN_TIMEOUT, nothing will
    # finish now, and the master SIGKILLs ~1s after SIGABRT so there is no
    # time budget for joining.
    try:
        from scheduler_lock import hard_exit_if_lingering_threads
        hard_exit_if_lingering_threads(
            worker.pid,
            grace_seconds=0.0,
            exit_code=1,
            log_fn=lambda msg: worker.log.error(msg),
        )
    except Exception:
        pass
