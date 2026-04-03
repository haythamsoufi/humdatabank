import pytest
import uuid
from unittest.mock import patch

from app import db
from app.models import (
    EmailDeliveryLog,
    Notification,
    NotificationPreferences,
    NotificationType,
    User,
)
from app.utils.datetime_helpers import utcnow
from app.utils.notification_emails import retry_email_delivery_log, send_instant_notification_email
from app.utils.notifications import create_notification


@pytest.mark.usefixtures("db_session")
def test_bulk_notification_includes_category_and_tags(app):
    """Ensure bulk inserts persist category and tags metadata."""
    with app.app_context():
        email_suffix = uuid.uuid4().hex
        users = []
        for idx in range(6):
            user = User(
                email=f"user{idx}-{email_suffix}@example.com",
                name=f"User {idx}",
                role="user",
                active=True,
            )
            user.set_password("test123")
            db.session.add(user)
            users.append(user)
        db.session.commit()

        user_ids = [user.id for user in users]

        create_notification(
            user_ids=user_ids,
            notification_type=NotificationType.assignment_created,
            title_key="notification.assignment_created.title",
            message_key="notification.assignment_created.message",
            title_params={"template": "Template A", "period": "2024", "due_date": "Jan 1"},
            message_params={
                "template": "Template A",
                "period": "2024",
                "due_date": "Jan 1",
            },
            category="assignment",
            tags=["urgent", "action-required"],
        )

        notifications = Notification.query.filter(
            Notification.user_id.in_(user_ids)
        ).all()

        assert len(notifications) == len(user_ids)
        for notification in notifications:
            assert notification.category == "assignment"
            assert notification.tags == ["urgent", "action-required"]


@pytest.mark.usefixtures("db_session")
def test_retry_email_delivery_log_handles_digest_success(app):
    """Retry helper should reuse existing digest logs and mark them as sent."""
    with app.app_context():
        digest_email = f"digest_user-{uuid.uuid4().hex}@example.com"
        app.config["ALLOWED_EMAIL_RECIPIENTS_DEV"] = [digest_email]

        user = User(
            email=digest_email,
            name="Digest User",
            role="user",
            active=True,
        )
        user.set_password("digest")
        db.session.add(user)
        db.session.flush()

        preferences = NotificationPreferences(
            user_id=user.id,
            email_notifications=True,
            notification_types_enabled=[],
            notification_frequency="daily",
        )
        db.session.add(preferences)

        notification = Notification(
            user_id=user.id,
            notification_type=NotificationType.assignment_created,
            title="Test Assignment",
            message="Test Message",
            created_at=utcnow(),
            is_read=False,
            is_archived=False,
        )
        db.session.add(notification)
        db.session.commit()

        log = EmailDeliveryLog(
            notification_id=None,
            user_id=user.id,
            email_address=digest_email,
            subject="Daily Notification Digest - 1 new notification(s)",
            status="retrying",
            retry_count=1,
        )
        db.session.add(log)
        db.session.commit()

        with patch("app.utils.notification_emails.send_email", return_value=True) as mock_send:
            success = retry_email_delivery_log(log)

        db.session.refresh(log)
        assert success is True
        assert log.status == "sent"
        assert mock_send.call_count == 1


@pytest.mark.usefixtures("db_session")
def test_urgent_notification_bypasses_digest_preferences(app):
    """Urgent notifications should bypass digest preference and send instantly."""
    with app.app_context():
        urgent_email = f"urgent_user-{uuid.uuid4().hex}@example.com"
        app.config["ALLOWED_EMAIL_RECIPIENTS_DEV"] = [urgent_email]

        user = User(
            email=urgent_email,
            name="Urgent User",
            role="user",
            active=True,
        )
        user.set_password("urgent")
        db.session.add(user)
        db.session.flush()

        preferences = NotificationPreferences(
            user_id=user.id,
            email_notifications=True,
            notification_types_enabled=[],
            notification_frequency="daily",
        )
        db.session.add(preferences)

        notification = Notification(
            user_id=user.id,
            notification_type=NotificationType.assignment_created,
            title="Urgent Assignment",
            message="Immediate attention required",
            created_at=utcnow(),
            is_read=False,
            is_archived=False,
            priority="urgent",
        )
        db.session.add(notification)
        db.session.commit()

        with patch("app.utils.notification_emails.send_email", return_value=True) as mock_send:
            send_instant_notification_email(user, notification)

        assert mock_send.call_count == 1
