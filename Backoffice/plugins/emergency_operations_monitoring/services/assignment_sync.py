"""Keep a DREF report in step with the project-cycle assignment status.

Save on the cycle leaves the report as a draft (the field writes the figures).
Submit, including send-for-review, is the National Society submission.
Approve records National Society validation. An IFRC approver — a delegation
address, the review permission, or an administrator — also records delegation
review, which is the last step the assignment workflow can express.
"""

from __future__ import annotations

import logging

from sqlalchemy import event, inspect
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.models.assignments import AssignmentEntityStatus
from app.models.enums import EntityType
from app.utils.common.datetime_helpers import utcnow
from plugins.emergency_operations_monitoring.constants import (
    REPORT_DRAFT,
    REPORT_REVIEWED,
    REPORT_SUBMITTED,
    REPORT_VALIDATED,
    REVIEW_PERMISSION,
)
from plugins.emergency_operations_monitoring.models import DrefPeriod, DrefReport

_INSTALLED = False
_QUIET = {"pending", "in_progress", "cancelled"}


def register_assignment_sync() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    event.listen(Session, "before_flush", _before_flush)
    _INSTALLED = True


def assignment_url(operation_id: int, period: DrefPeriod) -> str:
    """Country-dashboard link for a cycle, or the operation page when it has none."""
    if period.assigned_form_id:
        row = (
            AssignmentEntityStatus.query.filter_by(
                assigned_form_id=period.assigned_form_id,
                entity_type=EntityType.project.value,
            )
            .order_by(AssignmentEntityStatus.id.asc())
            .first()
        )
        if row is not None:
            return f"/assignment/{row.id}"
    return f"/emergency-operations/operations/{operation_id}"


def approver_completes_review(user) -> bool:
    """True when this approval is the IFRC delegation review, not only NS validation."""
    if user is None:
        return False
    try:
        from app.services.assignments.workflow_service import is_delegation_user
        from app.services.organization.authorization_service import AuthorizationService

        if AuthorizationService.is_system_manager(user) or AuthorizationService.is_admin(user):
            return True
        if is_delegation_user(user):
            return True
    except Exception:
        # Fall through to the DREF permission check, which is the stricter answer.
        logging.getLogger(__name__).warning("DREF delegation review check failed", exc_info=True)
    from plugins.emergency_operations_monitoring.access import actor_for_user

    actor = actor_for_user(user)
    return bool(actor.is_manager or REVIEW_PERMISSION in actor.permissions)


def _text(value) -> str:
    if value is None:
        return ""
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _before_flush(session, flush_context, instances) -> None:
    try:
        changed = []
        for obj in list(session.new) + list(session.dirty):
            if not isinstance(obj, AssignmentEntityStatus):
                continue
            history = inspect(obj).attrs.status.history
            if history.has_changes():
                changed.append(obj)
        for aes in changed:
            _apply(session, aes)
    except (OperationalError, ProgrammingError):
        return
    except Exception:
        # The report mirror must never block an unrelated assignment save.
        logging.getLogger(__name__).warning("DREF assignment sync skipped", exc_info=True)
        return


def _apply(session, aes: AssignmentEntityStatus) -> None:
    if not aes.assigned_form_id:
        return
    status = _text(aes.status)
    if status in _QUIET:
        return
    with session.no_autoflush:
        period = session.query(DrefPeriod).filter_by(assigned_form_id=aes.assigned_form_id).first()
        if period is None:
            return
        report = session.query(DrefReport).filter_by(period_id=period.id).first()
        if report is None:
            report = DrefReport(period_id=period.id, operation_id=period.operation_id, status=REPORT_DRAFT)
            session.add(report)
    when = aes.status_timestamp or utcnow()
    user_id = aes.status_changed_by_user_id or aes.approved_by_user_id or aes.submitted_by_user_id
    if status == "requires_revision":
        if report.status != REPORT_REVIEWED:
            report.status = REPORT_DRAFT
        if period.status != "open":
            period.status = "open"
        return
    if status in {"submitted", "sent_for_review"}:
        if report.status == REPORT_DRAFT:
            report.status = REPORT_SUBMITTED
            report.submitted_at = report.submitted_at or when
            report.submitted_by_user_id = report.submitted_by_user_id or user_id
        if period.status in {"open", "overdue"}:
            period.status = "submitted"
        return
    if status != "approved":
        return
    user = None
    completes_review = False
    if user_id:
        from app.models import User

        with session.no_autoflush:
            user = session.get(User, user_id)
            completes_review = approver_completes_review(user)
    if report.submitted_at is None:
        report.submitted_at = when
        report.submitted_by_user_id = user_id
    if report.validated_at is None:
        report.validated_at = when
        report.validated_by_user_id = user_id
    if completes_review:
        report.status = REPORT_REVIEWED
        report.reviewed_at = report.reviewed_at or when
        report.reviewed_by_user_id = report.reviewed_by_user_id or user_id
    elif report.status != REPORT_REVIEWED:
        report.status = REPORT_VALIDATED
    if period.status in {"open", "overdue"}:
        period.status = "submitted"
