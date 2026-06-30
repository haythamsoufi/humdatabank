"""Tests for FDS access request digest emails."""

from contextlib import contextmanager
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from app.models import CountryAccessRequest, EmailDeliveryLog
from app.services.country_access_request_service import (
    FDS_ACCESS_REQUEST_DIGEST_SUBJECT_PREFIX,
    pending_country_access_requests_by_fds_member,
)
from app.services.email.fds_access_request_digest import (
    run_fds_access_request_digest_job,
    send_fds_access_request_digest_email,
    send_fds_access_request_digests,
)
from app.utils.datetime_helpers import utcnow
from tests.factories import create_test_country, create_test_user

pytestmark = [pytest.mark.unit]

DIGEST_HOUR = 9


@contextmanager
def _at_digest_hour(hour=DIGEST_HOUR):
    """Simulate the scheduler firing at the configured Geneva hour."""
    geneva_now = datetime(2026, 6, 30, hour, 0, tzinfo=ZoneInfo("Europe/Zurich"))
    with patch(
        "app.services.email.fds_access_request_digest.now_in_org_timezone",
        return_value=geneva_now,
    ), patch(
        "app.services.email.fds_access_request_digest.get_fds_access_request_digest_local_hour",
        return_value=hour,
    ):
        yield


def _make_access_request(db_session, user, country, status="pending"):
    req = CountryAccessRequest(
        user_id=user.id,
        country_id=country.id,
        status=status,
    )
    db_session.add(req)
    db_session.commit()
    db_session.refresh(req)
    return req


class TestPendingCountryAccessRequestsByFdsMember:
    def test_groups_pending_requests_by_fds_member(self, db_session, app, admin_user):
        with app.app_context():
            fds_a = create_test_user(db_session, email="fds-a@example.com")
            fds_b = create_test_user(db_session, email="fds-b@example.com")
            country_a = create_test_country(db_session, iso3="FAA", iso2="FA")
            country_b = create_test_country(db_session, iso3="FBB", iso2="FB")
            country_a.fds_member_user_id = fds_a.id
            country_b.fds_member_user_id = fds_b.id
            db_session.commit()

            requester = create_test_user(db_session, email="requester@example.com")
            req_a = _make_access_request(db_session, requester, country_a)
            req_b = _make_access_request(db_session, requester, country_b)

            grouped = pending_country_access_requests_by_fds_member()
            assert len(grouped[fds_a.id]) == 1
            assert grouped[fds_a.id][0].id == req_a.id
            assert len(grouped[fds_b.id]) == 1
            assert grouped[fds_b.id][0].id == req_b.id

    def test_omits_countries_without_fds_member(self, db_session, app):
        with app.app_context():
            country = create_test_country(db_session, iso3="FUN", iso2="FU")
            requester = create_test_user(db_session, email="no-fds@example.com")
            _make_access_request(db_session, requester, country)

            grouped = pending_country_access_requests_by_fds_member()
            assert grouped == {}


