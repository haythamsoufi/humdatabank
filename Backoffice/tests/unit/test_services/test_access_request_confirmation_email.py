"""Confirmation email sent when a user submits a country access request."""

from unittest.mock import patch

import pytest

from app.models import CountryAccessRequest, EmailDeliveryLog
from app.services.email.access_request_confirmation import (
    ACCESS_REQUEST_CONFIRMATION_SUBJECT_PREFIX,
    confirmation_subject,
    country_names_from_confirmation_subject,
    queue_access_request_confirmation_email,
    retry_access_request_confirmation_email,
    send_access_request_confirmation_for_request_ids,
)
from tests.factories import create_test_country, create_test_user

pytestmark = [pytest.mark.unit]


def _status(log):
    return log.status.value if hasattr(log.status, "value") else log.status


def _make_request(db_session, user, country, message=None):
    req = CountryAccessRequest(
        user_id=user.id,
        country_id=country.id,
        request_message=message,
        status="pending",
    )
    db_session.add(req)
    db_session.commit()
    db_session.refresh(req)
    return req


class TestConfirmationSubject:
    def test_joins_country_names(self):
        subject = confirmation_subject(["Kenya", "Chad"])
        assert subject == f"{ACCESS_REQUEST_CONFIRMATION_SUBJECT_PREFIX}Kenya · Chad"
        assert country_names_from_confirmation_subject(subject) == ["Kenya", "Chad"]

    def test_truncated_subject_is_not_parsed(self):
        assert country_names_from_confirmation_subject(
            f"{ACCESS_REQUEST_CONFIRMATION_SUBJECT_PREFIX}Kenya..."
        ) == []


class TestQueueAccessRequestConfirmation:
    def test_disabled_does_not_schedule_send(self, app, db_session):
        with app.app_context():
            user = create_test_user(db_session, email="confirm-off@example.com")
            with app.test_request_context("/"):
                with patch(
                    "app.services.email.access_request_confirmation.get_access_request_confirmation_email_enabled",
                    return_value=False,
                ), patch(
                    "app.services.email.access_request_confirmation.register_post_commit",
                ) as mock_register:
                    queued = queue_access_request_confirmation_email(user.id, [1])
        assert queued is False
        mock_register.assert_not_called()

    def test_enabled_schedules_send_after_commit(self, app, db_session):
        with app.app_context():
            user = create_test_user(db_session, email="confirm-on@example.com")
            with app.test_request_context("/"):
                with patch(
                    "app.services.email.access_request_confirmation.get_access_request_confirmation_email_enabled",
                    return_value=True,
                ), patch(
                    "app.services.email.access_request_confirmation.register_post_commit",
                ) as mock_register:
                    queued = queue_access_request_confirmation_email(user.id, [4, 9])
        assert queued is True
        mock_register.assert_called_once()
        assert mock_register.call_args.args[1:] == (user.id, [4, 9])


class TestSendAccessRequestConfirmation:
    def test_sends_one_email_and_marks_delivery_log(self, app, db_session):
        with app.app_context():
            user = create_test_user(db_session, email="requester-mail@example.com", name="Jamie")
            country = create_test_country(db_session, name="Confirmland Alpha")
            req = _make_request(db_session, user, country, message="Need reporting access")
            with patch(
                "app.services.email.access_request_confirmation.send_email",
                return_value=True,
            ) as mock_send:
                ok = send_access_request_confirmation_for_request_ids(user.id, [req.id])
            assert ok is True
            mock_send.assert_called_once()
            kwargs = mock_send.call_args.kwargs
            assert kwargs["recipients"] == ["requester-mail@example.com"]
            assert country.name in kwargs["subject"]
            assert "Need reporting access" in kwargs["html"]
            log = EmailDeliveryLog.query.filter_by(user_id=user.id).one()
            assert _status(log) == "sent"
            assert log.subject.startswith(ACCESS_REQUEST_CONFIRMATION_SUBJECT_PREFIX)

    def test_disabled_skips_without_a_delivery_log(self, app, db_session):
        with app.app_context():
            user = create_test_user(db_session, email="skip-mail@example.com")
            country = create_test_country(db_session, name="Confirmland Beta")
            req = _make_request(db_session, user, country)
            with patch(
                "app.services.email.access_request_confirmation.get_access_request_confirmation_email_enabled",
                return_value=False,
            ), patch(
                "app.services.email.access_request_confirmation.send_email",
            ) as mock_send:
                ok = send_access_request_confirmation_for_request_ids(user.id, [req.id])
            assert ok is False
            mock_send.assert_not_called()
            assert EmailDeliveryLog.query.filter_by(user_id=user.id).count() == 0

    def test_api_failure_is_logged(self, app, db_session):
        with app.app_context():
            user = create_test_user(db_session, email="fail-mail@example.com")
            country = create_test_country(db_session, name="Confirmland Gamma")
            req = _make_request(db_session, user, country)
            with patch(
                "app.services.email.access_request_confirmation.send_email",
                return_value=False,
            ):
                ok = send_access_request_confirmation_for_request_ids(user.id, [req.id])
            assert ok is False
            log = EmailDeliveryLog.query.filter_by(user_id=user.id).one()
            assert _status(log) == "failed"

    def test_retry_resends_matched_request(self, app, db_session):
        with app.app_context():
            user = create_test_user(db_session, email="retry-mail@example.com")
            country = create_test_country(db_session, name="Confirmland Delta")
            req = _make_request(db_session, user, country)
            log = EmailDeliveryLog(
                user_id=user.id,
                email_address=user.email,
                subject=confirmation_subject([country.name]),
                status="failed",
            )
            db_session.add(log)
            db_session.commit()
            with patch(
                "app.services.email.access_request_confirmation.send_email",
                return_value=True,
            ) as mock_send:
                ok = retry_access_request_confirmation_email(user, log)
            assert ok is True
            mock_send.assert_called_once()
            assert country.name in mock_send.call_args.kwargs["subject"]
            db_session.refresh(log)
            assert _status(log) == "sent"
