"""
Comprehensive tests for app/services/email/delivery.py.

Covers:
- log_email_attempt
- mark_email_sent
- mark_email_failed  (including retry/no-retry/max-retries paths)
- get_pending_retries
"""
import pytest
import uuid
from datetime import timedelta
from unittest.mock import patch

from app import db
from app.models import EmailDeliveryLog, User
from app.services.email.delivery import (
    log_email_attempt,
    mark_email_sent,
    mark_email_failed,
    mark_email_skipped,
    get_pending_retries,
    classify_orphan_email_log,
    email_delivery_log_can_retry,
    cancel_email_delivery_log,
    email_delivery_log_can_cancel,
    email_delivery_log_is_skipped,
    email_delivery_log_needs_attention,
    get_email_delivery_logs_needing_attention,
    count_email_delivery_logs_needing_attention,
    get_skipped_email_delivery_logs,
)
from app.utils.datetime_helpers import utcnow


def _make_user(suffix=None):
    suffix = suffix or uuid.uuid4().hex
    user = User(email=f"del-{suffix}@example.com", name=f"Del {suffix}", active=True)
    user.set_password("test")
    return user


# ---------------------------------------------------------------------------
# log_email_attempt
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("db_session")
class TestLogEmailAttempt:
    def test_creates_log_with_pending_status(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.commit()

            log = log_email_attempt(None, user.id, user.email, "Test Subject")

            assert log.id is not None
            assert log.status == "pending"
            assert log.user_id == user.id
            assert log.email_address == user.email
            assert log.subject == "Test Subject"
            assert log.notification_id is None

    def test_creates_log_with_notification_id(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.commit()

            log = log_email_attempt(99, user.id, user.email, "Subject")
            assert log.notification_id == 99

    def test_log_is_persisted_to_db(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.commit()

            log = log_email_attempt(None, user.id, user.email, "Persist Subject")
            log_id = log.id

            fetched = EmailDeliveryLog.query.get(log_id)
            assert fetched is not None
            assert fetched.status == "pending"

    def test_returns_email_delivery_log_instance(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.commit()

            log = log_email_attempt(None, user.id, user.email, "S")
            assert isinstance(log, EmailDeliveryLog)


# ---------------------------------------------------------------------------
# mark_email_sent
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("db_session")
class TestMarkEmailSent:
    def test_marks_status_sent(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.commit()

            log = log_email_attempt(None, user.id, user.email, "Subject")
            result = mark_email_sent(log.id)

            assert result.status == "sent"
            assert result.sent_at is not None

    def test_returns_none_for_missing_id(self, app):
        with app.app_context():
            result = mark_email_sent(99999999)
            assert result is None

    def test_sent_at_is_set(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.commit()

            log = log_email_attempt(None, user.id, user.email, "Subject")
            before = utcnow()
            result = mark_email_sent(log.id)
            after = utcnow()

            assert result.sent_at >= before
            assert result.sent_at <= after

    def test_persists_to_db(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.commit()

            log = log_email_attempt(None, user.id, user.email, "Subject")
            mark_email_sent(log.id)

            fetched = EmailDeliveryLog.query.get(log.id)
            assert fetched.status == "sent"


# ---------------------------------------------------------------------------
# mark_email_failed
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("db_session")
class TestMarkEmailFailed:
    def test_returns_none_for_missing_id(self, app):
        with app.app_context():
            result = mark_email_failed(99999999, "error", retry=False)
            assert result is None

    def test_default_marks_failed_without_auto_retry(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.commit()

            log = log_email_attempt(None, user.id, user.email, "Subject")
            result = mark_email_failed(log.id, "SMTP error", retry=True, max_retries=3)

            assert result.status == "failed"
            assert result.retry_count == 1
            assert result.next_retry_at is None
            assert result.error_message == "SMTP error"
            assert result.failed_at is not None

    def test_retry_flag_is_ignored(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.commit()

            log = log_email_attempt(None, user.id, user.email, "Subject")
            log.retry_count = 2
            db.session.commit()

            result = mark_email_failed(log.id, "error", retry=True, max_retries=3)
            assert result.status == "failed"
            assert result.retry_count == 3
            assert result.next_retry_at is None

    def test_retry_false_marks_failed(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.commit()

            log = log_email_attempt(None, user.id, user.email, "Subject")
            result = mark_email_failed(log.id, "error", retry=False)

            assert result.status == "failed"
            assert result.retry_count == 1

    def test_error_message_stored(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.commit()

            log = log_email_attempt(None, user.id, user.email, "Subject")
            mark_email_failed(log.id, "Connection refused", retry=False)

            fetched = EmailDeliveryLog.query.get(log.id)
            assert fetched.error_message == "Connection refused"


# ---------------------------------------------------------------------------
# get_pending_retries (automatic retries disabled)
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("db_session")
class TestGetPendingRetries:
    def test_returns_empty_list(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.commit()

            log = EmailDeliveryLog(
                notification_id=None,
                user_id=user.id,
                email_address=user.email,
                subject="Retry me",
                status="retrying",
                retry_count=1,
                next_retry_at=utcnow() - timedelta(minutes=1),
            )
            db.session.add(log)
            db.session.commit()

            assert get_pending_retries(max_retries=3) == []


@pytest.mark.usefixtures("db_session")
class TestCancelEmailDeliveryLog:
    def test_cancels_failed_log(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.commit()

            log = log_email_attempt(None, user.id, user.email, "Subject")
            mark_email_failed(log.id, "SMTP error", retry=False)

            ok, message = cancel_email_delivery_log(log.id)
            fetched = EmailDeliveryLog.query.get(log.id)

        assert ok is True
        status = fetched.status.value if hasattr(fetched.status, 'value') else fetched.status
        assert status == 'cancelled'
        assert email_delivery_log_can_retry(fetched) is False
        assert email_delivery_log_can_cancel(fetched) is False

    def test_cannot_cancel_sent_log(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.commit()

            log = log_email_attempt(None, user.id, user.email, "Subject")
            mark_email_sent(log.id)

            ok, message = cancel_email_delivery_log(log.id)

        assert ok is False


@pytest.mark.usefixtures("db_session")
class TestClassifyOrphanEmailLog:
    def test_daily_digest(self):
        assert classify_orphan_email_log('Daily Notification Digest - 3 new notification(s)') == 'daily_digest'

    def test_weekly_digest(self):
        assert classify_orphan_email_log('Weekly Notification Digest - 1 new notification(s)') == 'weekly_digest'

    def test_welcome(self):
        assert classify_orphan_email_log('Welcome to Humanitarian Databank') == 'welcome'

    def test_fds_access_request_digest(self):
        assert classify_orphan_email_log('Country Access Requests - 2 pending request(s)') == 'fds_access_request_digest'

    def test_unsupported(self):
        assert classify_orphan_email_log('Random subject') == 'unsupported'


@pytest.mark.usefixtures("db_session")
class TestMarkEmailSkipped:
    def test_marks_cancelled_not_failed(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.commit()

            log = log_email_attempt(None, user.id, user.email, 'Country Access Requests - skipped')
            result = mark_email_skipped(log.id, 'Already sent today')
            fetched = EmailDeliveryLog.query.get(log.id)

        assert result is not None
        status = fetched.status.value if hasattr(fetched.status, 'value') else fetched.status
        assert status == 'cancelled'
        assert email_delivery_log_is_skipped(fetched) is True
        assert email_delivery_log_needs_attention(fetched) is False
        assert email_delivery_log_can_cancel(fetched) is False


@pytest.mark.usefixtures("db_session")
class TestEmailDeliveryAttention:
    def test_skipped_legacy_failed_log_not_counted(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.commit()

            log = log_email_attempt(None, user.id, user.email, 'Country Access Requests - skipped')
            mark_email_failed(log.id, '[Skipped] Already sent today', retry=False)

            assert email_delivery_log_needs_attention(EmailDeliveryLog.query.get(log.id)) is False
            assert count_email_delivery_logs_needing_attention() == 0
            skipped = get_skipped_email_delivery_logs()
            assert len(skipped) == 1
            assert skipped[0].id == log.id

    def test_superseded_failure_not_counted(self, app):
        from app.models import Notification, NotificationType

        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.flush()

            notification = Notification(
                user_id=user.id,
                notification_type=NotificationType.admin_message,
                title='Retry test',
                message='Body',
            )
            db.session.add(notification)
            db.session.flush()

            failed = EmailDeliveryLog(
                notification_id=notification.id,
                user_id=user.id,
                email_address=user.email,
                subject='Subject',
                status='failed',
                error_message='SMTP error',
                created_at=utcnow() - timedelta(minutes=5),
            )
            sent = EmailDeliveryLog(
                notification_id=notification.id,
                user_id=user.id,
                email_address=user.email,
                subject='Subject',
                status='sent',
                sent_at=utcnow(),
                created_at=utcnow(),
            )
            db.session.add_all([failed, sent])
            db.session.commit()

            assert email_delivery_log_needs_attention(failed) is False
            assert get_email_delivery_logs_needing_attention() == []

    def test_active_failure_is_counted(self, app):
        from app.models import Notification, NotificationType

        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.flush()

            notification = Notification(
                user_id=user.id,
                notification_type=NotificationType.admin_message,
                title='Failure',
                message='Body',
            )
            db.session.add(notification)
            db.session.flush()

            log = EmailDeliveryLog(
                notification_id=notification.id,
                user_id=user.id,
                email_address=user.email,
                subject='Subject',
                status='failed',
                error_message='SMTP error',
            )
            db.session.add(log)
            db.session.commit()

            attention = get_email_delivery_logs_needing_attention()

        assert len(attention) == 1
        assert attention[0].id == log.id

    def test_orphan_digest_failure_is_counted(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.commit()

            log = log_email_attempt(
                None,
                user.id,
                user.email,
                'Country Access Requests - 2 pending request(s)',
            )
            mark_email_failed(log.id, 'SMTP timeout', retry=False)

            attention = get_email_delivery_logs_needing_attention()

        assert len(attention) == 1
        assert attention[0].id == log.id
