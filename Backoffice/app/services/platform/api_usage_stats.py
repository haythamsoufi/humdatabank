"""Aggregate API usage for admin API Management dashboards."""

from __future__ import annotations

import re
from calendar import monthrange
from datetime import timedelta
from typing import Any

from sqlalchemy import case, func, or_

from app import db
from app.models.api_usage import APIUsage
from app.utils.datetime_helpers import utcnow

_VAR_RE = re.compile(r"<([^>]+)>|\{([^}]+)\}")

# Indicator Bank app routes live at the site root, outside /api.
_INDICATOR_BANK_EXACT_PATHS = (
    "/list-home",
    "/Sector",
    "/Subsector",
    "/CommonWord",
    "/Excel",
    "/Indicator",
)


def endpoint_path_prefix(path: str) -> str:
    """Registry path segment before the first Flask variable (<id> or {id})."""
    return path.split('<')[0].split('{')[0]


def is_indicator_bank_app_path(path: str | None) -> bool:
    """True for the Blazor Indicator Bank routes served at the site root."""
    raw = (path or "").split("?", 1)[0]
    normalized = raw.rstrip("/") or "/"
    if normalized in _INDICATOR_BANK_EXACT_PATHS:
        return True
    return normalized.startswith("/Indicator/")


def usage_tracked_clause():
    """SQL filter for rows the API Management page should count."""
    return or_(
        APIUsage.api_endpoint.like("/api/%"),
        APIUsage.api_endpoint.in_(_INDICATOR_BANK_EXACT_PATHS),
        APIUsage.api_endpoint.like("/Indicator/%"),
    )


def _pattern_for_registry_path(path: str) -> re.Pattern[str]:
    """Full-match regex for a registry path. Variables are one segment, except path converters."""
    parts: list[str] = []
    pos = 0
    for match in _VAR_RE.finditer(path):
        parts.append(re.escape(path[pos:match.start()]))
        token = match.group(1) or match.group(2) or ""
        converter = token.split(":", 1)[0] if ":" in token else ""
        parts.append(r".+" if converter == "path" else r"[^/]+")
        pos = match.end()
    parts.append(re.escape(path[pos:]))
    body = "".join(parts)
    if body.endswith("/"):
        body = body[:-1] + "/?"
    else:
        body += "/?"
    return re.compile("^" + body + "$")


def _specificity(path: str) -> tuple[int, int]:
    """More literal text, then fewer variables, wins a logged path."""
    literals = _VAR_RE.sub("", path).rstrip("/")
    params = len(_VAR_RE.findall(path))
    return (len(literals), -params)


def assign_logged_paths(registry_paths: list[str], logged_paths: list[str]) -> dict[str, str]:
    """Map each logged path to the single most specific registry route that matches it."""
    compiled = []
    for path in dict.fromkeys(p for p in registry_paths if p):
        compiled.append((path, _pattern_for_registry_path(path), _specificity(path)))
    compiled.sort(key=lambda item: item[2], reverse=True)

    assigned: dict[str, str] = {}
    for logged in logged_paths:
        if not logged or logged in assigned:
            continue
        for registry_path, pattern, _score in compiled:
            if pattern.match(logged):
                assigned[logged] = registry_path
                break
    return assigned


def bulk_endpoint_usage_stats(paths: list[str]) -> dict[str, dict[str, float | int]]:
    """
    Count APIUsage rows per registry route.

    A logged path is credited to the most specific matching route, so
    ``/api/v1/dashboard`` does not absorb ``/api/v1/dashboard/data-quality``
    and ``/documents/<id>`` does not absorb ``/documents/<id>/download``.

    APIKeyUsage stores per-key audit rows for the same events and is not
    merged here.
    """
    unique_paths = list(dict.fromkeys(p for p in paths if p))
    if not unique_paths:
        return {}

    rows = (
        db.session.query(
            APIUsage.api_endpoint,
            func.count().label('total_requests'),
            func.sum(case((APIUsage.status_code < 400, 1), else_=0)).label('successful_requests'),
        )
        .filter(usage_tracked_clause())
        .group_by(APIUsage.api_endpoint)
        .all()
    )

    endpoint_totals = {
        row.api_endpoint: (int(row.total_requests or 0), int(row.successful_requests or 0))
        for row in rows
    }
    assigned = assign_logged_paths(unique_paths, list(endpoint_totals))

    totals = {path: [0, 0] for path in unique_paths}
    for logged, registry_path in assigned.items():
        path_total, path_success = endpoint_totals[logged]
        bucket = totals[registry_path]
        bucket[0] += path_total
        bucket[1] += path_success

    return {
        path: {
            'total_requests': total,
            'success_rate': (success / total * 100) if total > 0 else 100.0,
        }
        for path, (total, success) in totals.items()
    }


