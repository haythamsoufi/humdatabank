"""
Aggregated overview numbers for the Audit Trail "Overview" tab.

Uses the same visibility rules as the audit entries grid (noise filters, hidden
activity types) so the overview counts match what reviewers see in the table.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta
from typing import Any

from app.models import AdminActionLog, User, UserActivityLog
from app.services.audit.trail_display_service import (
    consolidate_activity_type,
    refine_activity_row_consolidated_type,
)
from app.services.audit.trail_session_query import (
    AUDIT_TRAIL_DEFAULT_HIDDEN_ACTIVITY_TYPES,
    apply_audit_trail_user_activity_noise_filters,
)
from app.utils.audit_trail_labels import activity_type_display_label
from app.utils.datetime_helpers import ensure_utc, utcnow

OVERVIEW_WINDOW_DAYS = 30
TREND_DAYS = 14
TOP_CATEGORIES = 10
TOP_USERS = 10
MAX_ROWS_PER_SOURCE = 50000
RISK_LEVELS = ("low", "medium", "high", "critical")


def _pct_change(current: int, previous: int) -> float | None:
    if previous <= 0:
        return None
    return round(100.0 * (current - previous) / previous, 1)


def build_audit_trail_overview() -> dict[str, Any]:
    now = utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    yesterday_cutoff = yesterday_start + (now - today_start)  # like-for-like with "today so far"
    week_start = today_start - timedelta(days=today_start.weekday())  # Monday 00:00 UTC
    prev_week_start = week_start - timedelta(days=7)
    prev_week_cutoff = prev_week_start + (now - week_start)
    window_start = today_start - timedelta(days=OVERVIEW_WINDOW_DAYS - 1)
    # Need previous calendar week for the week-over-week delta.
    query_start = min(window_start, prev_week_start)

    activity_rows = (
        apply_audit_trail_user_activity_noise_filters(
            UserActivityLog.query.with_entities(
                UserActivityLog.timestamp,
                UserActivityLog.user_id,
                UserActivityLog.activity_type,
                UserActivityLog.activity_description,
                UserActivityLog.endpoint,
                UserActivityLog.http_method,
                UserActivityLog.response_status_code,
            ).filter(UserActivityLog.timestamp >= query_start)
        )
        .filter(~UserActivityLog.activity_type.in_(AUDIT_TRAIL_DEFAULT_HIDDEN_ACTIVITY_TYPES))
        .order_by(UserActivityLog.timestamp.desc())
        .limit(MAX_ROWS_PER_SOURCE)
        .all()
    )
    admin_rows = (
        AdminActionLog.query.with_entities(
            AdminActionLog.timestamp,
            AdminActionLog.admin_user_id,
            AdminActionLog.action_type,
            AdminActionLog.risk_level,
            AdminActionLog.requires_review,
        )
        .filter(AdminActionLog.timestamp >= query_start)
        .order_by(AdminActionLog.timestamp.desc())
        .limit(MAX_ROWS_PER_SOURCE)
        .all()
    )

    # Unified, minimal records: (ts, user_id, category, risk, needs_review, is_error, source)
    records: list[tuple] = []
    type_cache: dict[tuple, str] = {}
    for ts, user_id, act_type, desc, endpoint, method, status in activity_rows:
        key = (act_type, desc, endpoint, method)
        category = type_cache.get(key)
        if category is None:
            category = refine_activity_row_consolidated_type(act_type, desc, endpoint, method)
            type_cache[key] = category
        if category in AUDIT_TRAIL_DEFAULT_HIDDEN_ACTIVITY_TYPES:
            continue
        risk = "medium" if endpoint == "data_sync_imputation.run_data_sync" else "low"
        is_error = bool(status and status >= 400)
        records.append((ensure_utc(ts), user_id, category, risk, False, is_error, "activity"))
    for ts, user_id, action_type, risk, needs_review in admin_rows:
        category = consolidate_activity_type(None, action_type)
        if category in AUDIT_TRAIL_DEFAULT_HIDDEN_ACTIVITY_TYPES:
            continue
        records.append(
            (ensure_utc(ts), user_id, category, risk or "low", bool(needs_review), False, "admin")
        )

    # Period buckets
    total_today = total_yesterday = total_week = total_prev_week = total_window = 0
    users_today: set = set()
    users_week: set = set()
    users_window: set = set()
    needs_review_window = errors_window = errors_today = high_risk_window = 0
    source_window: Counter = Counter()
    risk_window: Counter = Counter()
    day_counts: Counter = Counter()
    hour_counts: Counter = Counter()  # last 7 days, hour of day (UTC)
    seven_days_ago = today_start - timedelta(days=6)

    cat_counts: dict[str, dict[str, int]] = defaultdict(lambda: {"today": 0, "week": 0, "window": 0})
    user_counts: dict[int, dict[str, int]] = defaultdict(lambda: {"today": 0, "week": 0, "window": 0})

    for ts, user_id, category, risk, needs_review, is_error, source in records:
        in_today = ts >= today_start
        in_week = ts >= week_start
        in_window = ts >= window_start

        if in_today:
            total_today += 1
            users_today.add(user_id)
            if is_error:
                errors_today += 1
        elif yesterday_start <= ts < yesterday_cutoff:
            total_yesterday += 1
        if in_week:
            total_week += 1
            users_week.add(user_id)
        elif prev_week_start <= ts < prev_week_cutoff:
            # Same elapsed span of the previous week, so the delta is like-for-like.
            total_prev_week += 1

        if not in_window:
            continue
        total_window += 1
        users_window.add(user_id)
        source_window[source] += 1
        risk_window[risk if risk in RISK_LEVELS else "low"] += 1
        if risk in ("high", "critical"):
            high_risk_window += 1
        if needs_review:
            needs_review_window += 1
        if is_error:
            errors_window += 1

        day_counts[ts.date()] += 1
        if ts >= seven_days_ago:
            hour_counts[ts.hour] += 1

        c = cat_counts[category]
        c["window"] += 1
        u = user_counts[user_id]
        u["window"] += 1
        if in_week:
            c["week"] += 1
            u["week"] += 1
        if in_today:
            c["today"] += 1
            u["today"] += 1

    # Top categories (ranked by 30-day volume; the client can re-rank per period)
    categories = [
        {
            "key": key,
            "label": activity_type_display_label(key),
            **counts,
        }
        for key, counts in cat_counts.items()
    ]
    categories.sort(key=lambda r: r["window"], reverse=True)
    categories = categories[: max(TOP_CATEGORIES, 25)]

    # Top users
    top_user_ids = [
        uid for uid, _ in sorted(user_counts.items(), key=lambda kv: kv[1]["window"], reverse=True)
    ][: max(TOP_USERS, 25)]
    user_lookup: dict[int, tuple[str, str]] = {}
    if top_user_ids:
        for uid, name, email in (
            User.query.with_entities(User.id, User.name, User.email)
            .filter(User.id.in_(top_user_ids))
            .all()
        ):
            user_lookup[uid] = (name or "", email or "")
    users = []
    for uid in top_user_ids:
        name, email = user_lookup.get(uid, ("", ""))
        users.append(
            {
                "user_id": uid,
                "name": name or email or f"#{uid}",
                "email": email,
                **user_counts[uid],
            }
        )

    trend = []
    for i in range(TREND_DAYS - 1, -1, -1):
        d = (today_start - timedelta(days=i)).date()
        trend.append({"date": d.isoformat(), "count": day_counts.get(d, 0)})

    hours = [{"hour": h, "count": hour_counts.get(h, 0)} for h in range(24)]
    peak_hour = max(hours, key=lambda r: r["count"]) if any(r["count"] for r in hours) else None

    active_days = len(day_counts)
    avg_per_day = round(total_window / OVERVIEW_WINDOW_DAYS, 1) if total_window else 0

    return {
        "generated_at": now.isoformat(),
        "window_days": OVERVIEW_WINDOW_DAYS,
        "week_start": week_start.date().isoformat(),
        "totals": {
            "today": total_today,
            "yesterday": total_yesterday,
            "today_vs_yesterday_pct": _pct_change(total_today, total_yesterday),
            "week": total_week,
            "prev_week": total_prev_week,
            "week_vs_prev_pct": _pct_change(total_week, total_prev_week),
            "window": total_window,
            "avg_per_day": avg_per_day,
            "active_days": active_days,
            "active_users_today": len(users_today),
            "active_users_week": len(users_week),
            "active_users_window": len(users_window),
            "needs_review": needs_review_window,
            "high_risk": high_risk_window,
            "errors_today": errors_today,
            "errors_window": errors_window,
            "truncated": len(activity_rows) >= MAX_ROWS_PER_SOURCE or len(admin_rows) >= MAX_ROWS_PER_SOURCE,
        },
        "categories": categories,
        "users": users,
        "trend": trend,
        "hours": hours,
        "peak_hour": peak_hour,
        "risk": [{"level": lvl, "count": risk_window.get(lvl, 0)} for lvl in RISK_LEVELS],
        "sources": {
            "activity": source_window.get("activity", 0),
            "admin": source_window.get("admin", 0),
        },
    }
