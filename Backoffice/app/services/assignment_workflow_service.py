"""Assignment status workflow helpers (NS review / delegation)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.enums import AssignmentEntityStatusValue
from app.services.app_settings_service import is_organization_email

if TYPE_CHECKING:
    from app.models.assignments import AssignmentEntityStatus


def review_enabled(assignment_entity_status: 'AssignmentEntityStatus') -> bool:
    """True when this assignment requires delegation review before final submission."""
    assigned_form = getattr(assignment_entity_status, 'assigned_form', None)
    return bool(assigned_form and getattr(assigned_form, 'requires_delegation_review', False))


def is_delegation_user(user) -> bool:
    """True when the user's email matches the configured organization domain."""
    if not user:
        return False
    return is_organization_email(getattr(user, 'email', '') or '')


def _status_value(assignment_entity_status: 'AssignmentEntityStatus') -> str:
    status = assignment_entity_status.status
    if hasattr(status, 'value'):
        return status.value
    return str(status)


def ns_review_source_statuses() -> tuple[AssignmentEntityStatusValue, ...]:
    return (AssignmentEntityStatusValue.in_progress, AssignmentEntityStatusValue.requires_revision)


def resolve_submit_action(
    assignment_entity_status: 'AssignmentEntityStatus',
    user,
    action: str,
) -> str:
    """
    Map form POST action to the effective workflow action.

    Returns 'save', 'send_for_review', or 'submit'.
    """
    action = (action or 'save').strip().lower()
    if action in ('save',):
        return 'save'
    if action in ('send_for_review',):
        return 'send_for_review'

    if action != 'submit':
        return action

    if not review_enabled(assignment_entity_status):
        return 'submit'

    if is_delegation_user(user):
        return 'submit'

    status = _status_value(assignment_entity_status)
    if status in {m.value for m in ns_review_source_statuses()}:
        return 'send_for_review'

    return 'submit'


def should_apply_sent_for_review(
    assignment_entity_status: 'AssignmentEntityStatus',
    user,
    effective_action: str,
) -> bool:
    return effective_action == 'send_for_review' and review_enabled(assignment_entity_status)
