from __future__ import annotations

from collections import deque
import json
import logging
import time
import uuid
import threading
from typing import Any, Callable, Dict, Optional, Tuple

from sqlalchemy.orm.attributes import flag_modified

try:
    from simple_websocket.errors import ConnectionClosed
except ImportError:
    ConnectionClosed = None  # type: ignore[misc, assignment]

from flask import current_app, g, request
from flask_login import current_user, login_user, logout_user
from flask import session

from app.extensions import db
from app.models.ai_chat import AIConversation, AIMessage
from app.utils.ai_request_user import resolve_ai_identity
from app.utils.ai_utils import openai_model_supports_sampling_params
from app.utils.constants import (
    DAILY_RATE_LIMIT_WINDOW_SECONDS,
    WS_HEARTBEAT_INTERVAL_SECONDS,
    WS_INACTIVITY_STALE_SECONDS,
)
from app.utils.datetime_helpers import utcnow
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE
from app.utils.user_analytics import get_client_ip

from app.routes.ai import _build_access_context, _is_allowed_public_proxy_request

logger = logging.getLogger(__name__)
from app.services.ai_dlp import evaluate_ai_message, log_dlp_audit_event
from app.services.ai_chat_request import (
    parse_chat_request,
    resolve_conversation_and_history,
    get_idempotent_reply,
    apply_anonymous_rules,
    load_conversation_history_for_llm,
    replace_conversation_messages,
)
from app.services.ai_fastpath import try_answer_value_question

# Document RAG (answer endpoint logic, reused for WS streaming)
from app.services.ai_vector_store import AIVectorStore


class QuotaExceededError(Exception):
    """Custom exception for API quota/rate limit errors."""

    def __init__(self, message, retry_delay=None):
        super().__init__(message)
        self.retry_delay = retry_delay


_GLOBAL_WS_RATE_LOCK = threading.Lock()
_GLOBAL_WS_RATE = {}  # key -> deque[timestamps]


def _global_ws_key(identity) -> str:
    """
    Best-effort stable key for WS throttling.
    - Authenticated: per-user
    - Anonymous: per-origin IP
    """
    try:
        if getattr(identity, "is_authenticated", False) and getattr(identity, "user", None) is not None:
            uid = getattr(identity.user, "id", None)
            if uid is not None:
                return f"u:{int(uid)}"
    except Exception as e:
        logger.debug("_global_ws_key identity resolution failed: %s", e)
    # Fallback: trusted client IP resolver (proxy-aware).
    ip = get_client_ip() or request.remote_addr or "unknown"
    return f"ip:{ip}"


def _global_ws_allow_memory(*, key: str, window_seconds: float, max_events: int) -> Optional[float]:
    """In-memory (per-worker) rate limiter. Returns retry_delay if limited, else None."""
    now = time.time()
    with _GLOBAL_WS_RATE_LOCK:
        q = _GLOBAL_WS_RATE.get(key)
        if q is None:
            q = deque()
            _GLOBAL_WS_RATE[key] = q
        while q and (now - q[0]) > window_seconds:
            q.popleft()
        if len(q) >= max_events:
            return float(max(1.0, window_seconds - (now - q[0])))
        q.append(now)
        if len(q) > max_events * 2:
            while len(q) > max_events * 2:
                q.popleft()
    return None


def _global_ws_allow_redis(*, key: str, window_seconds: float, max_events: int) -> Optional[float]:
    """Redis-backed rate limiter (cross-worker). Returns retry_delay if limited, else None. Fail-open on error."""
    try:
        import redis
        redis_url = current_app.config.get("REDIS_URL")
        if not redis_url:
            return None
        r = redis.from_url(redis_url)
        redis_key = f"ai_ws_rate:{key}"
        now = time.time()
        r.zadd(redis_key, {str(now): now})
        r.zremrangebyscore(redis_key, 0, now - window_seconds)
        count = r.zcard(redis_key)
        r.expire(redis_key, int(window_seconds) + 60)
        if count >= max_events:
            oldest = r.zrange(redis_key, 0, 0, withscores=True)
            if oldest:
                retry = max(1.0, window_seconds - (now - oldest[0][1]))
                return float(retry)
        return None
    except Exception as e:
        logger.debug("Redis rate limiter failed (fail-open): %s", e, exc_info=True)
        return None  # fail open


def _global_ws_allow(*, key: str, window_seconds: float, max_events: int) -> Optional[float]:
    """
    Global rate limiter. Uses Redis if REDIS_URL is set (and redis package installed), else in-memory.
    Returns retry_delay seconds if limited, else None.
    """
    if current_app.config.get("REDIS_URL"):
        ret = _global_ws_allow_redis(key=key, window_seconds=window_seconds, max_events=max_events)
        # If Redis failed, ret is None (fail open); otherwise ret is None or retry_delay
        return ret
    return _global_ws_allow_memory(key=key, window_seconds=window_seconds, max_events=max_events)


def _ws_send_json(ws, obj: dict) -> bool:
    """
    Send a JSON message on the WebSocket. Returns True if sent, False if connection already closed.
    Catches ConnectionClosed so we don't log errors when the client has disconnected (e.g. code 1005).
    """
    try:
        ws.send(json.dumps(obj))
        return True
    except Exception as e:
        if ConnectionClosed and isinstance(e, ConnectionClosed):
            current_app.logger.debug("AI ws: client already disconnected (code=%s)", getattr(e, "code", None))
            return False
        raise


def _ws_send_quota_error(ws, *, cancelled: threading.Event, details: str, retry_delay: Any = None) -> None:
    if cancelled.is_set():
        return
    try:
        ws.send(
            json.dumps(
                {
                    "type": "error",
                    "error_type": "quota_exceeded",
                    "message": "API quota exceeded. Please try again later.",
                    "details": details,
                    "retry_delay": retry_delay,
                }
            )
        )
    except Exception as e:
        logger.debug("_ws_send_quota_error failed (client may have disconnected): %s", e)


def _ws_send_retry_status(ws, *, cancelled: threading.Event, retry_delay_seconds: float) -> None:
    if cancelled.is_set():
        return
    try:
        ws.send(
            json.dumps(
                {
                    "type": "status",
                    "message": f"Rate limit reached. Retrying in {int(retry_delay_seconds)} seconds...",
                    "retry_delay": retry_delay_seconds,
                }
            )
        )
    except Exception as e:
        logger.debug("_ws_send_retry_status failed: %s", e)


def _ws_wait_with_cancel(*, seconds: float, cancelled: threading.Event) -> bool:
    """
    Sleep up to `seconds`, checking cancellation periodically.
    Returns True if cancelled was set during the wait.
    """
    wait_interval = 1.0
    waited = 0.0
    while waited < seconds and not cancelled.is_set():
        remaining = max(0.0, seconds - waited)
        time.sleep(min(wait_interval, remaining))
        waited += wait_interval
    return cancelled.is_set()


def _ws_run_with_retries(
    attempt_fn: Callable[[], Any],
    *,
    ws,
    cancelled: threading.Event,
    provider_label: str,
    max_retries: int = 1,
    retry_on_any_exception: bool = False,
) -> Tuple[Any, str]:
    """
    Run attempt_fn with quota-aware retry handling.
    - On QuotaExceededError: optionally wait for retry_delay and retry once.
    - On generic exceptions: retry only if retry_on_any_exception=True.
    Returns (result, outcome) where outcome is one of: "ok" | "quota" | "cancel" | "error".
    """
    retry_count = 0
    while retry_count <= max_retries and not cancelled.is_set():
        try:
            return attempt_fn(), "ok"
        except QuotaExceededError as e:
            current_app.logger.warning("%s quota exceeded (attempt %s): %s", provider_label, retry_count + 1, e)
            retry_delay = getattr(e, "retry_delay", None)
            if retry_delay is not None and retry_count < max_retries:
                try:
                    retry_delay_seconds = float(retry_delay)
                except Exception as e:
                    logger.debug("retry_delay parse failed: %s", e)
                    retry_delay_seconds = 0.0
                if retry_delay_seconds > 0:
                    current_app.logger.info(
                        "Waiting %s seconds before retry (as specified by API)", retry_delay_seconds
                    )
                    _ws_send_retry_status(ws, cancelled=cancelled, retry_delay_seconds=retry_delay_seconds)
                    if _ws_wait_with_cancel(seconds=retry_delay_seconds, cancelled=cancelled):
                        try:
                            ws.send(json.dumps({"type": "cancelled"}))
                        except Exception as e:
                            logger.debug("ws.send cancelled failed: %s", e)
                        return None, "cancel"
                retry_count += 1
                continue

            _ws_send_quota_error(ws, cancelled=cancelled, details="Rate limit exceeded.", retry_delay=retry_delay)
            return None, "quota"
        except Exception as e:
            if retry_on_any_exception and retry_count < max_retries and not cancelled.is_set():
                current_app.logger.warning(
                    "%s request failed (attempt %s): %s", provider_label, retry_count + 1, e
                )
                retry_count += 1
                continue
            if retry_on_any_exception:
                current_app.logger.warning(
                    "%s request failed (final attempt %s): %s", provider_label, retry_count + 1, e
                )
                return None, "error"
            raise
    if cancelled.is_set():
        return None, "cancel"
    return None, "error"


