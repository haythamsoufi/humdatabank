"""
Compact digest of what the agent actually did in a past turn.

Conversation history only stores the final answer text, so on a follow-up the model
cannot tell which tools ran, whether they failed, or what exact data they returned.
That leads to wrong claims ("the data you showed", "I checked these documents").

``build_turn_digest`` turns a stored reasoning-trace ``steps`` list into a short,
factual text block. ``attach_turn_digests`` adds it to loaded history entries as
``tool_digest`` so the agent prompt builder can append it to assistant messages.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

_SKIP_ACTIONS = frozenset({"finish", "evidence_plan_defer", "verify_answer"})
_DOC_SEARCH_TOOLS = frozenset({"search_documents", "search_documents_hybrid"})
_ARG_KEYS = (
    "country_identifier", "country", "indicator_name", "indicator", "query",
    "period", "assignment_period", "template_identifier", "top_k",
)
DIGEST_MAX_CHARS = 1800
DIGEST_HEADER = "[Record of tools I ran for this reply (internal context, not user-provided; do not quote this block)]"


def _short(value: Any, limit: int = 80) -> str:
    s = str(value)
    return s if len(s) <= limit else s[: limit - 1] + "…"


def _unwrap(obs: Any) -> Any:
    """Tool payloads are {success, result: ...}; return the inner result when present."""
    if isinstance(obs, dict) and "result" in obs:
        return obs.get("result")
    return obs


def _is_failed(obs: Any) -> bool:
    return isinstance(obs, dict) and (obs.get("success") is False or bool(obs.get("error")))


def _timeseries_summary(inner: Any) -> Optional[str]:
    if not isinstance(inner, dict) or not isinstance(inner.get("series"), list):
        return None
    parts: List[str] = []
    for row in inner["series"][:30]:
        if not isinstance(row, dict):
            continue
        label = row.get("period_name") or row.get("year")
        parts.append(f"{label}={row.get('value')} ({row.get('data_status') or 'n/a'})")
    ind = (inner.get("indicator") or {}).get("display_name") if isinstance(inner.get("indicator"), dict) else None
    head = f"{ind or 'series'} for {inner.get('country_display_name') or inner.get('iso3') or '?'}"
    return f"{head}: " + "; ".join(parts) if parts else None


def _doc_search_summary(inner: Any) -> Optional[str]:
    chunks = inner
    for _ in range(3):  # payloads may be wrapped as {result: {result: [...]}}
        if isinstance(chunks, dict) and "result" in chunks:
            chunks = chunks.get("result")
        else:
            break
    if not isinstance(chunks, list):
        return None
    if not chunks:
        return "0 chunks found"
    seen: List[str] = []
    for c in chunks:
        if not isinstance(c, dict):
            continue
        title = c.get("document_title") or c.get("title")
        if not title:
            continue
        page = c.get("page_number")
        label = f"{title}" + (f" p.{page}" if page else "")
        if label not in seen:
            seen.append(label)
    shown = "; ".join(seen[:8])
    more = f" (+{len(seen) - 8} more)" if len(seen) > 8 else ""
    return f"{len(chunks)} chunks retrieved from: {shown}{more}"


def _step_line(step: Dict[str, Any]) -> Optional[str]:
    action = str(step.get("action") or "").strip()
    if not action or action in _SKIP_ACTIONS:
        return None
    args = step.get("action_input") if isinstance(step.get("action_input"), dict) else {}
    arg_txt = ", ".join(f"{k}={_short(args[k])}" for k in _ARG_KEYS if args.get(k) not in (None, ""))
    obs = step.get("observation")

    if _is_failed(obs):
        etype = obs.get("error_type") if isinstance(obs, dict) else None
        cause = obs.get("error_cause_type") if isinstance(obs, dict) else None
        detail = _short(obs.get("error") or "error", 100) if isinstance(obs, dict) else "error"
        extra = f"{etype}" + (f" caused by {cause}" if cause else "") if etype else ""
        outcome = f"FAILED ({detail}{'; ' + extra if extra else ''}) — no results were obtained"
    else:
        inner = _unwrap(obs)
        summary: Optional[str] = None
        if action == "get_indicator_timeseries":
            summary = _timeseries_summary(inner)
        elif action in _DOC_SEARCH_TOOLS:
            summary = _doc_search_summary(obs if isinstance(obs, dict) else inner)
        outcome = f"OK — {summary}" if summary else "OK"
    return f"- {action}({arg_txt}) -> {outcome}"


def build_turn_digest(steps: Optional[Iterable[Dict[str, Any]]]) -> str:
    """Return a compact factual digest of tool activity, or '' when no tools ran."""
    lines: List[str] = []
    for step in steps or []:
        try:
            line = _step_line(step or {})
        except Exception as exc:  # never let digest building break chat
            logger.debug("turn digest step skipped: %s", exc)
            line = None
        if line:
            lines.append(line)
    if not lines:
        return ""
    body = "\n".join(lines)
    if len(body) > DIGEST_MAX_CHARS:
        body = body[: DIGEST_MAX_CHARS - 1] + "…"
    return f"{DIGEST_HEADER}\n{body}"


def attach_turn_digests(
    entries: List[Dict[str, Any]],
    trace_ids_by_index: Dict[int, int],
) -> None:
    """Add ``tool_digest`` to history entries (in place) using stored reasoning traces.

    ``trace_ids_by_index`` maps entry index -> AIReasoningTrace.id. Best-effort: any failure
    leaves the entries unchanged.
    """
    if not trace_ids_by_index:
        return
    try:
        from app.models.embeddings import AIReasoningTrace

        ids = sorted(set(trace_ids_by_index.values()))
        rows = AIReasoningTrace.query.filter(AIReasoningTrace.id.in_(ids)).all()
        digests = {r.id: build_turn_digest(r.steps if isinstance(r.steps, list) else []) for r in rows}
        for idx, tid in trace_ids_by_index.items():
            d = digests.get(tid)
            if d and 0 <= idx < len(entries):
                entries[idx]["tool_digest"] = d
    except Exception as exc:
        logger.debug("attach_turn_digests failed: %s", exc)
