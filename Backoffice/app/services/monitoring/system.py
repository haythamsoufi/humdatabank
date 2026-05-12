# app/utils/system_monitor.py
from app.utils.datetime_helpers import utcnow
"""
System monitoring utilities for tracking CPU, disk, database, and request metrics.
Complements memory monitoring to provide comprehensive system health tracking.
"""

import os
import time
import logging
from typing import Dict, Any, Optional
from flask import current_app, request, g
from datetime import datetime
from sqlalchemy import text
from contextlib import suppress


class SystemMonitor:
    """System monitoring manager for tracking various system metrics."""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self.enabled = False
            self.logger = None
            self.system_logger = None
            self.log_file_path = None
            self.file_handler = None
            self._initialized = True

    def configure(self, app, enabled: bool = False):
        """Configure system monitoring."""
        self.enabled = enabled
        self.logger = app.logger
        self.log_file_path = None
        self.file_handler = None

        if enabled:
            # Set up file logging for system metrics
            try:
                # Create logs directory if it doesn't exist
                logs_dir = os.path.join(app.instance_path, 'logs')
                os.makedirs(logs_dir, exist_ok=True)

                # Create system log file path
                self.log_file_path = os.path.join(logs_dir, 'system.log')

                # Use RotatingFileHandler to prevent unbounded log growth and improve performance
                from logging.handlers import RotatingFileHandler
                max_bytes = app.config.get('SYSTEM_LOG_MAX_BYTES', 10 * 1024 * 1024)  # 10MB default
                backup_count = app.config.get('SYSTEM_LOG_BACKUP_COUNT', 5)  # Keep 5 backups
                self.file_handler = RotatingFileHandler(
                    self.log_file_path,
                    maxBytes=max_bytes,
                    backupCount=backup_count,
                    encoding='utf-8'
                )
                self.file_handler.setLevel(logging.INFO)

                # Create formatter for system logs
                formatter = logging.Formatter(
                    '[%(asctime)s] %(levelname)s: %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S'
                )
                self.file_handler.setFormatter(formatter)

                # Create a separate logger for system metrics
                self.system_logger = logging.getLogger('app.system')
                self.system_logger.setLevel(logging.INFO)
                self.system_logger.addHandler(self.file_handler)
                # Prevent propagation to root logger
                self.system_logger.propagate = False

                self.logger.debug(f"System monitoring enabled - logs will be written to {self.log_file_path}")

            except Exception as e:
                self.logger.warning(f"Failed to set up system log file: {e}")
                self.system_logger = self.logger  # Fallback to app logger
        else:
            self.system_logger = None

    def get_cpu_usage(self) -> Dict[str, Any]:
        """Get current CPU usage statistics."""
        try:
            import psutil
            process = psutil.Process(os.getpid())

            # Get CPU percent (non-blocking, average over last second)
            cpu_percent = process.cpu_percent(interval=0.1)

            # Get system-wide CPU
            system_cpu = psutil.cpu_percent(interval=0.1, percpu=False)
            cpu_count = psutil.cpu_count()

            # Get CPU times
            cpu_times = process.cpu_times()

            return {
                'process_cpu_percent': cpu_percent,
                'system_cpu_percent': system_cpu,
                'cpu_count': cpu_count,
                'user_time': cpu_times.user,
                'system_time': cpu_times.system,
            }
        except ImportError:
            return {'error': 'psutil not available for CPU monitoring'}
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Failed to get CPU usage: {e}")
            return {'error': 'An error occurred.'}

    def get_disk_usage(self) -> Dict[str, Any]:
        """Get disk usage statistics."""
        try:
            import psutil

            # Get disk usage for root partition
            disk = psutil.disk_usage('/')

            # Get disk I/O stats
            disk_io = psutil.disk_io_counters()

            return {
                'total_gb': disk.total / 1024 / 1024 / 1024,
                'used_gb': disk.used / 1024 / 1024 / 1024,
                'free_gb': disk.free / 1024 / 1024 / 1024,
                'percent': disk.percent,
                'read_mb': disk_io.read_bytes / 1024 / 1024 if disk_io else 0,
                'write_mb': disk_io.write_bytes / 1024 / 1024 if disk_io else 0,
                'read_count': disk_io.read_count if disk_io else 0,
                'write_count': disk_io.write_count if disk_io else 0,
            }
        except ImportError:
            return {'error': 'psutil not available for disk monitoring'}
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Failed to get disk usage: {e}")
            return {'error': 'An error occurred.'}

    def get_database_pool_stats(self) -> Dict[str, Any]:
        """Get database connection pool statistics."""
        try:
            from app import db

            pool = db.engine.pool

            return {
                'size': pool.size(),
                'checked_in': pool.checkedin(),
                'checked_out': pool.checkedout(),
                'overflow': pool.overflow(),
            }
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Failed to get database pool stats: {e}")
            return {'error': 'An error occurred.'}

    def get_active_threads(self) -> Dict[str, Any]:
        """Get active thread count."""
        try:
            import threading
            active_count = threading.active_count()
            thread_list = threading.enumerate()

            return {
                'active_count': active_count,
                'thread_names': [t.name for t in thread_list[:10]],  # First 10 thread names
            }
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Failed to get thread stats: {e}")
            return {'error': 'An error occurred.'}

    def get_network_io(self) -> Dict[str, Any]:
        """Get network I/O statistics."""
        try:
            import psutil
            net_io = psutil.net_io_counters()

            return {
                'bytes_sent_mb': net_io.bytes_sent / 1024 / 1024,
                'bytes_recv_mb': net_io.bytes_recv / 1024 / 1024,
                'packets_sent': net_io.packets_sent,
                'packets_recv': net_io.packets_recv,
            }
        except ImportError:
            return {'error': 'psutil not available for network monitoring'}
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Failed to get network I/O: {e}")
            return {'error': 'An error occurred.'}

    def get_system_metrics(self) -> Dict[str, Any]:
        """Get all system metrics in one call."""
        return {
            'cpu': self.get_cpu_usage(),
            'disk': self.get_disk_usage(),
            'database_pool': self.get_database_pool_stats(),
            'threads': self.get_active_threads(),
            'network': self.get_network_io(),
            'timestamp': utcnow().isoformat(),
        }

    def log_system_metrics(self, context: str = ""):
        """Log current system metrics."""
        if not self.enabled:
            return

        logger = self.system_logger if self.system_logger else self.logger
        if not logger:
            return

        metrics = self.get_system_metrics()

        # Format log message
        parts = [f"[SYSTEM] {context}"]

        if 'error' not in metrics['cpu']:
            parts.append(f"CPU={metrics['cpu']['process_cpu_percent']:.1f}%")

        if 'error' not in metrics['disk']:
            parts.append(f"Disk={metrics['disk']['percent']:.1f}%")
            parts.append(f"DiskFree={metrics['disk']['free_gb']:.1f}GB")

        if 'error' not in metrics['database_pool']:
            pool = metrics['database_pool']
            parts.append(f"DBPool={pool['checked_out']}/{pool['size']}")

        if 'error' not in metrics['threads']:
            parts.append(f"Threads={metrics['threads']['active_count']}")

        logger.info(" | ".join(parts))

    def get_log_file_path(self) -> Optional[str]:
        """Get the path to the system log file."""
        return self.log_file_path


