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
    get_pending_retries,
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

    def test_first_failure_schedules_retry(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.commit()

            log = log_email_attempt(None, user.id, user.email, "Subject")
            result = mark_email_failed(log.id, "SMTP error", retry=True, max_retries=3)

            assert result.status == "retrying"
            assert result.retry_count == 1
            assert result.next_retry_at is not None
            assert result.error_message == "SMTP error"
            assert result.failed_at is not None

    def test_second_failure_uses_longer_delay(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.commit()

            log = log_email_attempt(None, user.id, user.email, "Subject")
            # Simulate already having retried once
            log.retry_count = 1
            db.session.commit()

            result = mark_email_failed(log.id, "error", retry=True, max_retries=3)
            assert result.retry_count == 2
            assert result.status == "retrying"
            # Second retry should be at least 60 minutes (3600 sec) from now
            from datetime import timedelta
            min_expected = utcnow() + timedelta(minutes=59)
            assert result.next_retry_at >= min_expected

    def test_third_failure_uses_longest_delay(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.commit()

            log = log_email_attempt(None, user.id, user.email, "Subject")
            log.retry_count = 2
            db.session.commit()

            result = mark_email_failed(log.id, "error", retry=True, max_retries=3)
            assert result.retry_count == 3
            assert result.status == "retrying"
            # Third delay index is 2 → 240 minutes
            min_expected = utcnow() + timedelta(minutes=239)
            assert result.next_retry_at >= min_expected

    def test_retry_false_marks_failed(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.commit()

            log = log_email_attempt(None, user.id, user.email, "Subject")
            result = mark_email_failed(log.id, "error", retry=False)

            assert result.status == "failed"
            assert result.retry_count == 1

    def test_max_retries_exceeded_marks_failed(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.commit()

            log = log_email_attempt(None, user.id, user.email, "Subject")
            log.retry_count = 3  # Already at max
            db.session.commit()

            result = mark_email_failed(log.id, "too many retries", retry=True, max_retries=3)
            assert result.status == "failed"
            assert result.retry_count == 4

    def test_error_message_stored(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.commit()

            log = log_email_attempt(None, user.id, user.email, "Subject")
            mark_email_failed(log.id, "Connection refused", retry=False)

            fetched = EmailDeliveryLog.query.get(log.id)
            assert fetched.error_message == "Connection refused"

    def test_custom_max_retries(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.commit()

            log = log_email_attempt(None, user.id, user.email, "Subject")
            log.retry_count = 0
            db.session.commit()

            # With max_retries=1, first failure should still schedule retry
            result = mark_email_failed(log.id, "err", retry=True, max_retries=1)
            assert result.status == "retrying"
            assert result.retry_count == 1

    def test_already_at_custom_max_retries_marks_failed(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.commit()

            log = log_email_attempt(None, user.id, user.email, "Subject")
            log.retry_count = 1
            db.session.commit()

            # With max_retries=1, retry_count(1) == max_retries(1), should fail
            result = mark_email_failed(log.id, "err", retry=True, max_retries=1)
            assert result.status == "failed"


# ---------------------------------------------------------------------------
# get_pending_retries
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("db_session")
class TestGetPendingRetries:
    def test_returns_ready_retries(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.commit()

            # Create a retrying log with next_retry_at in the past
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

            results = get_pending_retries(max_retries=3)
            ids = [r.id for r in results]
            assert log.id in ids

    def test_skips_future_retries(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.commit()

            log = EmailDeliveryLog(
                notification_id=None,
                user_id=user.id,
                email_address=user.email,
                subject="Future retry",
                status="retrying",
                retry_count=1,
                next_retry_at=utcnow() + timedelta(hours=1),
            )
            db.session.add(log)
            db.session.commit()

            results = get_pending_retries(max_retries=3)
            ids = [r.id for r in results]
            assert log.id not in ids

    def test_skips_sent_logs(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.commit()

            log = EmailDeliveryLog(
                notification_id=None,
                user_id=user.id,
                email_address=user.email,
                subject="Sent",
                status="sent",
                retry_count=0,
                next_retry_at=utcnow() - timedelta(minutes=1),
            )
            db.session.add(log)
            db.session.commit()

            results = get_pending_retries(max_retries=3)
            ids = [r.id for r in results]
            assert log.id not in ids

    def test_skips_exceeded_max_retries(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.commit()

            log = EmailDeliveryLog(
                notification_id=None,
                user_id=user.id,
                email_address=user.email,
                subject="Too many retries",
                status="retrying",
                retry_count=5,
                next_retry_at=utcnow() - timedelta(minutes=1),
            )
            db.session.add(log)
            db.session.commit()

            results = get_pending_retries(max_retries=3)
            ids = [r.id for r in results]
            assert log.id not in ids

    def test_returns_empty_when_no_pending(self, app):
        with app.app_context():
            results = get_pending_retries(max_retries=3)
            # No assertion on exact empty list since other tests may have data
            assert isinstance(results, list)

    def test_custom_max_retries_filter(self, app):
        with app.app_context():
            user = _make_user()
            db.session.add(user)
            db.session.commit()

            log = EmailDeliveryLog(
                notification_id=None,
                user_id=user.id,
                email_address=user.email,
                subject="Custom max",
                status="retrying",
                retry_count=2,
                next_retry_at=utcnow() - timedelta(minutes=1),
            )
            db.session.add(log)
            db.session.commit()

            # With max_retries=3: retry_count=2 <= 3 → included
            results_included = get_pending_retries(max_retries=3)
            assert log.id in [r.id for r in results_included]

            # With max_retries=1: retry_count=2 > 1 → excluded
            results_excluded = get_pending_retries(max_retries=1)
            assert log.id not in [r.id for r in results_excluded]
