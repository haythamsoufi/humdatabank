"""The reporting schedule a monitoring plan commits to, and a preview of it.

A DREF counts its periods from the operation start date. An Emergency Appeal can have begun years
before anyone monitors it, so it counts from the day its plan is confirmed. That day is stored on
the operation when the plan is confirmed, so the periods never move afterwards.
"""

from __future__ import annotations

from datetime import date

from plugins.dref_monitoring.constants import FREQ_BIWEEKLY, FREQ_MONTHLY
from plugins.dref_monitoring.services.go_parse import is_emergency_appeal
from plugins.dref_monitoring.services.periods import MAX_PERIODS, build_periods

FREQUENCIES = (FREQ_BIWEEKLY, FREQ_MONTHLY)


def valid_frequency(value) -> str | None:
    value = str(value or "").strip().lower()
    return value if value in FREQUENCIES else None


def schedule_start(operation, today: date | None = None, frequency: str | None = None) -> date | None:
    """The first day of the first reporting period."""
    if operation.reporting_start is not None:
        return operation.reporting_start
    start = operation.start_date
    if start is None or not is_emergency_appeal(operation.appeal_type or ""):
        return start
    today = today or date.today()
    if start >= today:
        return start
    # The appeal is already running: report from now on. Monthly periods follow the calendar month.
    if (frequency or operation.reporting_frequency) == FREQ_MONTHLY:
        return max(start, today.replace(day=1))
    return today


def lock_schedule_start(operation, today: date | None = None) -> None:
    """Fix the first day of reporting when the plan is confirmed. Existing periods are left as they are."""
    if operation.reporting_start is not None or not is_emergency_appeal(operation.appeal_type or ""):
        return
    from plugins.dref_monitoring.models import DrefPeriod

    if DrefPeriod.query.filter_by(operation_id=operation.id).first() is not None:
        return
    operation.reporting_start = schedule_start(operation, today)


def frequency_editable(operation) -> bool:
    """True while the plan is a draft and no reporting cycle has been opened from it yet."""
    from plugins.dref_monitoring.constants import PLAN_DRAFT
    from plugins.dref_monitoring.models import DrefPeriod
    from plugins.dref_monitoring.services.plans import latest_plan

    plan = latest_plan(operation.id)
    if plan is None or plan.status != PLAN_DRAFT:
        return False
    return DrefPeriod.query.filter_by(operation_id=operation.id).first() is None


def set_plan_frequency(operation, frequency, actor) -> str | None:
    """Choose the reporting frequency on the plan screen, before the plan is confirmed."""
    from app.extensions import db

    if not actor.allows(operation, "enter"):
        return "You cannot change this plan."
    value = valid_frequency(frequency)
    if value is None:
        return "Choose biweekly or monthly."
    if not frequency_editable(operation):
        return "The plan is confirmed or its reporting cycles are open. Portfolio staff can change the frequency under Governance."
    operation.reporting_frequency = value
    db.session.commit()
    return None


def schedule_preview(operation, frequency: str | None = None, today: date | None = None) -> dict:
    """The periods the plan would open, one row each. ``frequency`` previews a choice that is not saved."""
    today = today or date.today()
    frequency = valid_frequency(frequency) or valid_frequency(operation.reporting_frequency) or FREQ_MONTHLY
    start = schedule_start(operation, today, frequency)
    end = operation.end_date
    preview = {
        "frequency": frequency,
        "start": start,
        "end": end,
        "rows": [],
        "count": 0,
        "first_due": None,
        "last_due": None,
        "truncated": False,
        "missing_dates": start is None or end is None,
        "starts_at_confirmation": bool(
            start is not None
            and operation.reporting_start is None
            and operation.start_date is not None
            and start != operation.start_date
        ),
    }
    if preview["missing_dates"]:
        return preview
    periods = build_periods(start, end, frequency)
    preview["rows"] = [
        {
            "sequence": sequence,
            "start": period_start,
            "end": period_end,
            "due": due,
            "state": "past" if due < today else "upcoming",
        }
        for sequence, period_start, period_end, due in periods
    ]
    preview["count"] = len(periods)
    if periods:
        preview["first_due"] = periods[0][3]
        preview["last_due"] = periods[-1][3]
        preview["truncated"] = len(periods) >= MAX_PERIODS and periods[-1][2] < end
    return preview
