"""Shared exceptions and eligibility checks for UPR visuals."""

from __future__ import annotations

from app.models.assignments import AssignmentEntityStatus
from plugins.upr_visuals.catalog import UPR_VISUAL_TEMPLATE_IDS


class UprVisualsError(ValueError):
    """Raised when an assignment cannot produce UPR visuals."""


def assignment_supports_visuals(aes: AssignmentEntityStatus | None) -> bool:
    if not aes or not aes.assigned_form:
        return False
    return int(aes.assigned_form.template_id or 0) in UPR_VISUAL_TEMPLATE_IDS
