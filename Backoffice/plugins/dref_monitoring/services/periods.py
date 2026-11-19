"""Reporting cadence. Imminent and short operations default to every two weeks."""

from __future__ import annotations

from datetime import date, timedelta

from plugins.dref_monitoring.constants import FREQ_BIWEEKLY, FREQ_MONTHLY


def default_frequency(appeal_type: str, timeframe_months: int | None, start: date | None, end: date | None) -> str:
    kind = (appeal_type or "").strip().lower().replace("_", "-")
    if kind in {"i-dref", "idref"}:
        return FREQ_BIWEEKLY
    if start and end:
        days = (end - start).days
    else:
        days = (timeframe_months or 0) * 30
    if days and days <= 60:
        return FREQ_BIWEEKLY
    return FREQ_MONTHLY


def _month_end(cursor: date) -> date:
    year = cursor.year + (1 if cursor.month == 12 else 0)
    month = 1 if cursor.month == 12 else cursor.month + 1
    return date(year, month, 1) - timedelta(days=1)


def build_periods(start: date, end: date, frequency: str) -> list[tuple[int, date, date, date]]:
    """Return ``(sequence, start, end, due)``. Due is the period end."""
    if end < start:
        return []
    periods: list[tuple[int, date, date, date]] = []
    cursor = start
    sequence = 1
    while cursor <= end and sequence <= 36:
        if frequency == FREQ_BIWEEKLY:
            period_end = min(cursor + timedelta(days=13), end)
        else:
            period_end = min(_month_end(cursor), end)
            if period_end < cursor:
                period_end = end
        periods.append((sequence, cursor, period_end, period_end))
        if period_end >= end:
            break
        cursor = period_end + timedelta(days=1)
        sequence += 1
    return periods


def escalation_level(today: date, due: date, submitted: bool, settings: dict) -> str | None:
    """None when nothing is due. Otherwise reminder, validate, review, or portfolio."""
    if submitted:
        return None
    reminder_days = int(settings.get("reminder_days_before") or 0)
    if today < due - timedelta(days=reminder_days):
        return None
    if today <= due:
        return "reminder"
    late = (today - due).days
    if late >= int(settings.get("escalation_portfolio_days") or 14):
        return "portfolio"
    if late >= int(settings.get("escalation_review_days") or 7):
        return "review"
    if late >= int(settings.get("escalation_validate_days") or 3):
        return "validate"
    return "reminder"
