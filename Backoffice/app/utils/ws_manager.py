"""
WebSocket Manager for unified real-time communication.

Handles both AI chat streaming and notification delivery via WebSocket.
Uses connection pooling and timeouts to prevent blocking the main application.
"""

from typing import Dict, Optional
from collections import OrderedDict
from flask import current_app, has_app_context
import json
import logging
import os
import threading
import time
from app.utils.datetime_helpers import utcnow

logger = logging.getLogger(__name__)


def _default_ws_connection_budget() -> int:
    """
    Compute a safe cap on total concurrent WebSocket connections per worker process,
    derived from the Gunicorn thread pool size (``GUNICORN_THREADS``).

    Every WebSocket connection served by a `gthread` worker occupies one worker
    thread for the lifetime of the connection (these are long-lived, not request/
    response). A burst of WebSocket connections can therefore starve the same
    worker's ability to serve regular HTTP requests, which is a known contributor
    to 502/504 gateway errors. We reserve a minimum number of threads for HTTP so
    WebSockets can never consume the entire pool; once the cap is hit, new
    connections are rejected and clients fall back to polling/SSE (both already
    implemented client-side).

    Falls back to a generous default (100) when GUNICORN_THREADS is not set
    (local dev/tests), since this throttling only matters under Gunicorn.
    """
    raw = os.environ.get('GUNICORN_THREADS', '').strip()
    if not raw:
        return 100
    try:
        threads = int(raw)
    except ValueError:
        return 100
    try:
        reserved_raw = os.environ.get('WS_RESERVED_HTTP_THREADS', '2').strip()
        reserved = int(reserved_raw) if reserved_raw else 2
    except ValueError:
        reserved = 2
    return max(1, threads - reserved)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, '').strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _default_channel_budgets(total: int) -> Dict[str, int]:
    """
    Per-channel caps so long-running AI sockets cannot starve notification slots
    (and vice versa). Total budget still applies on top.
    """
    # Leave at least one slot for notifications when AI saturates.
    ai_chat = _env_int('WS_MAX_AI_CHAT', max(1, min(total // 2, total - 1) if total > 1 else total))
    ai_docs = _env_int('WS_MAX_AI_DOCS', max(1, min(total // 3, total - 1) if total > 1 else total))
    notifications = _env_int('WS_MAX_NOTIFICATIONS', total)
    return {
        'notifications': max(1, notifications),
        'ai_chat': max(1, ai_chat),
        'ai_docs': max(1, ai_docs),
        'default': total,
    }


class WebSocketManager:
    """Manages WebSocket connections for real-time communication"""

    def __init__(
        self,
        max_connections_per_user=None,
        max_total_connections=None,
        message_queue_size=50,
        channel_budgets: Optional[Dict[str, int]] = None,
    ):
        # Insertion-ordered per user so eviction is true FIFO.
        self._connections: Dict[object, OrderedDict] = {}
        self._lock = threading.RLock()

        budget = _default_ws_connection_budget()
        self.max_total_connections = max_total_connections if max_total_connections is not None else budget
        self.max_connections_per_user = (
            max_connections_per_user if max_connections_per_user is not None else min(5, self.max_total_connections)
        )
        self.message_queue_size = message_queue_size
        self.channel_budgets = channel_budgets if channel_budgets is not None else _default_channel_budgets(
            self.max_total_connections
        )

        # Track connection metadata for cleanup (includes 'channel' for diagnostics
        # and per-channel admission control).
        self._connection_metadata: Dict[object, dict] = {}
        self._metadata_lock = threading.RLock()
        self._channel_counts: Dict[str, int] = {}

        # DEBUG only: this singleton is constructed on first import even when
        # WEBSOCKET_ENABLED=false (broadcasts no-op, diagnostics snapshot).
        # Live occupancy is logged at INFO on connect/disconnect.
        logger.debug(
            "[WS_POOL] WebSocketManager initialized: worker_pid=%s max_total_connections=%s "
            "max_connections_per_user=%s channel_budgets=%s gunicorn_threads=%s reserved_http_threads=%s",
            os.getpid(), self.max_total_connections, self.max_connections_per_user,
            self.channel_budgets,
            os.environ.get('GUNICORN_THREADS', 'unset'), os.environ.get('WS_RESERVED_HTTP_THREADS', '2'),
        )

    def _channel_count_unlocked(self, channel: str) -> int:
        return self._channel_counts.get(channel, 0)

    def add_connection(self, user_id, ws, channel: str = 'default') -> bool:
        """
        Add a new WebSocket connection for a user.
        Returns True if connection was added, False if limit exceeded.

        Thread-safe implementation with proper atomic operations.

        ``channel`` tags the connection's purpose (e.g. 'notifications', 'ai_chat',
        'ai_docs') for diagnostics and per-channel admission. All channels still
        share the total per-process thread budget.
        """
        with self._lock:
            total_connections = sum(len(conns) for conns in self._connections.values())

            if total_connections >= self.max_total_connections:
                logger.warning(
                    "[WS_POOL] rejected: worker_pid=%s channel=%s user=%s reason=limit_reached "
                    "active=%s/%s (thread budget exhausted; client should fall back to polling/SSE)",
                    os.getpid(), channel, user_id, total_connections, self.max_total_connections,
                )
                return False

            channel_cap = self.channel_budgets.get(channel, self.max_total_connections)
            channel_active = self._channel_count_unlocked(channel)
            if channel_active >= channel_cap:
                logger.warning(
                    "[WS_POOL] rejected: worker_pid=%s channel=%s user=%s reason=channel_limit "
                    "channel_active=%s/%s total=%s/%s",
                    os.getpid(), channel, user_id, channel_active, channel_cap,
                    total_connections, self.max_total_connections,
                )
                return False

            if user_id not in self._connections:
                self._connections[user_id] = OrderedDict()

            user_connections = self._connections[user_id]

            if len(user_connections) >= self.max_connections_per_user:
                # True FIFO: OrderedDict popitem(last=False) removes oldest.
                oldest_ws, _ = user_connections.popitem(last=False)
                logger.warning(
                    "[WS_POOL] per-user eviction: user=%s channel=%s "
                    "evicted_oldest (max_per_user=%s)",
                    user_id, channel, self.max_connections_per_user,
                )
                self._remove_connection_internal(user_id, oldest_ws, already_popped=True)

            user_connections[ws] = None

            # Best-effort OS thread id (matches /proc/<pid>/task/<tid> on Linux) so
            # external diagnostics (check_gunicorn_pressure.py) can tell "this OS
            # thread is serving a long-lived WebSocket" apart from an idle pool
            # thread or one stuck elsewhere. Available on Python 3.8+; None is a
            # safe fallback everywhere else.
            try:
                native_id = threading.get_native_id()
            except Exception:
                native_id = None

            with self._metadata_lock:
                self._connection_metadata[ws] = {
                    'user_id': user_id,
                    'channel': channel,
                    'created_at': time.time(),
                    'last_activity': time.time(),
                    'message_count': 0,
                    'native_id': native_id,
                }
            self._channel_counts[channel] = self._channel_count_unlocked(channel) + 1

            new_total = sum(len(conns) for conns in self._connections.values())
            pct_used = round((new_total / self.max_total_connections) * 100) if self.max_total_connections else 0
            logger.info(
                "[WS_POOL] connect: worker_pid=%s channel=%s user=%s active=%s/%s (%s%% of thread budget) "
                "channel_active=%s/%s",
                os.getpid(), channel, user_id, new_total, self.max_total_connections, pct_used,
                self._channel_count_unlocked(channel), channel_cap,
            )
            if pct_used >= 75:
                logger.warning(
                    "[WS_POOL] approaching thread budget: worker_pid=%s active=%s/%s (%s%%) — "
                    "risk of HTTP thread starvation if this keeps growing",
                    os.getpid(), new_total, self.max_total_connections, pct_used,
                )

            return True

    def _remove_connection_internal(self, user_id, ws, *, already_popped: bool = False) -> None:
        """Internal method to remove connection (assumes lock is held)"""
        channel = 'default'
        with self._metadata_lock:
            meta = self._connection_metadata.pop(ws, None)
            if meta:
                channel = meta.get('channel', 'default')

        if not already_popped and user_id in self._connections:
            self._connections[user_id].pop(ws, None)
            if not self._connections[user_id]:
                del self._connections[user_id]
        elif already_popped:
            # Oldest was already popped from the OrderedDict; clean empty user entry.
            if user_id in self._connections and not self._connections[user_id]:
                del self._connections[user_id]

        if channel in self._channel_counts and self._channel_counts[channel] > 0:
            self._channel_counts[channel] -= 1
            if self._channel_counts[channel] == 0:
                del self._channel_counts[channel]

    def remove_connection(self, user_id, ws) -> None:
        """Remove a WebSocket connection for a user"""
        with self._metadata_lock:
            channel = self._connection_metadata.get(ws, {}).get('channel', 'default')
        with self._lock:
            self._remove_connection_internal(user_id, ws)
            total_connections = sum(len(conns) for conns in self._connections.values())
        logger.info(
            "[WS_POOL] disconnect: worker_pid=%s channel=%s user=%s active=%s/%s",
            os.getpid(), channel, user_id, total_connections, self.max_total_connections,
        )

    def snapshot(self) -> dict:
        """
        Return a diagnostics snapshot of current WebSocket connection pressure on
        this worker process, for use in platform-error diagnostics and health checks.

        Includes per-connection age/idle info and OS thread ids so external
        diagnostics can (a) tell a genuinely stuck WS connection apart from a
        normal long-lived one, and (b) attribute a specific OS thread (nlwp entry
        in /proc) to "serving a WebSocket" rather than counting it as untracked.
        """
        now = time.time()
        with self._lock:
            total = sum(len(conns) for conns in self._connections.values())
            user_count = len(self._connections)
            by_channel = dict(self._channel_counts)
        with self._metadata_lock:
            metas = list(self._connection_metadata.values())

        idle_ages = [now - float(m.get('last_activity', now)) for m in metas]
        conn_ages = [now - float(m.get('created_at', now)) for m in metas]
        native_ids = [m['native_id'] for m in metas if m.get('native_id') is not None]
        stale_after = _env_int('WS_IDLE_STALE_S', 180)
        idle_stale_count = sum(1 for age in idle_ages if age >= stale_after)

        budget = self.max_total_connections
        pct_used = round((total / budget) * 100) if budget else 0
        return {
            'worker_pid': os.getpid(),
            'active_total': total,
            'max_total_connections': budget,
            'pct_of_budget_used': pct_used,
            'distinct_users': user_count,
            'by_channel': by_channel,
            'channel_budgets': dict(self.channel_budgets),
            'oldest_connection_age_s': round(max(conn_ages), 1) if conn_ages else 0,
            'max_idle_s': round(max(idle_ages), 1) if idle_ages else 0,
            'idle_stale_count': idle_stale_count,
            'idle_stale_after_s': stale_after,
            'native_ids': native_ids,
        }

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
            with self._lock:
                if user_id not in self._connections:
                    return 0
                connections_copy = list(self._connections[user_id].keys())

            sent_count = 0
            broken_connections = []

            message = {
                'type': event_type,
                'data': data,
                'timestamp': utcnow().isoformat()
            }
            message_json = json.dumps(message)

            for ws in connections_copy:
                try:
                    ws.send(message_json)
                    self.update_activity(ws)
                    sent_count += 1
                except Exception as e:
                    logger.debug(
                        "[WS_POOL] send failed user=%s error=%s",
                        user_id, e,
                    )
                    broken_connections.append(ws)

            if broken_connections:
                with self._lock:
                    for ws in broken_connections:
                        if user_id in self._connections and ws in self._connections[user_id]:
                            self._remove_connection_internal(user_id, ws)

            return sent_count
        except Exception as e:
            logger.error(
                "[WS_POOL] unexpected error in send_to_user user=%s: %s",
                user_id, e, exc_info=True,
            )
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
            logger.debug("[WS_POOL] send_to_connection failed: %s", e)
            with self._lock:
                for uid, connections in list(self._connections.items()):
                    if ws in connections:
                        self._remove_connection_internal(uid, ws)
                        break
            return False

    def get_connection_count(self, user_id: int = None) -> int:
        """Get the number of active connections"""
        with self._lock:
            if user_id:
                return len(self._connections.get(user_id, {}))
            return sum(len(conns) for conns in self._connections.values())

    def get_all_user_ids(self) -> set:
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
                        stale_connections.append((metadata['user_id'], ws, metadata.get('channel', 'default')))

            for user_id, ws, channel in stale_connections:
                self._remove_connection_internal(user_id, ws)
                cleaned += 1
                logger.info(
                    "[WS_POOL] stale cleanup: user=%s channel=%s idle>%ss",
                    user_id, channel, max_idle_seconds,
                )

        if cleaned > 0:
            logger.info("[WS_POOL] cleaned up %s stale WebSocket connection(s)", cleaned)

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
    from app.utils.ws_helpers import is_notifications_websocket_enabled

    if not has_app_context() or not is_notifications_websocket_enabled():
        logger.debug("Notifications WebSocket disabled or no app context; skipping notification broadcast")
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
            logger.debug(
                "[WS:notifications] broadcasted notification user=%s connections=%s",
                user_id, sent_count,
            )
        return sent_count > 0
    except Exception as e:
        logger.error(
            "[WS:notifications] broadcast notification failed user=%s: %s",
            user_id, e, exc_info=True,
        )
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
    from app.utils.ws_helpers import is_notifications_websocket_enabled

    if not has_app_context() or not is_notifications_websocket_enabled():
        logger.debug("Notifications WebSocket disabled or no app context; skipping unread count broadcast")
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
            logger.debug(
                "[WS:notifications] broadcasted unread_count=%s user=%s connections=%s",
                unread_count, user_id, sent_count,
            )
        return sent_count > 0
    except Exception as e:
        logger.error(
            "[WS:notifications] broadcast unread_count failed user=%s: %s",
            user_id, e, exc_info=True,
        )
        return False
