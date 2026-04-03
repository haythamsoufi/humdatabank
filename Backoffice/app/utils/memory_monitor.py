# app/utils/memory_monitor.py
"""
Memory monitoring utilities for runtime memory tracking.
Provides decorators and context managers to monitor memory usage at key points.
"""

import os
import sys
import functools
import logging
import tracemalloc
from typing import Dict, Any, Optional, Callable
from flask import current_app, request, g
from datetime import datetime
from contextlib import suppress


class MemoryMonitor:
    """Memory monitoring manager for tracking memory usage."""

    _instance = None
    _initialized = False
    _tracemalloc_started = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self.enabled = False
            self.logger = None
            self.memory_logger = None
            self.log_file_path = None
            self.file_handler = None
            self._initialized = True

    def configure(self, app, enabled: bool = False):
        """Configure memory monitoring."""
        self.enabled = enabled
        self.logger = app.logger
        self.log_file_path = None
        self.file_handler = None

        if enabled:
            # Set up file logging for memory logs
            try:
                # Create logs directory if it doesn't exist
                logs_dir = os.path.join(app.instance_path, 'logs')
                os.makedirs(logs_dir, exist_ok=True)

                # Create memory log file path
                self.log_file_path = os.path.join(logs_dir, 'memory.log')

                # Use RotatingFileHandler to prevent unbounded log growth and improve performance
                from logging.handlers import RotatingFileHandler
                max_bytes = app.config.get('MEMORY_LOG_MAX_BYTES', 10 * 1024 * 1024)  # 10MB default
                backup_count = app.config.get('MEMORY_LOG_BACKUP_COUNT', 5)  # Keep 5 backups
                self.file_handler = RotatingFileHandler(
                    self.log_file_path,
                    maxBytes=max_bytes,
                    backupCount=backup_count,
                    encoding='utf-8'
                )
                self.file_handler.setLevel(logging.INFO)

                # Create formatter for memory logs
                formatter = logging.Formatter(
                    '[%(asctime)s] %(levelname)s: %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S'
                )
                self.file_handler.setFormatter(formatter)

                # Create a separate logger for memory logs
                self.memory_logger = logging.getLogger('app.memory')
                self.memory_logger.setLevel(logging.INFO)
                self.memory_logger.addHandler(self.file_handler)
                # Prevent propagation to root logger to avoid duplicate logs
                self.memory_logger.propagate = False

                self.logger.debug(f"Memory monitoring enabled - logs will be written to {self.log_file_path}")

            except Exception as e:
                self.logger.warning(f"Failed to set up memory log file: {e}")
                self.memory_logger = self.logger  # Fallback to app logger

            # Start tracemalloc if enabled (can be disabled in production for performance)
            # tracemalloc has 5-20% CPU overhead, so make it optional
            tracemalloc_enabled = app.config.get('TRACEMALLOC_ENABLED', False)
            if tracemalloc_enabled and not self._tracemalloc_started:
                try:
                    tracemalloc.start()
                    self._tracemalloc_started = True
                    self.logger.debug("Memory monitoring enabled - tracemalloc started")
                except Exception as e:
                    self.logger.warning(f"Failed to start tracemalloc: {e}")
                    # Don't disable memory monitoring if tracemalloc fails - can still use psutil
            elif not tracemalloc_enabled:
                self.logger.debug("Memory monitoring enabled - tracemalloc disabled (use TRACEMALLOC_ENABLED=True to enable)")
        else:
            self.memory_logger = None

    def get_memory_usage(self) -> Dict[str, Any]:
        """Get current memory usage statistics."""
        try:
            import psutil
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()

            return {
                'rss_mb': memory_info.rss / 1024 / 1024,  # Resident Set Size in MB
                'vms_mb': memory_info.vms / 1024 / 1024,  # Virtual Memory Size in MB
                'percent': process.memory_percent(),
                'available_mb': psutil.virtual_memory().available / 1024 / 1024,
                'total_mb': psutil.virtual_memory().total / 1024 / 1024,
            }
        except ImportError:
            # Fallback to tracemalloc if psutil not available
            if tracemalloc.is_tracing():
                current, peak = tracemalloc.get_traced_memory()
                return {
                    'current_mb': current / 1024 / 1024,
                    'peak_mb': peak / 1024 / 1024,
                    'method': 'tracemalloc'
                }
            else:
                return {'error': 'No memory monitoring available'}

    def get_top_memory_allocations(self, limit: int = 10) -> list:
        """Get top memory allocations using tracemalloc."""
        if not tracemalloc.is_tracing():
            return []

        try:
            snapshot = tracemalloc.take_snapshot()
            top_stats = snapshot.statistics('lineno')

            results = []
            for stat in top_stats[:limit]:
                results.append({
                    'filename': stat.traceback[0].filename if stat.traceback else 'unknown',
                    'lineno': stat.traceback[0].lineno if stat.traceback else 0,
                    'size_mb': stat.size / 1024 / 1024,
                    'count': stat.count
                })
            return results
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Failed to get memory allocations: {e}")
            return []

    def log_memory_usage(self, context: str = "", level: int = logging.INFO):
        """Log current memory usage."""
        if not self.enabled:
            return

        memory = self.get_memory_usage()
        logger = self.memory_logger if self.memory_logger else self.logger

        if not logger:
            return

        if 'error' in memory:
            logger.log(level, f"[MEMORY] {context}: {memory['error']}")
            return

        if 'rss_mb' in memory:
            # Using psutil (more detailed)
            msg = (
                f"[MEMORY] {context}: "
                f"RSS={memory['rss_mb']:.1f}MB, "
                f"VMS={memory['vms_mb']:.1f}MB, "
                f"Percent={memory['percent']:.1f}%, "
                f"Available={memory['available_mb']:.1f}MB/{memory['total_mb']:.1f}MB"
            )
        else:
            # Using tracemalloc
            msg = (
                f"[MEMORY] {context}: "
                f"Current={memory.get('current_mb', 0):.1f}MB, "
                f"Peak={memory.get('peak_mb', 0):.1f}MB"
            )

        logger.log(level, msg)

    def log_memory_diff(self, before: Dict[str, Any], after: Dict[str, Any], context: str = ""):
        """Log memory difference between two measurements."""
        if not self.enabled:
            return

        logger = self.memory_logger if self.memory_logger else self.logger
        if not logger:
            return

        if 'error' in before or 'error' in after:
            return

        if 'rss_mb' in before and 'rss_mb' in after:
            diff_mb = after['rss_mb'] - before['rss_mb']
            diff_percent = after['percent'] - before['percent']

            logger.info(
                f"[MEMORY] {context}: "
                f"ΔRSS={diff_mb:+.1f}MB ({diff_percent:+.1f}%), "
                f"Before={before['rss_mb']:.1f}MB, "
                f"After={after['rss_mb']:.1f}MB"
            )
        elif 'current_mb' in before and 'current_mb' in after:
            diff_mb = after['current_mb'] - before['current_mb']
            logger.info(
                f"[MEMORY] {context}: "
                f"ΔMemory={diff_mb:+.1f}MB, "
                f"Before={before['current_mb']:.1f}MB, "
                f"After={after['current_mb']:.1f}MB"
            )

    def get_log_file_path(self) -> Optional[str]:
        """Get the path to the memory log file."""
        return self.log_file_path


