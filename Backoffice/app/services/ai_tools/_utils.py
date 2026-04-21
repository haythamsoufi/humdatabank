"""
ai_tools._utils
───────────────
Shared utilities used by every tool in AIToolsRegistry:

- ``ToolExecutionError``  – sentinel exception for failed tool calls.
- ``tool_wrapper``        – decorator: logging, error handling, progress-cb filtering.
- ``json_sanitize``       – make any value JSON-serialisable (best effort).
- ``truncate_json_value`` – cap oversized payloads before DB persistence.
- ``log_tool_usage``      – persist tool call metadata to ``ai_tool_usage`` (best effort).
"""

import inspect
import json
import logging
import time
from functools import wraps
from typing import Any, Callable, Dict, Optional

from flask import current_app, g, has_request_context

logger = logging.getLogger(__name__)


class ToolExecutionError(Exception):
    """Raised when tool execution fails in a way the agent should surface."""


def json_sanitize(value: Any) -> Any:
    """Return a JSON-serialisable copy of *value* (round-trips through json)."""
    try:
        return json.loads(json.dumps(value, default=str, ensure_ascii=False))
    except Exception as exc:
        logger.debug("json_sanitize failed: %s", exc)
        return str(value)


def truncate_json_value(value: Any, *, max_chars: Optional[int] = None) -> Any:
    """
    Truncate oversized JSON payloads to stay within DB column limits.

    Returns the original value if small enough, otherwise a dict with a
    ``truncated=True`` flag and a ``preview`` of the first *max_chars* chars.
    """
    if max_chars is None:
        try:
            max_chars = int(current_app.config.get("AI_TOOL_LOG_MAX_CHARS", 120_000))
        except Exception:
            max_chars = 120_000
    max_chars = max(4_000, min(int(max_chars), 2_000_000))
    safe = json_sanitize(value)
    try:
        s = json.dumps(safe, ensure_ascii=False, default=str)
        if len(s) <= max_chars:
            return safe
        return {"truncated": True, "preview": s[:max_chars], "original_length": len(s)}
    except Exception as exc:
        logger.debug("truncate_json_value: dumps failed: %s", exc)
        text = str(safe)
        if len(text) <= max_chars:
            return text
        return {"truncated": True, "preview": text[:max_chars], "original_length": len(text)}


def log_tool_usage(
    *,
    tool_name: str,
    tool_input: Dict[str, Any],
    tool_output: Any,
    success: bool,
    error_message: Optional[str],
    execution_time_ms: Optional[float],
    user_id: Optional[int],
) -> None:
    """
    Persist tool-usage metadata for analytics.

    This is completely best-effort: any failure is swallowed so it never
    disrupts tool execution.  Writes only when an active ``ai_trace_id`` is
    present in the Flask request context.
    """
    if not has_request_context():
        return
    trace_id = getattr(g, "ai_trace_id", None)
    if not trace_id:
        return
    try:
        from app.extensions import db
        from app.models import AIToolUsage

        usage = AIToolUsage(
            trace_id=int(trace_id),
            tool_name=str(tool_name),
            tool_input=truncate_json_value(tool_input),
            tool_output=truncate_json_value(tool_output),
            success=bool(success),
            error_message=str(error_message)[:4_000] if error_message else None,
            execution_time_ms=int(execution_time_ms) if execution_time_ms is not None else None,
            user_id=int(user_id) if user_id else None,
        )
        db.session.add(usage)
        db.session.commit()
    except Exception as exc:
        logger.debug("log_tool_usage failed: %s", exc)
        try:
            from app.extensions import db as _db
            _db.session.rollback()
        except Exception:
            pass


