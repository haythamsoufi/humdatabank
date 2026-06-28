"""Orchestrator for template-agnostic data quality scoring."""

from __future__ import annotations

from app import db
from app.models import FormData, FormTemplate
from app.models.assignments import AssignmentEntityStatus, AssignedForm
from app.models.forms import FormTemplateVersion
from app.services.data_quality.helpers import get_assignment_aes
from app.services.reporting_period_service import period_chronology_sort_key
from app.services.data_quality.methodologies import get_methodology
from app.services.data_quality.types import DataQualityResult
from app.utils.data_quality_constants import METHODOLOGY_TO_DEFAULT_RULE_PACK


def get_methodology_for_template(template: FormTemplate) -> str | None:
    pv = template.published_version
    if pv and getattr(pv, "enable_data_quality", False):
        return pv.data_quality_methodology
    return None


def get_rule_pack_for_template(template: FormTemplate) -> str | None:
    pv = template.published_version
    if not pv or not getattr(pv, "enable_data_quality", False):
        return None
    pack = getattr(pv, "validation_rule_pack", None)
    if pack:
        return pack
    methodology = pv.data_quality_methodology
    if methodology:
        return METHODOLOGY_TO_DEFAULT_RULE_PACK.get(methodology)
    return None


def compute_data_quality(
    *,
    template_id: int,
    entity_type: str,
    entity_id: int,
    period_name: str,
    assignment_entity_status_id: int | None = None,
) -> DataQualityResult:
    template = FormTemplate.query.get(template_id)
    if not template or not template.published_version:
        raise ValueError(f"Template {template_id} has no published version.")

    methodology_code = template.published_version.data_quality_methodology
    if not methodology_code:
        raise ValueError(f"Template {template_id} has no data_quality_methodology configured.")

    methodology = get_methodology(methodology_code)
    return methodology.compute(
        template_id=template_id,
        entity_type=entity_type,
        entity_id=entity_id,
        period_name=period_name,
        assignment_entity_status_id=assignment_entity_status_id,
    )


def list_data_quality_templates_for_entity(
    entity_type: str,
    entity_id: int,
) -> list[dict]:
    """Templates with QoD enabled that the entity has assignments for."""
    rows = (
        db.session.query(FormTemplate.id, AssignedForm.period_name)
        .join(AssignedForm, AssignedForm.template_id == FormTemplate.id)
        .join(
            AssignmentEntityStatus,
            AssignmentEntityStatus.assigned_form_id == AssignedForm.id,
        )
        .join(
            FormTemplateVersion,
            FormTemplate.published_version_id == FormTemplateVersion.id,
        )
        .filter(
            AssignmentEntityStatus.entity_type == entity_type,
            AssignmentEntityStatus.entity_id == entity_id,
            FormTemplateVersion.enable_data_quality == True,
        )
        .distinct()
        .all()
    )

    template_ids = {r[0] for r in rows}
    templates = FormTemplate.query.filter(FormTemplate.id.in_(template_ids)).all() if template_ids else []

    result = []
    for tmpl in templates:
        pv = tmpl.published_version
        if not pv or not getattr(pv, "enable_data_quality", False):
            continue
        period_names = {r[1] for r in rows if r[0] == tmpl.id and r[1]}

        def _period_rank(period_name: str) -> tuple[int, tuple]:
            aes = get_assignment_aes(tmpl.id, entity_type, entity_id, period_name)
            if aes is None:
                data_rank = 0
                chrono = period_chronology_sort_key(period_name)
            else:
                data_count = FormData.query.filter_by(assignment_entity_status_id=aes.id).count()
                data_rank = 1 if data_count > 0 else 0
                assigned_form = aes.assigned_form
                chrono = period_chronology_sort_key(
                    assigned_form.period_name if assigned_form else period_name,
                    period_start=getattr(assigned_form, "period_start", None),
                    period_end=getattr(assigned_form, "period_end", None),
                )
            return (data_rank, chrono)

        periods = sorted(period_names, key=_period_rank, reverse=True)
        result.append(
            {
                "template_id": tmpl.id,
                "template_name": tmpl.name,
                "methodology": pv.data_quality_methodology,
                "validation_rule_pack": get_rule_pack_for_template(tmpl),
                "periods": periods,
            }
        )
    return result
