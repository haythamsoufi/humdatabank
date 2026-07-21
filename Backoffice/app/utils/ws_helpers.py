"""
Shared WebSocket helpers for Flask-Sock endpoints.

Centralizes origin checks, inbound control-plane pumping (so cancel/ping work
during long-running generation), DB session release for long-lived connections,
JSON size guards, and consistent structured logging.
"""
from __future__ import annotations

import json
import logging
import os
import queue
import threading
from typing import Any, Callable, Optional, Tuple
from urllib.parse import urlparse

from flask import current_app, has_app_context, has_request_context, request

logger = logging.getLogger(__name__)

try:
    from simple_websocket.errors import ConnectionClosed
except ImportError:  # pragma: no cover
    ConnectionClosed = None  # type: ignore[misc, assignment]

# Default max inbound JSON payload (bytes). Oversized frames are rejected before parse.
DEFAULT_WS_MAX_MESSAGE_BYTES = 256 * 1024

_REDIS_CLIENT = None
_REDIS_LOCK = threading.Lock()
_REDIS_FAILED = False


def is_notifications_websocket_enabled(app=None) -> bool:
    """
    Notification (bell) WebSockets are permanently disabled.

    Badge/list use HTTP polling only so idle tabs cannot pin gthread workers.
    AI chat/docs WebSockets remain gated solely by ``WEBSOCKET_ENABLED``.
    Always returns False so route registration, layout inject, and broadcasts
    stay off — including for clients still running cached JS that tries to connect.
    """
    return False


def is_ws_disconnect_error(exc: BaseException) -> bool:
    """True when the exception indicates a normal/expected client disconnect."""
    if ConnectionClosed is not None and isinstance(exc, ConnectionClosed):
        return True
    s = str(exc).lower()
    return any(
        token in s
        for token in (
            "closed",
            "disconnect",
            "broken",
            "1000",
            "1001",
            "1005",
            "1006",
            "connection reset",
        )
    )


def log_ws(
    level: int,
    channel: str,
    message: str,
    *args: Any,
    exc_info: bool = False,
    **ctx: Any,
) -> None:
    """Structured WebSocket log line: ``[WS:channel] message key=val ...``."""
    extras = " ".join(f"{k}={v}" for k, v in ctx.items() if v is not None)
    prefix = f"[WS:{channel}]"
    full = f"{prefix} {message}" + (f" {extras}" if extras else "")
    logger.log(level, full, *args, exc_info=exc_info)


def release_request_db_session(*, reason: str = "ws_idle") -> None:
    """
    Return the request-scoped SQLAlchemy session/connection to the pool.

    Flask-Sock handlers keep a single request context for the whole connection
    lifetime, so ``after_request`` / ``teardown_request`` only run on disconnect.
    Idle notification sockets would otherwise hold a pool connection indefinitely.
    """
    if not has_app_context():
        return
    try:
        from app.extensions import db
        from app.utils.transactions import safe_remove

        safe_remove(reason=reason)
    except Exception as e:
        logger.debug("[WS] release_request_db_session(%s) failed: %s", reason, e)


def _allowed_ws_origins() -> list[str]:
    origins: list[str] = []
    if has_app_context():
        cfg = current_app.config.get("CORS_ALLOWED_ORIGINS") or []
        if isinstance(cfg, (list, tuple)):
            origins.extend(str(o).strip() for o in cfg if str(o).strip())
        elif isinstance(cfg, str) and cfg.strip():
            origins.extend(o.strip() for o in cfg.split(",") if o.strip())
    env = os.environ.get("CORS_ALLOWED_ORIGINS", "")
    if env:
        origins.extend(o.strip() for o in env.split(",") if o.strip())
    # Deduplicate preserving order
    seen = set()
    out = []
    for o in origins:
        key = o.rstrip("/")
        if key not in seen:
            seen.add(key)
            out.append(o)
    return out


def check_websocket_origin(*, channel: str = "default") -> Tuple[bool, Optional[str]]:
    """
    Defense-in-depth Origin check for browser WebSocket upgrades.

    - Missing Origin: allow (native/mobile clients, some proxies).
    - Origin host matches request host: allow (same-origin).
    - Origin listed in CORS_ALLOWED_ORIGINS: allow.
    - Otherwise: reject.
    """
    if not has_request_context():
        return True, None
    origin = (request.headers.get("Origin") or "").strip()
    if not origin:
        return True, None

    try:
        origin_host = (urlparse(origin).netloc or "").lower()
    except Exception:
        origin_host = ""
    request_host = (request.host or "").lower()
    if origin_host and request_host and origin_host == request_host:
        return True, None

    allowed = _allowed_ws_origins()
    origin_norm = origin.rstrip("/")
    for allowed_origin in allowed:
        if origin_norm == allowed_origin.rstrip("/"):
            return True, None

    log_ws(
        logging.WARNING,
        channel,
        "origin rejected",
        origin=origin,
        request_host=request_host,
        allowed_count=len(allowed),
    )
    return False, "Origin not allowed"


