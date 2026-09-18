"""Assignment status workflow helpers for the delegation review feature."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.enums import AssignmentEntityStatusValue
from app.services.platform.app_settings_service import is_organization_email
from app.utils.datetime_helpers import utcnow

if TYPE_CHECKING:
    from app.models.assignments import AssignmentEntityStatus
    from datetime import datetime


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


def delegation_review_source_statuses() -> tuple[AssignmentEntityStatusValue, ...]:
    """Statuses from which NS focal points can send for delegation review.

    ``pending`` is included because the first save auto-transitions it to
    ``in_progress`` before action resolution runs, so a focal point clicking
    "Send for Review" on a fresh (pending) assignment should work exactly the
    same as from ``in_progress``.  Excluding it causes the UI to show a
    "Submit" button instead of "Send for Review" for brand-new assignments.
    """
    return (
        AssignmentEntityStatusValue.pending,
        AssignmentEntityStatusValue.in_progress,
        AssignmentEntityStatusValue.requires_revision,
    )


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
    if status in {m.value for m in delegation_review_source_statuses()}:
        return 'send_for_review'

    return 'submit'


def should_apply_sent_for_review(
    assignment_entity_status: 'AssignmentEntityStatus',
    effective_action: str,
) -> bool:
    """Return True when the effective action should transition status to sent_for_review."""
    return effective_action == 'send_for_review' and review_enabled(assignment_entity_status)


def apply_entity_status_change(
    assignment_entity_status: 'AssignmentEntityStatus',
    new_status,
    user_id: int | None = None,
    *,
    now: 'datetime | None' = None,
    sync_scoped: bool = True,
) -> AssignmentEntityStatusValue:
    """Set status, timestamp, last setter, and status-specific accountability fields.

    ``user_id`` is recorded on ``status_changed_by_user_id`` for every status.
    Submitted / approved / sent-for-review also keep their dedicated actor fields.
    """
    previous = assignment_entity_status.status
    if hasattr(previous, 'value'):
        previous = previous.value
    raw = new_status.value if hasattr(new_status, 'value') else new_status
    normalized = AssignmentEntityStatusValue.normalize(raw)
    stamp = now or utcnow()
    assignment_entity_status.status = normalized
    assignment_entity_status.status_timestamp = stamp
    if user_id is not None:
        assignment_entity_status.status_changed_by_user_id = user_id
        if normalized == AssignmentEntityStatusValue.approved:
            assignment_entity_status.approved_by_user_id = user_id
        elif normalized == AssignmentEntityStatusValue.submitted:
            assignment_entity_status.submitted_by_user_id = user_id
            assignment_entity_status.submitted_at = stamp
        elif normalized == AssignmentEntityStatusValue.sent_for_review:
            assignment_entity_status.sent_for_review_by_user_id = user_id
            assignment_entity_status.sent_for_review_at = stamp
    if sync_scoped:
        _sync_scoped_statuses(assignment_entity_status, previous, normalized, user_id)
    return normalized


def _sync_scoped_statuses(assignment_entity_status, previous_status, new_status, user_id: int | None) -> None:
    aes_id = getattr(assignment_entity_status, 'id', None)
    if not aes_id:
        return
    try:
        from app.services.assignments.section_submission_service import (
            is_section_submission_enabled,
            sync_section_statuses_for_entity_change,
        )
        from app.services.assignments.page_submission_service import (
            is_page_submission_enabled,
            sync_page_statuses_for_entity_change,
        )
        if is_section_submission_enabled(assignment_entity_status):
            sync_section_statuses_for_entity_change(aes_id, previous_status, new_status, user_id)
        if is_page_submission_enabled(assignment_entity_status):
            sync_page_statuses_for_entity_change(aes_id, previous_status, new_status, user_id)
    except Exception as exc:
        from flask import current_app
        current_app.logger.debug("Scoped status sync failed for AES %s: %s", aes_id, exc)