# Global memory monitor instance
memory_monitor = MemoryMonitor()


def memory_tracker(operation_name: str = None, log_top_allocations: bool = False):
    """Decorator to track memory usage of a function."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not memory_monitor.enabled:
                return func(*args, **kwargs)

            op_name = operation_name or f"{func.__module__}.{func.__name__}"

            # Log memory before
            before = memory_monitor.get_memory_usage()
            memory_monitor.log_memory_usage(f"Before {op_name}")

            try:
                # Execute function
                result = func(*args, **kwargs)

                # Log memory after
                after = memory_monitor.get_memory_usage()
                memory_monitor.log_memory_usage(f"After {op_name}")
                memory_monitor.log_memory_diff(before, after, op_name)

                # Log top allocations if requested
                if log_top_allocations:
                    top_allocations = memory_monitor.get_top_memory_allocations(limit=5)
                    if top_allocations:
                        logger = memory_monitor.memory_logger if memory_monitor.memory_logger else memory_monitor.logger
                        if logger:
                            logger.info(f"[MEMORY] Top allocations for {op_name}:")
                            for alloc in top_allocations:
                                logger.info(
                                    f"  {alloc['filename']}:{alloc['lineno']} - "
                                    f"{alloc['size_mb']:.2f}MB ({alloc['count']} blocks)"
                                )

                return result

            except Exception as e:
                after = memory_monitor.get_memory_usage()
                memory_monitor.log_memory_diff(before, after, f"{op_name} (ERROR)")
                raise

        return wrapper
    return decorator


class MemoryContext:
    """Context manager for tracking memory usage in a code block."""

    def __init__(self, context_name: str, log_top_allocations: bool = False):
        self.context_name = context_name
        self.log_top_allocations = log_top_allocations
        self.before = None

    def __enter__(self):
        if memory_monitor.enabled:
            self.before = memory_monitor.get_memory_usage()
            memory_monitor.log_memory_usage(f"Enter {self.context_name}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if memory_monitor.enabled:
            after = memory_monitor.get_memory_usage()
            memory_monitor.log_memory_usage(f"Exit {self.context_name}")
            memory_monitor.log_memory_diff(self.before, after, self.context_name)

            if self.log_top_allocations:
                top_allocations = memory_monitor.get_top_memory_allocations(limit=5)
                if top_allocations:
                    logger = memory_monitor.memory_logger if memory_monitor.memory_logger else memory_monitor.logger
                    if logger:
                        logger.info(f"[MEMORY] Top allocations in {self.context_name}:")
                        for alloc in top_allocations:
                            logger.info(
                                f"  {alloc['filename']}:{alloc['lineno']} - "
                                f"{alloc['size_mb']:.2f}MB ({alloc['count']} blocks)"
                            )


def log_request_memory():
    """Log memory usage for the current request (to be called in Flask hooks).
    Only logs if memory usage is abnormal (high usage or significant increase).
    """
    if not memory_monitor.enabled:
        return

    with suppress(Exception):  # Silently fail if request context not available
        # Skip static file requests - they're not interesting for memory monitoring
        if request.path.startswith('/static/') or request.path.startswith('/flags/'):
            return

        # Store initial memory in Flask g if not already set
        if not hasattr(g, 'request_memory_before'):
            memory = memory_monitor.get_memory_usage()
            g.request_memory_before = memory

            # Only log if memory usage is high (threshold: >80% or >500MB RSS)
            if 'rss_mb' in memory:
                if memory['percent'] > 80.0 or memory['rss_mb'] > 500.0:
                    memory_monitor.log_memory_usage(
                        f"Request START: {request.method} {request.path}"
                    )
            elif 'current_mb' in memory:
                if memory.get('current_mb', 0) > 500.0:
                    memory_monitor.log_memory_usage(
                        f"Request START: {request.method} {request.path}"
                    )


def log_request_memory_end():
    """Log memory usage at the end of a request.
    Only logs if there's a significant memory increase or high usage.
    """
    if not memory_monitor.enabled:
        return

    with suppress(Exception):  # Silently fail if request context not available
        # Skip static file requests
        if request.path.startswith('/static/') or request.path.startswith('/flags/'):
            return

        if hasattr(g, 'request_memory_before'):
            before = g.request_memory_before
            after = memory_monitor.get_memory_usage()

            # Check if we should log this request
            should_log = False

            if 'rss_mb' in before and 'rss_mb' in after:
                diff_mb = after['rss_mb'] - before['rss_mb']
                diff_percent = after['percent'] - before['percent']

                # Log if:
                # 1. Memory increased significantly (>10MB or >5%)
                # 2. Current memory usage is high (>80% or >500MB)
                # 3. Memory decreased significantly (potential leak indicator if negative)
                if (abs(diff_mb) > 10.0 or abs(diff_percent) > 5.0 or
                    after['percent'] > 80.0 or after['rss_mb'] > 500.0):
                    should_log = True
            elif 'current_mb' in before and 'current_mb' in after:
                diff_mb = after['current_mb'] - before['current_mb']
                if abs(diff_mb) > 10.0 or after.get('current_mb', 0) > 500.0:
                    should_log = True

            if should_log:
                memory_monitor.log_memory_diff(
                    before,
                    after,
                    f"Request END: {request.method} {request.path}"
                )
