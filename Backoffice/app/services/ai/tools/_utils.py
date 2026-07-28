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
from typing import Any, Callable, Dict, Optional, Tuple

from flask import current_app, g, has_request_context
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


def split_tool_kw_for_call(func: Callable, kwargs: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Return (call_kwargs, log_kwargs): strip `_progress_callback` when the callable
    does not accept ``**kwargs`` or that parameter explicitly.

    Used by ai_tools decorators so `_progress_callback` is only passed through
    when the wrapped tool accepts it.
    """

    tool_name = getattr(func, "__name__", "tool")
    call_kwargs = kwargs
    try:
        sig = inspect.signature(func)
        params = sig.parameters
        accepts_var_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
        if (
            "_progress_callback" in kwargs
            and "_progress_callback" not in params
            and not accepts_var_kwargs
        ):
            call_kwargs = dict(kwargs)
            call_kwargs.pop("_progress_callback", None)
    except Exception as exc:
        logger.debug("split_tool_kw_for_call(%s): inspect.signature failed: %s", tool_name, exc)
        if "_progress_callback" in kwargs:
            call_kwargs = dict(kwargs)
            call_kwargs.pop("_progress_callback", None)

    log_kwargs = dict(call_kwargs if call_kwargs is not kwargs else dict(kwargs))
    log_kwargs.pop("_progress_callback", None)
    return call_kwargs, log_kwargs


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
        with db.session.begin_nested():
            db.session.add(usage)
            db.session.flush()
    except SQLAlchemyError as exc:
        logger.debug("log_tool_usage failed (savepoint rolled back): %s", exc)
    except Exception as exc:
        logger.debug("log_tool_usage failed: %s", exc)


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
        call_kwargs, log_kwargs = split_tool_kw_for_call(func, kwargs)
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


def resolve_form_builder_context() -> Optional[Dict[str, Any]]:
    """
    Read the form-builder assistant context from Flask ``g``.

    Set by AIAgentExecutor.execute() from ``page_context.formBuilder`` when the
    chat request originates from the form-builder AI panel. Returns a dict like
    ``{"enabled": True, "template_id": 12, "version_id": 34}`` or ``None``.
    """
    if not has_request_context():
        return None
    try:
        raw = getattr(g, "ai_form_builder_ctx", None)
    except Exception:
        return None
    if not isinstance(raw, dict) or not raw.get("enabled"):
        return None
    return raw


_FORM_TEMPLATE_WRITE_TOOLS = frozenset({
    "create_form_template",
    "edit_form_template",
    "translate_form_template",
    "discard_template_draft",
})


def extract_form_builder_result_from_steps(steps: Any) -> Optional[Dict[str, Any]]:
    """
    Return structured create/edit metadata from the latest successful form-template
    write tool in an agent run (for SSE clients and grid refresh).
    """
    if not isinstance(steps, list):
        return None
    for step in reversed(steps):
        if not isinstance(step, dict):
            continue
        action = str(step.get("action") or "").strip()
        if action not in _FORM_TEMPLATE_WRITE_TOOLS:
            continue
        obs = step.get("observation")
        if not isinstance(obs, dict) or not obs.get("success"):
            continue
        inner = obs.get("result")
        if not isinstance(inner, dict):
            continue
        template_id = inner.get("template_id")
        edit_url = inner.get("edit_url")
        if template_id is None and not edit_url:
            continue
        refs = inner.get("refs")
        return {
            "action": action,
            "template_id": int(template_id) if template_id is not None else None,
            "version_id": int(inner["version_id"]) if inner.get("version_id") is not None else None,
            "name": inner.get("name"),
            "edit_url": edit_url,
            "version_status": inner.get("version_status"),
            "warnings": list(inner.get("warnings") or []),
            "changes": list(inner.get("changes") or []),
            "refs": refs if isinstance(refs, dict) else {},
            "undo_structure": inner.get("undo_structure"),
            "redo_structure": inner.get("redo_structure"),
        }
    return None


def resolve_form_builder_user():
    """
    Return the User for form-builder tool execution.

    Prefer Flask-Login ``current_user``; fall back to ``g.ai_user_id`` in SSE/WS
    worker threads where the agent propagates identity without a browser session.
    """
    from flask_login import current_user as _cu

    if getattr(_cu, "is_authenticated", False):
        return _cu
    if not has_request_context():
        return None
    try:
        uid = getattr(g, "ai_user_id", None)
        if uid is not None:
            from app.models import User

            return User.query.get(int(uid))
    except Exception as exc:
        logger.debug("resolve_form_builder_user failed: %s", exc)
    return None


def resolve_form_template_permissions() -> Dict[str, bool]:
    """Resolve form template RBAC permissions for the current AI request user."""
    from app.services.authorization_service import AuthorizationService

    user = resolve_form_builder_user()
    if not user:
        return {"view": False, "create": False, "edit": False}

    def _has(code: str) -> bool:
        try:
            return bool(AuthorizationService.has_rbac_permission(user, code))
        except Exception as exc:
            logger.debug("resolve_form_template_permissions %s failed: %s", code, exc)
            return False

    return {
        "view": _has("admin.templates.view"),
        "create": _has("admin.templates.create"),
        "edit": _has("admin.templates.edit"),
    }


def resolve_indicator_bank_permissions() -> Dict[str, bool]:
    """
    Resolve Indicator Bank RBAC permissions for the current AI request user.

    Uses Flask-Login ``current_user`` (including Bearer-authenticated chat sessions).
    """
    from flask_login import current_user as _cu
    from app.services.authorization_service import AuthorizationService

    if not getattr(_cu, "is_authenticated", False):
        return {"view": False, "create": False, "edit": False, "archive": False, "suggest": False}

    def _has(code: str) -> bool:
        try:
            return bool(AuthorizationService.has_rbac_permission(_cu, code))
        except Exception as exc:
            logger.debug("resolve_indicator_bank_permissions %s failed: %s", code, exc)
            return False

    return {
        "view": _has("admin.indicator_bank.view"),
        "create": _has("admin.indicator_bank.create"),
        "edit": _has("admin.indicator_bank.edit"),
        "archive": _has("admin.indicator_bank.archive"),
        "suggest": _has("admin.indicator_bank.suggestions.review"),
    }


def require_indicator_bank_permission(permission_code: str) -> None:
    """Raise ToolExecutionError when the current user lacks an Indicator Bank permission."""
    from flask_login import current_user as _cu
    from app.services.authorization_service import AuthorizationService

    if not getattr(_cu, "is_authenticated", False):
        raise ToolExecutionError("Authentication required for Indicator Bank management tools.")
    try:
        allowed = AuthorizationService.has_rbac_permission(_cu, permission_code)
    except Exception as exc:
        logger.debug("require_indicator_bank_permission check failed: %s", exc)
        allowed = False
    if not allowed:
        raise ToolExecutionError("You do not have permission to use this Indicator Bank tool.")


INDICATOR_BANK_MGMT_TOOL_NAMES = frozenset(
    {
        "get_indicator_usage_stats",
        "browse_indicators",
        "get_indicator_bank_stats",
        "get_indicator_change_history",
        "list_indicator_suggestions",
    }
)


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