# Global system monitor instance
system_monitor = SystemMonitor()


def _is_long_lived_connection_request() -> bool:
    """
    Return True for endpoints/requests that are expected to stay open.

    These routes (WebSocket/SSE/stream-style endpoints) should not be treated
    as "slow requests" because long duration is expected behavior.
    """
    with suppress(Exception):
        path = (request.path or "").lower()
        if path in {
            "/api/notifications/ws",
            "/api/ai/v2/ws",
        }:
            return True

        # WebSocket upgrade handshake
        upgrade = (request.headers.get("Upgrade") or "").lower()
        connection = (request.headers.get("Connection") or "").lower()
        if upgrade == "websocket" or "upgrade" in connection:
            return True

        # Server-Sent Events / streaming responses
        accept = (request.headers.get("Accept") or "").lower()
        if "text/event-stream" in accept:
            return True

    return False


def track_request_performance():
    """Track request performance metrics (to be called in Flask hooks)."""
    if not system_monitor.enabled:
        return

    with suppress(Exception):  # Silently fail if request context not available
        # Store start time in Flask g
        g.request_start_time = time.time()
        g.request_path = request.path
        g.request_method = request.method
        g.request_is_long_lived = _is_long_lived_connection_request()


def log_request_performance_end():
    """Log request performance at the end of a request."""
    if not system_monitor.enabled:
        return

    with suppress(Exception):  # Silently fail if request context not available
        if hasattr(g, 'request_start_time'):
            if getattr(g, "request_is_long_lived", False):
                return
            duration = time.time() - g.request_start_time
            logger = system_monitor.system_logger if system_monitor.system_logger else system_monitor.logger

            if logger and duration > 1.0:  # Only log slow requests (>1 second)
                logger.warning(
                    f"[SYSTEM] Slow Request: {g.request_method} {g.request_path} "
                    f"took {duration:.2f}s"
                )
