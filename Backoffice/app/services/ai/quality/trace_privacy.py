"""Privacy controls for persisted AI reasoning traces and tool-usage rows.

``ai_reasoning_traces`` and ``ai_tool_usage`` used to store the full user query and complete tool
outputs (which include country-scoped form values) indefinitely. This module is the one place that
decides what is persisted, who may see raw payloads, and when payloads are purged.

Config:

- ``AI_TRACE_STORE_MODE``               ``redacted`` (default) | ``full`` | ``minimal``
    - ``redacted``: text is masked with the DLP patterns (e-mail, phone, tokens, IBAN, cards, secrets)
      and structured payloads pass through ``redact_payload_for_storage`` (sensitive keys, size caps).
    - ``minimal``: queries/answers are redacted and tool inputs/outputs are replaced by a shape summary.
    - ``full``: legacy behaviour (no redaction) - not recommended.
- ``AI_TRACE_RETENTION_DAYS``           purge trace content older than N days      (default 90, 0 = keep)
- ``AI_TOOL_USAGE_PAYLOAD_RETENTION_DAYS`` null tool input/output older than N days  (default 30, 0 = keep)
- ``AI_TRACE_RAW_OUTPUT_PERMISSION``    RBAC permission that may view raw step observations / tool output in the
                                        admin trace viewer (default: system managers only)
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Dict, Optional

from flask import current_app
from sqlalchemy import null, or_

logger = logging.getLogger(__name__)

MODE_REDACTED = "redacted"
MODE_FULL = "full"
MODE_MINIMAL = "minimal"

PURGED_TEXT = "[purged]"


def _config(name: str, default: Any) -> Any:
    try:
        value = current_app.config.get(name)
    except Exception:
        value = None
    return default if value in (None, "") else value


def store_mode() -> str:
    mode = str(_config("AI_TRACE_STORE_MODE", MODE_REDACTED)).strip().lower()
    return mode if mode in {MODE_REDACTED, MODE_FULL, MODE_MINIMAL} else MODE_REDACTED


def _days(name: str, default: int) -> int:
    try:
        return max(0, int(_config(name, default)))
    except (TypeError, ValueError):
        return default


def redact_text(value: Optional[str], *, max_length: int = 20000) -> Optional[str]:
    """Mask DLP-detectable spans in free text stored on a trace (query, answer, error)."""
    if value is None or store_mode() == MODE_FULL:
        return value
    from app.services.ai.chat.dlp import mask_sensitive_text

    text = mask_sensitive_text(str(value))
    if len(text) > max_length:
        text = text[:max_length] + "…"
    return text


def _redact_strings(value: Any, depth: int = 0) -> Any:
    from app.services.ai.chat.dlp import mask_sensitive_text

    if isinstance(value, str):
        return mask_sensitive_text(value)
    if depth > 8:
        return value
    if isinstance(value, dict):
        return {k: _redact_strings(v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact_strings(v, depth + 1) for v in value]
    return value


def _shape(value: Any, depth: int = 0) -> Any:
    if isinstance(value, dict):
        if depth >= 2:
            return {"_keys": len(value)}
        return {str(k): _shape(v, depth + 1) for k, v in list(value.items())[:40]}
    if isinstance(value, (list, tuple)):
        return {"_items": len(value)}
    if isinstance(value, str):
        return {"_chars": len(value)}
    return type(value).__name__ if value is not None else None


def redact_payload(value: Any, *, max_bytes: int = 60_000) -> Any:
    """Structured payload (tool input/output, reasoning steps) as it may be persisted."""
    mode = store_mode()
    if mode == MODE_FULL or value is None:
        return value
    if mode == MODE_MINIMAL:
        return _shape(value)
    from app.utils.logging_security import redact_payload_for_storage

    return _redact_strings(redact_payload_for_storage(value, max_bytes=max_bytes))


def redact_tool_input(value: Any) -> Any:
    return redact_payload(value, max_bytes=20_000)


def redact_tool_output(value: Any) -> Any:
    return redact_payload(value)


def redact_trace_steps(steps: Any) -> Any:
    """Reasoning steps: thought text, action inputs and observations are all redacted."""
    if store_mode() == MODE_FULL or not isinstance(steps, list):
        return steps
    out = []
    for step in steps:
        if not isinstance(step, dict):
            out.append(step)
            continue
        cleaned: Dict[str, Any] = dict(step)
        for key in ("thought", "reasoning"):
            if isinstance(cleaned.get(key), str):
                cleaned[key] = redact_text(cleaned[key], max_length=4000)
        if "action_input" in cleaned:
            cleaned["action_input"] = redact_tool_input(cleaned["action_input"])
        if "observation" in cleaned:
            cleaned["observation"] = redact_tool_output(cleaned["observation"])
        out.append(cleaned)
    return out


def can_view_raw_tool_output(user: Any) -> bool:
    """Raw ``tool_output`` may contain country-scoped values; only AI managers see it."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    try:
        from app.services.organization.authorization_service import AuthorizationService

        if AuthorizationService.is_system_manager(user):
            return True
        perm = str(_config("AI_TRACE_RAW_OUTPUT_PERMISSION", "")).strip()
        return bool(perm) and bool(AuthorizationService.has_rbac_permission(user, perm))
    except Exception as exc:
        logger.debug("can_view_raw_tool_output failed (denying): %s", exc)
        return False


