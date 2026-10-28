"""Core project registry helpers used by Admin UI and plugins."""

from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

from app import db
from app.models.assignments import AssignmentEntityStatus, AssignedForm
from app.models.enums import AssignmentEntityStatusValue, EntityType
from app.models.projects import Project
from app.utils.datetime_helpers import utcnow


def upsert_project(
    *,
    reference: str,
    country_id: int,
    title: Optional[str] = None,
    portfolio: Optional[str] = None,
    fund: Optional[str] = None,
    organization_name: Optional[str] = None,
    status: Optional[str] = None,
    funding_modality: Optional[str] = None,
    categories: Optional[str] = None,
    start_date=None,
    end_date=None,
    amount_granted=None,
    expected_spending=None,
    planned_overview: Optional[str] = None,
    focal_name: Optional[str] = None,
    focal_email: Optional[str] = None,
    manager_name: Optional[str] = None,
    manager_email: Optional[str] = None,
    plan_data=None,
    **_extra: Any,
) -> Project:
    """Create or update a project by unique ``reference``."""
    ref = (reference or "").strip()
    if not ref:
        raise ValueError("project reference is required")
    proj = Project.query.filter_by(reference=ref).first()
    if proj is None:
        proj = Project(reference=ref, country_id=int(country_id))
        db.session.add(proj)

    def _date(v):
        if v is None or v == "":
            return None
        if isinstance(v, dt.datetime):
            return v.date()
        if isinstance(v, dt.date):
            return v
        try:
            return dt.date.fromisoformat(str(v)[:10])
        except ValueError:
            return None

    def _money(v):
        if v in (None, ""):
            return None
        try:
            return float(str(v).replace(",", "").replace(" ", ""))
        except ValueError:
            return None

    proj.country_id = int(country_id)
    if title is not None:
        proj.title = title
    if portfolio is not None:
        proj.portfolio = (portfolio or "").strip() or None
    if fund is not None:
        proj.fund = fund
    if organization_name is not None:
        proj.organization_name = organization_name
    if status is not None:
        proj.status = status or "Open"
    if funding_modality is not None:
        proj.funding_modality = funding_modality
    if categories is not None:
        proj.categories = categories
    sd = _date(start_date)
    if start_date is not None:
        proj.start_date = sd
    ed = _date(end_date)
    if end_date is not None:
        proj.end_date = ed
    if amount_granted is not None:
        proj.amount_granted = _money(amount_granted)
    if expected_spending is not None:
        proj.expected_spending = _money(expected_spending)
    if planned_overview is not None:
        proj.planned_overview = planned_overview
    if focal_name is not None:
        proj.focal_name = focal_name
    if focal_email is not None:
        proj.focal_email = (focal_email or "").strip() or None
    if manager_name is not None:
        proj.manager_name = manager_name
    if manager_email is not None:
        proj.manager_email = (manager_email or "").strip() or None
    if plan_data is not None:
        proj.plan_data = plan_data
    proj.updated_at = utcnow()
    db.session.flush()
    return proj


def ensure_project_on_assignment(
    assignment: AssignedForm,
    project: Project,
    *,
    due_date=None,
    status: AssignmentEntityStatusValue = AssignmentEntityStatusValue.pending,
) -> AssignmentEntityStatus:
    """Attach a project to an assignment (one AES per project per assignment)."""
    aes = AssignmentEntityStatus.query.filter_by(
        assigned_form_id=assignment.id,
        entity_type=EntityType.project.value,
        entity_id=project.id,
    ).first()
    if aes is None:
        aes = AssignmentEntityStatus(
            assigned_form_id=assignment.id,
            entity_type=EntityType.project.value,
            entity_id=project.id,
            status=status,
            due_date=due_date,
        )
        db.session.add(aes)
        db.session.flush()
    elif due_date is not None:
        aes.due_date = due_date
    return aes


def get_projects_for_country(country_id: int) -> List[Project]:
    return (
        Project.query.filter_by(country_id=int(country_id))
        .order_by(Project.reference.asc())
        .all()
    )


def project_to_admin_dict(p: Project) -> Dict[str, Any]:
    return {
        "id": p.id,
        "reference": p.reference,
        "title": p.title or "",
        "portfolio": p.portfolio or "",
        "fund": p.fund or "",
        "status": p.status or "",
        "country_id": p.country_id,
        "organization_name": p.organization_name or "",
        "name": p.name,
    }
