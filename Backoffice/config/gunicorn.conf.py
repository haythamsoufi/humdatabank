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
    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    info_handler.setFormatter(formatter)
    error_handler.setFormatter(formatter)

    # Add handlers
    gunicorn_logger.addHandler(info_handler)
    gunicorn_logger.addHandler(error_handler)

    server.log.info("Starting Gunicorn server...")
    server.log.info(f"Workers: {workers}, Threads: {threads}, Worker Class: {worker_class}")

def when_ready(server):
    """Called just after the server is started."""
    server.log.info("Gunicorn server is ready. Spawning workers...")

def on_exit(server):
    """Called just before exiting Gunicorn."""
    server.log.info("Shutting down Gunicorn server...")

def worker_int(worker):
    """Called when a worker receives INT or QUIT signal."""
    worker.log.warning(
        "Worker received INT/QUIT (pid=%s) — shutting down; in-flight requests may be interrupted",
        worker.pid,
    )

def pre_fork(server, worker):
    """Called just before a worker is forked."""
    pass

def post_fork(server, worker):
    """Called just after a worker has been forked."""
    server.log.info(f"Worker spawned (pid: {worker.pid})")

def pre_exec(server):
    """Called just before a new master process is forked."""
    server.log.info("Forking new master process")

def worker_exit(server, worker):
    """Called when a worker process exits — shut down APScheduler cleanly.

    Must not use Flask `current_app` here: there is no app/request context
    in this hook, so the worker would have skipped shutdown every time.
    Gunicorn loads the WSGI callable (e.g. `run:app`) as `worker.wsgi`.

    Also removes the scheduler lock file (written by _is_scheduler_worker in
    app/scheduler.py) so the next worker that starts can take over the
    scheduler role after max_requests recycling.
    """
    wsgi = getattr(worker, "wsgi", None)
    if wsgi is None or not hasattr(wsgi, "scheduler"):
        return
    sched = wsgi.scheduler
    if sched is None:
        return
    try:
        if sched.running:
            # Match app.scheduler: wait for the scheduler loop to stop so the
            # default ThreadPoolExecutor is not half-shut while still submitting.
            sched.shutdown(wait=True)
    except Exception:
        pass
    try:
        wsgi.scheduler = None
    except Exception:
        pass

    # Release the scheduler lock file so the replacement worker can acquire it.
    # The lock is keyed on the master PID (server.pid).
    try:
        import tempfile
        lock_path = os.path.join(tempfile.gettempdir(), f'hdb_scheduler_{server.pid}.lock')
        if os.path.exists(lock_path):
            os.remove(lock_path)
    except Exception:
        pass


def worker_abort(worker):
    """Called when a worker is killed after exceeding GUNICORN_TIMEOUT."""
    worker.log.error(
        "Worker timed out (ABRT, pid=%s): silent for >%ss — "
        "check logs for [STUCK_REQUEST] / [SLOW_REQUEST] before this line",
        worker.pid,
        timeout,
    )
