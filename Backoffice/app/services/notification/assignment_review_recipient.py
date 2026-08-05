"""Resolve IFRC reviewer(s) for assignment submission notifications."""

from __future__ import annotations

from typing import List, Optional

from flask import current_app

from app.models import Country, User
from app.models.assignments import (
    SUBMISSION_REVIEW_RECIPIENT_FDS,
    SUBMISSION_REVIEW_RECIPIENT_SPECIFIC,
)


def _resolve_fds_member_user_id(assignment_entity_status) -> Optional[int]:
    aes = assignment_entity_status
    assigned_form = getattr(aes, 'assigned_form', None)
    if getattr(aes, 'entity_type', None) == 'country' and getattr(aes, 'entity_id', None):
        country = Country.query.get(int(aes.entity_id))
        if country and country.fds_member_user_id:
            fds_user = User.query.get(int(country.fds_member_user_id))
            if fds_user and fds_user.active:
                return int(fds_user.id)
        current_app.logger.info(
            "[NOTIFY] No active FDS member for country %s on assignment %s submission (aes_id=%s)",
            getattr(aes, 'entity_id', '?'),
            getattr(assigned_form, 'id', '?') if assigned_form else '?',
            getattr(aes, 'id', '?'),
        )
        return None

    current_app.logger.info(
        "[NOTIFY] FDS member review routing skipped for non-country entity %s/%s (aes_id=%s)",
        getattr(aes, 'entity_type', '?'),
        getattr(aes, 'entity_id', '?'),
        getattr(aes, 'id', '?'),
    )
    return None


def resolve_submission_review_recipient_user_id(assignment_entity_status) -> Optional[int]:
    """Return the first reviewer id, if any (legacy helper)."""
    ids = resolve_submission_review_recipient_user_ids(assignment_entity_status)
    return ids[0] if ids else None


def resolve_submission_review_recipient_user_ids(
    assignment_entity_status,
    *,
    exclude_user_ids: Optional[List[int]] = None,
) -> List[int]:
    """
    Return user ids who should receive the admin review notification for this submission.

    Default mode uses the submitting country's designated FDS member; optional mode uses
    one or more admins configured on the assignment.
    """
    aes = assignment_entity_status
    assigned_form = getattr(aes, 'assigned_form', None)
    if not assigned_form:
        return []

    mode = (
        getattr(assigned_form, 'submission_review_recipient_mode', None)
        or SUBMISSION_REVIEW_RECIPIENT_FDS
    )

    if mode == SUBMISSION_REVIEW_RECIPIENT_SPECIFIC:
        users = getattr(assigned_form, 'submission_review_recipient_users', None) or []
        recipient_ids = [int(u.id) for u in users if getattr(u, 'active', False)]
        if not recipient_ids:
            current_app.logger.warning(
                "[NOTIFY] Assignment %s submission_review_recipient_mode=specific_admin "
                "but no active reviewer users are configured (aes_id=%s)",
                getattr(assigned_form, 'id', '?'),
                getattr(aes, 'id', '?'),
            )
            return []
    else:
        fds_id = _resolve_fds_member_user_id(aes)
        recipient_ids = [fds_id] if fds_id else []

    exclude = {int(x) for x in (exclude_user_ids or []) if x is not None}
    return [uid for uid in recipient_ids if uid not in exclude]
