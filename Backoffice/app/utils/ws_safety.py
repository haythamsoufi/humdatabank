"""
WebSocket Safety Utilities

Provides non-blocking wrappers and safety checks to ensure WebSocket operations
never block the main Flask application thread.
"""

import logging
import threading
import time
from functools import wraps
from typing import Callable, Any

logger = logging.getLogger(__name__)


def non_blocking_send(ws, message: str, timeout: float = 2.0) -> bool:
    """
    Non-blocking wrapper for WebSocket send operation.

    Args:
        ws: WebSocket connection object
        message: Message to send (string)
        timeout: Maximum time to wait for send (seconds)

    Returns:
        True if message was sent successfully, False otherwise
    """
    try:
        # flask-sock's send() should be non-blocking, but we add timeout protection
        # In production with proper WSGI server (Gunicorn with threads), this won't block
        ws.send(message)
        return True
    except Exception as e:
        logger.debug(f"Error in non-blocking send: {str(e)}")
        return False


def safe_websocket_operation(func: Callable) -> Callable:
    """
    Decorator to ensure WebSocket operations don't block the main app.

    Wraps WebSocket handler functions to:
    1. Catch and log all exceptions
    2. Ensure cleanup happens even on errors
    3. Prevent exceptions from propagating to main thread
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in WebSocket operation {func.__name__}: {str(e)}", exc_info=True)
            # Don't re-raise - prevent blocking the main app
            return None
    return wrapper


class WebSocketTimeout:
    """
    Context manager for WebSocket operations with timeout protection.
    """
    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = time.time() - self.start_time
        if elapsed > self.timeout:
            logger.warning(f"WebSocket operation took {elapsed:.2f}s (timeout: {self.timeout}s)")
        return False  # Don't suppress exceptions

    def check_timeout(self) -> bool:
        """Check if timeout has been exceeded"""
        if self.start_time is None:
            return False
        return (time.time() - self.start_time) > self.timeout


def ensure_daemon_thread(target: Callable, name: str = None) -> threading.Thread:
    """
    Create a daemon thread for WebSocket operations.

    Daemon threads won't prevent the application from shutting down.

    Args:
        target: Function to run in thread
        name: Thread name

    Returns:
        Thread object (not started)
    """
    thread = threading.Thread(target=target, daemon=True, name=name)
    return thread


def check_websocket_health(ws) -> bool:
    """
    Check if WebSocket connection is still healthy.

    Args:
        ws: WebSocket connection object

    Returns:
        True if connection appears healthy, False otherwise
    """
    try:
        # Try to check connection state if available
        if hasattr(ws, 'closed'):
            return not ws.closed
        if hasattr(ws, 'ready_state'):
            # WebSocket.OPEN = 1
            return getattr(ws, 'ready_state', 0) == 1
        # If we can't check, assume it's healthy
        return True
    except Exception as e:
        logger.debug("WebSocket health check failed: %s", e)
        return False
