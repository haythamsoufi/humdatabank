"""Routine monitoring reports, funds, procurement, delays, feedback, and risks."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from app.extensions import db
from plugins.dref_monitoring.constants import (
    ACTIVITY_BLOCKED,
    ACTIVITY_COMPLETED,
    ACTIVITY_DELAYED,
    ACTIVITY_ONGOING,
    ACTIVITY_PLANNED,
    PROCUREMENT_MILESTONES,
    REPORT_DRAFT,
    RISK_LEVELS,
    RISK_STATUSES,
)
from plugins.dref_monitoring.models import (
    DrefActivity,
    DrefActivityUpdate,
    DrefDelay,
    DrefFeedback,
    DrefFundsEvent,
    DrefGroup,
    DrefIndicator,
    DrefIndicatorValue,
    DrefPeriod,
    DrefPlan,
    DrefProcurement,
    DrefReport,
    DrefRisk,
)
from plugins.dref_monitoring.services.parsing import as_bool, as_date, as_int, as_money
from plugins.dref_monitoring.services.periods import build_periods
from plugins.dref_monitoring.services.schedule import schedule_start
from plugins.dref_monitoring.services.plans import (
    ACTIVITY_TYPE_CODES,
    CARRIED_OUT_CODES,
    _choice,
    activities_for,
    activity_status,
    groups_for,
    indicators_for_activity,
    latest_plan,
    plan_sections,
)

SHARE_PARTS = ("women", "men", "girls", "boys")


def shares_to_counts(total, shares: dict) -> dict:
    """Turn a percentage split into headcounts of the reached total."""
    counts = {}
    for part in SHARE_PARTS:
        percent = shares.get(part)
        if total is None or percent is None:
            counts[part] = None
        else:
            counts[part] = int(round(int(total) * int(percent) / 100))
    return counts


def disaggregation_reason(update) -> str:
    if update is None or not update.disaggregation_na:
        return ""
    data = update.disaggregation if isinstance(update.disaggregation, dict) else {}
    return str(data.get("reason") or "")


def counts_to_shares(total, counts: dict | None) -> dict:
    counts = counts or {}
    shares = {}
    for part in SHARE_PARTS:
        count = counts.get(part)
        if not total or count is None:
            shares[part] = None
        else:
            shares[part] = int(round(100 * int(count) / int(total)))
    return shares


def _chart_background(parts: list[dict]) -> str:
    colors = ("#111827", "#4b5563", "#6b7280", "#9ca3af", "#d1d5db")
    total = sum(part["count"] for part in parts)
    if not total:
        return "#e5e7eb"
    start = 0.0
    stops = []
    for index, part in enumerate(parts):
        if not part["count"]:
            continue
        end = start + part["count"] / total * 100
        stops.append(f"{colors[index % len(colors)]} {start:.1f}% {end:.1f}%")
        start = end
    return f"conic-gradient({', '.join(stops)})"


def ensure_periods(operation) -> None:
    if not operation.start_date or not operation.end_date:
        return
    existing = {
        row.sequence
        for row in DrefPeriod.query.filter_by(operation_id=operation.id).all()
    }
    for sequence, start, end, due in build_periods(
        schedule_start(operation), operation.end_date, operation.reporting_frequency
    ):
        if sequence in existing:
            continue
        db.session.add(
            DrefPeriod(
                operation_id=operation.id,
                sequence=sequence,
                start_date=start,
                end_date=end,
                due_date=due,
            )
        )
    db.session.flush()


def rebuild_open_periods(operation) -> None:
    periods = DrefPeriod.query.filter_by(operation_id=operation.id).all()
    for period in periods:
        report = DrefReport.query.filter_by(period_id=period.id).first()
        if report is None and period.assigned_form_id is None:
            db.session.delete(period)
    db.session.flush()
    ensure_periods(operation)


def periods_for(operation_id: int) -> list[DrefPeriod]:
    return DrefPeriod.query.filter_by(operation_id=operation_id).order_by(DrefPeriod.sequence).all()


def report_for_period(period_id: int) -> DrefReport | None:
    return DrefReport.query.filter_by(period_id=period_id).first()


def reporting_period_badge(period, report, today: date | None = None) -> str:
    """Status shown on the operation reporting tab.

    A period that has not started, and has not been filed, is upcoming.
    The stored period status stays open, so the row becomes an open period
    on its start date without a status change.
    """
    today = today or date.today()
    filed = report is not None and report.status != REPORT_DRAFT
    start = getattr(period, "start_date", None)
    if not filed and getattr(period, "status", None) == "open" and start is not None and start > today:
        return "upcoming"
    if report is not None:
        return report.status
    if getattr(period, "status", None) == "open":
        return "open"
    return getattr(period, "status", None) or ""


def get_or_create_report(operation, period: DrefPeriod) -> DrefReport:
    report = report_for_period(period.id)
    if report is None:
        report = DrefReport(period_id=period.id, operation_id=operation.id, status=REPORT_DRAFT)
        db.session.add(report)
        db.session.flush()
    return report


def _plan_activities(operation):
    plan = latest_plan(operation.id)
    if plan is None:
        return []
    rows = []
    for group in groups_for(plan.id):
        for activity in activities_for(group.id):
            rows.append((group, activity, indicators_for_activity(activity.id)))
    return rows


def _named(label, message: str) -> str:
    from plugins.dref_monitoring.i18n import named

    return named(label, message)


def _form_keys(form) -> set[str]:
    try:
        return {str(key) for key in form.keys()}
    except Exception:
        return set()


def _touches_activity(form, activity_id: int) -> bool:
    prefix = f"activity_{activity_id}_"
    return any(key.startswith(prefix) for key in _form_keys(form))


def _share_error(form, activity_id: int) -> str | None:
    """Reject a sex or age percentage above 100, or four that add up to more than 100."""
    numbers = []
    saw = False
    for part in SHARE_PARTS:
        raw = form.get(f"activity_{activity_id}_pct_{part}")
        text = "" if raw is None else str(raw).strip().replace(",", "")
        if text == "":
            continue
        try:
            number = Decimal(text)
        except (InvalidOperation, ValueError):
            return "Enter a number for the target."
        if number < 0:
            return "Amounts cannot be negative."
        if number > 100:
            return "A percentage cannot be more than 100."
        numbers.append(number)
        saw = True
    if saw and sum(numbers) > 100:
        return "The percentages together cannot be more than 100."
    return None


def _posted_amount(form, keys, field):
    """Posted money, whether the field was posted, and an error message."""
    if field not in keys:
        return None, False, None
    text = "" if form.get(field) is None else str(form.get(field)).strip()
    if text == "":
        return None, True, None
    amount = as_money(text)
    if amount is None:
        return None, True, "Enter a number for the target."
    if amount < 0:
        return None, True, "Amounts cannot be negative."
    return amount, True, None


def _posted_date(form, keys, field, current):
    """Posted date, or the current value when the field was not posted."""
    if field not in keys:
        return current, None
    text = "" if form.get(field) is None else str(form.get(field)).strip()
    if text == "":
        return None, None
    parsed = as_date(text)
    if parsed is None:
        return None, "Enter a valid date."
    return parsed, None


def _figure_error(form, keys, activity) -> str | None:
    """Budget, target, and dates edited on the entry form."""
    for suffix in ("budget", "target"):
        _amount, _posted, error = _posted_amount(form, keys, f"activity_{activity.id}_{suffix}")
        if error:
            return error
    start, start_error = _posted_date(form, keys, f"activity_{activity.id}_start_date", activity.start_date)
    if start_error:
        return start_error
    end, end_error = _posted_date(form, keys, f"activity_{activity.id}_end_date", activity.end_date)
    if end_error:
        return end_error
    if start and end and end < start:
        return "The end date must be on or after the start date."
    return None


def _apply_figures(form, keys, activity) -> None:
    budget, posted, _error = _posted_amount(form, keys, f"activity_{activity.id}_budget")
    if posted:
        activity.budget_chf = budget
    target, posted, _error = _posted_amount(form, keys, f"activity_{activity.id}_target")
    if posted:
        activity.target = target
    if f"activity_{activity.id}_start_date" in keys:
        activity.start_date, _error = _posted_date(form, keys, f"activity_{activity.id}_start_date", activity.start_date)
    if f"activity_{activity.id}_end_date" in keys:
        activity.end_date, _error = _posted_date(form, keys, f"activity_{activity.id}_end_date", activity.end_date)


def write_report_fields(operation, period, form) -> str | None:
    """Write one draft report from form fields. Does not commit and does not check a DREF role."""
    if period.operation_id != operation.id:
        return "Period not found on this operation."
    report = get_or_create_report(operation, period)
    if report.status != REPORT_DRAFT:
        return "This report has already been submitted."
    keys = _form_keys(form)
    for _group, activity, _indicators in _plan_activities(operation):
        if f"activity_{activity.id}_expenditure" not in keys:
            continue
        expenditure = as_money(form.get(f"activity_{activity.id}_expenditure"))
        if expenditure is not None and expenditure < 0:
            return _named(activity.title, "Expenditure cannot be negative.")

    for _group, activity, _indicators in _plan_activities(operation):
        if not _touches_activity(form, activity.id):
            continue
        figure_error = _figure_error(form, keys, activity)
        if figure_error:
            return _named(activity.title, figure_error)
        share_error = _share_error(form, activity.id)
        if share_error:
            return _named(activity.title, share_error)
        if as_bool(form.get(f"activity_{activity.id}_disaggregation_na")):
            reason = str(form.get(f"activity_{activity.id}_disaggregation_reason") or "").strip()
            if not reason:
                return _named(activity.title, "Explain why this data is not available.")
            continue
        if not any(f"activity_{activity.id}_pct_{part}" in keys for part in SHARE_PARTS):
            continue
        percents = [as_int(form.get(f"activity_{activity.id}_pct_{part}")) for part in SHARE_PARTS]
        if not any(value is not None for value in percents):
            continue
        if any(value is None for value in percents) or sum(value or 0 for value in percents) != 100:
            return _named(activity.title, "The percentage split must add up to 100.")
        reached = as_int(form.get(f"activity_{activity.id}_reached"))
        if reached is None:
            reached = as_int(form.get(f"activity_{activity.id}_individuals"))
        if reached is None:
            return _named(activity.title, "Enter the reached total before the percentage split.")

    total = 0
    saw_expenditure = False
    for _group, activity, indicators in _plan_activities(operation):
        if not _touches_activity(form, activity.id):
            continue
        status = activity_status(form.get(f"activity_{activity.id}_status")) or ACTIVITY_PLANNED
        percent = as_int(form.get(f"activity_{activity.id}_percent"))
        if percent is not None:
            percent = max(0, min(percent, 100))
        households = as_int(form.get(f"activity_{activity.id}_households"))
        individuals = as_int(form.get(f"activity_{activity.id}_individuals"))
        if f"activity_{activity.id}_reached" in keys:
            individuals = as_int(form.get(f"activity_{activity.id}_reached"))
        expenditure = as_money(form.get(f"activity_{activity.id}_expenditure"))
        skipped = as_bool(form.get(f"activity_{activity.id}_disaggregation_na"))
        share_error = _share_error(form, activity.id)
        if share_error:
            return _named(activity.title, share_error)
        percents = {
            part: as_int(form.get(f"activity_{activity.id}_pct_{part}"))
            for part in SHARE_PARTS
        }
        percent_posted = any(f"activity_{activity.id}_pct_{part}" in keys for part in SHARE_PARTS)
        if skipped:
            disaggregation = {part: None for part in SHARE_PARTS}
            disaggregation["reason"] = str(form.get(f"activity_{activity.id}_disaggregation_reason") or "").strip()[:2000]
        elif percent_posted and any(value is not None for value in percents.values()):
            if any(value is None for value in percents.values()) or sum(value or 0 for value in percents.values()) != 100:
                return _named(activity.title, "The percentage split must add up to 100.")
            if individuals is None:
                return _named(activity.title, "Enter the reached total before the percentage split.")
            disaggregation = shares_to_counts(individuals, percents)
        else:
            disaggregation = {
                part: as_int(form.get(f"activity_{activity.id}_{part}"))
                for part in SHARE_PARTS
            }
        update = DrefActivityUpdate.query.filter_by(report_id=report.id, activity_id=activity.id).first()
        if update is None:
            update = DrefActivityUpdate(report_id=report.id, activity_id=activity.id)
            db.session.add(update)
        update.status = status
        update.percent = percent
        update.people_households = households
        update.people_individuals = individuals
        update.disaggregation = disaggregation
        update.disaggregation_na = skipped
        update.expenditure = expenditure
        update.note = str(form.get(f"activity_{activity.id}_note") or "")[:2000]
        activity.status = status
        activity.percent = percent
        type_field = f"activity_{activity.id}_activity_type"
        actor_field = f"activity_{activity.id}_carried_out_by"
        if type_field in keys:
            activity.activity_type = _choice(form.get(type_field), ACTIVITY_TYPE_CODES)
        if actor_field in keys:
            activity.carried_out_by = _choice(form.get(actor_field), CARRIED_OUT_CODES)
        _apply_figures(form, keys, activity)
        if expenditure is not None:
            saw_expenditure = True
            total += expenditure
        for indicator in indicators:
            field = f"indicator_{indicator.id}_actual"
            actual = as_money(form.get(field))
            if actual is None and field not in keys:
                continue
            value = DrefIndicatorValue.query.filter_by(report_id=report.id, indicator_id=indicator.id).first()
            if value is None:
                value = DrefIndicatorValue(report_id=report.id, indicator_id=indicator.id)
                db.session.add(value)
            value.actual = actual
    if "narrative" in keys:
        report.narrative = str(form.get("narrative") or "")
    if saw_expenditure:
        report.expenditure_total = total
    db.session.flush()
    return None


def form_from_cycle_payload(data: dict) -> dict:
    """Flat field names the report writer already understands."""
    form: dict = {}
    if "narrative" in data:
        form["narrative"] = data.get("narrative") or ""
    activities = data.get("activities") or {}
    if isinstance(activities, dict):
        for activity_id, fields in activities.items():
            if not isinstance(fields, dict):
                continue
            prefix = f"activity_{activity_id}"
            for part in (
                "status",
                "percent",
                "households",
                "individuals",
                "reached",
                "women",
                "men",
                "girls",
                "boys",
                "pct_women",
                "pct_men",
                "pct_girls",
                "pct_boys",
                "disaggregation_na",
                "disaggregation_reason",
                "expenditure",
                "note",
            ):
                if part in fields:
                    form[f"{prefix}_{part}"] = fields.get(part)
    indicators = data.get("indicators") or {}
    if isinstance(indicators, dict):
        for indicator_id, fields in indicators.items():
            actual = fields.get("actual") if isinstance(fields, dict) else fields
            form[f"indicator_{indicator_id}_actual"] = actual
    return form


def apply_cycle_payload(operation, period, data: dict, user_id=None) -> str | None:
    """Save a cycle field payload. The focal point does not need a DREF monitoring role."""
    del user_id  # draft saves are not attributed; submit records the assignment user
    return write_report_fields(operation, period, form_from_cycle_payload(data))


def _activity_row(activity, saved, actuals):
    update = saved.get(activity.id)
    counts = (update.disaggregation if update is not None else None) or {}
    total = None if update is None else update.people_individuals
    indicators = indicators_for_activity(activity.id)
    return {
        "activity": activity,
        "indicators": indicators,
        "update": update,
        "actuals": actuals,
        "shares": counts_to_shares(total, counts),
        "disaggregation_na": bool(update and update.disaggregation_na),
        "disaggregation_reason": disaggregation_reason(update),
        "tracks_households": any(indicator.beneficiary_unit == "households" for indicator in indicators),
    }


def report_sections(operation, report) -> list:
    plan = latest_plan(operation.id)
    if plan is None or report is None:
        return []
    saved = updates_for(report.id)
    actuals = values_for(report.id)
    sections = []
    for section in plan_sections(plan.id):
        blocks = []
        for block in section["blocks"]:
            blocks.append(
                {
                    "indicator": block["indicator"],
                    "activities": [_activity_row(activity, saved, actuals) for activity in block["activities"]],
                }
            )
        sections.append({"group": section["group"], "blocks": blocks, "activities": [_activity_row(activity, saved, actuals) for activity in section["activities"]]})
    return sections


def context_for_assignment(aes_id: int):
    """Operation and period for a project-cycle assignment, or None."""
    from app.models.assignments import AssignmentEntityStatus

    assignment_status = db.session.get(AssignmentEntityStatus, aes_id)
    if assignment_status is None or not assignment_status.assigned_form_id:
        return None
    period = DrefPeriod.query.filter_by(assigned_form_id=assignment_status.assigned_form_id).first()
    if period is None:
        return None
    from plugins.dref_monitoring.models import DrefOperation

    operation = db.session.get(DrefOperation, period.operation_id)
    if operation is None:
        return None
    return operation, period


def matrix_for_request():
    """Report matrix for the assignment currently being opened, if it is a DREF cycle."""
    from flask import has_request_context, request

    if not has_request_context():
        return None
    aes_id = (request.view_args or {}).get("aes_id")
    if not aes_id:
        return None
    found = context_for_assignment(int(aes_id))
    if found is None:
        return None
    operation, period = found
    report = get_or_create_report(operation, period)
    return {
        "operation": operation,
        "period": period,
        "report": report,
        "sections": report_sections(operation, report),
    }


def monitoring_snapshot(operation, plan=None, sections=None) -> dict:
    """Four timeline marks, plus activity counts by sector and status.

    The operation page already holds the latest plan and its sections, so it
    passes them in rather than reading them again.
    """
    if plan is None:
        plan = latest_plan(operation.id)
    confirmed = plan.validated_at.date() if plan is not None and plan.validated_at else None
    events = [
        {
            "date": operation.date_of_approval,
            "label": "Approved",
            "state": "done" if operation.date_of_approval else "upcoming",
        },
        {
            "date": confirmed,
            "label": "Plan confirmed",
            "state": "done" if confirmed else "upcoming",
        },
    ]
    filed_count = 0
    period_count = 0
    next_update = None
    next_overdue = False
    for period in periods_for(operation.id):
        period_count += 1
        report = report_for_period(period.id)
        filed = report is not None and report.status != REPORT_DRAFT
        if filed:
            filed_count += 1
        elif next_update is None:
            next_overdue = period.status == "overdue" or (period.due_date is not None and period.due_date < date.today())
            next_update = {"date": period.due_date, "label": "Next update", "state": "current"}
    if next_update is not None:
        events.append(next_update)
    elif period_count:
        events.append({"date": None, "label": "Updates filed", "state": "done"})
    if operation.end_date:
        events.append(
            {
                "date": operation.end_date,
                "label": "Operation ends",
                "state": "done" if operation.operation_status == "closed" else "upcoming",
            }
        )
    known = (ACTIVITY_PLANNED, ACTIVITY_ONGOING, ACTIVITY_COMPLETED, ACTIVITY_BLOCKED, ACTIVITY_DELAYED)
    status_counts = {key: 0 for key in known}
    by_sector = []
    if plan is not None:
        if sections is None:
            sections = plan_sections(plan.id)
        for section in sections:
            for activity in section["activities"]:
                status_counts[activity.status] = status_counts.get(activity.status, 0) + 1
            by_sector.append({"label": section["group"].label, "count": len(section["activities"])})
    by_status = [{"key": key, "count": status_counts[key]} for key in known]
    return {
        "events": events,
        "by_status": by_status,
        "by_sector": by_sector,
        "status_chart": _chart_background(by_status),
        "sector_chart": _chart_background(by_sector),
        "period_count": period_count,
        "filed_count": filed_count,
        "next_overdue": next_overdue,
    }


def set_funds(operation, form, actor) -> str | None:
    if not actor.allows(operation, "enter"):
        return "You cannot update funds for this operation."
    received = as_bool(form.get("funds_received"))
    received_on = as_date(form.get("funds_received_on"))
    operation.funds_received = received
    operation.funds_received_on = received_on
    db.session.add(
        DrefFundsEvent(
            operation_id=operation.id,
            received=received,
            received_on=received_on,
            note=str(form.get("note") or "")[:1000],
            user_id=actor.user_id,
        )
    )
    db.session.commit()
    return None


def add_procurement(operation, form, actor) -> str | None:
    if not actor.allows(operation, "enter"):
        return "You cannot update procurement for this operation."
    item_id = as_int(form.get("procurement_id"))
    milestone = str(form.get("milestone") or "not_started")
    if milestone not in PROCUREMENT_MILESTONES:
        return "Unknown procurement milestone."
    if item_id:
        row = db.session.get(DrefProcurement, item_id)
        if row is None or row.operation_id != operation.id:
            return "Procurement item not found."
        row.milestone = milestone
        row.note = str(form.get("note") or "")[:1000]
        if str(form.get("item") or "").strip():
            row.item = str(form.get("item")).strip()[:255]
    else:
        item = str(form.get("item") or "").strip()
        if not item:
            return "Name the item being procured."
        db.session.add(
            DrefProcurement(operation_id=operation.id, item=item[:255], milestone=milestone, note=str(form.get("note") or "")[:1000])
        )
    db.session.commit()
    return None


def _activity_on_operation(operation, activity_id: int) -> bool:
    """True when the activity sits on any plan version of this operation."""
    activity = db.session.get(DrefActivity, activity_id)
    if activity is None:
        return False
    group = db.session.get(DrefGroup, activity.group_id)
    plan = db.session.get(DrefPlan, group.plan_id) if group is not None else None
    return plan is not None and plan.operation_id == operation.id


def add_delay(operation, form, actor) -> str | None:
    if not actor.allows(operation, "enter"):
        return "You cannot log a delay on this operation."
    reason = str(form.get("reason") or "").strip()
    if not reason:
        return "Describe the delay."
    activity_id = as_int(form.get("activity_id"))
    if activity_id and not _activity_on_operation(operation, activity_id):
        return "Activity not found."
    report_id = as_int(form.get("report_id"))
    if report_id:
        report = db.session.get(DrefReport, report_id)
        if report is None or report.operation_id != operation.id:
            return "Report not found."
    db.session.add(
        DrefDelay(
            operation_id=operation.id,
            activity_id=activity_id,
            report_id=report_id,
            reason=reason,
            created_by_user_id=actor.user_id,
        )
    )
    db.session.commit()
    return None


def add_feedback(operation, form, actor) -> str | None:
    if not actor.allows(operation, "enter"):
        return "You cannot add feedback on this operation."
    summary = str(form.get("summary") or "").strip()
    if not summary:
        return "Summarise the feedback."
    db.session.add(
        DrefFeedback(
            operation_id=operation.id,
            channel=str(form.get("channel") or "")[:80],
            summary=summary,
            received_on=as_date(form.get("received_on")),
            created_by_user_id=actor.user_id,
        )
    )
    db.session.commit()
    return None


def add_risk(operation, form, actor) -> str | None:
    if not actor.allows(operation, "enter"):
        return "You cannot add a risk on this operation."
    title = str(form.get("title") or "").strip()
    if not title:
        return "Name the risk."
    likelihood = str(form.get("likelihood") or "medium")
    impact = str(form.get("impact") or "medium")
    status = str(form.get("status") or "open")
    if likelihood not in RISK_LEVELS or impact not in RISK_LEVELS or status not in RISK_STATUSES:
        return "Unknown risk value."
    mitigation = "" if status == "open" else str(form.get("mitigation") or "")
    risk_id = as_int(form.get("risk_id"))
    if risk_id:
        row = db.session.get(DrefRisk, risk_id)
        if row is None or row.operation_id != operation.id:
            return "Risk not found."
        row.title = title[:255]
        row.likelihood = likelihood
        row.impact = impact
        row.status = status
        row.mitigation = mitigation
    else:
        db.session.add(
            DrefRisk(
                operation_id=operation.id,
                title=title[:255],
                likelihood=likelihood,
                impact=impact,
                mitigation=mitigation,
                status=status,
                created_by_user_id=actor.user_id,
            )
        )
    db.session.commit()
    return None


def updates_for(report_id: int) -> dict[int, DrefActivityUpdate]:
    return {row.activity_id: row for row in DrefActivityUpdate.query.filter_by(report_id=report_id).all()}


def values_for(report_id: int) -> dict[int, DrefIndicatorValue]:
    return {row.indicator_id: row for row in DrefIndicatorValue.query.filter_by(report_id=report_id).all()}
