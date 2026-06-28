"""Reporting period catalog: parse labels, upsert catalog rows, sync assigned forms."""

from __future__ import annotations

import calendar
import re
from datetime import date
from typing import Optional, Tuple

from app.extensions import db
from app.models.assignments import AssignedForm, ReportingPeriod

PeriodBounds = Tuple[str, date, date]

_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2}|21\d{2})\b")
_QUARTER_RE = re.compile(r"\bQ([1-4])\b", re.IGNORECASE)


def _last_day_of_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def _extract_years(period_name: str) -> list[int]:
    return [int(y) for y in _YEAR_RE.findall(str(period_name or "").strip())]


def parse_period_label(period_name: str) -> Optional[PeriodBounds]:
    """
    Parse a human period label into (period_type, period_start, period_end).

    Matches migration backfill rules for annual/custom spans, plus quarterly labels
    (e.g. "Q1 2024"). Returns None when the label cannot be interpreted.
    """
    raw = (period_name or "").strip()
    if not raw:
        return None

    years = _extract_years(raw)
    if not years:
        return None

    if len(years) == 1:
        year = years[0]
        quarter_match = _QUARTER_RE.search(raw)
        if quarter_match:
            quarter = int(quarter_match.group(1))
            start_month = (quarter - 1) * 3 + 1
            end_month = quarter * 3
            return (
                "quarterly",
                date(year, start_month, 1),
                date(year, end_month, _last_day_of_month(year, end_month)),
            )
        return "annual", date(year, 1, 1), date(year, 12, 31)

    start_year = min(years)
    end_year = max(years)
    return "custom", date(start_year, 1, 1), date(end_year, 12, 31)


def get_or_create_reporting_period(period_name: str) -> Optional[ReportingPeriod]:
    """Upsert a catalog row for the given label. Returns None when unparseable."""
    name = (period_name or "").strip()
    if not name:
        return None

    parsed = parse_period_label(name)
    if parsed is None:
        return None

    period_type, period_start, period_end = parsed
    existing = ReportingPeriod.query.filter_by(name=name).first()
    if existing:
        if (
            existing.period_type != period_type
            or existing.period_start != period_start
            or existing.period_end != period_end
        ):
            existing.period_type = period_type
            existing.period_start = period_start
            existing.period_end = period_end
        return existing

    reporting_period = ReportingPeriod(
        name=name,
        period_type=period_type,
        period_start=period_start,
        period_end=period_end,
    )
    db.session.add(reporting_period)
    db.session.flush()
    return reporting_period


def sync_assigned_form_reporting_period(assigned_form: AssignedForm) -> None:
    """
    Link an AssignedForm to the reporting_period catalog and copy typed dates.

    Clears period_id / period_start / period_end when the label is empty or unparseable
  (e.g. Self-Reported, load-test labels without a 4-digit year).
    """
    period_name = (assigned_form.period_name or "").strip()
    if not period_name:
        assigned_form.period_id = None
        assigned_form.period_start = None
        assigned_form.period_end = None
        return

    reporting_period = get_or_create_reporting_period(period_name)
    if reporting_period is None:
        assigned_form.period_id = None
        assigned_form.period_start = None
        assigned_form.period_end = None
        return

    assigned_form.period_id = reporting_period.id
    assigned_form.period_start = reporting_period.period_start
    assigned_form.period_end = reporting_period.period_end


def backfill_assigned_forms_missing_period(
    *,
    dry_run: bool = False,
    batch_size: int = 500,
) -> dict[str, int]:
    """Backfill period_id / dates on assigned_form rows that lack a catalog link."""
    stats = {
        "examined": 0,
        "synced": 0,
        "cleared_unparseable": 0,
        "skipped_already_linked": 0,
    }

    query = (
        AssignedForm.query.filter(AssignedForm.period_name.isnot(None))
        .order_by(AssignedForm.id)
        .yield_per(batch_size)
    )

    for assigned_form in query:
        stats["examined"] += 1
        if assigned_form.period_id is not None:
            stats["skipped_already_linked"] += 1
            continue

        if dry_run:
            parsed = parse_period_label(assigned_form.period_name)
            if parsed is None:
                stats["cleared_unparseable"] += 1
            else:
                stats["synced"] += 1
            continue

        sync_assigned_form_reporting_period(assigned_form)
        if assigned_form.period_id is None:
            stats["cleared_unparseable"] += 1
        else:
            stats["synced"] += 1

    if not dry_run:
        db.session.commit()

    return stats
