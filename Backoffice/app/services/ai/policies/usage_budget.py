"""Aggregate AI usage limits: per-user / anonymous / system daily request and cost budgets.

Per-run caps (``AI_AGENT_COST_LIMIT_USD``) bound a single agent run; these budgets bound what a user, the
anonymous public chat as a whole, and the platform can spend per UTC day. Cost is summed from persisted
``ai_reasoning_traces`` so it is shared by every worker process.

Config (``0`` disables a budget; defaults are deliberately finite):

- ``AI_CHAT_DAILY_USER_LIMIT``             requests per user per day        (default 1500)
- ``AI_CHAT_DAILY_MANAGER_LIMIT``          requests per system manager/day  (default 5000)
- ``AI_CHAT_DAILY_ANON_IP_LIMIT``          requests per anonymous IP/day    (default 150)
- ``AI_CHAT_DAILY_ANON_LIMIT``             requests for all anonymous/day   (default 20000)
- ``AI_CHAT_DAILY_SYSTEM_LIMIT``           requests for the platform/day    (default 100000)
- ``AI_DAILY_COST_BUDGET_USER_USD``        USD per user per day             (default 10)
- ``AI_DAILY_COST_BUDGET_ANON_USD``        USD for all anonymous per day    (default 25)
- ``AI_DAILY_COST_BUDGET_SYSTEM_USD``      USD for the platform per day     (default 250)
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from flask import current_app

logger = logging.getLogger(__name__)

_DEFAULTS: Dict[str, float] = {
    "AI_CHAT_DAILY_USER_LIMIT": 1500,
    "AI_CHAT_DAILY_MANAGER_LIMIT": 5000,
    "AI_CHAT_DAILY_ANON_IP_LIMIT": 150,
    "AI_CHAT_DAILY_ANON_LIMIT": 20000,
    "AI_CHAT_DAILY_SYSTEM_LIMIT": 100000,
    "AI_DAILY_COST_BUDGET_USER_USD": 10.0,
    "AI_DAILY_COST_BUDGET_ANON_USD": 25.0,
    "AI_DAILY_COST_BUDGET_SYSTEM_USD": 250.0,
}

_CACHE_TTL_SECONDS = 20.0
_cache: Dict[Tuple[str, Optional[int]], Tuple[float, float]] = {}
_cache_lock = threading.Lock()


def budget_setting(name: str) -> float:
    """Numeric config value; invalid or missing falls back to the finite default (never to unlimited)."""
    default = _DEFAULTS[name]
    try:
        raw = current_app.config.get(name)
    except Exception:
        raw = None
    if raw in (None, ""):
        return float(default)
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return float(default)


def daily_request_limit_string(name: str) -> str:
    """Flask-Limiter string for a request budget; ``0`` (disabled) maps to an effectively-unbounded ceiling."""
    value = int(budget_setting(name))
    return f"{value if value > 0 else 100000000} per day"


@dataclass(frozen=True)
class BudgetVerdict:
    allowed: bool
    scope: Optional[str] = None
    spent_usd: float = 0.0
    budget_usd: float = 0.0


def _today_start():
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)


def _spent_today(scope: str, user_id: Optional[int]) -> float:
    key = (scope, user_id)
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < _CACHE_TTL_SECONDS:
            return hit[1]
    try:
        from sqlalchemy import func

        from app.extensions import db
        from app.models import AIReasoningTrace

        q = db.session.query(func.coalesce(func.sum(AIReasoningTrace.total_cost_usd), 0.0)).filter(
            AIReasoningTrace.created_at >= _today_start()
        )
        if scope == "user":
            q = q.filter(AIReasoningTrace.user_id == int(user_id))
        elif scope == "anonymous":
            q = q.filter(AIReasoningTrace.user_id.is_(None))
        spent = float(q.scalar() or 0.0)
    except Exception as exc:
        logger.warning("AI cost budget lookup failed (%s): %s", scope, exc)
        try:
            from app.extensions import db

            db.session.rollback()
        except Exception:
            pass
        return -1.0
    with _cache_lock:
        _cache[key] = (now, spent)
    return spent


def check_daily_cost_budget(user_id: Optional[int]) -> BudgetVerdict:
    """Deny when the caller's, the anonymous, or the platform daily cost budget is exhausted.

    A failing cost lookup does not block the request (the request-count limits and the per-run cap still
    apply) but is logged at warning level.
    """
    checks = []
    if user_id:
        checks.append(("user", int(user_id), budget_setting("AI_DAILY_COST_BUDGET_USER_USD")))
    else:
        checks.append(("anonymous", None, budget_setting("AI_DAILY_COST_BUDGET_ANON_USD")))
    checks.append(("system", None, budget_setting("AI_DAILY_COST_BUDGET_SYSTEM_USD")))

    for scope, uid, budget in checks:
        if budget <= 0:
            continue
        spent = _spent_today(scope, uid)
        if spent >= 0 and spent >= budget:
            return BudgetVerdict(False, scope, spent, budget)
    return BudgetVerdict(True)


def reset_budget_cache() -> None:
    with _cache_lock:
        _cache.clear()


def budget_exceeded_payload(verdict: BudgetVerdict) -> Dict[str, Any]:
    return {
        "error": "The AI assistant's daily usage budget has been reached. Please try again tomorrow.",
        "error_type": "budget_exceeded",
        "scope": verdict.scope,
    }
