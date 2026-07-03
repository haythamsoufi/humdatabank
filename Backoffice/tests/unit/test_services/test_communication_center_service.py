"""Tests for admin Communication Center grid assembly."""

import uuid
from datetime import timedelta

import pytest

from app import db
from app.models import EmailDeliveryLog, Notification, NotificationType, User
from app.services.communication_center_service import (
    RECORD_TYPE_BOTH,
    RECORD_TYPE_EMAIL,
    RECORD_TYPE_NOTIFICATION,
    build_communications_center_grid,
    build_email_grid_rows,
    build_notification_grid_rows,
    ensure_notifications_for_attention_failures,
    get_orphan_email_delivery_logs_for_grid,
)
from app.services.email.delivery import get_email_delivery_logs_needing_attention
from app.services.notification_service import NotificationService
from app.utils.datetime_helpers import utcnow


def _make_user(suffix=None):
    suffix = suffix or uuid.uuid4().hex
    user = User(email=f"cc-{suffix}@example.com", name=f"CC {suffix}", active=True)
    user.set_password("test")
    return user


@pytest.mark.usefixtures("db_session")
class TestCommunicationCenterService:
    def test_ensure_notifications_for_attention_failures_adds_archived(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.flush()

            archived = Notification(
                user_id=user.id,
                notification_type=NotificationType.admin_message,
                title='Archived failure',
                message='Body',
                is_archived=True,
            )
            db.session.add(archived)
            db.session.flush()

            log = EmailDeliveryLog(
                notification_id=archived.id,
                user_id=user.id,
                email_address=user.email,
                subject='Archived subject',
                status='failed',
                error_message='SMTP error',
            )
            db.session.add(log)
            db.session.commit()

            attention_logs = get_email_delivery_logs_needing_attention()
            merged = ensure_notifications_for_attention_failures([], attention_logs)

        assert len(merged) == 1
        assert merged[0].id == archived.id

    def test_email_only_row_has_no_notification_fields(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.commit()

            log = EmailDeliveryLog(
                notification_id=None,
                user_id=user.id,
                email_address=user.email,
                subject='Country Access Requests - skipped',
                status='failed',
                error_message='[Skipped] Already sent today',
                created_at=utcnow(),
            )
            db.session.add(log)
            db.session.commit()

            rows = build_email_grid_rows([log])

        assert len(rows) == 1
        assert rows[0]['row_kind'] == RECORD_TYPE_EMAIL
        assert rows[0]['record_type'] == RECORD_TYPE_EMAIL
        assert rows[0]['has_notification'] is False
        assert rows[0]['has_email'] is True
        assert rows[0]['notification_type'] is None
        assert rows[0]['title'] == ''
        assert rows[0]['email_status'] == 'skipped'
        assert rows[0]['email_subject'] == log.subject

    def test_notification_only_row(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.flush()

            notification = Notification(
                user_id=user.id,
                notification_type=NotificationType.assignment_created,
                title='In-app only',
                message='No email',
            )
            db.session.add(notification)
            db.session.commit()

            actor_fields_by_id = NotificationService.build_actor_display_fields_map([notification], {})
            email_fields_by_id = NotificationService.build_email_delivery_fields_map([notification.id])

            rows = build_notification_grid_rows(
                [notification],
                actor_fields_by_id=actor_fields_by_id,
                email_fields_by_id=email_fields_by_id,
            )

        assert rows[0]['record_type'] == RECORD_TYPE_NOTIFICATION
        assert rows[0]['has_notification'] is True
        assert rows[0]['has_email'] is False

    def test_notification_with_email_row(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.flush()

            notification = Notification(
                user_id=user.id,
                notification_type=NotificationType.admin_message,
                title='Both channels',
                message='Body',
            )
            db.session.add(notification)
            db.session.flush()

            log = EmailDeliveryLog(
                notification_id=notification.id,
                user_id=user.id,
                email_address=user.email,
                subject='Both channels',
                status='sent',
                sent_at=utcnow(),
            )
            db.session.add(log)
            db.session.commit()

            actor_fields_by_id = NotificationService.build_actor_display_fields_map([notification], {})
            email_fields_by_id = NotificationService.build_email_delivery_fields_map([notification.id])

            rows = build_notification_grid_rows(
                [notification],
                actor_fields_by_id=actor_fields_by_id,
                email_fields_by_id=email_fields_by_id,
            )

        assert rows[0]['record_type'] == RECORD_TYPE_BOTH
        assert rows[0]['has_notification'] is True
        assert rows[0]['has_email'] is True

    def test_build_communications_center_grid_merges_rows(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.flush()

            notification = Notification(
                user_id=user.id,
                notification_type=NotificationType.admin_message,
                title='Notification row',
                message='Body',
                created_at=utcnow() - timedelta(hours=1),
            )
            db.session.add(notification)
            db.session.flush()

            orphan = EmailDeliveryLog(
                notification_id=None,
                user_id=user.id,
                email_address=user.email,
                subject='Email only row',
                status='failed',
                error_message='SMTP timeout',
                created_at=utcnow(),
            )
            db.session.add(orphan)
            db.session.commit()

            actor_fields_by_id = NotificationService.build_actor_display_fields_map([notification], {})
            email_fields_by_id = NotificationService.build_email_delivery_fields_map([notification.id])

            rows = build_communications_center_grid(
                [notification],
                [orphan],
                actor_fields_by_id=actor_fields_by_id,
                email_fields_by_id=email_fields_by_id,
            )

        assert len(rows) == 2
        assert rows[0]['record_type'] == RECORD_TYPE_EMAIL
        assert rows[1]['record_type'] == RECORD_TYPE_NOTIFICATION

    def test_get_orphan_email_delivery_logs_for_grid(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.flush()

            notification = Notification(
                user_id=user.id,
                notification_type=NotificationType.admin_message,
                title='Linked',
                message='Body',
            )
            db.session.add(notification)
            db.session.flush()

            orphan = EmailDeliveryLog(
                notification_id=None,
                user_id=user.id,
                email_address=user.email,
                subject='Orphan',
                status='sent',
            )
            linked = EmailDeliveryLog(
                notification_id=notification.id,
                user_id=user.id,
                email_address=user.email,
                subject='Linked',
                status='sent',
            )
            db.session.add_all([orphan, linked])
            db.session.commit()

            logs = get_orphan_email_delivery_logs_for_grid()

        assert len(logs) == 1
        assert logs[0].subject == 'Orphan'

    def test_build_notification_grid_row_marks_archived_attention(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.flush()

            archived = Notification(
                user_id=user.id,
                notification_type=NotificationType.admin_message,
                title='Archived failure',
                message='Body',
                is_archived=True,
            )
            db.session.add(archived)
            db.session.flush()

            log = EmailDeliveryLog(
                notification_id=archived.id,
                user_id=user.id,
                email_address=user.email,
                subject='Archived subject',
                status='failed',
                error_message='SMTP error',
                created_at=utcnow() - timedelta(minutes=1),
            )
            db.session.add(log)
            db.session.commit()

            actor_fields_by_id = NotificationService.build_actor_display_fields_map([archived], {})
            email_fields_by_id = NotificationService.build_email_delivery_fields_map([archived.id])

            rows = build_notification_grid_rows(
                [archived],
                actor_fields_by_id=actor_fields_by_id,
                email_fields_by_id=email_fields_by_id,
                original_notification_ids=set(),
                attention_notification_ids={archived.id},
            )

        assert rows[0]['included_for_email_failure'] is True
        assert rows[0]['email_status'] == 'failed'
        assert rows[0]['record_type'] == RECORD_TYPE_BOTH