def _ws_exception_looks_like_quota(e: Exception) -> bool:
    error_str = str(e) or ""
    s = error_str.lower()
    return ("429" in error_str) or ("quota" in s) or ("exceeded" in s)


def _persist_ai_conversation_async(
    *,
    app,
    user_id: int,
    conversation_id: str,
    user_message: str,
    assistant_message: str,
    page_context: Dict[str, Any] | None,
    client_message_id: str | None,
    provider: str,
    model: Optional[str],
    function_calls_used: Any,
    map_payload: Optional[Dict[str, Any]],
    chart_payload: Optional[Dict[str, Any]],
    table_payload: Optional[Dict[str, Any]] = None,
    client_meta: str = "unknown",
    skip_user_message: bool = False,
    trace_id: Optional[int] = None,
) -> None:
    """
    Best-effort persistence for WS chat.
    Runs in the caller's thread; failures are logged and ignored.
    When skip_user_message is True (e.g. branch_from_edit), only the assistant message is inserted.
    """
    with app.app_context():
        try:
            convo = AIConversation.query.filter_by(id=conversation_id, user_id=user_id).first()
            if not convo:
                title = (user_message[:80] + "…") if len(user_message) > 80 else user_message
                convo = AIConversation(
                    id=conversation_id,
                    user_id=user_id,
                    title=title,
                    created_at=utcnow(),
                    updated_at=utcnow(),
                    last_message_at=utcnow(),
                    meta={"client": client_meta},
                )
                db.session.add(convo)
            else:
                convo.updated_at = utcnow()
                convo.last_message_at = utcnow()

            # When branch_from_edit, user message was already included in _replace_conversation_messages.
            # In WS flow, we also typically persist the user message immediately on receipt.
            should_insert_user = not skip_user_message
            if should_insert_user and client_message_id:
                existing_user = AIMessage.query.filter_by(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    role="user",
                    client_message_id=client_message_id,
                ).first()
                if existing_user:
                    should_insert_user = False
            elif should_insert_user:
                # Without a client_message_id, avoid duplicating the early-inserted user row.
                should_insert_user = False

            if should_insert_user:
                db.session.add(
                    AIMessage(
                        conversation_id=conversation_id,
                        user_id=user_id,
                        role="user",
                        content=user_message,
                        client_message_id=client_message_id,
                        meta={"page_context": page_context} if page_context else None,
                    )
                )

            assistant_meta: Dict[str, Any] = {
                "provider": provider,
                "model": model,
                "function_calls": function_calls_used,
                **({"map_payload": map_payload} if map_payload else {}),
                **({"chart_payload": chart_payload} if chart_payload else {}),
                **({"table_payload": table_payload} if table_payload else {}),
                **({"in_reply_to_client_message_id": client_message_id} if client_message_id else {}),
            }
            if trace_id is not None:
                assistant_meta["trace_id"] = trace_id
            db.session.add(
                AIMessage(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    role="assistant",
                    content=assistant_message,
                    meta=assistant_meta,
                )
            )
            db.session.commit()
        except Exception as e:
            current_app.logger.exception("Failed to persist AI conversation from WS")
            try:
                db.session.rollback()
            except Exception as e_rb:
                current_app.logger.warning("WS persist rollback failed: %s", e_rb, exc_info=True)
        finally:
            # WS handlers don't get Flask request teardowns; clean up sessions explicitly.
            try:
                db.session.remove()
            except Exception as e:
                logger.debug("db.session.remove failed: %s", e)