class TestSendFdsAccessRequestDigests:
    def test_skips_when_disabled(self, db_session, app, admin_user):
        with app.app_context():
            country = create_test_country(db_session, iso3="OFF", iso2="OF")
            country.fds_member_user_id = admin_user.id
            db_session.commit()
            requester = create_test_user(db_session, email="disabled@example.com")
            _make_access_request(db_session, requester, country)

            with patch(
                "app.services.email.fds_access_request_digest.get_fds_access_request_digest_enabled",
                return_value=False,
            ), patch(
                "app.services.email.fds_access_request_digest.get_auto_approve_access_requests",
                return_value=False,
            ), patch(
                "app.services.email.fds_access_request_digest.send_fds_access_request_digest_email",
            ) as mock_send:
                assert send_fds_access_request_digests() == 0
            mock_send.assert_not_called()

    def test_skips_when_auto_approve_enabled(self, db_session, app, admin_user):
        with app.app_context():
            country = create_test_country(db_session, iso3="AUT", iso2="AU")
            country.fds_member_user_id = admin_user.id
            db_session.commit()
            requester = create_test_user(db_session, email="auto@example.com")
            _make_access_request(db_session, requester, country)

            with patch(
                "app.services.email.fds_access_request_digest.get_auto_approve_access_requests",
                return_value=True,
            ):
                assert send_fds_access_request_digests() == 0

    def test_sends_digest_to_fds_member_with_pending_requests(self, db_session, app, admin_user):
        with app.app_context():
            country = create_test_country(db_session, iso3="DIG", iso2="DI")
            country.fds_member_user_id = admin_user.id
            db_session.commit()
            requester = create_test_user(db_session, email="digest@example.com")
            _make_access_request(db_session, requester, country)

            with _at_digest_hour(), patch(
                "app.services.email.fds_access_request_digest.get_auto_approve_access_requests",
                return_value=False,
            ), patch(
                "app.services.email.fds_access_request_digest.send_fds_access_request_digest_email",
                return_value=True,
            ) as mock_send:
                sent = send_fds_access_request_digests()

            assert sent == 1
            mock_send.assert_called_once()
            assert mock_send.call_args[0][0].id == admin_user.id

    def test_does_not_resend_same_day(self, db_session, app, admin_user):
        with app.app_context():
            country = create_test_country(db_session, iso3="ONC", iso2="ON")
            country.fds_member_user_id = admin_user.id
            db_session.commit()
            requester = create_test_user(db_session, email="once@example.com")
            _make_access_request(db_session, requester, country)

            db_session.add(
                EmailDeliveryLog(
                    user_id=admin_user.id,
                    email_address=admin_user.email,
                    subject=f"{FDS_ACCESS_REQUEST_DIGEST_SUBJECT_PREFIX}1 pending request(s)",
                    status='sent',
                    sent_at=utcnow(),
                )
            )
            db_session.commit()

            with _at_digest_hour(), patch(
                "app.services.email.fds_access_request_digest.get_auto_approve_access_requests",
                return_value=False,
            ), patch(
                "app.services.email.fds_access_request_digest.send_fds_access_request_digest_email",
            ) as mock_send:
                sent = send_fds_access_request_digests()

            assert sent == 0
            mock_send.assert_not_called()

    def test_send_digest_email_returns_false_without_requests(self, app, admin_user):
        with app.app_context():
            assert send_fds_access_request_digest_email(admin_user, []) is False

    def test_send_digest_email_ccs_team_email(self, db_session, app, admin_user):
        with app.app_context():
            country = create_test_country(db_session, iso3="TCC", iso2="TC")
            country.fds_member_user_id = admin_user.id
            db_session.commit()
            requester = create_test_user(db_session, email="cc-test@example.com")
            req = _make_access_request(db_session, requester, country)

            with patch(
                "app.services.email.fds_access_request_digest.get_org_team_email",
                return_value="team@ifrc.org",
            ), patch(
                "app.services.email.fds_access_request_digest.send_email",
                return_value=True,
            ) as mock_send, patch(
                "app.services.email.fds_access_request_digest.log_email_attempt",
                return_value=type("Log", (), {"id": 1})(),
            ), patch(
                "app.services.email.fds_access_request_digest.mark_email_sent",
            ):
                assert send_fds_access_request_digest_email(admin_user, [req]) is True

            mock_send.assert_called_once()
            assert mock_send.call_args.kwargs["recipients"] == [admin_user.email]
            assert mock_send.call_args.kwargs["cc"] == ["team@ifrc.org"]
            assert mock_send.call_args.kwargs.get("expose_recipients_in_to") is True

    def test_send_digest_email_skips_cc_when_team_is_recipient(self, db_session, app):
        with app.app_context():
            fds_user = create_test_user(db_session, email="team@ifrc.org")
            country = create_test_country(db_session, iso3="TSK", iso2="TS")
            country.fds_member_user_id = fds_user.id
            db_session.commit()
            requester = create_test_user(db_session, email="cc-skip@example.com")
            req = _make_access_request(db_session, requester, country)

            with patch(
                "app.services.email.fds_access_request_digest.get_org_team_email",
                return_value="team@ifrc.org",
            ), patch(
                "app.services.email.fds_access_request_digest.send_email",
                return_value=True,
            ) as mock_send, patch(
                "app.services.email.fds_access_request_digest.log_email_attempt",
                return_value=type("Log", (), {"id": 2})(),
            ), patch(
                "app.services.email.fds_access_request_digest.mark_email_sent",
            ):
                assert send_fds_access_request_digest_email(fds_user, [req]) is True

            assert mock_send.call_args.kwargs.get("cc") is None


