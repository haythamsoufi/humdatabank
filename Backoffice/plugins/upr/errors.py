"""Shared exceptions and eligibility checks for UPR."""

from __future__ import annotations

from app.models.assignments import AssignmentEntityStatus
from plugins.upr.catalog import UPR_VISUAL_TEMPLATE_IDS


class UprError(ValueError):
    """Raised when an assignment cannot produce UPR."""


def assignment_supports_visuals(aes: AssignmentEntityStatus | None) -> bool:
    if not aes or not aes.assigned_form:
        return False
    return int(aes.assigned_form.template_id or 0) in UPR_VISUAL_TEMPLATE_IDS
