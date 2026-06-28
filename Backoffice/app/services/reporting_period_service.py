"""Reporting period catalog: link assigned forms to typed catalog rows."""

from __future__ import annotations

from datetime import date
from typing import Iterable, Sequence

from app.extensions import db
from app.models.assignments import AssignedForm, ReportingPeriod

ChronologyKey = tuple[date, date, str]


def _chronology_key_from_bounds(
    period_name: str,
    period_start: date,
    period_end: date,
) -> ChronologyKey:
    return (period_end, period_start, period_name)


def _unknown_chronology_key(period_name: str) -> ChronologyKey:
    return (date.min, date.min, period_name)


def get_reporting_period(period_name: str | None) -> ReportingPeriod | None:
    """Return the catalog row for an exact period label, if present."""
    name = (period_name or "").strip()
    if not name:
        return None
    return ReportingPeriod.query.filter_by(name=name).first()


def upsert_reporting_period(
    period_name: str,
    *,
    period_type: str,
    period_start: date,
    period_end: date,
) -> ReportingPeriod:
    """Create or update a catalog row using explicit typed bounds."""
    name = (period_name or "").strip()
    if not name:
        raise ValueError("period_name is required")

    existing = ReportingPeriod.query.filter_by(name=name).first()
    if existing:
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


def catalog_bounds_for_period_name(
    period_name: str | None,
) -> tuple[date | None, date | None]:
    """Return typed bounds from the reporting_period catalog when present."""
    row = get_reporting_period(period_name)
    if row is None:
        return None, None
    return row.period_start, row.period_end


def build_period_chronology_keys(
    period_names: Iterable[str | None],
) -> dict[str, ChronologyKey]:
    """Batch-build chronology keys from catalog rows only."""
    unique_names = sorted({(name or "").strip() for name in period_names if (name or "").strip()})
    if not unique_names:
        return {}

    catalog_rows = ReportingPeriod.query.filter(ReportingPeriod.name.in_(unique_names)).all()
    keys = {
        row.name: _chronology_key_from_bounds(row.name, row.period_start, row.period_end)
        for row in catalog_rows
    }
    for name in unique_names:
        if name not in keys:
            keys[name] = _unknown_chronology_key(name)
    return keys


def sort_period_names(
    period_names: Sequence[str | None],
    *,
    reverse: bool = True,
) -> list[str]:
    """Return period names sorted by catalog chronology (latest first by default)."""
    names = [(name or "").strip() for name in period_names if (name or "").strip()]
    if not names:
        return []
    keys = build_period_chronology_keys(names)
    return sorted(names, key=lambda name: keys[name], reverse=reverse)


def period_chronology_sort_key(
    period_name: str | None,
    *,
    period_start: date | None = None,
    period_end: date | None = None,
) -> ChronologyKey:
    """
    Sort key for reporting periods (latest first when used with reverse=True).

    Uses typed period_start/period_end when present, otherwise the catalog row
    for period_name. Unknown labels sort last.
    """
    name = (period_name or "").strip()
    if period_start is not None and period_end is not None:
        return _chronology_key_from_bounds(name, period_start, period_end)

    if name:
        catalog_start, catalog_end = catalog_bounds_for_period_name(name)
        if catalog_start is not None and catalog_end is not None:
            return _chronology_key_from_bounds(name, catalog_start, catalog_end)

    return _unknown_chronology_key(name)


def dashboard_assignment_period_sort_key(item: dict) -> ChronologyKey:
    """Sort key for dashboard assignment rows grouped by reporting period."""
    if item.get("type") == "assigned":
        aes = item.get("item_object")
        assigned_form = getattr(aes, "assigned_form", None) if aes else None
        if assigned_form is not None:
            return period_chronology_sort_key(
                assigned_form.period_name,
                period_start=assigned_form.period_start,
                period_end=assigned_form.period_end,
            )
    return period_chronology_sort_key(item.get("period"))


def sync_assigned_form_reporting_period(assigned_form: AssignedForm) -> None:
    """
    Link an AssignedForm to an existing reporting_period catalog row by name.

    Copies typed dates from the catalog. Clears period_id / dates when the label
    is empty or no catalog row exists.
    """
    period_name = (assigned_form.period_name or "").strip()
    if not period_name:
        assigned_form.period_id = None
        assigned_form.period_start = None
        assigned_form.period_end = None
        return

    reporting_period = get_reporting_period(period_name)
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
    """Link assigned_form rows that lack period_id to existing catalog rows."""
    stats = {
        "examined": 0,
        "synced": 0,
        "missing_catalog": 0,
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
            if get_reporting_period(assigned_form.period_name) is None:
                stats["missing_catalog"] += 1
            else:
                stats["synced"] += 1
            continue

        sync_assigned_form_reporting_period(assigned_form)
        if assigned_form.period_id is None:
            stats["missing_catalog"] += 1
        else:
            stats["synced"] += 1

    if not dry_run:
        db.session.commit()

    return stats


def resync_all_reporting_periods(
    *,
    dry_run: bool = False,
    batch_size: int = 500,
) -> dict[str, int]:
    """Re-link every assigned_form to the reporting_period catalog by period_name."""
    stats = {
        "assigned_examined": 0,
        "assigned_linked": 0,
        "assigned_missing_catalog": 0,
    }

    for assigned_form in (
        AssignedForm.query.filter(AssignedForm.period_name.isnot(None))
        .order_by(AssignedForm.id)
        .yield_per(batch_size)
    ):
        stats["assigned_examined"] += 1
        if dry_run:
            if get_reporting_period(assigned_form.period_name) is None:
                stats["assigned_missing_catalog"] += 1
            else:
                stats["assigned_linked"] += 1
            continue

        sync_assigned_form_reporting_period(assigned_form)
        if assigned_form.period_id is None:
            stats["assigned_missing_catalog"] += 1
        else:
            stats["assigned_linked"] += 1

    if not dry_run:
        db.session.commit()

    return stats
