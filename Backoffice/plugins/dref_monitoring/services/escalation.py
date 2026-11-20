"""Open reporting periods, then remind and escalate when a report is still a draft."""

from __future__ import annotations

import logging
from datetime import date, timedelta

from app.extensions import db
from app.models.enums import NotificationType
from app.utils.common.datetime_helpers import utcnow
from plugins.dref_monitoring.config_store import schedule_settings
from plugins.dref_monitoring.constants import PLAN_DRAFT, WORKFLOW_PLAN_DRAFT
from plugins.dref_monitoring.models import DrefEscalation, DrefMember, DrefOperation, DrefPeriod, DrefPlan, DrefReport
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
    from app.models.core import User
    from app.services.notification.creation import create_notification
    from plugins.dref_monitoring.i18n import normalize_language, translate

    templates = {
        "plan": "The monitoring plan for {appeal} should be validated by {due}.",
        "reminder": "A monitoring report for {appeal} is due on {due}.",
        "validate": "The monitoring report for {appeal} is overdue. National Society validation has been asked to follow up.",
        "review": "The monitoring report for {appeal} is still overdue. The delegation has been asked to follow up.",
        "portfolio": "The monitoring report for {appeal} remains overdue for portfolio follow-up.",
    }
    related_url = (
        f"/dref-monitoring/operations/{operation.id}"
        if level == "plan"
        else _assignment_url(operation, period)
    )
    due = period.validation_due if level == "plan" else period.due_date
    groups: dict[str, list[int]] = {}
    for user_id in user_ids:
        user = db.session.get(User, user_id)
        language = normalize_language(getattr(user, "preferred_language", None) if user else None)
        groups.setdefault(language, []).append(user_id)
    for language, ids in groups.items():
        detail = translate(templates[level], lang=language).format(appeal=operation.appeal_code, due=due)
        create_notification(
            ids,
            NotificationType.deadline_reminder,
            "notification.dref_monitoring.reminder.title",
            "notification.dref_monitoring.reminder.message",
            title_params={"appeal": operation.appeal_code},
            message_params={"detail": detail},
            related_object_type="dref_operation",
            related_object_id=operation.id,
            related_url=related_url,
            priority="high" if level != "reminder" else "normal",
            category="dref_monitoring",
            respect_preferences=True,
        )


def remind_unvalidated_plans(today: date, settings: dict, notify) -> int:
    """Once a day, ask the validation tier to confirm a plan that is still a draft."""
    reminder_days = int(settings.get("reminder_days_before") or 0)
    sent = 0
    operations = DrefOperation.query.filter_by(workflow_status=WORKFLOW_PLAN_DRAFT).all()
    for operation in operations:
        if operation.operation_status == "closed":
            continue
        plan = (
            DrefPlan.query.filter_by(operation_id=operation.id)
            .order_by(DrefPlan.version.desc())
            .first()
        )
        if plan is None or plan.status != PLAN_DRAFT or plan.validation_due is None:
            continue
        if plan.validation_reminded_on == today:
            continue
        if today < plan.validation_due - timedelta(days=reminder_days):
            continue
        user_ids = recipients(operation.id, "validate")
        if not user_ids:
            continue
        try:
            notify(user_ids, operation, plan, "plan")
        except Exception:
            logger.warning("DREF plan reminder failed for %s", operation.appeal_code, exc_info=True)
            db.session.rollback()
            continue
        plan.validation_reminded_on = today
        sent += 1
    return sent


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
    sent += remind_unvalidated_plans(today, settings, notify)
    db.session.commit()
    try:
        from plugins.dref_monitoring.services.drafts import generate_scheduled_drafts

        generate_scheduled_drafts(today)
    except Exception:
        logger.warning("DREF Draft 0 milestone generation failed", exc_info=True)
        db.session.rollback()
    return sent
