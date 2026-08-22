"""Bulk PNG export assignment/country listings."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models.assignments import AssignedForm, AssignmentEntityStatus
from plugins.upr_visuals.catalog import UPR_VISUAL_TEMPLATE_IDS, kind_for_template
from plugins.upr_visuals.errors import UprVisualsError

def list_assigned_forms_for_bulk() -> list[dict[str, Any]]:
    """Unified Plan and Report assignments available for bulk PNG generation."""
    rows = (
        AssignedForm.query.options(joinedload(AssignedForm.template))
        .filter(AssignedForm.template_id.in_(UPR_VISUAL_TEMPLATE_IDS))
        .order_by(
            AssignedForm.assigned_at.desc().nullslast(),
            AssignedForm.id.desc(),
        )
        .all()
    )
    return [
        {
            "id": assigned.id,
            "display_name": assigned.display_name,
            "template_id": assigned.template_id,
            "template_name": assigned.template.name if assigned.template else "",
            "period_name": assigned.period_name,
            "kind": kind_for_template(int(assigned.template_id or 0)),
        }
        for assigned in rows
    ]


def list_countries_for_bulk(assigned_form_id: int) -> list[dict[str, Any]]:
    """Country rows on one assignment, for bulk PNG generation."""
    from app.models.core import Country

    rows = (
        db.session.query(AssignmentEntityStatus, Country)
        .outerjoin(
            Country,
            db.and_(
                AssignmentEntityStatus.entity_type == "country",
                AssignmentEntityStatus.entity_id == Country.id,
            ),
        )
        .filter(AssignmentEntityStatus.assigned_form_id == int(assigned_form_id))
        .filter(AssignmentEntityStatus.entity_type == "country")
        .order_by(Country.name.asc().nullslast())
        .all()
    )
    return [
        {
            "aes_id": aes.id,
            "country_name": country.name if country else "",
            "iso3": country.iso3 if country else "",
        }
        for aes, country in rows
    ]


def get_assigned_form_for_bulk(assigned_form_id: int) -> AssignedForm:
    assigned = AssignedForm.query.get(int(assigned_form_id))
    if assigned is None or int(assigned.template_id or 0) not in UPR_VISUAL_TEMPLATE_IDS:
        raise UprVisualsError("Select a Unified Plan or Report assignment.")
    return assigned


