"""Routine monitoring reports, funds, procurement, delays, feedback, and risks."""

from __future__ import annotations

from app.extensions import db
from plugins.dref_monitoring.constants import (
    ACTIVITY_COMPLETED,
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
    DrefIndicator,
    DrefIndicatorValue,
    DrefPeriod,
    DrefProcurement,
    DrefReport,
    DrefRisk,
)
from plugins.dref_monitoring.services.parsing import as_bool, as_date, as_int, as_money
from plugins.dref_monitoring.services.periods import build_periods
from plugins.dref_monitoring.services.plans import activities_for, groups_for, indicators_for_activity, latest_plan


def ensure_periods(operation) -> None:
    if not operation.start_date or not operation.end_date:
        return
    existing = {
        row.sequence
        for row in DrefPeriod.query.filter_by(operation_id=operation.id).all()
    }
    for sequence, start, end, due in build_periods(operation.start_date, operation.end_date, operation.reporting_frequency):
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


def _form_keys(form) -> set[str]:
    try:
        return {str(key) for key in form.keys()}
    except Exception:
        return set()


def _touches_activity(form, activity_id: int) -> bool:
    prefix = f"activity_{activity_id}_"
    return any(key.startswith(prefix) for key in _form_keys(form))


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
            return "Expenditure cannot be negative."

    total = 0
    saw_expenditure = False
    for _group, activity, indicators in _plan_activities(operation):
        if not _touches_activity(form, activity.id):
            continue
        status = str(form.get(f"activity_{activity.id}_status") or ACTIVITY_PLANNED)
        if status not in {ACTIVITY_PLANNED, ACTIVITY_ONGOING, ACTIVITY_COMPLETED}:
            status = ACTIVITY_PLANNED
        percent = as_int(form.get(f"activity_{activity.id}_percent"))
        if percent is not None:
            percent = max(0, min(percent, 100))
        households = as_int(form.get(f"activity_{activity.id}_households"))
        individuals = as_int(form.get(f"activity_{activity.id}_individuals"))
        expenditure = as_money(form.get(f"activity_{activity.id}_expenditure"))
        disaggregation = {
            "women": as_int(form.get(f"activity_{activity.id}_women")),
            "men": as_int(form.get(f"activity_{activity.id}_men")),
            "girls": as_int(form.get(f"activity_{activity.id}_girls")),
            "boys": as_int(form.get(f"activity_{activity.id}_boys")),
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
        update.expenditure = expenditure
        update.note = str(form.get(f"activity_{activity.id}_note") or "")[:2000]
        activity.status = status
        activity.percent = percent
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
                "women",
                "men",
                "girls",
                "boys",
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


def report_sections(operation, report) -> list:
    plan = latest_plan(operation.id)
    if plan is None or report is None:
        return []
    saved = updates_for(report.id)
    actuals = values_for(report.id)
    sections = []
    for group in groups_for(plan.id):
        activities = []
        for activity in activities_for(group.id):
            activities.append(
                {
                    "activity": activity,
                    "indicators": indicators_for_activity(activity.id),
                    "update": saved.get(activity.id),
                    "actuals": actuals,
                }
            )
        sections.append({"group": group, "activities": activities})
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


def add_delay(operation, form, actor) -> str | None:
    if not actor.allows(operation, "enter"):
        return "You cannot log a delay on this operation."
    reason = str(form.get("reason") or "").strip()
    if not reason:
        return "Describe the delay."
    activity_id = as_int(form.get("activity_id"))
    if activity_id:
        activity = db.session.get(DrefActivity, activity_id)
        if activity is None:
            return "Activity not found."
    db.session.add(
        DrefDelay(
            operation_id=operation.id,
            activity_id=activity_id,
            report_id=as_int(form.get("report_id")),
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
    risk_id = as_int(form.get("risk_id"))
    if risk_id:
        row = db.session.get(DrefRisk, risk_id)
        if row is None or row.operation_id != operation.id:
            return "Risk not found."
        row.title = title[:255]
        row.likelihood = likelihood
        row.impact = impact
        row.status = status
        row.mitigation = str(form.get("mitigation") or "")
    else:
        db.session.add(
            DrefRisk(
                operation_id=operation.id,
                title=title[:255],
                likelihood=likelihood,
                impact=impact,
                mitigation=str(form.get("mitigation") or ""),
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
