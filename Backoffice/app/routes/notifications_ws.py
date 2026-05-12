"""
WebSocket endpoint for real-time notifications.

Provides bidirectional communication and prevents blocking the main application thread.
"""

from flask import current_app
from flask_login import login_required, current_user
from app.utils.constants import SESSION_INACTIVITY_SECONDS, WS_INACTIVITY_STALE_SECONDS
from app.utils.ws_manager import ws_manager
import json
import logging
import threading
import time
import os

logger = logging.getLogger(__name__)

# Heartbeat interval for notifications WebSocket (shorter than AI WS for responsiveness)
HEARTBEAT_INTERVAL_SECONDS = 15


def register_notifications_ws(app) -> bool:
    """
    Register WebSocket endpoints for notifications if flask-sock is available.

    We keep this separate so deployments that don't install websocket deps can still run.
    Returns True if the endpoint was registered, False otherwise.
    """
    # Check if WebSocket is enabled
    if not app.config.get('WEBSOCKET_ENABLED', True):
        app.logger.debug("WebSocket disabled; Notifications WebSocket endpoint not registered")
        return False

    # ------------------------------------------------------------------
    # Windows/gevent dev server path (avoid simple-websocket threads)
    # ------------------------------------------------------------------
    # Flask-Sock uses `simple-websocket`, which uses a background thread for recv().
    # Under gevent's WSGI server, the underlying socket is a gevent socket; calling
    # gevent socket recv() from a different OS thread can crash with:
    #   greenlet.error: Cannot switch to a different thread
    #
    # When running the gevent dev server (`USE_GEVENT_DEV=true` + `python run.py`),
    # use gevent-websocket directly instead (no thread-based recv loop).
    use_gevent_dev = os.environ.get("USE_GEVENT_DEV", "false").strip().lower() == "true" or os.environ.get("USE_GEVENT", "false").strip().lower() == "true"
    gevent_ws_available = False
    try:
        import geventwebsocket  # type: ignore  # noqa: F401
        gevent_ws_available = True
    except Exception as e:
        logger.debug("geventwebsocket import failed: %s", e)
        gevent_ws_available = False

    if use_gevent_dev and gevent_ws_available:
        from flask import request

        @app.route("/api/notifications/ws")
        @login_required
        def notifications_ws_gevent():  # type: ignore
            ws = request.environ.get("wsgi.websocket")
            if ws is None:
                return {"error": "WebSocket upgrade required"}, 400

            user_id = current_user.id
            connection_added = False
            cancelled = threading.Event()
            last_activity = time.time()

            def send_heartbeat():
                while not cancelled.is_set():
                    try:
                        time.sleep(HEARTBEAT_INTERVAL_SECONDS)
                        if cancelled.is_set():
                            break
                        if time.time() - last_activity < WS_INACTIVITY_STALE_SECONDS:
                            try:
                                ws.send(json.dumps({"type": "pong"}))
                            except Exception as e:
                                logger.debug("WS pong send failed: %s", e)
                                break
                    except Exception as e:
                        logger.debug("heartbeat loop failed: %s", e)
                        break

            heartbeat_thread = threading.Thread(target=send_heartbeat, daemon=True)
            heartbeat_thread.start()

            try:
                connection_added = ws_manager.add_connection(user_id, ws)
                if not connection_added:
                    try:
                        ws.send(json.dumps({
                            "type": "error",
                            "data": {"message": "Connection limit exceeded. Please close other tabs and try again."},
                        }))
                    except Exception as e:
                        logger.debug("WS connection limit error send failed: %s", e)
                    return ""

                from app.services.notification.service import NotificationService
                initial_unread_count = NotificationService.get_unread_count(user_id)

                try:
                    ws.send(json.dumps({
                        "type": "connected",
                        "data": {
                            "message": "WebSocket connection established",
                            "user_id": user_id,
                            "unread_count": initial_unread_count,
                        },
                    }))

                    ws_manager.send_to_connection(ws, "unread_count", {
                        "type": "unread_count_update",
                        "unread_count": initial_unread_count,
                    })
                except Exception as e:
                    logger.debug("WS connected/unread send failed: %s", e)
                    return ""

                while not cancelled.is_set():
                    try:
                        raw = ws.receive()
                        if not raw:
                            if time.time() - last_activity > SESSION_INACTIVITY_SECONDS:
                                logger.info(f"Closing stale WebSocket connection for user {user_id}")
                                break
                            continue

                        try:
                            payload = json.loads(raw)
                        except json.JSONDecodeError:
                            continue

                        msg_type = payload.get("type", "")
                        last_activity = time.time()
                        if msg_type == "ping":
                            try:
                                ws.send(json.dumps({"type": "pong"}))
                            except Exception as e:
                                logger.debug("WS pong send failed: %s", e)
                                break
                    except Exception as e:
                        logger.debug("WS recv loop failed: %s", e)
                        break
            finally:
                cancelled.set()
                if connection_added:
                    ws_manager.remove_connection(user_id, ws)

            return ""

        app.logger.info("Notifications WebSocket endpoint registered (gevent-websocket)")
        return True

    # ------------------------------------------------------------------
    # Default path (Flask-Sock / simple-websocket)
    # ------------------------------------------------------------------
    try:
        from flask_sock import Sock
    except Exception as e:
        app.logger.warning("flask-sock not installed; Notifications WebSocket endpoint disabled: %s", e)
        return False

    sock = Sock(app)

    @sock.route("/api/notifications/ws")
    @login_required
    def notifications_ws(ws):
        """
        WebSocket endpoint for real-time notifications.

        Protocol:
        - Client can send: {"type": "ping"} for heartbeat
        - Server sends: {"type": "notification", "data": {...}} for new notifications
        - Server sends: {"type": "unread_count", "data": {"unread_count": N}} for count updates
        - Server sends: {"type": "pong"} in response to ping

        Connection is automatically cleaned up on disconnect.
        Uses non-blocking operations to prevent hanging the main app.
        """
        user_id = current_user.id
        connection_added = False

        # Cancel flag for graceful shutdown
        cancelled = threading.Event()
        last_activity = time.time()

        def send_heartbeat():
            """Send periodic heartbeat to keep connection alive"""
            while not cancelled.is_set():
                try:
                    time.sleep(HEARTBEAT_INTERVAL_SECONDS)
                    if cancelled.is_set():
                        break
                    if time.time() - last_activity < WS_INACTIVITY_STALE_SECONDS:
                        try:
                            ws.send(json.dumps({"type": "pong"}))
                        except Exception as e:
                            logger.debug("WS pong send failed: %s", e)
                            break
                except Exception as e:
                    logger.debug("heartbeat loop failed: %s", e)
                    break

        # Start heartbeat thread (daemon so it doesn't block shutdown)
        heartbeat_thread = threading.Thread(target=send_heartbeat, daemon=True)
        heartbeat_thread.start()

        try:
            # Register this connection
            connection_added = ws_manager.add_connection(user_id, ws)
            if not connection_added:
                # Connection limit exceeded
                ws.send(json.dumps({
                    'type': 'error',
                    'data': {
                        'message': 'Connection limit exceeded. Please close other tabs and try again.'
                    }
                }))
                return

            # Send initial connection message with unread count
            from app.services.notification.service import NotificationService
            initial_unread_count = NotificationService.get_unread_count(user_id)

            try:
                ws.send(json.dumps({
                    'type': 'connected',
                    'data': {
                        'message': 'WebSocket connection established',
                        'user_id': user_id,
                        'unread_count': initial_unread_count
                    }
                }))

                # Also send as unread_count message for consistency
                from app.utils.ws_manager import broadcast_unread_count
                ws_manager.send_to_connection(ws, 'unread_count', {
                    'type': 'unread_count_update',
                    'unread_count': initial_unread_count
                })
            except Exception as send_error:
                # Connection was closed before we could send initial message
                error_str = str(send_error).lower()
                if "closed" in error_str or "1005" in str(send_error) or "1006" in str(send_error):
                    return
                raise

            # Main message loop - handle incoming messages (pings, etc.)
            # Note: ws.receive() may block, but flask-sock handles this at the WSGI level
            # We use daemon threads and proper error handling to prevent hanging
            while not cancelled.is_set():
                try:
                    # flask-sock's receive() blocks until a message is received
                    # This is handled by the WSGI server's async capabilities
                    # We add timeout checks and error handling to prevent issues
                    raw = ws.receive()

                    if not raw:
                        # Check if connection is stale
                        if time.time() - last_activity > 300:  # 5 minutes of inactivity
                            logger.info(f"Closing stale WebSocket connection for user {user_id}")
                            break
                        continue

                    # Parse incoming message
                    try:
                        payload = json.loads(raw)
                        msg_type = payload.get("type", "")
                        last_activity = time.time()

                        # Handle ping
                        if msg_type == "ping":
                            ws.send(json.dumps({"type": "pong"}))
                            continue

                        # Unknown message type - just acknowledge
                        logger.debug(f"Received unknown message type from user {user_id}: {msg_type}")

                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON received from user {user_id}: {raw[:100]}")
                        continue

                except Exception as e:
                    # Check if it's a connection error (connection closed)
                    error_str = str(e).lower()
                    if "closed" in error_str or "disconnect" in error_str or "broken" in error_str:
                        break

                    # Check if connection is stale
                    if time.time() - last_activity > 300:
                        logger.info(f"Closing stale WebSocket connection for user {user_id}")
                        break

                    # For other errors, log and continue (connection might still be alive)
                    logger.debug(f"Error in WebSocket receive for user {user_id}: {str(e)}")
                    # Small delay to prevent tight loop on errors
                    time.sleep(0.1)
                    continue

        except Exception as e:
            error_str = str(e).lower()
            # Don't log connection closed as an error - it's expected behavior
            if "closed" in error_str or "disconnect" in error_str or "1005" in str(e) or "1006" in str(e):
                pass
            else:
                logger.error(f"Error in notifications WebSocket for user {user_id}: {str(e)}", exc_info=True)
        finally:
            # Clean up connection
            cancelled.set()  # Stop heartbeat
            if connection_added:
                ws_manager.remove_connection(user_id, ws)

    return True
