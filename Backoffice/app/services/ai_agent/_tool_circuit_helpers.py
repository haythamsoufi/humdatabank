"""Factory helpers for per-execution tool circuit breakers."""

from __future__ import annotations

from typing import Callable, Dict

from flask import current_app

from app.services.ai_agent._circuit_breaker import CircuitBreaker


def make_tool_breaker_factory() -> Callable[[str], CircuitBreaker]:
    """Return a callable that caches one ``CircuitBreaker`` per tool name (one agent run)."""
    thresh_raw = current_app.config.get("AI_AGENT_TOOL_CB_FAILURE_THRESHOLD", None)
    reset_raw = current_app.config.get("AI_AGENT_TOOL_CB_RESET_SECONDS", None)
    try:
        thresh = int(thresh_raw) if thresh_raw not in (None, "") else 3
    except (TypeError, ValueError):
        thresh = 3
    try:
        reset_sec = float(reset_raw) if reset_raw not in (None, "") else 30.0
    except (TypeError, ValueError):
        reset_sec = 30.0

    cache: Dict[str, CircuitBreaker] = {}

    def _factory(tool_name: str) -> CircuitBreaker:
        nm = str(tool_name or "").strip() or "_"
        if nm not in cache:
            cache[nm] = CircuitBreaker(
                failure_threshold=max(1, thresh),
                reset_timeout_seconds=max(0.0, reset_sec),
            )
        return cache[nm]

    return _factory
