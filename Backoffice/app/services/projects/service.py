"""Core project registry helpers used by Admin UI and plugins."""

from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional, Tuple

from app import db
from app.models.assignments import AssignmentEntityStatus, AssignedForm
from app.models.enums import AssignmentEntityStatusValue, AssignmentScope, EntityType
from app.models.projects import Project
from app.utils.datetime_helpers import utcnow

# Separator in period_name for project_cycle assignments: "<reference> · Y1Q2"
CYCLE_PERIOD_SEP = " · "


def cycle_period_name(reference: str, slot: str) -> str:
    """Unique AssignedForm.period_name for one project report cycle."""
    ref = (reference or "").strip()
    label = (slot or "").strip()
    if not ref or not label:
        raise ValueError("reference and slot are required for a project cycle period name")
    name = f"{ref}{CYCLE_PERIOD_SEP}{label}"
    if len(name) > 100:
        # Keep the slot; trim the reference so the unique key still fits.
        keep = 100 - len(CYCLE_PERIOD_SEP) - len(label)
        name = f"{ref[:keep]}{CYCLE_PERIOD_SEP}{label}"
    return name


def parse_cycle_slot(period_name: str) -> Optional[str]:
    """Return the slot label (Y1Q2 / Final) from a cycle or legacy shared period_name."""
    import re

    raw = (period_name or "").strip()
    if not raw:
        return None
    if CYCLE_PERIOD_SEP in raw:
        return raw.rsplit(CYCLE_PERIOD_SEP, 1)[-1].strip() or None
    # Shared-slot legacy (bare Y1Q2 / Final) or "ref - Y1Q2" / "ref Y1Q2"
    if raw == "Final" or re.match(r"^Y\d+Q\d+$", raw):
        return raw
    if " - " in raw:
        tail = raw.rsplit(" - ", 1)[-1].strip()
        if tail == "Final" or re.match(r"^Y\d+Q\d+$", tail):
            return tail
    if " " in raw:
        tail = raw.rsplit(" ", 1)[-1].strip()
        if tail == "Final" or re.match(r"^Y\d+Q\d+$", tail):
            return tail
    return None


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
    previous_open = None
    if proj is None:
        proj = Project(reference=ref, country_id=int(country_id))
        db.session.add(proj)
    else:
        previous_open = proj.is_open

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
        raw_status = (status or "").strip()
        proj.status = raw_status.capitalize() if raw_status else "Open"
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

    if previous_open is not None and previous_open != proj.is_open:
        sync_project_cycle_closure(proj)
    return proj


def sync_cycle_names_for_project(project: Project) -> int:
    """Rewrite period_name / custom_name on cycle assignments after a reference change."""
    touched = 0
    for af in list_project_cycle_assignments(project):
        slot = parse_cycle_slot(af.period_name)
        if not slot:
            continue
        new_period = cycle_period_name(project.reference, slot)
        new_custom = f"{project.reference}{CYCLE_PERIOD_SEP}{slot}"
        if af.period_name != new_period or af.custom_name != new_custom:
            af.period_name = new_period
            af.custom_name = new_custom
            touched += 1
    return touched


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


def ensure_project_cycle_assignment(
    project: Project,
    template_id: int,
    slot: str,
    *,
    period_start=None,
    period_end=None,
    due_date=None,
    is_active: Optional[bool] = None,
) -> Tuple[AssignedForm, AssignmentEntityStatus]:
    """Get-or-create a per-project report assignment and its single AES.

    ``slot`` is the relative period label (``Y1Q2``, ``Final``, …).
    """
    period = cycle_period_name(project.reference, slot)
    af = AssignedForm.query.filter_by(
        template_id=int(template_id),
        period_name=period,
    ).first()
    if af is None:
        # Also match by project_id + slot in case the reference was renamed mid-flight
        candidates = AssignedForm.query.filter_by(
            project_id=project.id,
            scope=AssignmentScope.project_cycle.value,
            template_id=int(template_id),
        ).all()
        for cand in candidates:
            if parse_cycle_slot(cand.period_name) == slot:
                af = cand
                af.period_name = period
                break
    created = af is None
    if af is None:
        af = AssignedForm(
            template_id=int(template_id),
            period_name=period,
            scope=AssignmentScope.project_cycle.value,
            project_id=project.id,
            custom_name=f"{project.reference}{CYCLE_PERIOD_SEP}{slot}",
            is_active=True if is_active is None else bool(is_active),
            is_closed=not project.is_open,
        )
        db.session.add(af)
        db.session.flush()
    else:
        af.scope = AssignmentScope.project_cycle.value
        af.project_id = project.id
        af.custom_name = af.custom_name or f"{project.reference}{CYCLE_PERIOD_SEP}{slot}"
        if is_active is not None:
            af.is_active = bool(is_active)
        # Closing the project closes all cycles; do not reopen admin-closed cycles on import.
        if not project.is_open:
            af.is_closed = True

    if period_start is not None:
        af.period_start = period_start.date() if isinstance(period_start, dt.datetime) else period_start
    if period_end is not None:
        af.period_end = period_end.date() if isinstance(period_end, dt.datetime) else period_end

    aes = ensure_project_on_assignment(af, project, due_date=due_date)
    if created:
        af  # noqa: B018 — clarity for callers checking identity
    return af, aes


def sync_project_cycle_closure(project: Project) -> int:
    """Mirror project open/closed onto its project_cycle assignments. Returns rows touched."""
    cycles = AssignedForm.query.filter_by(
        project_id=project.id,
        scope=AssignmentScope.project_cycle.value,
    ).all()
    want_closed = not project.is_open
    touched = 0
    for af in cycles:
        if af.is_closed != want_closed:
            af.is_closed = want_closed
            touched += 1
        if want_closed:
            # Closing a project also clears per-entity reopen flags
            for aes in AssignmentEntityStatus.query.filter_by(assigned_form_id=af.id).all():
                aes.reopened_after_close = False
        else:
            af.is_active = True
    return touched


def list_project_cycle_assignments(project: Project) -> List[AssignedForm]:
    return (
        AssignedForm.query.filter_by(
            project_id=project.id,
            scope=AssignmentScope.project_cycle.value,
        )
        .order_by(AssignedForm.period_name.asc())
        .all()
    )


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