def strip_raw_outputs(trace_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Replace step observations in a serialized trace with a summary for viewers without raw access."""
    out = dict(trace_dict)
    steps = out.get("steps")
    if isinstance(steps, list):
        cleaned = []
        for step in steps:
            if isinstance(step, dict) and "observation" in step:
                step = dict(step)
                summary = step.get("observation_summary")
                step["observation"] = {"redacted": True, **({"summary": summary} if summary else {})}
            cleaned.append(step)
        out["steps"] = cleaned
    return out


def purge_expired_trace_content(*, dry_run: bool = False, batch_size: int = 500) -> Dict[str, int]:
    """Scrub old trace/tool-usage content while keeping the analytics columns (cost, status, timings)."""
    from app.extensions import db
    from app.models import AIReasoningTrace, AIToolUsage
    from app.utils.datetime_helpers import utcnow

    stats = {"traces_scrubbed": 0, "tool_usage_scrubbed": 0}
    now = utcnow()

    trace_days = _days("AI_TRACE_RETENTION_DAYS", 90)
    if trace_days > 0:
        cutoff = now - timedelta(days=trace_days)
        rows = (
            db.session.query(AIReasoningTrace)
            .filter(AIReasoningTrace.created_at < cutoff, AIReasoningTrace.query != PURGED_TEXT)
            .limit(max(1, int(batch_size)))
            .all()
        )
        for trace in rows:
            stats["traces_scrubbed"] += 1
            if dry_run:
                continue
            trace.query = PURGED_TEXT
            trace.original_query = None
            trace.final_answer = None
            trace.steps = []
            trace.output_payloads = None
            trace.progress_steps = None
            trace.error_message = None
            trace.llm_quality_reasoning = None

    usage_days = _days("AI_TOOL_USAGE_PAYLOAD_RETENTION_DAYS", 30)
    if usage_days > 0:
        cutoff = now - timedelta(days=usage_days)
        q = db.session.query(AIToolUsage).filter(
            AIToolUsage.created_at < cutoff,
            or_(
                AIToolUsage.tool_input.isnot(None),
                AIToolUsage.tool_output.isnot(None),
                AIToolUsage.error_message.isnot(None),
            ),
        )
        stats["tool_usage_scrubbed"] = q.count()
        if not dry_run and stats["tool_usage_scrubbed"]:
            q.update(
                {AIToolUsage.tool_input: null(), AIToolUsage.tool_output: null(), AIToolUsage.error_message: None},
                synchronize_session=False,
            )

    if dry_run:
        return stats
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return stats
