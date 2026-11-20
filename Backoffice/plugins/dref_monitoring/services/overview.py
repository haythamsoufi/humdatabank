"""Portfolio figures for the Data Explorer tab."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from plugins.dref_monitoring.constants import ACTIVITY_COMPLETED, WORKFLOW_MONITORING, WORKFLOW_PLAN_DRAFT
from plugins.dref_monitoring.models import (
    DrefActivity,
    DrefActivityUpdate,
    DrefChangeRequest,
    DrefGroup,
    DrefOperation,
    DrefPeriod,
    DrefPlan,
    DrefReport,
)


def _money(value) -> float:
    if value is None:
        return 0.0
    return float(Decimal(value))


def build_overview(today: date | None = None) -> dict:
    today = today or date.today()
    operations = DrefOperation.query.order_by(DrefOperation.end_date.desc()).all()
    pending = DrefChangeRequest.query.filter_by(status="pending").count()
    overdue = 0
    rows = []
    approved = 0.0
    reported = 0.0
    people_reached = 0
    households_reached = 0
    activities_completed = 0
    for operation in operations:
        approved += _money(operation.total_approved)
        periods = DrefPeriod.query.filter_by(operation_id=operation.id).all()
        operation_overdue = False
        for period in periods:
            report = DrefReport.query.filter_by(period_id=period.id).first()
            submitted = report is not None and report.status != "draft"
            if period.due_date < today and not submitted and operation.operation_status != "closed":
                operation_overdue = True
        if operation_overdue:
            overdue += 1
        latest = (
            DrefReport.query.filter_by(operation_id=operation.id)
            .order_by(DrefReport.id.desc())
            .first()
        )
        spent = _money(latest.expenditure_total) if latest else 0.0
        reported += spent
        people = 0
        households = 0
        if latest is not None:
            for update in DrefActivityUpdate.query.filter_by(report_id=latest.id):
                people += int(update.people_individuals or 0)
                households += int(update.people_households or 0)
        people_reached += people
        households_reached += households
        plan = (
            DrefPlan.query.filter_by(operation_id=operation.id)
            .order_by(DrefPlan.version.desc())
            .first()
        )
        completed = 0
        if plan is not None:
            completed = (
                DrefActivity.query.join(DrefGroup, DrefActivity.group_id == DrefGroup.id)
                .filter(DrefGroup.plan_id == plan.id, DrefActivity.status == ACTIVITY_COMPLETED)
                .count()
            )
        activities_completed += completed
        rows.append(
            {
                "id": operation.id,
                "appeal_code": operation.appeal_code,
                "country": operation.country_name,
                "iso3": operation.country_iso3,
                "hazard": operation.hazard,
                "workflow": operation.workflow_status,
                "status": operation.operation_status,
                "approved_chf": _money(operation.total_approved),
                "reported_chf": spent,
                "people_reached": people,
                "households_reached": households,
                "activities_completed": completed,
                "overdue": operation_overdue,
                "funds_received": bool(operation.funds_received),
            }
        )
    return {
        "active": sum(1 for row in rows if row["status"] == "active"),
        "plan_draft": sum(1 for row in rows if row["workflow"] == WORKFLOW_PLAN_DRAFT),
        "monitoring": sum(1 for row in rows if row["workflow"] == WORKFLOW_MONITORING),
        "overdue": overdue,
        "pending_changes": pending,
        "approved_chf": approved,
        "reported_chf": reported,
        "people_reached": people_reached,
        "households_reached": households_reached,
        "activities_completed": activities_completed,
        "operations": rows[:50],
    }