def ws_max_message_bytes() -> int:
    if has_app_context():
        try:
            return int(current_app.config.get("WS_MAX_MESSAGE_BYTES", DEFAULT_WS_MAX_MESSAGE_BYTES))
        except (TypeError, ValueError):
            pass
    return DEFAULT_WS_MAX_MESSAGE_BYTES


def parse_ws_json(
    raw: Any,
    *,
    channel: str = "default",
    max_bytes: Optional[int] = None,
) -> Tuple[Optional[dict], Optional[str]]:
    """Parse inbound WS payload with a hard size limit. Returns (payload, error)."""
    if raw is None:
        return None, "empty"
    if isinstance(raw, (bytes, bytearray)):
        size = len(raw)
        text = raw.decode("utf-8", errors="replace")
    else:
        text = str(raw)
        size = len(text.encode("utf-8", errors="replace"))

    limit = max_bytes if max_bytes is not None else ws_max_message_bytes()
    if size > limit:
        log_ws(
            logging.WARNING,
            channel,
            "message too large",
            size=size,
            limit=limit,
        )
        return None, "Message too large"

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        log_ws(logging.WARNING, channel, "invalid JSON", size=size)
        return None, "Invalid JSON"
    if not isinstance(payload, dict):
        return None, "Invalid JSON object"
    return payload, None


def get_ws_redis_client():
    """Cached Redis client for WS rate limiting (shared across calls)."""
    global _REDIS_CLIENT, _REDIS_FAILED
    if _REDIS_FAILED:
        return None
    if _REDIS_CLIENT is not None:
        return _REDIS_CLIENT
    with _REDIS_LOCK:
        if _REDIS_FAILED:
            return None
        if _REDIS_CLIENT is not None:
            return _REDIS_CLIENT
        if not has_app_context():
            return None
        url = current_app.config.get("REDIS_URL")
        if not url:
            _REDIS_FAILED = True
            return None
        try:
            import redis as _redis_lib

            _REDIS_CLIENT = _redis_lib.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            return _REDIS_CLIENT
        except Exception as e:
            logger.warning("[WS] Redis client init failed (fail-open): %s", e, exc_info=True)
            _REDIS_FAILED = True
            return None


def reset_ws_redis_client_for_tests() -> None:
    """Test helper to clear the cached Redis client."""
    global _REDIS_CLIENT, _REDIS_FAILED
    with _REDIS_LOCK:
        _REDIS_CLIENT = None
        _REDIS_FAILED = False