def subtract_months(dt, months: int):
    """Return *dt* shifted back *months* calendar months (UTC-aware safe)."""
    year = dt.year
    month = dt.month - months
    while month <= 0:
        month += 12
        year -= 1
    day = min(dt.day, monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def _group_counts_by_hour(timestamps) -> dict[str, int]:
    hour_counts: dict[str, int] = {}
    for ts in timestamps:
        hour = ts.strftime('%H:00')
        hour_counts[hour] = hour_counts.get(hour, 0) + 1
    return hour_counts


def _group_counts_by_day(timestamps) -> dict[str, int]:
    day_counts: dict[str, int] = {}
    for ts in timestamps:
        day = ts.strftime('%Y-%m-%d')
        day_counts[day] = day_counts.get(day, 0) + 1
    return day_counts


def _group_counts_by_month(timestamps) -> dict[str, int]:
    month_counts: dict[str, int] = {}
    for ts in timestamps:
        month = ts.strftime('%Y-%m')
        month_counts[month] = month_counts.get(month, 0) + 1
    return month_counts


def _fill_hourly_buckets(hour_counts: dict[str, int]) -> list[dict[str, Any]]:
    current = utcnow()
    all_hours = {}
    for i in range(24):
        hour = (current - timedelta(hours=i)).strftime('%H:00')
        all_hours[hour] = hour_counts.get(hour, 0)
    return [{'label': h, 'count': c} for h, c in reversed(all_hours.items())]


def _fill_daily_buckets(day_counts: dict[str, int], days: int) -> list[dict[str, Any]]:
    current = utcnow()
    all_days = {}
    for i in range(days):
        day = (current - timedelta(days=i)).strftime('%Y-%m-%d')
        all_days[day] = day_counts.get(day, 0)
    return [{'label': d, 'count': c} for d, c in reversed(all_days.items())]


def _fill_monthly_buckets(month_counts: dict[str, int], months: int) -> list[dict[str, Any]]:
    current = utcnow()
    all_months = {}
    for i in range(months):
        month_dt = subtract_months(current, i)
        month_key = month_dt.strftime('%Y-%m')
        all_months[month_key] = month_counts.get(month_key, 0)
    return [{'label': m, 'count': c} for m, c in reversed(all_months.items())]


def chart_stats_for_period(base_query, period: str) -> list[dict[str, Any]]:
    """Return chart buckets for daily / weekly / monthly / quarterly / yearly."""
    if period == 'daily':
        last_24h = utcnow() - timedelta(days=1)
        timestamps = [
            row[0]
            for row in base_query.filter(APIUsage.timestamp >= last_24h)
            .with_entities(APIUsage.timestamp)
            .all()
        ]
        return _fill_hourly_buckets(_group_counts_by_hour(timestamps))

    if period == 'weekly':
        last_7d = utcnow() - timedelta(days=7)
        timestamps = [
            row[0]
            for row in base_query.filter(APIUsage.timestamp >= last_7d)
            .with_entities(APIUsage.timestamp)
            .all()
        ]
        return _fill_daily_buckets(_group_counts_by_day(timestamps), days=7)

    if period == 'monthly':
        last_30d = utcnow() - timedelta(days=30)
        timestamps = [
            row[0]
            for row in base_query.filter(APIUsage.timestamp >= last_30d)
            .with_entities(APIUsage.timestamp)
            .all()
        ]
        return _fill_daily_buckets(_group_counts_by_day(timestamps), days=30)

    if period == 'quarterly':
        last_90d = utcnow() - timedelta(days=90)
        timestamps = [
            row[0]
            for row in base_query.filter(APIUsage.timestamp >= last_90d)
            .with_entities(APIUsage.timestamp)
            .all()
        ]
        return _fill_daily_buckets(_group_counts_by_day(timestamps), days=90)

    # yearly — calendar months, not fixed 30-day steps
    last_year = utcnow() - timedelta(days=365)
    timestamps = [
        row[0]
        for row in base_query.filter(APIUsage.timestamp >= last_year)
        .with_entities(APIUsage.timestamp)
        .all()
    ]
    return _fill_monthly_buckets(_group_counts_by_month(timestamps), months=12)