class TestRunFdsAccessRequestDigestJob:
    def test_logs_skip_reason_when_disabled(self, db_session, app, admin_user):
        with app.app_context():
            with patch(
                "app.services.email.fds_access_request_digest.get_fds_access_request_digest_enabled",
                return_value=False,
            ):
                result = run_fds_access_request_digest_job()

            assert result.ran is False
            assert result.skip_reason == "Digest emails disabled in settings"

    def test_waits_when_geneva_hour_does_not_match(self, db_session, app):
        with app.app_context():
            with patch(
                "app.services.email.fds_access_request_digest.get_fds_access_request_digest_enabled",
                return_value=True,
            ), patch(
                "app.services.email.fds_access_request_digest.get_auto_approve_access_requests",
                return_value=False,
            ), patch(
                "app.services.email.fds_access_request_digest.now_in_org_timezone",
                return_value=datetime(2026, 6, 30, 8, 0, tzinfo=ZoneInfo("Europe/Zurich")),
            ), patch(
                "app.services.email.fds_access_request_digest.get_fds_access_request_digest_local_hour",
                return_value=9,
            ):
                result = run_fds_access_request_digest_job()

            assert result.ran is False
            assert result.skip_reason is None
            assert result.geneva_hour == 8
            assert result.configured_hour == 9

    def test_no_system_manager_comms_when_no_pending_requests(self, db_session, app):
        with app.app_context():
            sm = create_test_user(db_session, email="sm-digest@example.com", role="system_manager")

            with _at_digest_hour(), patch(
                "app.services.email.fds_access_request_digest.get_fds_access_request_digest_enabled",
                return_value=True,
            ), patch(
                "app.services.email.fds_access_request_digest.get_auto_approve_access_requests",
                return_value=False,
            ):
                result = run_fds_access_request_digest_job()

            assert result.ran is True
            assert result.skip_reason == "No pending country access requests"
            assert EmailDeliveryLog.query.filter_by(user_id=sm.id).count() == 0

    def test_creates_email_log_without_notification_on_successful_send(self, db_session, app, admin_user):
        with app.app_context():
            country = create_test_country(db_session, iso3="COM", iso2="CM")
            country.fds_member_user_id = admin_user.id
            db_session.commit()
            requester = create_test_user(db_session, email="comms@example.com")
            _make_access_request(db_session, requester, country)

            with _at_digest_hour(), patch(
                "app.services.email.fds_access_request_digest.get_fds_access_request_digest_enabled",
                return_value=True,
            ), patch(
                "app.services.email.fds_access_request_digest.get_auto_approve_access_requests",
                return_value=False,
            ), patch(
                "app.services.email.fds_access_request_digest.send_email",
                return_value=True,
            ):
                result = run_fds_access_request_digest_job()

            assert result.sent_count == 1

            log = EmailDeliveryLog.query.filter_by(user_id=admin_user.id).order_by(
                EmailDeliveryLog.created_at.desc()
            ).first()
            assert log is not None
            assert log.status == "sent"
            assert log.notification_id is None


class TestFdsDigestLastSentSummary:
    def test_empty_when_no_logs(self, db_session, app):
        with app.app_context():
            from app.services.email.fds_access_request_digest import (
                get_fds_access_request_digest_last_sent_summary,
            )

            EmailDeliveryLog.query.filter(
                EmailDeliveryLog.subject.like(
                    f"{FDS_ACCESS_REQUEST_DIGEST_SUBJECT_PREFIX}% pending request(s)"
                )
            ).delete(synchronize_session=False)
            db_session.commit()

            summary = get_fds_access_request_digest_last_sent_summary()
            assert summary["recipient_count"] == 0
            assert summary["recipients"] == []

    def test_returns_latest_geneva_day_recipients(self, db_session, app, admin_user):
        with app.app_context():
            from app.services.email.fds_access_request_digest import (
                get_fds_access_request_digest_last_sent_summary,
            )

            sent_at = utcnow()
            db_session.add(
                EmailDeliveryLog(
                    user_id=admin_user.id,
                    email_address=admin_user.email,
                    subject=f"{FDS_ACCESS_REQUEST_DIGEST_SUBJECT_PREFIX}2 pending request(s)",
                    status="sent",
                    sent_at=sent_at,
                )
            )
            db_session.commit()

            summary = get_fds_access_request_digest_last_sent_summary()
            assert summary["recipient_count"] == 1
            assert summary["recipients"][0]["email"] == admin_user.email
            assert summary["recipients"][0]["request_count"] == 2


class TestManualFdsDigestRun:
    def test_manual_bypasses_hour_and_once_per_day(self, db_session, app, admin_user):
        with app.app_context():
            country = create_test_country(db_session, iso3="MAN", iso2="MN")
            country.fds_member_user_id = admin_user.id
            db_session.commit()
            requester = create_test_user(db_session, email="manual@example.com")
            _make_access_request(db_session, requester, country)

            db_session.add(
                EmailDeliveryLog(
                    user_id=admin_user.id,
                    email_address=admin_user.email,
                    subject=f"{FDS_ACCESS_REQUEST_DIGEST_SUBJECT_PREFIX}1 pending request(s)",
                    status="sent",
                    sent_at=utcnow(),
                )
            )
            db_session.commit()

            with patch(
                "app.services.email.fds_access_request_digest.get_fds_access_request_digest_enabled",
                return_value=False,
            ), patch(
                "app.services.email.fds_access_request_digest.get_auto_approve_access_requests",
                return_value=False,
            ), patch(
                "app.services.email.fds_access_request_digest.now_in_org_timezone",
                return_value=datetime(2026, 6, 30, 8, 0, tzinfo=ZoneInfo("Europe/Zurich")),
            ), patch(
                "app.services.email.fds_access_request_digest.get_fds_access_request_digest_local_hour",
                return_value=9,
            ), patch(
                "app.services.email.fds_access_request_digest.send_fds_access_request_digest_email",
                return_value=True,
            ) as mock_send:
                result = run_fds_access_request_digest_job(manual=True)

            assert result.ran is True
            assert result.sent_count == 1
            mock_send.assert_called_once()