class WsInboundPump:
    """
    Single-threaded inbound reader that keeps consuming while generation runs.

    Ping/cancel are handled immediately on the reader thread so cancel works
    during long ``engine.run()`` / LLM streams. Application messages are queued
    for the main handler.
    """

    _SENTINEL = object()

    def __init__(
        self,
        ws,
        closed: threading.Event,
        *,
        channel: str = "default",
        on_activity: Optional[Callable[[], None]] = None,
        on_cancel: Optional[Callable[[], None]] = None,
        control_types: Optional[set[str]] = None,
    ):
        self.ws = ws
        # Set only on disconnect / stop — never on a soft cancel.
        self.closed = closed
        self.channel = channel
        self.on_activity = on_activity
        self.on_cancel = on_cancel
        self.control_types = control_types or {"ping", "cancel"}
        self._queue: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.disconnected = threading.Event()

    def _signal_disconnect(self) -> None:
        self.closed.set()
        self.disconnected.set()
        if self.on_cancel:
            try:
                self.on_cancel()
            except Exception as e:
                logger.debug("[WS:%s] on_cancel (disconnect) failed: %s", self.channel, e)

    def _signal_cancel(self) -> None:
        if self.on_cancel:
            try:
                self.on_cancel()
            except Exception as e:
                logger.debug("[WS:%s] on_cancel failed: %s", self.channel, e)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._loop,
            name=f"ws-inbound-{self.channel}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.closed.set()

    def get(self, timeout: Optional[float] = None) -> Any:
        """
        Block for the next application message.

        Returns:
            dict payload, or None when the connection closed / pump stopped.
        """
        try:
            item = self._queue.get(timeout=timeout)
        except queue.Empty:
            return self._SENTINEL  # timeout marker — caller distinguishes
        if item is self._SENTINEL:
            return None
        return item

    def get_message(self, timeout: Optional[float] = None) -> Optional[dict]:
        """Like get(), but returns None on timeout or disconnect (no sentinel)."""
        try:
            item = self._queue.get(timeout=timeout if timeout is not None else None)
        except queue.Empty:
            return None
        if item is self._SENTINEL:
            return None
        return item if isinstance(item, dict) else None

    def wait_message(self, *, idle_timeout: float) -> Tuple[Optional[dict], str]:
        """
        Wait for an application message.

        Returns (payload, status) where status is ``ok`` | ``timeout`` | ``closed``.
        """
        if self.disconnected.is_set() or self._stop.is_set():
            return None, "closed"
        try:
            item = self._queue.get(timeout=idle_timeout)
        except queue.Empty:
            return None, "timeout"
        if item is self._SENTINEL:
            return None, "closed"
        if isinstance(item, dict):
            return item, "ok"
        return None, "closed"

    def _touch(self) -> None:
        if self.on_activity:
            try:
                self.on_activity()
            except Exception as e:
                logger.debug("[WS:%s] on_activity failed: %s", self.channel, e)

    def _loop(self) -> None:
        # Keep reading after cancel so a subsequent user_message can arrive on
        # persistent connections. Only stop/disconnect ends the pump.
        while not self._stop.is_set():
            try:
                raw = self.ws.receive(timeout=0.5)
            except StopIteration:
                # Mock / exhausted iterator — treat as disconnect.
                self._signal_disconnect()
                self._queue.put(self._SENTINEL)
                break
            except Exception as e:
                if is_ws_disconnect_error(e):
                    log_ws(logging.DEBUG, self.channel, "inbound closed", error=str(e))
                else:
                    log_ws(
                        logging.WARNING,
                        self.channel,
                        "inbound receive error",
                        error=str(e),
                        exc_info=True,
                    )
                self._signal_disconnect()
                self._queue.put(self._SENTINEL)
                break

            if raw is None:
                if not getattr(self.ws, "connected", True):
                    self._signal_disconnect()
                    self._queue.put(self._SENTINEL)
                    break
                continue

            self._touch()
            payload, err = parse_ws_json(raw, channel=self.channel)
            if err:
                # Surface parse errors to the main loop as synthetic errors when useful
                if err != "empty":
                    self._queue.put({"type": "_parse_error", "message": err})
                continue

            msg_type = str(payload.get("type") or "").strip().lower()
            if msg_type == "ping":
                try:
                    self.ws.send(json.dumps({"type": "pong"}))
                except Exception as e:
                    if is_ws_disconnect_error(e):
                        self._signal_disconnect()
                        self._queue.put(self._SENTINEL)
                        break
                    log_ws(
                        logging.WARNING,
                        self.channel,
                        "pong send failed",
                        error=str(e),
                    )
                continue

            if msg_type == "cancel":
                log_ws(logging.INFO, self.channel, "cancel requested")
                self._signal_cancel()
                try:
                    self.ws.send(json.dumps({"type": "cancelled"}))
                except Exception as e:
                    if is_ws_disconnect_error(e):
                        self._signal_disconnect()
                        self._queue.put(self._SENTINEL)
                        break
                    log_ws(
                        logging.DEBUG,
                        self.channel,
                        "cancelled ack send failed",
                        error=str(e),
                    )
                continue

            # Application message
            self._queue.put(payload)

        self.disconnected.set()


def apply_sock_server_options(app) -> None:
    """Ensure Flask-Sock enforces a max inbound message size."""
    existing = dict(app.config.get("SOCK_SERVER_OPTIONS") or {})
    if "max_message_size" not in existing:
        try:
            existing["max_message_size"] = int(
                app.config.get("WS_MAX_MESSAGE_BYTES", DEFAULT_WS_MAX_MESSAGE_BYTES)
            )
        except (TypeError, ValueError):
            existing["max_message_size"] = DEFAULT_WS_MAX_MESSAGE_BYTES
    app.config["SOCK_SERVER_OPTIONS"] = existing
