"""Open reporting periods, then remind and escalate when a report is still a draft."""

from __future__ import annotations

import logging
from datetime import date

from app.extensions import db
from app.models.enums import NotificationType
from app.utils.common.datetime_helpers import utcnow
from plugins.dref_monitoring.config_store import schedule_settings
from plugins.dref_monitoring.models import DrefEscalation, DrefMember, DrefOperation, DrefPeriod, DrefReport
from plugins.dref_monitoring.services.periods import escalation_level

logger = logging.getLogger(__name__)

_TIER_FOR_LEVEL = {
    "reminder": {"enter", "validate", "review", "portfolio"},
    "validate": {"validate", "review", "portfolio"},
    "review": {"review", "portfolio"},
    "portfolio": {"portfolio"},
}


def recipients(operation_id: int, level: str) -> list[int]:
    tiers = _TIER_FOR_LEVEL.get(level, set())
    return [
        row.user_id
        for row in DrefMember.query.filter_by(operation_id=operation_id).all()
        if row.tier in tiers
    ]


def _already_sent(period_id: int, level: str, today: date) -> bool:
    start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    existing = (
        DrefEscalation.query.filter_by(period_id=period_id, level=level)
        .filter(DrefEscalation.created_at >= start)
        .first()
    )
    return existing is not None


def _assignment_url(operation, period) -> str:
    from plugins.dref_monitoring.services.assignment_sync import assignment_url

    return assignment_url(operation.id, period)


def default_notify(user_ids: list[int], operation, period, level: str) -> None:
    if not user_ids:
        return
    from app.services.notification.creation import create_notification

    detail = {
        "reminder": f"A monitoring report for {operation.appeal_code} is due on {period.due_date}.",
        "validate": f"The monitoring report for {operation.appeal_code} is overdue. National Society validation has been asked to follow up.",
        "review": f"The monitoring report for {operation.appeal_code} is still overdue. The delegation has been asked to follow up.",
        "portfolio": f"The monitoring report for {operation.appeal_code} remains overdue for portfolio follow-up.",
    }[level]
    create_notification(
        user_ids,
        NotificationType.deadline_reminder,
        "notification.dref_monitoring.reminder.title",
        "notification.dref_monitoring.reminder.message",
        title_params={"appeal": operation.appeal_code},
        message_params={"detail": detail},
        related_object_type="dref_operation",
        related_object_id=operation.id,
        related_url=_assignment_url(operation, period),
        priority="high" if level != "reminder" else "normal",
        category="dref_monitoring",
        respect_preferences=True,
    )


def run_escalation(today: date | None = None, notify=None) -> int:
    today = today or date.today()
    settings = schedule_settings()
    notify = notify or default_notify
    sent = 0
    periods = DrefPeriod.query.filter(DrefPeriod.due_date <= today).all()
    # Also remind before the due date.
    upcoming = DrefPeriod.query.filter(DrefPeriod.due_date > today).all()
    for period in list(periods) + list(upcoming):
        report = DrefReport.query.filter_by(period_id=period.id).first()
        submitted = report is not None and report.status != "draft"
        level = escalation_level(today, period.due_date, submitted, settings)
        if level is None or _already_sent(period.id, level, today):
            continue
        operation = db.session.get(DrefOperation, period.operation_id)
        if operation is None or operation.operation_status == "closed":
            continue
        user_ids = recipients(operation.id, level)
        try:
            notify(user_ids, operation, period, level)
        except Exception:
            logger.warning("DREF escalation notify failed for %s", operation.appeal_code, exc_info=True)
            db.session.rollback()
            continue
        db.session.add(
            DrefEscalation(
                operation_id=operation.id,
                period_id=period.id,
                level=level,
                notified_user_ids=user_ids,
            )
        )
        if level != "reminder" and period.status == "open":
            period.status = "overdue"
        sent += 1
    db.session.commit()
    return sent