def tool_wrapper(func: Callable) -> Callable:
    """
    Decorator applied to every AIToolsRegistry method.

    Responsibilities:
    - Strip ``_progress_callback`` from kwargs if the wrapped function does
      not accept it (prevents unexpected-keyword-argument errors).
    - Log tool name + sanitised args at INFO level.
    - Catch all exceptions and re-raise as ``ToolExecutionError`` so the agent
      loop sees a uniform error type.
    - Persist tool-usage metrics via ``log_tool_usage`` (best-effort).
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        tool_name = func.__name__
        call_kwargs = kwargs
        try:
            sig = inspect.signature(func)
            params = sig.parameters
            accepts_var_kwargs = any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
            )
            if (
                "_progress_callback" in kwargs
                and "_progress_callback" not in params
                and not accepts_var_kwargs
            ):
                call_kwargs = dict(kwargs)
                call_kwargs.pop("_progress_callback", None)
        except Exception as exc:
            logger.debug("tool_wrapper: inspect.signature failed: %s", exc)
            if "_progress_callback" in kwargs:
                call_kwargs = dict(kwargs)
                call_kwargs.pop("_progress_callback", None)

        log_kwargs = dict(call_kwargs) if call_kwargs is not kwargs else dict(kwargs)
        log_kwargs.pop("_progress_callback", None)
        logger.info("Executing tool: %s  args=%s  kwargs=%s", tool_name, args, log_kwargs)

        start = time.time()
        user_id: Optional[int] = None
        try:
            from flask_login import current_user
            if current_user and current_user.is_authenticated:
                user_id = getattr(current_user, "id", None)
        except Exception:
            pass

        try:
            result = func(*args, **call_kwargs)
            elapsed = (time.time() - start) * 1_000
            log_tool_usage(
                tool_name=tool_name,
                tool_input=log_kwargs,
                tool_output=result,
                success=True,
                error_message=None,
                execution_time_ms=elapsed,
                user_id=user_id,
            )
            return result
        except ToolExecutionError:
            raise
        except Exception as exc:
            elapsed = (time.time() - start) * 1_000
            error_msg = str(exc)
            log_tool_usage(
                tool_name=tool_name,
                tool_input=log_kwargs,
                tool_output={"error": error_msg},
                success=False,
                error_message=error_msg,
                execution_time_ms=elapsed,
                user_id=user_id,
            )
            logger.error("Tool %s failed: %s", tool_name, exc, exc_info=True)
            raise ToolExecutionError(f"Tool '{tool_name}' failed: {exc}") from exc

    return wrapper


# ──────────────────────────────────────────────────────────────────────
# Shared context-resolution helpers
# ──────────────────────────────────────────────────────────────────────

def resolve_ai_user_context():
    """
    Resolve AI user identity and permissions from Flask context.

    Checks Flask-Login ``current_user`` first, falls back to request-scoped
    agent user context in ``g`` (token-based auth).

    Returns:
        tuple: (user_id, user_role, is_admin)
    """
    from flask_login import current_user as _cu

    user_id = None
    user_role = None
    is_admin = False

    if getattr(_cu, "is_authenticated", False):
        user_id = getattr(_cu, "id", None)
        try:
            from app.services.authorization_service import AuthorizationService
            user_role = AuthorizationService.access_level(_cu)
            is_admin = bool(
                AuthorizationService.is_admin(_cu)
                or AuthorizationService.is_system_manager(_cu)
            )
        except Exception as exc:
            logger.debug("resolve_ai_user_context: AuthorizationService failed: %s", exc)
            user_role = getattr(_cu, "role", None)
    elif has_request_context():
        try:
            user_id = getattr(g, "ai_user_id", None)
        except Exception as exc:
            logger.debug("resolve_ai_user_context: ai_user_id failed: %s", exc)
        try:
            user_role = (
                getattr(g, "ai_user_access_level", None)
                or getattr(g, "ai_user_role", None)
            )
        except Exception as exc:
            logger.debug("resolve_ai_user_context: ai_user_role failed: %s", exc)
        is_admin = str(user_role or "").strip().lower() in {"admin", "system_manager"}

    return user_id, user_role, is_admin


def resolve_source_config():
    """
    Read per-request source selection from Flask ``g`` context.

    Returns:
        dict with ``historical``, ``system_documents``, ``upr_documents`` booleans,
        or ``None`` when not configured.
    """
    if not has_request_context():
        return None
    try:
        raw = getattr(g, "ai_sources_cfg", None)
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    try:
        return {
            "historical": bool(raw.get("historical", False)),
            "system_documents": bool(raw.get("system_documents", False)),
            "upr_documents": bool(raw.get("upr_documents", False)),
        }
    except Exception:
        return None


def apply_document_source_filters(filters, sources_cfg, query=None):
    """
    Apply document-source selection to a search *filters* dict.

    Modifies *filters* in-place.  Returns ``True`` if search should proceed,
    ``False`` if all document sources are disabled.
    """
    if not isinstance(sources_cfg, dict):
        return True

    include_system = bool(sources_cfg.get("system_documents", False))
    include_upr = bool(sources_cfg.get("upr_documents", False))

    if include_system and not include_upr:
        filters["is_api_import"] = False
    elif include_upr and not include_system:
        filters["is_api_import"] = True
    elif not include_system and not include_upr:
        return False
    elif include_system and include_upr and query:
        from app.services.upr.query_detection import query_prefers_upr_documents
        if query_prefers_upr_documents(query):
            filters["is_api_import"] = True
            filters["is_system_document"] = False
    return True
