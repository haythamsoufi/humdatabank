"""
Collect cache hit/miss events during an AI agent run for reasoning traces.

Events are stored on Flask ``g.ai_cache_trace_events`` when a request context exists,
otherwise in a module-level fallback list (cleared on ``reset_ai_cache_trace``).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.utils.datetime_helpers import utcnow

_G_ATTR = "ai_cache_trace_events"
_fallback_events: List[Dict[str, Any]] = []


def reset_ai_cache_trace() -> None:
    """Clear cache trace events at the start of an agent run."""
    global _fallback_events  # noqa: PLW0603
    _fallback_events = []
    try:
        from flask import g, has_request_context

        if has_request_context():
            g.ai_cache_trace_events = []
    except Exception:
        pass


def _events_list() -> List[Dict[str, Any]]:
    try:
        from flask import g, has_request_context

        if has_request_context():
            existing = getattr(g, _G_ATTR, None)
            if isinstance(existing, list):
                return existing
            g.ai_cache_trace_events = []
            return g.ai_cache_trace_events
    except Exception:
        pass
    return _fallback_events


def record_ai_cache_event(
    kind: str,
    *,
    name: Optional[str] = None,
    hit: bool,
    detail: Optional[Dict[str, Any]] = None,
) -> None:
    """Record one cache lookup outcome for trace diagnostics."""
    event: Dict[str, Any] = {
        "kind": str(kind or "").strip() or "unknown",
        "hit": bool(hit),
        "timestamp": utcnow().isoformat(),
    }
    if name:
        event["name"] = str(name).strip()
    if isinstance(detail, dict) and detail:
        event["detail"] = detail
    _events_list().append(event)


def build_ai_cache_trace_payload() -> Optional[Dict[str, Any]]:
    """Return a compact cache-usage payload for trace ``output_payloads``."""
    events = list(_events_list())
    if not events:
        return None

    hits = sum(1 for e in events if e.get("hit"))
    misses = len(events) - hits
    kinds = sorted({str(e.get("kind") or "unknown") for e in events})

    lines: List[str] = []
    for e in events:
        label = str(e.get("kind") or "unknown")
        if e.get("name"):
            label = f"{label}:{e['name']}"
        lines.append(f"{label}={'hit' if e.get('hit') else 'miss'}")

    return {
        "events": events,
        "summary": {
            "total_events": len(events),
            "hits": hits,
            "misses": misses,
            "kinds": kinds,
            "line": "; ".join(lines),
        },
    }
