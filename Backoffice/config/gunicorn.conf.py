"""
Gunicorn configuration file for production deployment.

This configuration optimizes for WebSocket support and prevents blocking.
"""

import multiprocessing
import os
import sys
import logging

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

# Threads per worker
# Each worker can handle multiple concurrent requests
# Recommended: 2-4 threads per worker for I/O-bound applications
threads = int(os.environ.get('GUNICORN_THREADS', '4'))

# Worker connections
# Maximum number of simultaneous clients per worker
worker_connections = int(os.environ.get('GUNICORN_WORKER_CONNECTIONS', '1000'))

# Timeout
# Workers silent for more than this many seconds are killed and restarted.
# Production uses Azure Application Gateway with a 30s backend timeout. Default 25s
# so Gunicorn recycles stuck workers (and releases DB connections) before the gateway
# returns an opaque 504 while the worker is still busy.
# Override via GUNICORN_TIMEOUT (e.g. 120) only when a longer upstream timeout is configured.
timeout = int(os.environ.get('GUNICORN_TIMEOUT', '25'))

# Keep-alive
# Seconds to wait for requests on a Keep-Alive connection
keepalive = int(os.environ.get('GUNICORN_KEEPALIVE', '5'))

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

# Graceful timeout for worker shutdown
graceful_timeout = int(os.environ.get('GUNICORN_GRACEFUL_TIMEOUT', '30'))

# Enable statsd (if configured)
# statsd_host = None
# statsd_prefix = 'gunicorn'

def on_starting(server):
    """Called just before the master process is initialized."""
    from app.utils.logging_handlers import configure_process_org_timezone, create_app_log_formatter

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
        from app.scheduler_lock import clear_stale_scheduler_locks_for_master
        if clear_stale_scheduler_locks_for_master(server.pid):
            server.log.warning(
                "Removed stale scheduler lock on master start (master pid=%s)",
                server.pid,
            )
    except Exception:
        pass
    server.log.info("Gunicorn server is ready. Spawning workers...")

def on_exit(server):
    """Called just before exiting Gunicorn."""
    server.log.info("Shutting down Gunicorn server...")

def worker_int(worker):
    """Called when a worker receives INT or QUIT signal."""
    is_scheduler_worker = False
    try:
        from app.scheduler_lock import scheduler_lock_path, read_lock_owner
        is_scheduler_worker = read_lock_owner(scheduler_lock_path(os.getppid())) == worker.pid
    except Exception:
        pass
    worker.log.warning(
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
    """Called (in the master process) when a worker exits.

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
        from app.scheduler_lock import scheduler_lock_path, read_lock_owner
        lock_path = scheduler_lock_path(server.pid)
        is_scheduler_worker = read_lock_owner(lock_path) == worker.pid
    except Exception:
        pass

    server.log.info(
        "[WORKER_EXIT] pid=%s reason=%s scheduler_owner=%s",
        worker.pid, reason, is_scheduler_worker,
    )

    try:
        from app.scheduler_lock import shutdown_worker_scheduler
        shutdown_worker_scheduler(
            getattr(worker, "wsgi", None), server.pid, worker.pid,
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


def worker_abort(worker):
    """Called (in the worker process) when Gunicorn kills a worker that exceeded GUNICORN_TIMEOUT.

    This fires *before* SIGKILL, so we have a short window to emit diagnostics.
    """
    import time as _wtime
    _t0 = _wtime.monotonic()

    # worker.alive is False when the worker was already in recycle (max_requests) when killed.
    is_recycle = not getattr(worker, 'alive', True)
    recycle_hint = ' [was in recycle — scheduler shutdown likely blocked]' if is_recycle else ''

    # Check whether this worker owned the scheduler lock.
    is_scheduler_worker = False
    try:
        from app.scheduler_lock import scheduler_lock_path, read_lock_owner
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
        from app.scheduler_lock import shutdown_worker_scheduler
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
