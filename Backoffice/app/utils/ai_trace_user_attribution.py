"""
Extensible ``trace_diagnostics`` JSON on AI reasoning traces.

Convention: top-level keys are namespaced sections, e.g. ``user_attribution`` holds
signals when ``user_id`` could not be set. Other features can add their own keys
without overwriting unrelated data.

No secrets/tokens — only booleans and coarse request metadata safe for admins.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_JSON_VERSION = 1

# Canonical key inside trace_diagnostics for user-id attribution snapshots
USER_ATTRIBUTION_KEY = "user_attribution"


def build_user_attribution_diagnostics(
    *,
    phase: str,
    platform_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Snapshot for trace_diagnostics[USER_ATTRIBUTION_KEY] when user_id was not linked.

    phase: logical write point — e.g. create_trace | finalize_trace | save_trace_fallback
    platform_context: optional dict from chat/agent (merged user/platform context).
    """
    ctx: Dict[str, Any] = {
        "v": _JSON_VERSION,
        "phase": (phase or "unknown").strip()[:80] or "unknown",
    }

    resolved_would_be: Optional[int] = None
    try:
        from app.services.ai_chat_integration import resolve_ai_trace_user_id

        resolved_would_be = resolve_ai_trace_user_id(platform_context)
    except Exception as e:
        logger.debug("resolve_ai_trace_user_id in attribution snapshot failed: %s", e)
        ctx["resolve_ai_trace_user_id_error"] = type(e).__name__

    ctx["resolve_ai_trace_user_id_would_be"] = resolved_would_be

    try:
        if platform_context and isinstance(platform_context, dict):
            ui = platform_context.get("user_info") if isinstance(platform_context.get("user_info"), dict) else {}
            acc = platform_context.get("access") if isinstance(platform_context.get("access"), dict) else {}
            ctx["platform"] = {
                "has_user_info_id": ui.get("id") is not None,
                "user_info_id": ui.get("id"),
                "has_access_user_id": acc.get("user_id") is not None,
                "access_user_id": acc.get("user_id"),
                "access_level": acc.get("access_level") or ui.get("access_level"),
                "has_conversation_id": bool(
                    str(platform_context.get("conversation_id") or "").strip()
                ),
            }
        else:
            ctx["platform"] = None
    except Exception as e:
        logger.debug("platform slice for attribution snapshot failed: %s", e)
        ctx["platform"] = {"error": type(e).__name__}

    try:
        from flask import has_app_context, has_request_context, g

        ctx["flask_app_context"] = has_app_context()
        ctx["flask_request_context"] = has_request_context()
        if has_request_context():
            from flask import request

            ctx["endpoint"] = (request.endpoint or "")[:200] or None
            ctx["blueprint"] = getattr(request, "blueprint", None)
            raw_path = getattr(request, "path", "") or ""
            ctx["request_path_prefix"] = (raw_path[:120] + ("…" if len(raw_path) > 120 else "")) or None
            scheme = ""
            try:
                auth = request.headers.get("Authorization") or ""
                scheme = auth.split(" ", 1)[0].strip().lower() if auth.strip() else ""
            except Exception as e:
                logger.debug("Authorization scheme parse failed: %s", e)
            ctx["authorization_scheme"] = scheme or None
            try:
                from flask_login import current_user as _cu

                ctx["flask_login_authenticated"] = bool(
                    getattr(_cu, "is_authenticated", False)
                )
                if ctx["flask_login_authenticated"]:
                    ctx["flask_login_user_id"] = getattr(_cu, "id", None)
                else:
                    ctx["flask_login_user_id"] = None
            except Exception as e:
                logger.debug("flask_login slice failed: %s", e)
                ctx["flask_login_error"] = type(e).__name__

        if has_request_context():
            try:
                ctx["g_ai_user_id"] = getattr(g, "ai_user_id", None)
                ctx["g_ai_trace_id"] = getattr(g, "ai_trace_id", None)
            except Exception as e:
                logger.debug("g snapshot failed: %s", e)
    except Exception as e:
        logger.debug("request snapshot for attribution failed: %s", e)
        ctx["request_snapshot_error"] = type(e).__name__

    reasons: list[str] = []
    if not ctx.get("flask_request_context"):
        reasons.append("no_flask_request_context")
    elif not ctx.get("flask_login_authenticated"):
        reasons.append("flask_login_anonymous")
    pl = ctx.get("platform")
    if isinstance(pl, dict) and not (pl.get("has_user_info_id") or pl.get("has_access_user_id")):
        reasons.append("platform_context_missing_user_ids")
    if resolved_would_be is not None:
        reasons.append("resolver_would_set_user_id_but_trace_stored_null")
    if not reasons:
        reasons.append("no_user_attribution")

    ctx["reason_tags"] = reasons
    ctx["summary"] = "; ".join(reasons)

    return ctx


def merge_trace_diagnostics_user_attribution(
    trace: Any,
    *,
    stored_user_id: Optional[int],
    phase: str,
    platform_context: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Maintain trace.trace_diagnostics:

    - When user_id is set: drop only the user_attribution section; keep other keys.
    - When user_id is null: merge/replace trace_diagnostics[user_attribution] with a snapshot.
    """
    if not hasattr(trace, "trace_diagnostics"):
        return

    td: Dict[str, Any] = (
        dict(trace.trace_diagnostics) if isinstance(trace.trace_diagnostics, dict) else {}
    )

    if stored_user_id is not None:
        td.pop(USER_ATTRIBUTION_KEY, None)
        trace.trace_diagnostics = td if td else None
    else:
        td[USER_ATTRIBUTION_KEY] = build_user_attribution_diagnostics(
            phase=phase, platform_context=platform_context
        )
        trace.trace_diagnostics = td