def register_ai_ws(app) -> None:
    """
    Register WebSocket endpoints if flask-sock is available.

    We keep this separate so deployments that don't install websocket deps can still run.
    """
    # Note on gevent (Windows/dev):
    # When running `USE_GEVENT_DEV=true` via `python run.py`, WebSocket upgrades must be handled
    # by gevent's WebSocketHandler (from `gevent-websocket`). `Backoffice/run.py` already attempts
    # to do that. We do NOT special-case gevent here; the same flask-sock endpoints are registered.

    try:
        from flask_sock import Sock
    except Exception as e:
        app.logger.warning("flask-sock not installed; AI WebSocket endpoint disabled: %s", e)
        return

    sock = Sock(app)

    @sock.route("/api/ai/v2/ws")
    def ai_ws(ws):
        """
        Mobile-first WebSocket API with improved streaming, heartbeat, and cancel support.

        Protocol:
        - Client sends JSON messages:
          {
            "type": "user_message",
            "message": "...",
            "conversation_id": "uuid(optional)",
            "preferred_language": "en",
            "page_context": {...},
            "client": "mobile"|"website"|"backoffice"
          }
          OR
          {
            "type": "cancel"  // Cancel current generation
          }
          OR
          {
            "type": "ping"  // Heartbeat ping
          }
        - Server replies with:
          {"type":"meta", ...}
          {"type":"delta","text":"..."} repeated (streaming)
          {"type":"done","conversation_id":"..."}
          OR
          {"type":"pong"}  // Heartbeat response
          OR
          {"type":"cancelled"}  // Generation cancelled
        """
        identity = resolve_ai_identity()
        try:
            from app.utils.app_settings import is_ai_beta_restricted, user_has_ai_beta_access

            if is_ai_beta_restricted():
                if not getattr(identity, "is_authenticated", False) or not getattr(identity, "user", None):
                    try:
                        ws.send(json.dumps({"type": "error", "message": "AI beta access is limited to selected users.", "error_type": "auth_required"}))
                    except Exception as e:
                        logger.debug("ws.send beta auth-required failed (client disconnected): %s", e)
                    return
                if not user_has_ai_beta_access(identity.user):
                    try:
                        ws.send(json.dumps({"type": "error", "message": "AI beta access is limited to selected users.", "error_type": "forbidden"}))
                    except Exception as e:
                        logger.debug("ws.send beta forbidden failed (client disconnected): %s", e)
                    return
        except Exception as e:
            logger.debug("AI WebSocket beta gate check failed: %s", e, exc_info=True)
        # Anonymous access is only allowed via the Website proxy (shared-secret header), matching HTTP/SSE policy.
        if not getattr(identity, "is_authenticated", False) and not _is_allowed_public_proxy_request():
            try:
                ws.send(json.dumps({"type": "error", "message": "Authentication required", "error_type": "auth_required"}))
            except Exception as e:
                logger.debug("ws.send auth error failed (client disconnected): %s", e)
            return
        # Ensure RBAC helpers (which use current_user) work for Bearer auth
        did_login = False
        try:
            if identity.user and getattr(identity, "auth_source", "") == "bearer" and not current_user.is_authenticated:
                login_user(identity.user, remember=False)
                did_login = True
                # Avoid emitting a session cookie for bearer-token clients.
                try:
                    session.modified = False
                except Exception as sess_e:
                    logger.debug("session.modified = False failed: %s", sess_e)
        except Exception as e:
            current_app.logger.warning(
                "AI WebSocket: failed to attach bearer-auth identity to flask-login session: %s",
                e,
                exc_info=True,
            )

        # Cancel flag for aborting generation
        cancelled = threading.Event()
        # Last activity timestamp for heartbeat
        last_activity = time.time()

        # Basic per-connection rate limiting (WS decorators don't apply here).
        # This protects the LLM providers + DB from message floods.
        ws_window_seconds = 60.0
        try:
            ws_max_per_min = int(current_app.config.get("AI_WS_MAX_MESSAGES_PER_MINUTE", 30))
        except Exception as e:
            logger.debug("AI_WS_MAX_MESSAGES_PER_MINUTE parse failed: %s", e)
            ws_max_per_min = 30  # fallback when config is invalid
        recent_user_msgs = deque()

        def _ws_allow_user_message() -> Optional[float]:
            """
            Returns retry_delay seconds if rate-limited, else None.
            """
            now = time.time()
            while recent_user_msgs and (now - recent_user_msgs[0]) > ws_window_seconds:
                recent_user_msgs.popleft()
            if len(recent_user_msgs) >= ws_max_per_min:
                retry = max(1.0, ws_window_seconds - (now - recent_user_msgs[0]))
                return float(retry)
            recent_user_msgs.append(now)
            return None

        def send_heartbeat():
            """Send periodic heartbeat to keep connection alive"""
            while not cancelled.is_set():
                try:
                    time.sleep(WS_HEARTBEAT_INTERVAL_SECONDS)
                    if time.time() - last_activity < 60:  # Only if connection is active
                        ws.send(json.dumps({"type": "ping"}))
                except Exception as e:
                    logger.debug("Heartbeat send failed: %s", e)
                    break

        # Start heartbeat thread
        heartbeat_thread = threading.Thread(target=send_heartbeat, daemon=True)
        heartbeat_thread.start()

        user_id_log = getattr(getattr(identity, "user", None), "id", "anon")
        current_app.logger.info("AI WebSocket: connection accepted user_id=%s", user_id_log)

        try:
            # Main message loop
            # Note: ws.receive() may block, but flask-sock handles this at the WSGI level
            # We use daemon threads and proper error handling to prevent hanging the main app
            while True:
                try:
                    # flask-sock's receive() blocks until a message is received
                    # This is handled by the WSGI server's async capabilities
                    # We add timeout checks and error handling to prevent issues
                    raw = ws.receive()
                    if not raw:
                        # Check if connection is still alive
                        if time.time() - last_activity > WS_INACTIVITY_STALE_SECONDS:
                            current_app.logger.debug("Closing stale AI WebSocket connection")
                            break
                        continue
                    payload = json.loads(raw)
                except Exception as e:
                    # Check if it's a connection error (connection closed)
                    if "closed" in str(e).lower() or "disconnect" in str(e).lower():
                        break
                    # Check if connection is stale
                    if time.time() - last_activity > WS_INACTIVITY_STALE_SECONDS:
                        break
                    # For other errors, try to send error message (might fail if connection is dead)
                    try:
                        ws.send(json.dumps({"type": "error", "message": "Invalid JSON"}))
                    except Exception as e:
                        logger.debug("ws.send Invalid JSON error failed: %s", e)
                        break
                    continue

                msg_type = payload.get("type", "user_message")
                last_activity = time.time()

                # Handle ping
                if msg_type == "ping":
                    ws.send(json.dumps({"type": "pong"}))
                    continue

                # Handle cancel
                if msg_type == "cancel":
                    cancelled.set()
                    ws.send(json.dumps({"type": "cancelled"}))
                    continue

                # Accept legacy Backoffice format (type "message") as user_message for unified API
                if msg_type == "message":
                    payload["type"] = "user_message"
                    if not payload.get("client"):
                        payload["client"] = "backoffice"
                    msg_type = "user_message"

                # Handle user message
                if msg_type != "user_message":
                    continue

                # Daily quotas (cost control). Uses Redis if REDIS_URL is configured; otherwise per-worker memory.
                # Note: This is independent of the HTTP/SSE daily limiter buckets.
                try:
                    daily_user_limit = int(current_app.config.get("AI_CHAT_DAILY_LIMIT_PER_USER", 20))
                except Exception as e:
                    logger.debug("AI_CHAT_DAILY_LIMIT_PER_USER parse failed: %s", e)
                    daily_user_limit = 20
                try:
                    daily_system_limit = int(current_app.config.get("AI_CHAT_DAILY_LIMIT_PER_SYSTEM", 100))
                except Exception as e:
                    logger.debug("AI_CHAT_DAILY_LIMIT_PER_SYSTEM parse failed: %s", e)
                    daily_system_limit = 100

                is_system_manager = False
                try:
                    if identity.is_authenticated and identity.user:
                        from app.services.authorization_service import AuthorizationService
                        is_system_manager = bool(AuthorizationService.is_system_manager(identity.user))
                except Exception as e:
                    logger.debug("is_system_manager check failed: %s", e)
                    is_system_manager = False

                if (not is_system_manager) and daily_user_limit > 0:
                    daily_user_key = f"day:{_global_ws_key(identity)}"
                    daily_user_retry = _global_ws_allow(
                        key=daily_user_key,
                        window_seconds=float(DAILY_RATE_LIMIT_WINDOW_SECONDS),
                        max_events=daily_user_limit,
                    )
                    if daily_user_retry is not None:
                        try:
                            ws.send(
                                json.dumps(
                                    {
                                        "type": "error",
                                        "error_type": "rate_limited",
                                        "message": "Daily AI limit reached (per user). Please try again tomorrow.",
                                        "retry_delay": float(daily_user_retry),
                                    }
                                )
                            )
                        except Exception as e:
                            logger.debug("ws.send daily user limit error failed: %s", e)
                            break
                        continue

                if daily_system_limit > 0:
                    daily_system_key = "day:system"
                    daily_system_retry = _global_ws_allow(
                        key=daily_system_key,
                        window_seconds=float(DAILY_RATE_LIMIT_WINDOW_SECONDS),
                        max_events=daily_system_limit,
                    )
                    if daily_system_retry is not None:
                        try:
                            ws.send(
                                json.dumps(
                                    {
                                        "type": "error",
                                        "error_type": "rate_limited",
                                        "message": "Daily AI limit reached (system). Please try again tomorrow.",
                                        "retry_delay": float(daily_system_retry),
                                    }
                                )
                            )
                        except Exception as e:
                            logger.debug("ws.send daily system limit error failed: %s", e)
                            break
                        continue

                retry_delay = _ws_allow_user_message()
                if retry_delay is not None:
                    try:
                        ws.send(
                            json.dumps(
                                {
                                    "type": "error",
                                    "error_type": "rate_limited",
                                    "message": "Too many messages. Please wait before sending another message.",
                                    "retry_delay": retry_delay,
                                }
                            )
                        )
                    except Exception as e:
                        logger.debug("ws.send rate limit error failed: %s", e)
                        break
                    continue

                # Global per-user/per-IP limiter (protects against many parallel connections).
                try:
                    global_max = int(current_app.config.get("AI_WS_MAX_MESSAGES_PER_MINUTE_PER_USER", 60))
                except Exception as e:
                    logger.debug("AI_WS_MAX_MESSAGES_PER_MINUTE_PER_USER parse failed: %s", e)
                    global_max = 60
                gkey = _global_ws_key(identity)
                global_retry = _global_ws_allow(key=gkey, window_seconds=60.0, max_events=global_max)
                if global_retry is not None:
                    try:
                        ws.send(
                            json.dumps(
                                {
                                    "type": "error",
                                    "error_type": "rate_limited",
                                    "message": "Too many messages. Please wait before sending another message.",
                                    "retry_delay": global_retry,
                                }
                            )
                        )
                    except Exception as e:
                        logger.debug("ws.send global rate limit error failed: %s", e)
                        break
                    continue

                parsed, err_msg, _ = parse_chat_request(payload)
                if err_msg:
                    try:
                        ws.send(json.dumps({"type": "error", "message": err_msg, "error_type": "validation"}))
                    except Exception as e:
                        logger.debug("ws.send validation error failed: %s", e)
                        break
                    continue

                # DLP guard (must run BEFORE any persistence).
                allow_sensitive = bool(payload.get("allow_sensitive"))
                allowed, dlp_err, dlp_findings = evaluate_ai_message(
                    message=parsed.message,
                    allow_sensitive=allow_sensitive,
                )
                if dlp_findings:
                    log_dlp_audit_event(
                        user_id=(int(identity.user.id) if getattr(identity, "is_authenticated", False) and getattr(identity, "user", None) else None),
                        action=("blocked" if (not allowed and (dlp_err or {}).get("error_type") == "dlp_blocked") else
                                "confirm_required" if (not allowed) else
                                "send_anyway" if allow_sensitive else
                                "allowed"),
                        transport="ws",
                        endpoint_path=(request.path or "/api/ai/v2/ws"),
                        client=str((payload.get("client") or "unknown")),
                        conversation_id=(getattr(parsed, "conversation_id", None) or payload.get("conversation_id")),
                        client_message_id=getattr(parsed, "client_message_id", None),
                        allow_sensitive=allow_sensitive,
                        findings=dlp_findings,
                    )
                if not allowed and dlp_err:
                    # Ensure WS uses the standard streaming envelope: type=error + error_type + dlp object.
                    err_payload = dict(dlp_err)
                    err_payload["type"] = "error"
                    try:
                        ws.send(json.dumps(err_payload))
                    except Exception as e:
                        logger.debug("ws.send DLP error failed: %s", e)
                        break
                    continue

                if not identity.is_authenticated:
                    parsed = apply_anonymous_rules(parsed)
                    conversation_id = None
                    ws_conversation_history = parsed.conversation_history or []
                else:
                    conversation_id, ws_conversation_history = resolve_conversation_and_history(identity, parsed)

                msg = parsed.message
                preferred_language = parsed.preferred_language
                page_context = parsed.page_context
                client_message_id = parsed.client_message_id
                branch_from_edit = parsed.branch_from_edit
                sources_cfg = getattr(parsed, "sources_cfg", None)

                # Ensure conversation exists immediately so immersive sidebar refresh can see it.
                if identity.is_authenticated and identity.user and conversation_id:
                    user_id_raw = getattr(identity.user, "id", None)
                    if user_id_raw is not None:
                        try:
                            user_id = int(user_id_raw)
                            convo = AIConversation.query.filter_by(id=conversation_id, user_id=user_id).first()
                            if not convo:
                                title = (msg[:80] + "…") if len(msg) > 80 else msg
                                client_meta = payload.get("client") or "unknown"
                                if not isinstance(client_meta, str):
                                    client_meta = "unknown"
                                client_meta = client_meta.strip().lower()
                                if client_meta not in {"website", "mobile", "backoffice", "unknown"}:
                                    client_meta = "unknown"
                                convo = AIConversation(
                                    id=conversation_id,
                                    user_id=user_id,
                                    title=title,
                                    created_at=utcnow(),
                                    updated_at=utcnow(),
                                    last_message_at=utcnow(),
                                    meta={"client": client_meta, "source": "ws_init"},
                                )
                                db.session.add(convo)
                                db.session.commit()
                            else:
                                convo.updated_at = utcnow()
                                db.session.commit()
                        except Exception as e:
                            current_app.logger.exception("AI WS: failed to pre-create conversation")
                            try:
                                db.session.rollback()
                            except Exception as rb_e:
                                logger.debug("Session rollback failed: %s", rb_e)

                # Persist the USER message immediately for logged-in users (before generation starts).
                # This matches SSE behavior and makes conversation reload reliable.
                if identity.is_authenticated and identity.user and conversation_id and msg and not branch_from_edit:
                    user_id_raw = getattr(identity.user, "id", None)
                    if user_id_raw is not None:
                        try:
                            user_id = int(user_id_raw)
                            should_insert_user = True
                            if client_message_id:
                                existing_user = AIMessage.query.filter_by(
                                    conversation_id=conversation_id,
                                    user_id=user_id,
                                    role="user",
                                    client_message_id=client_message_id,
                                ).first()
                                if existing_user:
                                    should_insert_user = False
                            if should_insert_user:
                                db.session.add(
                                    AIMessage(
                                        conversation_id=conversation_id,
                                        user_id=user_id,
                                        role="user",
                                        content=msg,
                                        client_message_id=client_message_id,
                                        meta={"page_context": page_context} if page_context else None,
                                    )
                                )
                                # Touch conversation timestamps so it sorts correctly.
                                convo = AIConversation.query.filter_by(id=conversation_id, user_id=user_id).first()
                                if convo:
                                    convo.updated_at = utcnow()
                                    convo.last_message_at = utcnow()
                            # Commit even if we skipped insert so we don't leave pending work in the session.
                            db.session.commit()
                        except Exception as e:
                            current_app.logger.exception("AI WS: failed to persist user message at start")
                            try:
                                db.session.rollback()
                            except Exception as rb_e:
                                logger.debug("Session rollback failed: %s", rb_e)

                # Per-request id for progress restore + debugging (safe to expose).
                request_id = str(uuid.uuid4())

                ws.send(
                    json.dumps(
                        {
                            "type": "meta",
                            "conversation_id": conversation_id,
                            "request_id": request_id,
                            "auth_source": "cookie" if getattr(identity, "auth_source", "") == "cookie" else "bearer_or_public",
                        }
                    )
                )

                # Best-effort idempotency: if the client retries with the same client_message_id,
                # stream the already-generated assistant reply (if present) and skip LLM generation.
                existing = get_idempotent_reply(identity, conversation_id, client_message_id) if not cancelled.is_set() else None
                if existing:
                    reply_text, _, _ = existing
                    chunk_size = 20
                    for i in range(0, len(reply_text), chunk_size):
                        if cancelled.is_set():
                            break
                        ws.send(json.dumps({"type": "delta", "text": reply_text[i : i + chunk_size]}))
                        time.sleep(0.001)
                    if not cancelled.is_set():
                        ws.send(
                            json.dumps(
                                {
                                    "type": "done",
                                    "conversation_id": conversation_id,
                                    "deduped": True,
                                    "response": reply_text,
                                    "provider": "deduped",
                                    "model": None,
                                }
                            )
                        )
                    continue

                # Persist an "in-flight" progress snapshot so immersive UI can restore steps/progress
                # after a refresh while generation continues server-side.
                if identity.is_authenticated and identity.user and conversation_id:
                    user_id_raw = getattr(identity.user, "id", None)
                    if user_id_raw is not None:
                        try:
                            user_id = int(user_id_raw)
                            convo = AIConversation.query.filter_by(id=conversation_id, user_id=user_id).first()
                            if convo:
                                meta = convo.meta if isinstance(convo.meta, dict) else {}
                                meta = dict(meta)
                                meta["inflight"] = {
                                    "request_id": request_id,
                                    "status": "in_progress",
                                    "started_at": utcnow().isoformat(),
                                    "updated_at": utcnow().isoformat(),
                                    "steps": [{"message": "Preparing query…", "detail_lines": []}],
                                }
                                convo.meta = meta
                                convo.updated_at = utcnow()
                                db.session.commit()
                        except Exception as e:
                            current_app.logger.exception("AI WS[%s] failed to persist inflight snapshot", request_id)
                            try:
                                db.session.rollback()
                            except Exception as rb_e:
                                logger.debug("Session rollback failed: %s", rb_e)

                # Platform context aligned with HTTP path (RBAC via _build_access_context).
                access_context = _build_access_context(identity)
                platform_context = {
                    "user_info": {
                        "id": int(getattr(identity.user, "id", 0) or 0) if identity.is_authenticated and identity.user else None,
                        "role": access_context["role"],
                        "access_level": access_context["access_level"],
                    },
                    "access": access_context,
                    "available_countries": [],
                }

                llm_provider = "openai"
                model_name: Optional[str] = None
                function_calls_used = []
                response_text = ""

                try:
                    # Provide an RBAC-safe country list for focal points to improve extraction accuracy.
                    if identity.is_authenticated and identity.user:
                        if access_context["role"] not in ("admin", "system_manager"):
                            try:
                                user_countries = identity.user.countries.all() if hasattr(identity.user, "countries") else []
                                platform_context["available_countries"] = [
                                    {"id": c.id, "name": c.name, "iso3": getattr(c, "iso3", "")}
                                    for c in user_countries
                                ]
                            except Exception as e:
                                logger.debug("available_countries resolution failed: %s", e)
                                platform_context["available_countries"] = []

                    # Centralized OpenAI-only chain (agent -> OpenAI)
                    # Emits `step` + `delta` events via callbacks so WS/SSE/HTTP can share behavior.
                    from app.services.ai_chat_engine import AIChatEngine
                    
                    # Accumulate deltas server-side so we can reconstruct the final response
                    # even if a provider path only emits deltas (defensive; mirrors SSE behavior).
                    delta_accum: list[str] = []
                    inflight_last_persist = 0.0

                    def _clear_inflight_snapshot(force: bool = False) -> None:
                        if not (identity.is_authenticated and identity.user and conversation_id):
                            return
                        user_id_raw = getattr(identity.user, "id", None)
                        if user_id_raw is None:
                            return
                        try:
                            user_id = int(user_id_raw)
                            convo = AIConversation.query.filter_by(id=conversation_id, user_id=user_id).first()
                            if not convo:
                                return
                            meta = convo.meta if isinstance(convo.meta, dict) else {}
                            meta = dict(meta)
                            inflight = meta.get("inflight")
                            if not isinstance(inflight, dict):
                                return
                            if inflight.get("request_id") != request_id and not force:
                                return
                            meta.pop("inflight", None)
                            convo.meta = meta or None
                            convo.updated_at = utcnow()
                            db.session.commit()
                        except Exception as e:
                            current_app.logger.exception("AI WS[%s] failed to clear inflight snapshot", request_id)
                            try:
                                db.session.rollback()
                            except Exception as rb_e:
                                logger.debug("Session rollback failed: %s", rb_e)

                    def _persist_inflight_update(kind: str, step_message: Optional[str] = None, detail: Optional[str] = None, force: bool = False) -> None:
                        nonlocal inflight_last_persist
                        if not (identity.is_authenticated and identity.user and conversation_id):
                            return
                        user_id_raw = getattr(identity.user, "id", None)
                        if user_id_raw is None:
                            return
                        now_mono = time.monotonic()
                        if not force and kind == "detail" and (now_mono - inflight_last_persist) < 1.5:
                            return
                        inflight_last_persist = now_mono
                        try:
                            user_id = int(user_id_raw)
                            # Use a dedicated app context so DB ops always run in a clean session,
                            # not the synthetic test_request_context() session used for engine.run().
                            # Without this, inflight steps were committed to a session that didn't
                            # propagate to PostgreSQL, so page-refresh step restoration saw only the
                            # initial "Preparing query…" step rather than all accumulated steps.
                            with app_obj.app_context():
                                convo = AIConversation.query.filter_by(id=conversation_id, user_id=user_id).first()
                                if not convo:
                                    logger.debug("AI WS[%s] _persist_inflight_update: conversation not found", request_id)
                                    return
                                # Deep copy so nested dict mutations don't alias the
                                # original convo.meta (which defeats SQLAlchemy change detection).
                                meta = json.loads(json.dumps(convo.meta)) if isinstance(convo.meta, dict) else {}
                                inflight = meta.get("inflight")
                                if not isinstance(inflight, dict) or inflight.get("request_id") != request_id:
                                    logger.debug("AI WS[%s] _persist_inflight_update: request_id mismatch or no inflight (stored=%s)", request_id, inflight.get("request_id") if isinstance(inflight, dict) else None)
                                    return
                                steps = inflight.get("steps")
                                if not isinstance(steps, list):
                                    steps = []

                                def _coalesce_progress_tick(lines: list, new_line: str) -> None:
                                    import re
                                    progress_re = re.compile(r"^(.+?):\s*(\d+)\s*/\s*(\d+)\s*$")
                                    if not lines:
                                        lines.append(new_line)
                                        return
                                    m_new = progress_re.match(new_line.strip())
                                    m_last = progress_re.match(str(lines[-1] or "").strip())
                                    if m_new and m_last:
                                        if (m_new.group(1) or "").strip() == (m_last.group(1) or "").strip():
                                            lines[-1] = new_line
                                            return
                                    lines.append(new_line)

                                if kind == "step":
                                    msg_s = (step_message or "").strip()
                                    if msg_s:
                                        if steps and isinstance(steps[-1], dict) and str(steps[-1].get("message") or "").strip() == msg_s:
                                            if detail and str(detail).strip():
                                                dl = steps[-1].get("detail_lines")
                                                if not isinstance(dl, list):
                                                    dl = []
                                                _coalesce_progress_tick(dl, str(detail).strip())
                                                steps[-1]["detail_lines"] = dl
                                        else:
                                            obj = {"message": msg_s, "detail_lines": []}
                                            if detail and str(detail).strip():
                                                obj["detail_lines"] = [str(detail).strip()]
                                            steps.append(obj)
                                elif kind == "detail":
                                    d = (detail or "").strip()
                                    if d:
                                        if not steps:
                                            steps.append({"message": "Preparing query…", "detail_lines": []})
                                        if not isinstance(steps[-1], dict):
                                            steps[-1] = {"message": str(steps[-1]), "detail_lines": []}
                                        dl = steps[-1].get("detail_lines")
                                        if not isinstance(dl, list):
                                            dl = []
                                        _coalesce_progress_tick(dl, d)
                                        steps[-1]["detail_lines"] = dl

                                inflight["steps"] = steps
                                inflight["status"] = "in_progress"
                                inflight["updated_at"] = utcnow().isoformat()
                                meta["inflight"] = inflight
                                convo.meta = meta
                                flag_modified(convo, "meta")
                                convo.updated_at = utcnow()
                                db.session.commit()
                                logger.debug("AI WS[%s] _persist_inflight_update: committed kind=%s steps=%d", request_id, kind, len(steps))
                        except Exception as e:
                            logger.exception("AI WS[%s] failed to update inflight progress", request_id)

                    ws_client_disconnected = threading.Event()

                    def _ws_step(step_message: Optional[str] = None, detail: Optional[str] = None) -> None:
                        if cancelled.is_set():
                            return
                        try:
                            if step_message is None and detail is not None:
                                current_app.logger.debug("AI WS sending step_detail: %s", detail)
                                _persist_inflight_update("detail", detail=detail)
                                if not ws_client_disconnected.is_set():
                                    ws.send(json.dumps({"type": "step_detail", "detail": detail}))
                                return
                            if step_message:
                                current_app.logger.debug("AI WS sending step event: %s", step_message)
                            payload = {"type": "step", "message": step_message or ""}
                            if detail is not None:
                                payload["detail"] = detail
                            _persist_inflight_update("step", step_message=step_message, detail=detail, force=True)
                            if not ws_client_disconnected.is_set():
                                ws.send(json.dumps(payload))
                        except Exception as e:
                            ws_client_disconnected.set()
                            logger.debug("_ws_step send failed (client disconnected): %s", e)

                    def _ws_delta(delta_html: str) -> None:
                        if cancelled.is_set():
                            return
                        try:
                            if delta_html:
                                delta_accum.append(str(delta_html))
                            if not ws_client_disconnected.is_set():
                                ws.send(json.dumps({"type": "delta", "text": delta_html}))
                        except Exception as e:
                            ws_client_disconnected.set()
                            logger.debug("_ws_delta send failed (client disconnected): %s", e)

                    # Run inside app + request context so `current_user`/RBAC helpers work for tool calls.
                    app_obj = current_app._get_current_object()
                    with app_obj.app_context():
                        with app_obj.test_request_context():
                            try:
                                if getattr(identity, "is_authenticated", False) and getattr(identity, "user", None):
                                    login_user(identity.user, remember=False)
                            except Exception as e:
                                logger.debug("login_user in WS worker failed: %s", e)
                            try:
                                g.ai_sources_cfg = sources_cfg
                            except Exception as e:
                                logger.debug("g.ai_sources_cfg in WS worker failed: %s", e)
                            # Pass conversation_id so agent traces can log it
                            run_platform_context = {**platform_context, "conversation_id": conversation_id} if conversation_id else platform_context
                            engine = AIChatEngine()
                            result = engine.run(
                                message=msg,
                                platform_context=run_platform_context,
                                page_context=page_context,
                                preferred_language=preferred_language,
                                conversation_history=ws_conversation_history,
                                enable_agent=True,
                                on_step=_ws_step,
                                on_delta=_ws_delta,
                                cancelled=cancelled,
                            )

                    # Prefer the engine's final HTML; otherwise reconstruct from streamed deltas.
                    response_text = result.response_html or ("".join(delta_accum) if delta_accum else "")
                    llm_provider = result.provider or "openai"
                    model_name = result.model
                    function_calls_used = result.function_calls_used or []
                    map_payload = getattr(result, "map_payload", None)
                    chart_payload = getattr(result, "chart_payload", None)
                    table_payload = getattr(result, "table_payload", None)
                    has_visual = bool(map_payload or chart_payload or table_payload)
                    # When agent returns only map/chart/table (no text), use placeholder for persistence and UI.
                    persist_content = response_text or ""
                    if not persist_content.strip() and getattr(result, "success", False) and has_visual:
                        if map_payload and chart_payload:
                            persist_content = "[Map and chart visualization]"
                        elif map_payload:
                            persist_content = "[Map visualization]"
                        elif chart_payload:
                            persist_content = "[Chart visualization]"
                        elif table_payload:
                            persist_content = "[Data table]"
                        else:
                            persist_content = "[Visualization]"

                    if cancelled.is_set():
                        ws.send(json.dumps({"type": "cancelled"}))
                        _clear_inflight_snapshot()
                        continue

                    if not bool(getattr(result, "success", False)):
                        if not cancelled.is_set():
                            ws.send(
                                json.dumps(
                                    {
                                        "type": "error",
                                        "message": (getattr(result, "error_message", None) or GENERIC_ERROR_MESSAGE),
                                        "error_type": (getattr(result, "error_type", None) or "LLMError"),
                                    }
                                )
                            )
                        _clear_inflight_snapshot(force=True)
                        continue

                    # Check if we have a response to send (text or map/chart)
                    if (not response_text or not response_text.strip()) and not has_visual:
                        # No response generated - send error
                        if not cancelled.is_set():
                            ws.send(json.dumps({
                                "type": "error",
                                "message": "Unable to generate a response. Please try again.",
                                "error_type": "empty_response"
                            }))
                        _clear_inflight_snapshot(force=True)
                        continue

                    # Persist if logged-in (non-blocking - don't wait for DB if it's slow).
                    # Persist when we have text OR a successful result with map/chart (agent map-only case).
                    _user_id = getattr(identity.user, "id", None) if (identity.is_authenticated and identity.user) else None
                    if _user_id is not None and conversation_id and (response_text or (getattr(result, "success", False) and has_visual)):
                        app = current_app._get_current_object()
                        msg_to_persist = msg
                        response_to_persist = persist_content
                        page_ctx = page_context
                        conv_id = conversation_id
                        client_msg_id = client_message_id
                        prov = llm_provider
                        mod = model_name
                        fc_used = function_calls_used
                        client_meta = payload.get("client") or "unknown"
                        tid_persist = getattr(result, "trace_id", None)
                        _persist_ai_conversation_async(
                            app=app,
                            user_id=int(_user_id),
                            conversation_id=str(conv_id),
                            user_message=str(msg_to_persist),
                            assistant_message=str(response_to_persist),
                            page_context=page_ctx,
                            client_message_id=client_msg_id,
                            provider=str(prov),
                            model=mod,
                            function_calls_used=fc_used,
                            map_payload=map_payload,
                            chart_payload=chart_payload,
                            table_payload=table_payload,
                            client_meta=str(client_meta),
                            skip_user_message=branch_from_edit,
                            trace_id=int(tid_persist) if tid_persist is not None else None,
                        )

                    if not cancelled.is_set():
                        if map_payload or chart_payload or table_payload:
                            _ws_send_json(
                                ws,
                                {
                                    "type": "structured",
                                    "map_payload": map_payload,
                                    "chart_payload": chart_payload,
                                    "table_payload": table_payload,
                                },
                            )
                        # Include response in `done` for robustness (some clients rely on done.response).
                        done_payload = {
                            "type": "done",
                            "conversation_id": conversation_id,
                            "response": response_text,
                            "provider": llm_provider,
                            "model": model_name,
                            "map_payload": map_payload,
                            "chart_payload": chart_payload,
                            "table_payload": table_payload,
                        }
                        tid = getattr(result, "trace_id", None)
                        if tid is not None:
                            done_payload["trace_id"] = tid
                        _ws_send_json(ws, done_payload)
                    _clear_inflight_snapshot()
                except QuotaExceededError as e:
                    current_app.logger.warning("API quota exceeded: %s", e)
                    _ws_send_quota_error(ws, cancelled=cancelled, details=GENERIC_ERROR_MESSAGE, retry_delay=getattr(e, "retry_delay", None))
                    _clear_inflight_snapshot()
                except Exception as e:
                    # Client may have closed the connection (e.g. 1005); avoid error log and second send
                    if ConnectionClosed and isinstance(e, ConnectionClosed):
                        current_app.logger.debug("AI ws: client disconnected before done (code=%s)", getattr(e, "code", None))
                    else:
                        # Check for quota errors in generic exceptions too
                        if _ws_exception_looks_like_quota(e):
                            current_app.logger.warning("API quota exceeded (generic): %s", e)
                            _ws_send_quota_error(ws, cancelled=cancelled, details="Rate limit exceeded.")
                        else:
                            current_app.logger.exception("AI ws failed: %s", str(e))
                            if not cancelled.is_set():
                                _ws_send_json(ws, {"type": "error", "message": "Chat failed"})
                    _clear_inflight_snapshot()

        except Exception as e:
            current_app.logger.exception("WebSocket connection error: %s", str(e))
        finally:
            cancelled.set()  # Stop heartbeat
            current_app.logger.info("AI WebSocket: connection closed user_id=%s", user_id_log)
            if did_login:
                try:
                    logout_user()
                    try:
                        session.modified = False
                    except Exception as sess_e:
                        logger.debug("session.modified = False in cleanup failed: %s", sess_e)
                except Exception as e_logout:
                    current_app.logger.debug("AI WebSocket: logout_user() failed during cleanup: %s", e_logout, exc_info=True)

    @sock.route("/api/ai/documents/ws")
    def ai_documents_ws(ws):
        """
        WebSocket endpoint for document-QA streaming (admin UI).

        Client sends:
          {"type":"answer","query":"...","top_k":5,"min_score":0.35,"file_type":"","search_mode":"hybrid"}
          {"type":"cancel"}
          {"type":"ping"}

        Server streams:
          {"type":"meta","request_id":"..."}
          {"type":"sources","sources":[...]}
          {"type":"delta","text":"..."} repeated
          {"type":"done","answer":"...","sources":[...],"model":"..."}
        """
        if not current_app.config.get("WEBSOCKET_ENABLED", True):
            try:
                ws.send(json.dumps({"type": "error", "message": "WebSocket disabled"}))
            except Exception as e:
                logger.debug("ws.send WebSocket disabled failed: %s", e)
            return

        # Admin-only (matches where this UI is exposed)
        # RBAC-only: legacy `current_user.role` is not authoritative.
        from app.services.authorization_service import AuthorizationService
        if not getattr(current_user, "is_authenticated", False) or not AuthorizationService.has_rbac_permission(current_user, "admin.ai.manage"):
            try:
                ws.send(json.dumps({"type": "error", "message": "Unauthorized"}))
            except Exception as e:
                logger.debug("ws.send Unauthorized failed: %s", e)
            return

        cancelled = threading.Event()
        request_id = str(uuid.uuid4())

        def _send(obj: Dict[str, Any]) -> None:
            try:
                ws.send(json.dumps(obj))
            except Exception as e:
                logger.debug("_send failed: %s", e)
                cancelled.set()

        _send({"type": "meta", "request_id": request_id})

        # Simple per-connection throttle
        recent = deque()
        window_seconds = float(WS_HEARTBEAT_INTERVAL_SECONDS)
        max_events = 10

        def _allow() -> bool:
            now = time.time()
            while recent and (now - recent[0]) > window_seconds:
                recent.popleft()
            if len(recent) >= max_events:
                return False
            recent.append(now)
            return True

        try:
            while not cancelled.is_set():
                raw = ws.receive()
                if not raw:
                    break
                try:
                    payload = json.loads(raw)
                except Exception as e:
                    logger.debug("JSON parse failed: %s", e)
                    _send({"type": "error", "message": "Invalid JSON"})
                    continue

                msg_type = (payload.get("type") or "answer").strip().lower()
                if msg_type == "ping":
                    _send({"type": "pong"})
                    continue
                if msg_type == "cancel":
                    cancelled.set()
                    _send({"type": "cancelled"})
                    continue
                if msg_type not in ("answer", "query"):
                    continue
                if not _allow():
                    _send({"type": "error", "error_type": "rate_limited", "message": "Too many requests. Please wait."})
                    continue

                query = (payload.get("query") or payload.get("message") or "").strip()
                if not query:
                    _send({"type": "error", "message": "Query is required"})
                    continue

                # Params
                try:
                    top_k = min(int(payload.get("top_k", 5)), 20)
                except Exception as e:
                    logger.debug("top_k parse failed: %s", e)
                    top_k = 5
                try:
                    min_score = float(payload.get("min_score", 0.35))
                except Exception as e:
                    logger.debug("min_score parse failed: %s", e)
                    min_score = 0.35
                # Default to full-document mode if the client doesn't specify.
                # This is safer (less risk of missing context) for admin usage.
                if "use_full_document" in payload:
                    use_full_document = str(payload.get("use_full_document") or "").strip().lower() in {"1", "true", "yes", "on"}
                else:
                    use_full_document = True
                try:
                    max_docs = min(int(payload.get("max_docs", 3)), 5)
                except Exception as e:
                    logger.debug("max_docs parse failed: %s", e)
                    max_docs = 3
                retrieval_top_k = top_k
                if use_full_document:
                    retrieval_top_k = max(top_k, max_docs * 50)
                    retrieval_top_k = min(retrieval_top_k, 200)
                file_type = (payload.get("file_type") or "").strip() or None
                search_mode = (payload.get("search_mode") or "hybrid").strip().lower()
                if search_mode not in {"hybrid", "vector"}:
                    search_mode = "hybrid"

                vector_store = AIVectorStore()
                # Reuse the same retrieval/scoring helpers as the HTTP endpoint to avoid
                # drift between WS and REST behavior.
                try:
                    from app.routes.ai_documents import (
                        _run_document_search,
                        _score_retrieval_results,
                        _apply_min_score,
                        _has_country_filter,
                        _strip_country_filters,
                        _select_doc_scope,
                        _dedupe_retrieval_results,
                        _build_contextual_snippet,
                    )
                except Exception as e:
                    logger.warning("Document QA helpers unavailable: %s", e, exc_info=True)
                    _send({"type": "done", "answer": "Document QA helpers unavailable.", "sources": [], "model": "error"})
                    continue

                # LLM planning step to improve retrieval quality (no-op if OpenAI not configured).
                try:
                    from app.routes.ai_documents import _plan_query_with_llm, _resolve_country_from_text
                    plan = _plan_query_with_llm(query=query, file_type=file_type)
                    retrieval_query = (plan.get("retrieval_query") or query).strip() or query
                    focus_country_text = plan.get("focus_country_text")
                    focus_country_id, focus_country_name = _resolve_country_from_text(focus_country_text)
                except Exception as e:
                    logger.debug("Plan parsing failed: %s", e)
                    plan = None
                    retrieval_query = query
                    focus_country_id, focus_country_name = None, None

                filters = {"file_type": file_type} if file_type else {}
                if focus_country_id:
                    filters["country_id"] = int(focus_country_id)
                if focus_country_name:
                    filters["country_name"] = str(focus_country_name)
                if not filters:
                    filters = None

                from app.services.authorization_service import AuthorizationService
                user_role = (
                    "system_manager"
                    if AuthorizationService.is_system_manager(current_user)
                    else "admin"
                    if AuthorizationService.is_admin(current_user)
                    else "focal_point"
                    if AuthorizationService.has_role(current_user, "assignment_editor_submitter")
                    else "user"
                )
                # Pass 1: planned query + planned country filter.
                results = _run_document_search(
                    vector_store,
                    search_mode=search_mode,
                    query_text=retrieval_query,
                    top_k=retrieval_top_k,
                    filters=filters,
                    user_id=int(current_user.id),
                    user_role=user_role,
                )

                # Fallback: if country-scoped retrieval returns nothing, retry globally.
                if (not results) and _has_country_filter(filters):
                    fallback_filters = _strip_country_filters(filters)
                    results = _run_document_search(
                        vector_store,
                        search_mode=search_mode,
                        query_text=retrieval_query,
                        top_k=retrieval_top_k,
                        filters=fallback_filters,
                        user_id=int(current_user.id),
                        user_role=user_role,
                    )

                if not results:
                    _send({"type": "done", "answer": "No relevant documents found for this query.", "sources": [], "model": "none"})
                    continue

                scored_results = _score_retrieval_results(results, search_mode=search_mode)
                kept = _apply_min_score(scored_results, min_score=min_score)
                kept.sort(key=lambda r: (r.get("__rank_score") or 0), reverse=True)
                if not use_full_document:
                    kept = kept[:8]

                if not kept:
                    # Fallback: if we applied a country filter, retry globally before giving up.
                    if _has_country_filter(filters):
                        fallback_filters = _strip_country_filters(filters)
                        results2 = _run_document_search(
                            vector_store,
                            search_mode=search_mode,
                            query_text=retrieval_query,
                            top_k=retrieval_top_k,
                            filters=fallback_filters,
                            user_id=int(current_user.id),
                            user_role=user_role,
                        )
                        scored_results = _score_retrieval_results(results2 or [], search_mode=search_mode)
                        kept = _apply_min_score(scored_results, min_score=min_score)
                        kept.sort(key=lambda r: (r.get("__rank_score") or 0), reverse=True)
                        if not use_full_document:
                            kept = kept[:8]

                    if not kept:
                        _send({"type": "done", "answer": "No relevant documents found above the minimum score threshold.", "sources": [], "model": "none"})
                        continue

                # If query appears single-document, restrict to the intended document_id (prevents cross-country bleed like Türkiye).
                scoped_doc_id = _select_doc_scope(retrieval_query, kept)
                if scoped_doc_id:
                    kept = [r for r in kept if int(r.get("document_id") or 0) == int(scoped_doc_id)]
                    kept.sort(key=lambda r: (r.get("__rank_score") or 0), reverse=True)
                    if not kept:
                        _send({"type": "done", "answer": "No relevant documents found for the selected document scope.", "sources": [], "model": "none"})
                        continue
                kept = _dedupe_retrieval_results(kept)

                if use_full_document:
                    openai_key = current_app.config.get("OPENAI_API_KEY")
                    if not openai_key:
                        _send({"type": "done", "answer": "OPENAI_API_KEY not configured.", "sources": [], "model": "error"})
                        continue
                    try:
                        from openai import OpenAI
                    except Exception as e:
                        logger.warning("OpenAI SDK not available for document QA: %s", e)
                        _send({"type": "done", "answer": "OpenAI SDK not available.", "sources": [], "model": "error"})
                        continue

                    client = OpenAI(api_key=openai_key)
                    model_name = current_app.config.get("OPENAI_MODEL", "gpt-5-mini")
                    try:
                        from app.routes.ai_documents import _answer_with_full_documents
                        answer_text, sources = _answer_with_full_documents(
                            client=client,
                            model_name=model_name,
                            query=query,
                            filtered_results=kept,
                            max_docs=max_docs,
                            focus_country_id=focus_country_id,
                            focus_country_name=focus_country_name,
                            user_id=int(current_user.id),
                            is_admin=bool(AuthorizationService.is_admin(current_user) or AuthorizationService.is_system_manager(current_user)),
                            file_type=file_type,
                        )
                    except Exception as e:
                        _send({"type": "done", "answer": f"Failed to generate answer: {e}", "sources": [], "model": "error"})
                        continue

                    _send({"type": "sources", "sources": sources})
                    for i in range(0, len(answer_text), 24):
                        if cancelled.is_set():
                            break
                        _send({"type": "delta", "text": answer_text[i : i + 24]})
                        time.sleep(0.005)
                    if not cancelled.is_set():
                        _send({"type": "done", "answer": answer_text, "sources": sources, "model": model_name})
                    continue

                sources = []
                for idx, r in enumerate(kept, start=1):
                    content = (r.get("content") or "").strip()
                    sources.append(
                        {
                            "id": idx,
                            "document_id": r.get("document_id"),
                            "title": r.get("document_title"),
                            "filename": r.get("document_filename"),
                            "page_number": r.get("page_number"),
                            "chunk_index": r.get("chunk_index"),
                            "score": r.get("__filter_score"),
                            "rank_score": r.get("__rank_score"),
                            "similarity_score": r.get("similarity_score"),
                            "snippet": _build_contextual_snippet(content, query, max_len=1400),
                            "metadata": r.get("metadata") or {},
                        }
                    )

                _send({"type": "sources", "sources": [{k: v for k, v in s.items() if k != "metadata"} for s in sources]})

                # Deterministic table answer (reuse HTTP helper)
                try:
                    from app.routes.ai_documents import _try_answer_from_table_records
                    deterministic = _try_answer_from_table_records(query, kept)
                except Exception as e:
                    logger.debug("_try_answer_from_table_records failed: %s", e)
                    deterministic = None

                if deterministic:
                    answer = deterministic + " [1]."
                    # Stream it in small chunks for a “typing” feel
                    for i in range(0, len(answer), 24):
                        if cancelled.is_set():
                            break
                        _send({"type": "delta", "text": answer[i : i + 24]})
                        time.sleep(0.005)
                    if not cancelled.is_set():
                        _send({"type": "done", "answer": answer, "sources": sources[:1], "model": "table_records"})
                    continue

                # Deterministic UPR visual answering (metadata['upr']).
                try:
                    from app.routes.ai_documents import _try_answer_from_upr_metadata, _detect_participating_national_societies_intent
                    upr_hit = _try_answer_from_upr_metadata(query, kept)
                    if not upr_hit and kept:
                        top_doc_id = (kept[0] or {}).get("document_id")
                        if top_doc_id:
                            extra = vector_store.keyword_search(
                                query_text=("Participating National Societies" if _detect_participating_national_societies_intent(query) else "UPR visual block"),
                                top_k=25,
                                filters={"document_id": int(top_doc_id)},
                                user_id=int(current_user.id),
                                user_role=user_role,
                            )
                            upr_hit = _try_answer_from_upr_metadata(query, extra or [])
                except Exception as e:
                    logger.debug("_try_answer_from_upr_metadata failed: %s", e)
                    upr_hit = None

                if upr_hit:
                    upr_answer, used = upr_hit
                    answer = upr_answer + " [1]."
                    try:
                        from app.routes.ai_documents import _build_contextual_snippet
                    except Exception as e:
                        logger.debug("_build_contextual_snippet import failed (upr): %s", e)
                        _build_contextual_snippet = None  # type: ignore
                    used_content = (used.get("content") or "").strip()
                    used_source = {"id": 1,
                                   "document_id": used.get("document_id"),
                                   "title": used.get("document_title"),
                                   "filename": used.get("document_filename"),
                                   "page_number": used.get("page_number"),
                                   "chunk_index": used.get("chunk_index"),
                                   "score": used.get("__filter_score") if used.get("__filter_score") is not None else used.get("similarity_score") or used.get("keyword_score") or used.get("combined_score") or used.get("score"),
                                   "rank_score": used.get("__rank_score"),
                                   "similarity_score": used.get("similarity_score"),
                                   "snippet": (_build_contextual_snippet(used_content, query, max_len=1400) if _build_contextual_snippet else used_content[:800]),
                                   }
                    for i in range(0, len(answer), 24):
                        if cancelled.is_set():
                            break
                        _send({"type": "delta", "text": answer[i : i + 24]})
                        time.sleep(0.005)
                    if not cancelled.is_set():
                        _send({"type": "done", "answer": answer, "sources": [used_source], "model": "upr_visual"})
                    continue

                # Deterministic Participating National Societies list extraction (Planning visuals).
                try:
                    from app.routes.ai_documents import _try_answer_participating_national_societies
                    pns_hit = _try_answer_participating_national_societies(query, kept)
                    if not pns_hit and kept:
                        top_doc_id = (kept[0] or {}).get("document_id")
                        if top_doc_id:
                            extra = vector_store.keyword_search(
                                query_text="Participating National Societies",
                                top_k=25,
                                filters={"document_id": int(top_doc_id)},
                                user_id=int(current_user.id),
                                user_role=user_role,
                            )
                            pns_hit = _try_answer_participating_national_societies(query, extra or [])
                except Exception as e:
                    logger.debug("_try_answer_participating_national_societies failed: %s", e)
                    pns_hit = None

                if pns_hit:
                    pns_answer, used = pns_hit
                    answer = pns_answer + " [1]."
                    try:
                        from app.routes.ai_documents import _build_contextual_snippet
                    except Exception as e:
                        logger.debug("_build_contextual_snippet import failed (metric): %s", e)
                        _build_contextual_snippet = None  # type: ignore
                    used_content = (used.get("content") or "").strip()
                    used_source = {
                        "id": 1,
                        "document_id": used.get("document_id"),
                        "title": used.get("document_title"),
                        "filename": used.get("document_filename"),
                        "page_number": used.get("page_number"),
                        "chunk_index": used.get("chunk_index"),
                        "score": used.get("__filter_score") if used.get("__filter_score") is not None else used.get("similarity_score") or used.get("keyword_score") or used.get("combined_score") or used.get("score"),
                        "rank_score": used.get("__rank_score"),
                        "similarity_score": used.get("similarity_score"),
                        "snippet": (_build_contextual_snippet(used_content, query, max_len=1400) if _build_contextual_snippet else used_content[:800]),
                    }
                    for i in range(0, len(answer), 24):
                        if cancelled.is_set():
                            break
                        _send({"type": "delta", "text": answer[i : i + 24]})
                        time.sleep(0.005)
                    if not cancelled.is_set():
                        _send({"type": "done", "answer": answer, "sources": [used_source], "model": "participating_national_societies_blocks"})
                    continue

                # Deterministic KPI extraction for PDF header blocks.
                # If initial retrieval didn't include the KPI chunk, do a targeted second-pass keyword search
                # within the top document (helps when the KPI chunk doesn't include "Afghanistan" token).
                try:
                    from app.routes.ai_documents import _try_answer_from_metric_blocks, _detect_metric_intent, _metric_query_text
                    metric_intent = _detect_metric_intent(query)
                    metric_hit = _try_answer_from_metric_blocks(query, kept)
                    if not metric_hit and metric_intent and kept:
                        top_doc_id = (kept[0] or {}).get("document_id")
                        if top_doc_id:
                            term = _metric_query_text(metric_intent)
                            extra = vector_store.keyword_search(
                                query_text=term,
                                top_k=25,
                                filters={"document_id": top_doc_id},
                                user_id=int(current_user.id),
                                user_role=user_role,
                            )
                            metric_hit = _try_answer_from_metric_blocks(query, extra or [])
                except Exception as e:
                    logger.debug("_try_answer_from_metric_blocks failed: %s", e)
                    metric_hit = None

                if metric_hit:
                    metric_answer, used = metric_hit
                    answer = metric_answer + " [1]."
                    # Build a single correct source from the used chunk
                    try:
                        from app.routes.ai_documents import _build_contextual_snippet
                    except Exception as e:
                        logger.debug("_build_contextual_snippet import failed (metric): %s", e)
                        _build_contextual_snippet = None  # type: ignore
                    used_content = (used.get("content") or "").strip()
                    used_source = {
                        "id": 1,
                        "document_id": used.get("document_id"),
                        "title": used.get("document_title"),
                        "filename": used.get("document_filename"),
                        "page_number": used.get("page_number"),
                        "chunk_index": used.get("chunk_index"),
                        "score": used.get("__filter_score") if used.get("__filter_score") is not None else used.get("similarity_score") or used.get("keyword_score") or used.get("combined_score") or used.get("score"),
                        "rank_score": used.get("__rank_score"),
                        "similarity_score": used.get("similarity_score"),
                        "snippet": (_build_contextual_snippet(used_content, query, max_len=1400) if _build_contextual_snippet else used_content[:800]),
                    }
                    for i in range(0, len(answer), 24):
                        if cancelled.is_set():
                            break
                        _send({"type": "delta", "text": answer[i : i + 24]})
                        time.sleep(0.005)
                    if not cancelled.is_set():
                        _send({"type": "done", "answer": answer, "sources": [used_source], "model": "metric_blocks"})
                    continue

                # Deterministic People Reached extraction (e.g. "PEOPLE REACHED in Disasters and crises").
                try:
                    from app.routes.ai_documents import (
                        _try_answer_people_reached,
                        _detect_people_reached_intent,
                        _people_reached_query_text,
                        _is_people_to_be_reached_query,
                    )
                    people_hit = _try_answer_people_reached(query, kept)
                    if not people_hit and kept:
                        top_doc_id = (kept[0] or {}).get("document_id")
                        if top_doc_id:
                            category = _detect_people_reached_intent(query)
                            term = _people_reached_query_text(category, to_be=_is_people_to_be_reached_query(query)) if category else (
                                "people to be reached" if _is_people_to_be_reached_query(query) else "people reached"
                            )
                            extra = vector_store.keyword_search(
                                query_text=term,
                                top_k=25,
                                filters={"document_id": int(top_doc_id)},
                                user_id=int(current_user.id),
                                user_role=user_role,
                            )
                            people_hit = _try_answer_people_reached(query, extra or [])
                except Exception as e:
                    logger.debug("_try_answer_people_reached failed: %s", e)
                    people_hit = None

                if people_hit:
                    people_answer, used = people_hit
                    answer = people_answer + " [1]."
                    try:
                        from app.routes.ai_documents import _build_contextual_snippet
                    except Exception as e:
                        logger.debug("_build_contextual_snippet import failed (metric): %s", e)
                        _build_contextual_snippet = None  # type: ignore
                    used_content = (used.get("content") or "").strip()
                    used_source = {
                        "id": 1,
                        "document_id": used.get("document_id"),
                        "title": used.get("document_title"),
                        "filename": used.get("document_filename"),
                        "page_number": used.get("page_number"),
                        "chunk_index": used.get("chunk_index"),
                        "score": used.get("__filter_score") if used.get("__filter_score") is not None else used.get("similarity_score") or used.get("keyword_score") or used.get("combined_score") or used.get("score"),
                        "rank_score": used.get("__rank_score"),
                        "similarity_score": used.get("similarity_score"),
                        "snippet": (_build_contextual_snippet(used_content, query, max_len=1400) if _build_contextual_snippet else used_content[:800]),
                    }
                    for i in range(0, len(answer), 24):
                        if cancelled.is_set():
                            break
                        _send({"type": "delta", "text": answer[i : i + 24]})
                        time.sleep(0.005)
                    if not cancelled.is_set():
                        _send(
                            {
                                "type": "done",
                                "answer": answer,
                                "sources": [used_source],
                                "model": "people_to_be_reached_blocks" if _is_people_to_be_reached_query(query) else "people_reached_blocks",
                            }
                        )
                    continue

                # Stream from OpenAI (true first-token streaming)
                openai_key = current_app.config.get("OPENAI_API_KEY")
                if not openai_key:
                    _send({"type": "done", "answer": "OPENAI_API_KEY not configured.", "sources": sources, "model": "error"})
                    continue

                try:
                    from openai import OpenAI
                except Exception as e:
                    logger.warning("OpenAI SDK not available: %s", e)
                    _send({"type": "done", "answer": "OpenAI SDK not available.", "sources": sources, "model": "error"})
                    continue

                client = OpenAI(api_key=openai_key)
                model_name = current_app.config.get("OPENAI_MODEL", "gpt-5-mini")

                source_blocks = []
                for s in sources:
                    page_info = f"Page {s.get('page_number')}" if s.get("page_number") else "Page N/A"
                    source_blocks.append(
                        f"[{s['id']}] {s.get('title') or s.get('filename') or 'Document'} ({s.get('filename') or ''}, {page_info})\n{s.get('snippet')}"
                    )
                sources_text = "\n\n".join(source_blocks)

                system_prompt = (
                    "You are a document QA assistant. Answer using ONLY the sources provided. "
                    "If the answer is not in the sources, say you do not have enough information. "
                    "Cite sources using [1], [2], etc.\n\n"
                    "PDF/OCR layout rule (critical):\n"
                    "- Some sources are extracted from PDFs with column layouts. If you see a line of numbers followed by labels on the next lines, "
                    "pair values to labels LEFT-TO-RIGHT by their column position (do not ignore the numeric line).\n\n"
                    "Country scoping rule (critical):\n"
                    "- If the question is about a single country, answer ONLY for that country and mention it explicitly in the first sentence.\n"
                    "- Do NOT include facts from other countries. Do NOT cite sources you didn't use.\n\n"
                    "Table handling rules (critical):\n"
                    "- Do NOT infer missing values from context.\n"
                    "- Treat empty cells as 'not provided' (do not claim an allocation).\n"
                    "- Do NOT treat 'Funding Requirement' as 'Confirmed Funding' unless the source explicitly provides Confirmed Funding.\n"
                    "- Only list categories/allocations that are explicitly present in the sources.\n"
                )
                user_prompt = f"Question: {query}\n\nSources:\n{sources_text}"

                answer_accum = []
                try:
                    kwargs = {
                        "model": model_name,
                        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                        "max_completion_tokens": 800,
                        "stream": True,
                    }
                    if openai_model_supports_sampling_params(model_name):
                        kwargs["temperature"] = 0.2

                    stream = client.chat.completions.create(**kwargs)
                    for event in stream:
                        if cancelled.is_set():
                            break
                        try:
                            delta = event.choices[0].delta.content
                        except Exception as e:
                            logger.debug("delta extraction failed: %s", e)
                            delta = None
                        if delta:
                            answer_accum.append(delta)
                            _send({"type": "delta", "text": delta})
                    answer_text = "".join(answer_accum).strip()
                    if not answer_text and not cancelled.is_set():
                        answer_text = "I do not have enough information."
                    if not cancelled.is_set():
                        _send({"type": "done", "answer": answer_text, "sources": sources, "model": model_name})
                except Exception as e:
                    _send({"type": "done", "answer": f"Failed to generate answer: {e}", "sources": sources, "model": "error"})

        finally:
            cancelled.set()
