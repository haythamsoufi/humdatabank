"""NSD CBF schedule: shared relative slots (Y1Q1…Final) on core Project AES rows."""
from __future__ import annotations

import datetime as dt
import logging
from typing import Dict, List, Optional, Tuple

from app import db
from app.models import AssignedForm, FormTemplate, FormTemplateVersion
from app.models.projects import Project
from app.services.projects.service import ensure_project_on_assignment, upsert_project
from app.utils.datetime_helpers import utcnow

from plugins.nsd_report_forms.constants import (
    FINAL_SLOT,
    FINAL_TEMPLATE_KEY,
    QUARTER_TEMPLATE_KEY,
    all_quarter_slots,
    parse_quarter_slot,
)
from plugins.nsd_report_forms.importer import layout

log = logging.getLogger(__name__)


def _template_id(key: str) -> Optional[int]:
    name = layout.TEMPLATE_NAMES[key]
    row = (
        db.session.query(FormTemplate.id)
        .join(FormTemplateVersion, FormTemplateVersion.id == FormTemplate.published_version_id)
        .filter(FormTemplateVersion.name == name)
        .first()
    )
    return int(row[0]) if row else None


def ensure_shared_slots(max_years: int = 3) -> Dict[str, AssignedForm]:
    """Create/find shared AssignedForms for all quarter slots + Final. Keyed by period_name."""
    from plugins.nsd_report_forms.ensure_templates import ensure_cbf_report_templates

    ensure_cbf_report_templates(commit=True)

    out: Dict[str, AssignedForm] = {}
    q_tpl = _template_id(QUARTER_TEMPLATE_KEY)
    f_tpl = _template_id(FINAL_TEMPLATE_KEY)
    if q_tpl is None or f_tpl is None:
        missing = []
        if q_tpl is None:
            missing.append(layout.TEMPLATE_NAMES[QUARTER_TEMPLATE_KEY])
        if f_tpl is None:
            missing.append(layout.TEMPLATE_NAMES[FINAL_TEMPLATE_KEY])
        raise RuntimeError(
            "NSD report templates are not published: " + ", ".join(missing)
        )

    for slot in all_quarter_slots(max_years):
        out[slot] = _get_or_create_slot(q_tpl, slot, is_active=True)
    out[FINAL_SLOT] = _get_or_create_slot(f_tpl, FINAL_SLOT, is_active=True)
    return out


def _get_or_create_slot(template_id: int, period_name: str, is_active: bool) -> AssignedForm:
    af = AssignedForm.query.filter_by(template_id=template_id, period_name=period_name).first()
    if af is None:
        af = AssignedForm(
            template_id=template_id,
            period_name=period_name,
            is_active=is_active,
            custom_name=f"NSD CBF — {period_name}",
        )
        db.session.add(af)
        db.session.flush()
        log.info("NSD schedule: created shared slot %s (template %s)", period_name, template_id)
    _ensure_slot_nsd_audience(af)
    return af


def _ensure_slot_nsd_audience(af: AssignedForm) -> None:
    """Restrict shared NSD slots by Access Group.

    - Final: NSD Focal Points + NSD PMs
    - Quarters (Y1Q1…): NSD PMs only
    """
    try:
        from plugins.nsd_report_forms.importer import restrictions

        is_final = (af.period_name or "").strip() == FINAL_SLOT
        restrictions.sync_nsd_audience_on_assignment(
            af.id,
            allow_focal=is_final,
            allow_pm=True,
        )
    except Exception as exc:
        log.warning("NSD schedule: could not sync Access Groups on slot %s: %s", af.period_name, exc)


def slot_for_schedule_row(report_type: str, period: str) -> Optional[Tuple[str, str]]:
    if report_type == layout.FINAL_PERIOD or report_type == "CBF final report":
        return FINAL_TEMPLATE_KEY, FINAL_SLOT
    if report_type == "CBF quarter":
        parsed = parse_quarter_slot(period)
        if not parsed:
            return None
        return QUARTER_TEMPLATE_KEY, period.strip()
    return None


def ensure_project_aes(project: Project, slot_af: AssignedForm, *, due=None, active=None):
    """AES for this project on the shared slot (core helper)."""
    aes = ensure_project_on_assignment(slot_af, project, due_date=due)
    want_active = project.is_open if active is None else active
    if want_active and not slot_af.is_active:
        slot_af.is_active = True
    return aes


def apply_schedule(project: Project, schedule_rows: List[dict], *, slots=None):
    slots = slots or ensure_shared_slots()
    created = []
    for row in schedule_rows:
        mapped = slot_for_schedule_row(row.get("report_type") or "", row.get("period") or "")
        if not mapped:
            continue
        _, slot_name = mapped
        af = slots.get(slot_name)
        if af is None:
            key = QUARTER_TEMPLATE_KEY if slot_name != FINAL_SLOT else FINAL_TEMPLATE_KEY
            tpl_id = _template_id(key)
            if tpl_id is None:
                continue
            af = _get_or_create_slot(tpl_id, slot_name, is_active=True)
            slots[slot_name] = af
        due = None
        raw_due = row.get("deadline") or ""
        if raw_due:
            try:
                due = dt.datetime.fromisoformat(str(raw_due)[:19])
            except ValueError:
                try:
                    due = dt.datetime.combine(dt.date.fromisoformat(str(raw_due)[:10]), dt.time.min)
                except ValueError:
                    due = None
        created.append(ensure_project_aes(project, af, due=due))
    return created


def upsert_project_from_import(p: dict, country_id: int, logframe=None) -> Project:
    """Map an NSD master-workbook Projects row onto the core Project registry."""
    return upsert_project(
        reference=(p.get("reference") or "").strip(),
        country_id=country_id,
        title=p.get("title"),
        portfolio="NSD",
        fund=(p.get("fund") or "CBF").strip() or "CBF",
        organization_name=p.get("ns_name"),
        status=p.get("status") or "Open",
        funding_modality=p.get("funding_modality"),
        categories=p.get("categories"),
        start_date=p.get("start_date"),
        end_date=p.get("end_date"),
        amount_granted=p.get("amount_granted_chf"),
        expected_spending=p.get("expected_spending_chf"),
        planned_overview=p.get("planned_overview"),
        focal_name=p.get("ns_focal_name"),
        focal_email=p.get("ns_focal_email"),
        manager_name=p.get("ifrc_pm_name"),
        manager_email=p.get("ifrc_pm_email"),
        plan_data=logframe,
    )
