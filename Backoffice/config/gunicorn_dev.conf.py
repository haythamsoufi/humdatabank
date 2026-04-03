"""
Gunicorn configuration for development with hot reloading.

This configuration is optimized for development with auto-reload and debugging.
"""

import os

# Server socket
# In Fly.io, bind to 0.0.0.0 to accept external connections
# In local dev, 127.0.0.1 is fine, but Fly.io needs 0.0.0.0
port = os.environ.get('PORT', '5000')
bind = os.environ.get('GUNICORN_BIND', f"0.0.0.0:{port}")
backlog = 2048

# Worker processes - use 1 worker in development for easier debugging
workers = 1

# Worker class - use gthread for WebSocket support
worker_class = 'gthread'

# Threads per worker - more threads in dev for testing concurrency
threads = int(os.environ.get('GUNICORN_DEV_THREADS', '4'))

# Worker connections
worker_connections = 1000

# Timeout - longer in dev for debugging
timeout = 300

# Keep-alive
keepalive = 5

# Logging - more verbose in development
accesslog = '-'
errorlog = '-'
loglevel = 'debug'
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = 'ngo-databank-backoffice-dev'

# Development settings
daemon = False
reload = True  # Auto-reload on code changes
reload_extra_files = []  # Additional files to watch

# Preload app - disable in dev for better reloading
preload_app = False

# Max requests - lower in dev to catch memory issues early
max_requests = 100
max_requests_jitter = 10

# Graceful timeout
graceful_timeout = 10

def on_starting(server):
    """Called just before the master process is initialized."""
    server.log.info("Starting Gunicorn development server...")
    server.log.info(f"Workers: {workers}, Threads: {threads}, Worker Class: {worker_class}")
    server.log.info("Auto-reload enabled - code changes will restart the server")

def when_ready(server):
    """Called just after the server is started."""
    server.log.info("Gunicorn development server is ready")
    server.log.info(f"Server running at {bind}")

def on_reload(server):
    """Called to recycle workers during a reload via SIGHUP."""
    server.log.info("Reloading workers...")
