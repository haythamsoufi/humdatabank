"""
WebSocket endpoint for real-time notifications.

Provides bidirectional communication and prevents blocking the main application thread.
"""

from flask_login import login_required, current_user
from app.utils.constants import SESSION_INACTIVITY_SECONDS, WS_INACTIVITY_STALE_SECONDS
from app.utils.ws_manager import ws_manager
from app.utils.ws_helpers import (
    apply_sock_server_options,
    check_websocket_origin,
    is_notifications_websocket_enabled,
    is_ws_disconnect_error,
    log_ws,
    parse_ws_json,
    release_request_db_session,
)
import json
import logging
import threading
import time
import os

logger = logging.getLogger(__name__)

# Heartbeat interval for notifications WebSocket (shorter than AI WS for responsiveness)
HEARTBEAT_INTERVAL_SECONDS = 15
CHANNEL = "notifications"


def register_notifications_ws(app) -> bool:
    """
    Register WebSocket endpoints for notifications if flask-sock is available.

    We keep this separate so deployments that don't install websocket deps can still run.
    Returns True if the endpoint was registered, False otherwise.
    """
    # Notifications never use WebSocket (HTTP polling only). Do not register the
    # route so cached old JS cannot open a socket and pin a gthread worker.
    # AI chat/docs WS remain controlled by WEBSOCKET_ENABLED alone.
    if not is_notifications_websocket_enabled(app):
        app.logger.debug(
            "Notifications WebSocket disabled (HTTP-only); endpoint not registered"
        )
        return False

    apply_sock_server_options(app)

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
            ok_origin, origin_err = check_websocket_origin(channel=CHANNEL)
            if not ok_origin:
                return {"error": origin_err or "Origin not allowed"}, 403

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
                                log_ws(logging.DEBUG, CHANNEL, "pong send failed", user=user_id, error=str(e))
                                break
                    except Exception as e:
                        log_ws(logging.DEBUG, CHANNEL, "heartbeat loop failed", user=user_id, error=str(e))
                        break

            heartbeat_thread = threading.Thread(target=send_heartbeat, daemon=True)
            heartbeat_thread.start()

            try:
                connection_added = ws_manager.add_connection(user_id, ws, channel=CHANNEL)
                if not connection_added:
                    try:
                        ws.send(json.dumps({
                            "type": "error",
                            "data": {"message": "Connection limit exceeded. Please close other tabs and try again."},
                        }))
                    except Exception as e:
                        log_ws(logging.DEBUG, CHANNEL, "limit error send failed", user=user_id, error=str(e))
                    return ""

                from app.services.notification.service import NotificationService
                initial_unread_count = NotificationService.get_unread_count(user_id)
                # Long-lived WS must not hold a DB pool connection after the handshake query.
                release_request_db_session(reason="notifications_ws_gevent_handshake")

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
                    log_ws(logging.DEBUG, CHANNEL, "connected/unread send failed", user=user_id, error=str(e))
                    return ""

                log_ws(logging.INFO, CHANNEL, "connected", user=user_id, mode="gevent")

                while not cancelled.is_set():
                    try:
                        raw = ws.receive()
                        if not raw:
                            if time.time() - last_activity > SESSION_INACTIVITY_SECONDS:
                                log_ws(logging.INFO, CHANNEL, "closing stale connection", user=user_id)
                                break
                            continue

                        payload, err = parse_ws_json(raw, channel=CHANNEL)
                        if err or not payload:
                            continue

                        msg_type = payload.get("type", "")
                        last_activity = time.time()
                        if msg_type == "ping":
                            try:
                                ws.send(json.dumps({"type": "pong"}))
                            except Exception as e:
                                log_ws(logging.DEBUG, CHANNEL, "pong send failed", user=user_id, error=str(e))
                                break
                    except Exception as e:
                        if is_ws_disconnect_error(e):
                            log_ws(logging.DEBUG, CHANNEL, "recv loop closed", user=user_id, error=str(e))
                        else:
                            log_ws(logging.WARNING, CHANNEL, "recv loop failed", user=user_id, error=str(e), exc_info=True)
                        break
            finally:
                cancelled.set()
                if connection_added:
                    ws_manager.remove_connection(user_id, ws)
                release_request_db_session(reason="notifications_ws_gevent_cleanup")
                log_ws(logging.INFO, CHANNEL, "disconnected", user=user_id, mode="gevent")

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
        ok_origin, origin_err = check_websocket_origin(channel=CHANNEL)
        if not ok_origin:
            try:
                ws.send(json.dumps({
                    "type": "error",
                    "data": {"message": origin_err or "Origin not allowed", "error_type": "origin_rejected"},
                }))
            except Exception:
                pass
            return

        user_id = current_user.id
        connection_added = False

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
                            log_ws(logging.DEBUG, CHANNEL, "pong send failed", user=user_id, error=str(e))
                            break
                except Exception as e:
                    log_ws(logging.DEBUG, CHANNEL, "heartbeat loop failed", user=user_id, error=str(e))
                    break

        heartbeat_thread = threading.Thread(target=send_heartbeat, daemon=True)
        heartbeat_thread.start()

        try:
            connection_added = ws_manager.add_connection(user_id, ws, channel=CHANNEL)
            if not connection_added:
                ws.send(json.dumps({
                    'type': 'error',
                    'data': {
                        'message': 'Connection limit exceeded. Please close other tabs and try again.'
                    }
                }))
                return

            from app.services.notification.service import NotificationService
            initial_unread_count = NotificationService.get_unread_count(user_id)
            # Critical: release the request-scoped DB session so idle notification
            # sockets do not pin a pool connection for the connection lifetime.
            release_request_db_session(reason="notifications_ws_handshake")

            try:
                ws.send(json.dumps({
                    'type': 'connected',
                    'data': {
                        'message': 'WebSocket connection established',
                        'user_id': user_id,
                        'unread_count': initial_unread_count
                    }
                }))

                ws_manager.send_to_connection(ws, 'unread_count', {
                    'type': 'unread_count_update',
                    'unread_count': initial_unread_count
                })
            except Exception as send_error:
                if is_ws_disconnect_error(send_error):
                    log_ws(logging.DEBUG, CHANNEL, "closed before handshake send", user=user_id)
                    return
                log_ws(
                    logging.WARNING,
                    CHANNEL,
                    "handshake send failed",
                    user=user_id,
                    error=str(send_error),
                    exc_info=True,
                )
                raise

            log_ws(logging.INFO, CHANNEL, "connected", user=user_id)

            while not cancelled.is_set():
                try:
                    raw = ws.receive()

                    if not raw:
                        if time.time() - last_activity > SESSION_INACTIVITY_SECONDS:
                            log_ws(logging.INFO, CHANNEL, "closing stale connection", user=user_id)
                            break
                        continue

                    payload, err = parse_ws_json(raw, channel=CHANNEL)
                    if err or not payload:
                        continue

                    msg_type = payload.get("type", "")
                    last_activity = time.time()

                    if msg_type == "ping":
                        ws.send(json.dumps({"type": "pong"}))
                        continue

                    log_ws(logging.DEBUG, CHANNEL, "unknown message type", user=user_id, msg_type=msg_type)

                except Exception as e:
                    if is_ws_disconnect_error(e):
                        log_ws(logging.DEBUG, CHANNEL, "connection closed", user=user_id, error=str(e))
                        break

                    if time.time() - last_activity > SESSION_INACTIVITY_SECONDS:
                        log_ws(logging.INFO, CHANNEL, "closing stale connection", user=user_id)
                        break

                    log_ws(
                        logging.WARNING,
                        CHANNEL,
                        "receive error",
                        user=user_id,
                        error=str(e),
                        exc_info=True,
                    )
                    time.sleep(0.1)
                    continue

        except Exception as e:
            if is_ws_disconnect_error(e):
                log_ws(logging.DEBUG, CHANNEL, "session ended", user=user_id, error=str(e))
            else:
                log_ws(
                    logging.ERROR,
                    CHANNEL,
                    "handler error",
                    user=user_id,
                    error=str(e),
                    exc_info=True,
                )
        finally:
            cancelled.set()
            if connection_added:
                ws_manager.remove_connection(user_id, ws)
            release_request_db_session(reason="notifications_ws_cleanup")
            log_ws(logging.INFO, CHANNEL, "disconnected", user=user_id)

    return True
