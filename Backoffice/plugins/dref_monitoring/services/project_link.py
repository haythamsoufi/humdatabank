"""Turn a DREF operation into a project and one report cycle per period."""

from __future__ import annotations

import datetime as dt

from app.extensions import db
from app.models.assignments import AssignedForm
from app.services.projects.service import ensure_project_cycle_assignment, parse_cycle_slot, upsert_project
from plugins.dref_monitoring.constants import PORTFOLIO
from plugins.dref_monitoring.models import DrefOperation, DrefPeriod, DrefPlan
from plugins.dref_monitoring.services.go_parse import appeal_kind
from plugins.dref_monitoring.services.plans import latest_plan


def fund_label(appeal_type: str) -> str:
    """Portfolio fund tag: DREF, i-DREF, or EA."""
    kind = appeal_kind(appeal_type)
    if kind in {"i-dref", "idref"}:
        return "i-DREF"
    if kind in {"ea", "emergency-appeal"}:
        return "EA"
    return "DREF"


def project_status_for(operation: DrefOperation) -> str:
    if (operation.operation_status or "").strip().lower() == "closed":
        return "Closed"
    return "Open"


def sync_operation_project(operation: DrefOperation):
    """Create or update the project for this operation. None when the country is unknown."""
    if not operation.country_id:
        return None
    amount = operation.total_approved if operation.total_approved is not None else operation.amount_approved
    project = upsert_project(
        reference=operation.appeal_code,
        country_id=int(operation.country_id),
        title=(operation.disaster_name or operation.appeal_code)[:500],
        portfolio=PORTFOLIO,
        fund=fund_label(operation.appeal_type),
        status=project_status_for(operation),
        start_date=operation.start_date,
        end_date=operation.end_date,
        amount_granted=amount,
        plan_data={"dref_operation_id": operation.id},
    )
    operation.project_id = project.id
    return project


def cycle_slot(start: dt.date, sequence: int, used: set[str]) -> str:
    """Period label after the appeal code. ``2026-08``, or the start date when that month is taken."""
    month = start.strftime("%Y-%m")
    if month not in used:
        return month
    day = start.isoformat()
    if day not in used:
        return day
    return f"{day}-{sequence}"


def ensure_monitoring_template(operation: DrefOperation):
    """Update the published DREF operational monitoring template for this operation's sectors."""
    from plugins.dref_monitoring.services.report_template import ensure_operation_template

    return ensure_operation_template(operation)


def _used_slots(periods: list[DrefPeriod]) -> set[str]:
    used: set[str] = set()
    for period in periods:
        if not period.assigned_form_id:
            continue
        assignment = db.session.get(AssignedForm, period.assigned_form_id)
        if assignment is None:
            period.assigned_form_id = None
            continue
        slot = parse_cycle_slot(assignment.period_name)
        if slot:
            used.add(slot)
    return used


def open_cycles(operation: DrefOperation) -> int:
    """Open one project cycle per period that does not have one yet. Returns how many were attached."""
    from plugins.dref_monitoring.services.reporting import ensure_periods, periods_for

    ensure_periods(operation)
    project = sync_operation_project(operation)
    if project is None:
        return 0
    template = ensure_monitoring_template(operation)
    periods = periods_for(operation.id)
    used = _used_slots(periods)
    attached = 0
    for period in sorted(periods, key=lambda row: (row.start_date, row.sequence)):
        assignment = db.session.get(AssignedForm, period.assigned_form_id) if period.assigned_form_id else None
        if assignment is not None:
            if assignment.template_id != template.id:
                assignment.template_id = template.id
            continue
        slot = cycle_slot(period.start_date, period.sequence, used)
        used.add(slot)
        due = dt.datetime.combine(period.due_date, dt.time.min)
        assignment, _aes = ensure_project_cycle_assignment(
            project,
            template.id,
            slot,
            period_start=period.start_date,
            period_end=period.end_date,
            due_date=due,
        )
        period.assigned_form_id = assignment.id
        attached += 1
    db.session.flush()
    return attached


def backfill_projects() -> dict:
    """Create missing projects, and cycles where the latest plan is already validated."""
    from plugins.dref_monitoring.constants import PLAN_VALIDATED

    projects = 0
    cycles = 0
    skipped = 0
    for operation in DrefOperation.query.order_by(DrefOperation.id.asc()).all():
        if not operation.country_id:
            skipped += 1
            continue
        if sync_operation_project(operation) is None:
            skipped += 1
            continue
        projects += 1
        plan: DrefPlan | None = latest_plan(operation.id)
        if plan is not None and plan.status == PLAN_VALIDATED:
            cycles += open_cycles(operation)
    db.session.commit()
    return {"projects": projects, "cycles": cycles, "skipped": skipped}
