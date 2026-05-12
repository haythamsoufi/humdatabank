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
# Formula: (2 x CPU cores) + 1
# For production, adjust based on your server's CPU cores
workers = int(os.environ.get('GUNICORN_WORKERS', multiprocessing.cpu_count() * 2 + 1))

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
# Use at least 600 for AI chat/agent (multi-tool + LLM); shorter values can
# cause "timed out" during long agent runs even when client/app timeouts are higher.
timeout = int(os.environ.get('GUNICORN_TIMEOUT', '600'))

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
max_requests = int(os.environ.get('GUNICORN_MAX_REQUESTS', '1000'))
max_requests_jitter = int(os.environ.get('GUNICORN_MAX_REQUESTS_JITTER', '50'))

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
    worker.log.info("Worker received INT or QUIT signal")

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


def worker_abort(worker):
    """Called when a worker receives the ABRT signal."""
    worker.log.warning("Worker received ABRT signal")
