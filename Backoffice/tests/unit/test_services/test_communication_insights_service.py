"""Tests for Communication Center insights aggregation."""

import uuid
from datetime import timedelta

import pytest

from app import db
from app.models import (
    EmailDeliveryLog,
    Notification,
    NotificationCampaign,
    NotificationCampaignStatusValue,
    NotificationType,
    User,
)
from app.services.communication.insights_service import (
    DEFAULT_INSIGHTS_DAYS,
    build_communications_insights,
    clamp_insights_days,
    empty_communications_insights,
)
from app.services.email.delivery import SKIP_ERROR_PREFIX
from app.utils.datetime_helpers import utcnow


def _make_user(suffix=None):
    suffix = suffix or uuid.uuid4().hex
    user = User(email=f"ci-{suffix}@example.com", name=f"CI {suffix}", active=True)
    user.set_password("test")
    return user


@pytest.mark.unit
class TestClampInsightsDays:
    def test_defaults_and_allowed_values(self):
        assert clamp_insights_days(None) == DEFAULT_INSIGHTS_DAYS
        assert clamp_insights_days('nope') == DEFAULT_INSIGHTS_DAYS
        assert clamp_insights_days(14) == DEFAULT_INSIGHTS_DAYS
        assert clamp_insights_days(7) == 7
        assert clamp_insights_days(365) == 365


@pytest.mark.usefixtures("db_session")
class TestCommunicationInsightsService:
    def test_empty_window_has_daily_series(self, app):
        with app.app_context():
            payload = build_communications_insights(7)

        assert payload['success'] is True
        assert payload['period_days'] == 7
        assert len(payload['by_day']) == 7
        assert payload['totals']['communications'] == 0
        assert payload['totals']['busiest_day'] is None
        assert {row['channel'] for row in payload['by_channel']} == {
            'notification',
            'email',
            'both',
        }

    def test_aggregates_types_channels_and_daily_volume(self, app):
        with app.app_context():
            user_a = _make_user('a')
            user_b = _make_user('b')
            db.session.add_all([user_a, user_b])
            db.session.flush()

            now = utcnow()
            today_notif = Notification(
                user_id=user_a.id,
                notification_type=NotificationType.admin_message,
                title='Today admin',
                message='Body',
                priority='high',
                is_read=True,
                created_at=now,
            )
            yesterday_notif = Notification(
                user_id=user_b.id,
                notification_type=NotificationType.assignment_created,
                title='Yesterday assignment',
                message='Body',
                priority='normal',
                is_read=False,
                created_at=now - timedelta(days=1),
            )
            old_notif = Notification(
                user_id=user_a.id,
                notification_type=NotificationType.deadline_reminder,
                title='Old reminder',
                message='Body',
                created_at=now - timedelta(days=40),
            )
            db.session.add_all([today_notif, yesterday_notif, old_notif])
            db.session.flush()

            linked = EmailDeliveryLog(
                notification_id=today_notif.id,
                user_id=user_a.id,
                email_address=user_a.email,
                subject='Today admin',
                status='sent',
                created_at=now,
            )
            orphan = EmailDeliveryLog(
                notification_id=None,
                user_id=user_b.id,
                email_address=user_b.email,
                subject='Orphan email',
                status='failed',
                error_message='SMTP error',
                created_at=now,
            )
            skipped = EmailDeliveryLog(
                notification_id=None,
                user_id=user_a.id,
                email_address=user_a.email,
                subject='Skipped digest',
                status='cancelled',
                error_message=f'{SKIP_ERROR_PREFIX}Already sent today',
                created_at=now,
            )
            db.session.add_all([linked, orphan, skipped])

            campaign = NotificationCampaign(
                name='Cycle reminder',
                title='Please submit',
                message='Due Friday',
                created_by=user_a.id,
                status=NotificationCampaignStatusValue.sent,
                sent_count=4,
                created_at=now,
            )
            db.session.add(campaign)
            db.session.commit()

            payload = build_communications_insights(30)

        assert payload['totals']['notifications'] == 2
        assert payload['totals']['orphan_emails'] == 2
        assert payload['totals']['communications'] == 4
        assert payload['totals']['today'] == 3  # today notif + 2 orphan emails
        assert payload['totals']['unique_recipients'] == 2
        assert payload['notifications']['read'] == 1
        assert payload['notifications']['unread'] == 1
        assert payload['email']['sent'] == 1
        assert payload['email']['failed'] == 1
        assert payload['email']['skipped'] == 1
        assert payload['email']['attention_needed'] == 1
        assert payload['campaigns']['total'] == 1
        assert payload['campaigns']['sent_recipients'] == 4

        type_keys = {row['type']: row['count'] for row in payload['by_type']}
        assert type_keys['admin_message'] == 1
        assert type_keys['assignment_created'] == 1
        assert type_keys['email'] == 2
        assert 'deadline_reminder' not in type_keys

        channel = {row['channel']: row['count'] for row in payload['by_channel']}
        assert channel['both'] == 1
        assert channel['notification'] == 1
        assert channel['email'] == 2

        today_key = now.date().isoformat()
        today_row = next(row for row in payload['by_day'] if row['date'] == today_key)
        assert today_row['notifications'] == 1
        assert today_row['orphan_emails'] == 2
        assert today_row['communications'] == 3
        assert payload['totals']['busiest_day']['date'] == today_key
        assert payload['totals']['busiest_day']['count'] == 3

    def test_empty_fallback_matches_window(self, app):
        with app.app_context():
            payload = empty_communications_insights(7)
        assert payload['period_days'] == 7
        assert len(payload['by_day']) == 7
        assert payload['totals']['communications'] == 0
