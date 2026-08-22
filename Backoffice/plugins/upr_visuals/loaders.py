"""Shared SQLAlchemy loaders for UPR visual payloads."""

from __future__ import annotations

import logging

from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models.assignments import AssignedForm, AssignmentEntityStatus
from app.models.form_items import FormItem
from app.models.forms import DynamicIndicatorData, FormData, FormSection
from plugins.upr_visuals.errors import UprVisualsError, assignment_supports_visuals

logger = logging.getLogger(__name__)

def _load_aes(aes_id: int) -> AssignmentEntityStatus:
    aes = (
        AssignmentEntityStatus.query.options(
            joinedload(AssignmentEntityStatus.assigned_form).joinedload(AssignedForm.template),
        )
        .filter_by(id=int(aes_id))
        .first()
    )
    if not aes:
        raise UprVisualsError("Assignment not found.")
    if not assignment_supports_visuals(aes):
        raise UprVisualsError("UPR visuals are only available for Unified Plan and Report assignments.")
    return aes


def _indicator_bank_options(root):
    from app.models.indicator_bank import IndicatorBank

    return joinedload(root).joinedload(IndicatorBank.spef_area)


def _load_dynamic_indicator_rows(aes_id: int) -> list[DynamicIndicatorData]:
    query = DynamicIndicatorData.query.options(
        _indicator_bank_options(DynamicIndicatorData.indicator_bank),
        joinedload(DynamicIndicatorData.section),
    ).filter(DynamicIndicatorData.assignment_entity_status_id == aes_id)
    try:
        return query.all()
    except Exception:
        db.session.rollback()
        logger.debug("UPR visuals: falling back to dynamic rows without SPEF catalog join", exc_info=True)
        return (
            DynamicIndicatorData.query.options(
                joinedload(DynamicIndicatorData.indicator_bank),
                joinedload(DynamicIndicatorData.section),
            )
            .filter(DynamicIndicatorData.assignment_entity_status_id == aes_id)
            .all()
        )


def _section_load_options():
    return joinedload(FormItem.form_section).joinedload(FormSection.parent_section)


def _load_items(template) -> list[FormItem]:
    version_id = getattr(template, "published_version_id", None) if template else None
    if not version_id:
        return []
    query = FormItem.query.options(
        _section_load_options(),
        _indicator_bank_options(FormItem.indicator_bank),
    ).filter(FormItem.version_id == version_id, FormItem.archived.is_(False))
    try:
        return query.all()
    except Exception:
        db.session.rollback()
        logger.debug("UPR visuals: falling back to items without SPEF catalog join", exc_info=True)
        return (
            FormItem.query.options(
                _section_load_options(),
                joinedload(FormItem.indicator_bank),
            )
            .filter(FormItem.version_id == version_id, FormItem.archived.is_(False))
            .all()
        )


def _load_entries(aes_id: int) -> list[FormData]:
    return FormData.query.filter_by(assignment_entity_status_id=aes_id).all()


