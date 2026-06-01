"""Aggregate API usage for admin API Management dashboards."""

from __future__ import annotations

from calendar import monthrange
from datetime import timedelta
from typing import Any

from sqlalchemy import case, func

from app import db
from app.models.api_usage import APIUsage
from app.utils.datetime_helpers import utcnow


def endpoint_path_prefix(path: str) -> str:
    """Registry path segment before the first Flask variable (<id> or {id})."""
    return path.split('<')[0].split('{')[0]


def bulk_endpoint_usage_stats(prefixes: list[str]) -> dict[str, dict[str, float | int]]:
    """
    Aggregate request counts by endpoint prefix in one query.

    APIUsage is the canonical log for all /api traffic. APIKeyUsage stores
    per-key audit rows for the same events when a DB-managed key is used;
    those rows are not merged here to avoid double-counting.
    """
    if not prefixes:
        return {}

    rows = (
        db.session.query(
            APIUsage.api_endpoint,
            func.count().label('total_requests'),
            func.sum(case((APIUsage.status_code < 400, 1), else_=0)).label('successful_requests'),
        )
        .filter(APIUsage.api_endpoint.like('/api/%'))
        .group_by(APIUsage.api_endpoint)
        .all()
    )

    endpoint_totals = [
        (row.api_endpoint, int(row.total_requests or 0), int(row.successful_requests or 0))
        for row in rows
    ]

    result: dict[str, dict[str, float | int]] = {}
    for prefix in dict.fromkeys(prefixes):
        total = 0
        success = 0
        for path, path_total, path_success in endpoint_totals:
            if path.startswith(prefix):
                total += path_total
                success += path_success
        result[prefix] = {
            'total_requests': total,
            'success_rate': (success / total * 100) if total > 0 else 100.0,
        }
    return result


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
