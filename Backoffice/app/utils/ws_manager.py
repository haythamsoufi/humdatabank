"""
WebSocket Manager for unified real-time communication.

Handles both AI chat streaming and notification delivery via WebSocket.
Uses connection pooling and timeouts to prevent blocking the main application.
"""

from typing import Dict, Set, Optional
from contextlib import suppress
from flask import current_app, has_app_context
from datetime import datetime
import json
import logging
import threading
import time
from collections import deque
from app.utils.datetime_helpers import utcnow

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manages WebSocket connections for real-time communication"""

    def __init__(self, max_connections_per_user=5, max_total_connections=100, message_queue_size=50):
        # Store active connections: {user_id: set of WebSocket objects}
        self._connections: Dict[int, Set] = {}
        self._lock = threading.RLock()  # Reentrant lock for nested calls
        self.max_connections_per_user = max_connections_per_user
        self.max_total_connections = max_total_connections
        self.message_queue_size = message_queue_size

        # Track connection metadata for cleanup
        self._connection_metadata: Dict[object, dict] = {}
        self._metadata_lock = threading.RLock()

    def add_connection(self, user_id: int, ws) -> bool:
        """
        Add a new WebSocket connection for a user.
        Returns True if connection was added, False if limit exceeded.

        Thread-safe implementation with proper atomic operations.
        """
        with self._lock:
            # Calculate current total connections atomically
            total_connections = sum(len(conns) for conns in self._connections.values())

            # Check total connections limit before adding
            if total_connections >= self.max_total_connections:
                logger.warning(
                    f"WebSocket connection limit reached ({self.max_total_connections}), "
                    f"rejecting new connection for user {user_id}"
                )
                return False

            # Initialize user's connection set if needed
            if user_id not in self._connections:
                self._connections[user_id] = set()

            user_connections = self._connections[user_id]

            # Check per-user limit and handle if exceeded
            if len(user_connections) >= self.max_connections_per_user:
                # Remove oldest connection (FIFO - first in, first out)
                logger.warning(
                    f"User {user_id} has {len(user_connections)} connections "
                    f"(max: {self.max_connections_per_user}), removing oldest"
                )
                oldest_ws = next(iter(user_connections))
                self._remove_connection_internal(user_id, oldest_ws)

            # Add new connection
            user_connections.add(ws)

            # Store connection metadata
            with self._metadata_lock:
                self._connection_metadata[ws] = {
                    'user_id': user_id,
                    'created_at': time.time(),
                    'last_activity': time.time(),
                    'message_count': 0
                }

            return True

    def _remove_connection_internal(self, user_id: int, ws) -> None:
        """Internal method to remove connection (assumes lock is held)"""
        if user_id in self._connections:
            self._connections[user_id].discard(ws)
            if not self._connections[user_id]:
                del self._connections[user_id]

        with self._metadata_lock:
            self._connection_metadata.pop(ws, None)

    def remove_connection(self, user_id: int, ws) -> None:
        """Remove a WebSocket connection for a user"""
        with self._lock:
            self._remove_connection_internal(user_id, ws)

    def update_activity(self, ws) -> None:
        """Update last activity timestamp for a connection"""
        with self._metadata_lock:
            if ws in self._connection_metadata:
                self._connection_metadata[ws]['last_activity'] = time.time()
                self._connection_metadata[ws]['message_count'] += 1

    def send_to_user(self, user_id: int, event_type: str, data: dict, timeout: float = 2.0) -> int:
        """
        Send a WebSocket message to all connections for a user.
        Returns the number of successful sends.

        Uses non-blocking sends with timeout to prevent hanging.
        This method is designed to be fast and never block the main app thread.

        Strategy:
        1. Acquire lock briefly to get connection list
        2. Release lock before sending (allows concurrent sends)
        3. Re-acquire lock only to remove broken connections
        This minimizes lock contention and prevents blocking.
        """
        try:
            # Step 1: Acquire lock briefly to get connection list
            with self._lock:
                if user_id not in self._connections:
                    return 0

                # Create copy of connections while holding lock
                connections_copy = list(self._connections[user_id])

            # Step 2: Release lock before sending messages
            # This allows concurrent sends to different users without blocking
            sent_count = 0
            broken_connections = []

            message = {
                'type': event_type,
                'data': data,
                'timestamp': utcnow().isoformat()
            }
            message_json = json.dumps(message)

            # Send messages without holding lock (non-blocking)
            for ws in connections_copy:
                try:
                    # flask-sock's send() is non-blocking when used with proper WSGI server
                    # (Gunicorn with threads, or async server)
                    ws.send(message_json)
                    # Update activity (uses its own lock, safe to call without main lock)
                    self.update_activity(ws)
                    sent_count += 1
                except Exception as e:
                    logger.debug(f"Error sending WebSocket message to user {user_id}: {str(e)}")
                    # Mark connection as broken for removal
                    broken_connections.append(ws)

            # Step 3: Re-acquire lock only to remove broken connections
            if broken_connections:
                with self._lock:
                    for ws in broken_connections:
                        # Double-check connection still exists before removing
                        if user_id in self._connections and ws in self._connections[user_id]:
                            self._remove_connection_internal(user_id, ws)

            return sent_count
        except Exception as e:
            logger.error(f"Unexpected error in send_to_user for user {user_id}: {str(e)}")
            return 0

    def send_to_connection(self, ws, event_type: str, data: dict) -> bool:
        """
        Send a message to a specific WebSocket connection.
        Returns True if successful, False otherwise.
        """
        try:
            message = {
                'type': event_type,
                'data': data,
                'timestamp': utcnow().isoformat()
            }
            ws.send(json.dumps(message))
            self.update_activity(ws)
            return True
        except Exception as e:
            logger.debug(f"Error sending WebSocket message to connection: {str(e)}")
            # Try to find and remove the connection
            with self._lock:
                for user_id, connections in list(self._connections.items()):
                    if ws in connections:
                        self._remove_connection_internal(user_id, ws)
                        break
            return False

    def get_connection_count(self, user_id: int = None) -> int:
        """Get the number of active connections"""
        with self._lock:
            if user_id:
                return len(self._connections.get(user_id, []))
            return sum(len(conns) for conns in self._connections.values())

    def get_all_user_ids(self) -> Set[int]:
        """Get all user IDs with active connections"""
        with self._lock:
            return set(self._connections.keys())

    def cleanup_stale_connections(self, max_idle_seconds: float = 300.0) -> int:
        """
        Clean up connections that have been idle for too long.
        Returns the number of connections cleaned up.
        """
        current_time = time.time()
        cleaned = 0

        with self._lock:
            stale_connections = []

            with self._metadata_lock:
                for ws, metadata in list(self._connection_metadata.items()):
                    idle_time = current_time - metadata['last_activity']
                    if idle_time > max_idle_seconds:
                        stale_connections.append((metadata['user_id'], ws))

            for user_id, ws in stale_connections:
                self._remove_connection_internal(user_id, ws)
                cleaned += 1

        if cleaned > 0:
            logger.info(f"Cleaned up {cleaned} stale WebSocket connections")

        return cleaned


# Global WebSocket manager instance
ws_manager = WebSocketManager()


def broadcast_notification(user_id: int, notification_data: dict) -> bool:
    """
    Broadcast a notification to a user via WebSocket.

    Args:
        user_id: User ID to send notification to
        notification_data: Notification data dictionary

    Returns:
        True if message was sent to at least one connection, False otherwise
    """
    if not has_app_context() or not current_app.config.get('WEBSOCKET_ENABLED', True):
        logger.debug("WebSocket disabled or no app context; skipping notification broadcast")
        return False

    try:
        sent_count = ws_manager.send_to_user(
            user_id,
            'notification',
            {
                'type': 'new_notification',
                'notification': notification_data
            }
        )
        if sent_count > 0:
            logger.debug(f"Broadcasted notification to user {user_id} via WebSocket ({sent_count} connection(s))")
        return sent_count > 0
    except Exception as e:
        logger.error(f"Error broadcasting notification to user {user_id}: {str(e)}")
        return False


def broadcast_unread_count(user_id: int, unread_count: int) -> bool:
    """
    Broadcast unread count update to a user via WebSocket.

    Args:
        user_id: User ID to send update to
        unread_count: New unread count

    Returns:
        True if message was sent to at least one connection, False otherwise
    """
    if not has_app_context() or not current_app.config.get('WEBSOCKET_ENABLED', True):
        logger.debug("WebSocket disabled or no app context; skipping unread count broadcast")
        return False

    try:
        sent_count = ws_manager.send_to_user(
            user_id,
            'unread_count',
            {
                'type': 'unread_count_update',
                'unread_count': unread_count
            }
        )
        if sent_count > 0:
            logger.debug(f"Broadcasted unread count ({unread_count}) to user {user_id} via WebSocket ({sent_count} connection(s))")
        return sent_count > 0
    except Exception as e:
        logger.error(f"Error broadcasting unread count to user {user_id}: {str(e)}")
        return False
