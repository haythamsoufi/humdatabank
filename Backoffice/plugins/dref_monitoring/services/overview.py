"""Portfolio figures for the Data Explorer tab."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from plugins.dref_monitoring.constants import WORKFLOW_MONITORING, WORKFLOW_PLAN_DRAFT
from plugins.dref_monitoring.models import (
    DrefChangeRequest,
    DrefOperation,
    DrefPeriod,
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
        "operations": rows[:50],
    }
