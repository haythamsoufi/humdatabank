"""Tests for FDS access request digest emails."""

from unittest.mock import patch

import pytest

from app.models import CountryAccessRequest, EmailDeliveryLog
from app.services.country_access_request_service import (
    FDS_ACCESS_REQUEST_DIGEST_SUBJECT_PREFIX,
    pending_country_access_requests_by_fds_member,
)
from app.services.email.fds_access_request_digest import (
    send_fds_access_request_digest_email,
    send_fds_access_request_digests,
)
from app.utils.datetime_helpers import utcnow
from tests.factories import create_test_country, create_test_user

pytestmark = [pytest.mark.unit]


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

            with patch(
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

            with patch(
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
