"""NSD CBF schedule: per-project report cycles on core Project AES rows."""
from __future__ import annotations

import datetime as dt
import logging
from typing import List, Optional, Tuple

from app import db
from app.models import FormTemplate, FormTemplateVersion
from app.models.projects import Project
from app.services.projects.service import (
    ensure_project_cycle_assignment,
    upsert_project,
)

from plugins.nsd_report_forms.constants import (
    FINAL_SLOT,
    FINAL_TEMPLATE_KEY,
    QUARTER_TEMPLATE_KEY,
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


def ensure_cbf_templates_ready() -> Tuple[int, int]:
    """Ensure published CBF quarter + final templates exist. Returns (quarter_id, final_id)."""
    from plugins.nsd_report_forms.ensure_templates import ensure_cbf_report_templates

    ensure_cbf_report_templates(commit=True)
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
    return q_tpl, f_tpl


def slot_for_schedule_row(report_type: str, period: str) -> Optional[Tuple[str, str]]:
    if report_type == layout.FINAL_PERIOD or report_type == "CBF final report":
        return FINAL_TEMPLATE_KEY, FINAL_SLOT
    if report_type == "CBF quarter":
        parsed = parse_quarter_slot(period)
        if not parsed:
            return None
        return QUARTER_TEMPLATE_KEY, period.strip()
    return None


def _sync_audience(af, slot: str) -> None:
    """Apply NSD Access Group audience on a per-project cycle assignment."""
    try:
        from plugins.nsd_report_forms.importer import restrictions

        is_final = (slot or "").strip() == FINAL_SLOT
        restrictions.sync_nsd_audience_on_assignment(
            af.id,
            allow_focal=is_final,
            allow_pm=True,
        )
    except Exception as exc:
        log.warning(
            "NSD schedule: could not sync Access Groups on %s: %s",
            af.period_name,
            exc,
        )


def ensure_project_aes(project: Project, slot: str, *, due=None, active=None, template_id=None):
    """AES for this project on its own cycle assignment for ``slot`` (Y1Q2 / Final)."""
    if template_id is None:
        key = FINAL_TEMPLATE_KEY if slot == FINAL_SLOT else QUARTER_TEMPLATE_KEY
        template_id = _template_id(key)
        if template_id is None:
            raise RuntimeError(f"NSD template missing for slot {slot}")
    want_active = project.is_open if active is None else active
    af, aes = ensure_project_cycle_assignment(
        project,
        int(template_id),
        slot,
        due_date=due,
        is_active=want_active,
    )
    _sync_audience(af, slot)
    return aes


def apply_schedule(project: Project, schedule_rows: List[dict]):
    """Create per-project cycle assignments for each scheduled report row."""
    ensure_cbf_templates_ready()
    created = []
    for row in schedule_rows:
        mapped = slot_for_schedule_row(row.get("report_type") or "", row.get("period") or "")
        if not mapped:
            continue
        key, slot_name = mapped
        tpl_id = _template_id(key)
        if tpl_id is None:
            continue
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
        created.append(ensure_project_aes(project, slot_name, due=due, template_id=tpl_id))
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


# Backwards-compatible aliases (callers that still expect shared slots)
def ensure_shared_slots(max_years: int = 3):
    """Deprecated: templates only. Returns empty dict — cycles are per-project now."""
    ensure_cbf_templates_ready()
    log.info("NSD schedule: ensure_shared_slots is a no-op; use per-project cycles")
    return {}
