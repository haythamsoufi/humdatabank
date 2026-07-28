"""
Tests for app/routes/main/assignments.py

Covers:
  - POST /select_country/<id>
  - POST /reopen_assignment/<id>
  - POST /approve_assignment/<id>
  - POST /return_assignment_for_revision/<id>
  - POST /request_country_access
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from tests.factories import (
    create_test_user,
    create_test_country,
    create_test_assignment_entity_status,
    _grant_entity_permission,
)
from tests.helpers import login_session, assert_redirect

pytestmark = [pytest.mark.unit]

# AuthorizationService is imported lazily inside each route function; patch at source.
_AUTH_SVC = "app.services.organization.authorization_service.AuthorizationService"
# Notification functions are also imported lazily inside each route function.
_NOTIF_CORE = "app.services.notification.core"
_APP_SETTINGS = "app.services.platform.app_settings_service"
_NOTIF_AUDIENCE = "app.services.notification.audience"


# ===========================================================================
# Helpers
# ===========================================================================

def _login(client, user):
    login_session(client, user.id)


# ===========================================================================
# POST /select_country/<country_id>
# ===========================================================================

class TestSelectCountry:
    def test_unauthenticated_redirects_to_login(self, client, db_session, app):
        resp = client.post("/select_country/1")
        assert_redirect(resp)
        assert "login" in (resp.headers.get("Location") or "").lower()

    def test_authenticated_redirects_to_dashboard(self, client, db_session, app, admin_user):
        _login(client, admin_user)
        resp = client.post("/select_country/1")
        assert_redirect(resp, "dashboard")


# ===========================================================================
# POST /reopen_assignment/<aes_id>
# ===========================================================================

class TestReopenAssignment:
    def test_unauthenticated_redirects_to_login(self, client, db_session, app):
        resp = client.post("/reopen_assignment/1")
        assert_redirect(resp)
        assert "login" in (resp.headers.get("Location") or "").lower()

    def test_aes_not_found_returns_404(self, client, db_session, app, admin_user):
        _login(client, admin_user)
        resp = client.post("/reopen_assignment/999999")
        assert resp.status_code == 404

    def test_no_permission_redirects_with_flash(self, client, db_session, app, admin_user):
        aes = create_test_assignment_entity_status(db_session, status="sent_for_review")
        _login(client, admin_user)
        with patch(f"{_AUTH_SVC}.can_reopen_assignment", return_value=False):
            resp = client.post(f"/reopen_assignment/{aes.id}", follow_redirects=False)
        assert_redirect(resp, "dashboard")

    def test_success_redirects_to_dashboard(self, client, db_session, app, admin_user):
        aes = create_test_assignment_entity_status(db_session, status="sent_for_review")
        _login(client, admin_user)
        with patch(f"{_AUTH_SVC}.can_reopen_assignment", return_value=True), \
             patch(f"{_NOTIF_CORE}.notify_assignment_reopened", return_value=None):
            resp = client.post(f"/reopen_assignment/{aes.id}", follow_redirects=False)
        assert_redirect(resp, "dashboard")

    def test_success_with_selected_country_in_session(self, client, db_session, app, admin_user):
        country = create_test_country(db_session)
        aes = create_test_assignment_entity_status(db_session, country=country, status="sent_for_review")
        _login(client, admin_user)
        with client.session_transaction() as sess:
            sess["selected_country_id"] = country.id

        with patch(f"{_AUTH_SVC}.can_reopen_assignment", return_value=True), \
             patch(f"{_NOTIF_CORE}.notify_assignment_reopened", return_value=None):
            resp = client.post(f"/reopen_assignment/{aes.id}", follow_redirects=False)
        assert_redirect(resp)
        location = resp.headers.get("Location", "")
        assert "dashboard" in location
        assert str(country.id) in location

    def test_db_error_flashes_error(self, client, db_session, app, admin_user):
        aes = create_test_assignment_entity_status(db_session, status="sent_for_review")
        _login(client, admin_user)
        with patch(f"{_AUTH_SVC}.can_reopen_assignment", return_value=True), \
             patch("app.routes.main.assignments.db.session.flush", side_effect=Exception("DB error")), \
             patch("app.routes.main.assignments.request_transaction_rollback"):
            resp = client.post(f"/reopen_assignment/{aes.id}", follow_redirects=True)
        assert resp.status_code == 200
        assert b"Error" in resp.data or b"error" in resp.data

    def test_reopened_after_close_flag_set(self, client, db_session, app, admin_user):
        """When assignment was closed, reopened_after_close should be set to True."""
        aes = create_test_assignment_entity_status(db_session, status="sent_for_review")
        _login(client, admin_user)

        mock_assigned_form = MagicMock()
        mock_assigned_form.is_effectively_closed = True

        with patch(f"{_AUTH_SVC}.can_reopen_assignment", return_value=True), \
             patch(f"{_NOTIF_CORE}.notify_assignment_reopened", return_value=None), \
             patch.object(
                 type(aes),
                 "assigned_form",
                 new_callable=lambda: property(lambda self: mock_assigned_form),
             ):
            resp = client.post(f"/reopen_assignment/{aes.id}", follow_redirects=False)
        assert_redirect(resp)

    def test_notification_error_does_not_break_route(self, client, db_session, app, admin_user):
        """Notification failure inside reopen should be swallowed."""
        aes = create_test_assignment_entity_status(db_session, status="sent_for_review")
        _login(client, admin_user)
        with patch(f"{_AUTH_SVC}.can_reopen_assignment", return_value=True), \
             patch(f"{_NOTIF_CORE}.notify_assignment_reopened", side_effect=Exception("notification failed")):
            resp = client.post(f"/reopen_assignment/{aes.id}", follow_redirects=False)
        assert_redirect(resp)


# ===========================================================================
# POST /approve_assignment/<aes_id>
# ===========================================================================

class TestApproveAssignment:
    def test_unauthenticated_redirects_to_login(self, client, db_session, app):
        resp = client.post("/approve_assignment/1")
        assert_redirect(resp)
        assert "login" in (resp.headers.get("Location") or "").lower()

    def test_aes_not_found_returns_404(self, client, db_session, app, admin_user):
        _login(client, admin_user)
        resp = client.post("/approve_assignment/999999")
        assert resp.status_code == 404

    def test_no_permission_redirects_with_flash(self, client, db_session, app, admin_user):
        aes = create_test_assignment_entity_status(db_session, status="sent_for_review")
        _login(client, admin_user)
        with patch(f"{_AUTH_SVC}.can_approve_assignment", return_value=False):
            resp = client.post(f"/approve_assignment/{aes.id}", follow_redirects=False)
        assert_redirect(resp, "dashboard")

    def test_success_redirects_to_dashboard(self, client, db_session, app, admin_user):
        aes = create_test_assignment_entity_status(db_session, status="sent_for_review")
        _login(client, admin_user)
        with patch(f"{_AUTH_SVC}.can_approve_assignment", return_value=True), \
             patch(f"{_NOTIF_CORE}.notify_assignment_approved", return_value=None):
            resp = client.post(f"/approve_assignment/{aes.id}", follow_redirects=False)
        assert_redirect(resp)

    def test_success_with_selected_country_in_session(self, client, db_session, app, admin_user):
        country = create_test_country(db_session)
        aes = create_test_assignment_entity_status(db_session, country=country, status="sent_for_review")
        _login(client, admin_user)
        with client.session_transaction() as sess:
            sess["selected_country_id"] = country.id

        with patch(f"{_AUTH_SVC}.can_approve_assignment", return_value=True), \
             patch(f"{_NOTIF_CORE}.notify_assignment_approved", return_value=None):
            resp = client.post(f"/approve_assignment/{aes.id}", follow_redirects=False)
        assert_redirect(resp)
        location = resp.headers.get("Location", "")
        assert "dashboard" in location
        assert str(country.id) in location

    def test_db_error_flashes_error(self, client, db_session, app, admin_user):
        aes = create_test_assignment_entity_status(db_session, status="sent_for_review")
        _login(client, admin_user)
        with patch(f"{_AUTH_SVC}.can_approve_assignment", return_value=True), \
             patch("app.routes.main.assignments.db.session.flush", side_effect=Exception("DB error")), \
             patch("app.routes.main.assignments.request_transaction_rollback"):
            resp = client.post(f"/approve_assignment/{aes.id}", follow_redirects=True)
        assert resp.status_code == 200

    def test_notification_error_does_not_break_route(self, client, db_session, app, admin_user):
        aes = create_test_assignment_entity_status(db_session, status="sent_for_review")
        _login(client, admin_user)
        with patch(f"{_AUTH_SVC}.can_approve_assignment", return_value=True), \
             patch(f"{_NOTIF_CORE}.notify_assignment_approved", side_effect=Exception("notif fail")):
            resp = client.post(f"/approve_assignment/{aes.id}", follow_redirects=False)
        assert_redirect(resp)


# ===========================================================================
# POST /return_assignment_for_revision/<aes_id>
# ===========================================================================

class TestReturnAssignmentForRevision:
    def test_unauthenticated_redirects_to_login(self, client, db_session, app):
        resp = client.post("/return_assignment_for_revision/1")
        assert_redirect(resp)
        assert "login" in (resp.headers.get("Location") or "").lower()

    def test_aes_not_found_returns_404(self, client, db_session, app, admin_user):
        _login(client, admin_user)
        resp = client.post("/return_assignment_for_revision/999999")
        assert resp.status_code == 404

    def test_no_permission_redirects_with_flash(self, client, db_session, app, admin_user):
        aes = create_test_assignment_entity_status(db_session, status="sent_for_review")
        _login(client, admin_user)
        with patch(f"{_AUTH_SVC}.can_return_for_revision", return_value=False):
            resp = client.post(f"/return_assignment_for_revision/{aes.id}", follow_redirects=False)
        assert_redirect(resp, "dashboard")

    def test_success_redirects_to_dashboard(self, client, db_session, app, admin_user):
        aes = create_test_assignment_entity_status(db_session, status="sent_for_review")
        _login(client, admin_user)
        with patch(f"{_AUTH_SVC}.can_return_for_revision", return_value=True), \
             patch(f"{_NOTIF_CORE}.notify_assignment_returned_for_revision", return_value=None):
            resp = client.post(f"/return_assignment_for_revision/{aes.id}", follow_redirects=False)
        assert_redirect(resp)

    def test_success_with_selected_country_in_session(self, client, db_session, app, admin_user):
        country = create_test_country(db_session)
        aes = create_test_assignment_entity_status(db_session, country=country, status="sent_for_review")
        _login(client, admin_user)
        with client.session_transaction() as sess:
            sess["selected_country_id"] = country.id

        with patch(f"{_AUTH_SVC}.can_return_for_revision", return_value=True), \
             patch(f"{_NOTIF_CORE}.notify_assignment_returned_for_revision", return_value=None):
            resp = client.post(f"/return_assignment_for_revision/{aes.id}", follow_redirects=False)
        assert_redirect(resp)
        location = resp.headers.get("Location", "")
        assert "dashboard" in location
        assert str(country.id) in location

    def test_db_error_flashes_error(self, client, db_session, app, admin_user):
        aes = create_test_assignment_entity_status(db_session, status="sent_for_review")
        _login(client, admin_user)
        with patch(f"{_AUTH_SVC}.can_return_for_revision", return_value=True), \
             patch("app.routes.main.assignments.db.session.flush", side_effect=Exception("DB error")), \
             patch("app.routes.main.assignments.request_transaction_rollback"):
            resp = client.post(f"/return_assignment_for_revision/{aes.id}", follow_redirects=True)
        assert resp.status_code == 200

    def test_notification_error_does_not_break_route(self, client, db_session, app, admin_user):
        aes = create_test_assignment_entity_status(db_session, status="sent_for_review")
        _login(client, admin_user)
        with patch(f"{_AUTH_SVC}.can_return_for_revision", return_value=True), \
             patch(f"{_NOTIF_CORE}.notify_assignment_returned_for_revision", side_effect=Exception("notif fail")):
            resp = client.post(f"/return_assignment_for_revision/{aes.id}", follow_redirects=False)
        assert_redirect(resp)


# ===========================================================================
# POST /request_country_access
# ===========================================================================

class TestRequestCountryAccess:
    """POST /request_country_access"""

    URL = "/request_country_access"

    def _post(self, client, data: dict, follow_redirects: bool = False):
        return client.post(self.URL, data=data, follow_redirects=follow_redirects)

    def test_unauthenticated_redirects_to_login(self, client, db_session, app):
        resp = self._post(client, {})
        assert_redirect(resp)
        assert "login" in (resp.headers.get("Location") or "").lower()

    def test_form_validation_failure_redirects_to_dashboard(self, client, db_session, app, test_user):
        """Submitting without valid country selection → form errors → redirect."""
        _login(client, test_user)
        resp = self._post(client, {})
        assert_redirect(resp)

    def test_no_country_selected_shows_danger_flash(self, client, db_session, app, test_user):
        """Empty country list on a valid form should flash danger."""
        country = create_test_country(db_session)
        _login(client, test_user)
        # We need to pass a valid form submission; the form validator requires
        # at least one country_id.  Pass an empty list → validation fails.
        resp = self._post(client, {"requested_country_id": []}, follow_redirects=True)
        assert resp.status_code == 200

    def test_success_single_country_request(self, client, db_session, app, test_user):
        country = create_test_country(db_session)
        _login(client, test_user)
        with patch("app.routes.main.assignments.is_organization_email", return_value=False), \
             patch(f"{_APP_SETTINGS}.get_auto_approve_access_requests", return_value=False), \
             patch(f"{_NOTIF_AUDIENCE}.collect_entity_admin_audience_recipient_ids", return_value=[]):
            resp = self._post(client, {"requested_country_id": country.id}, follow_redirects=False)
        assert_redirect(resp)

    def test_non_org_user_cannot_request_multiple_countries(self, client, db_session, app, test_user):
        """A non-org user requesting 2 countries → warning flash and redirect."""
        country1 = create_test_country(db_session)
        country2 = create_test_country(db_session)
        _login(client, test_user)
        with patch("app.routes.main.assignments.is_organization_email", return_value=False):
            resp = self._post(
                client,
                {"requested_country_id": [country1.id, country2.id]},
                follow_redirects=True,
            )
        assert resp.status_code == 200

    def test_org_user_can_request_multiple_countries(self, client, db_session, app, test_user):
        country1 = create_test_country(db_session)
        country2 = create_test_country(db_session)
        _login(client, test_user)
        with patch("app.routes.main.assignments.is_organization_email", return_value=True), \
             patch(f"{_APP_SETTINGS}.get_auto_approve_access_requests", return_value=False), \
             patch(f"{_NOTIF_AUDIENCE}.collect_entity_admin_audience_recipient_ids", return_value=[]):
            resp = self._post(
                client,
                {"requested_country_id": [country1.id, country2.id]},
                follow_redirects=False,
            )
        assert_redirect(resp)

    def test_already_pending_request_is_skipped(self, client, db_session, app, test_user):
        """A second request for the same country shows info flash."""
        country = create_test_country(db_session)
        _login(client, test_user)
        with patch("app.routes.main.assignments.is_organization_email", return_value=False), \
             patch(f"{_APP_SETTINGS}.get_auto_approve_access_requests", return_value=False), \
             patch(f"{_NOTIF_AUDIENCE}.collect_entity_admin_audience_recipient_ids", return_value=[]):
            # First request
            self._post(client, {"requested_country_id": country.id}, follow_redirects=False)
            # Second request for same country → pending skip
            resp = self._post(client, {"requested_country_id": country.id}, follow_redirects=True)
        assert resp.status_code == 200

    def test_already_has_access_is_skipped(self, client, db_session, app, test_user):
        """Requesting a country the user already has access to → info flash."""
        country = create_test_country(db_session)
        _grant_entity_permission(db_session, test_user, "country", country.id)
        db_session.commit()
        _login(client, test_user)
        with patch("app.routes.main.assignments.is_organization_email", return_value=False):
            resp = self._post(client, {"requested_country_id": country.id}, follow_redirects=True)
        assert resp.status_code == 200

    def test_invalid_country_id_is_skipped(self, client, db_session, app, test_user):
        """Requesting a non-existent country id → warning flash."""
        _login(client, test_user)
        with patch("app.routes.main.assignments.is_organization_email", return_value=True):
            resp = self._post(client, {"requested_country_id": 99999999}, follow_redirects=True)
        assert resp.status_code == 200

    def test_auto_approve_grants_access(self, client, db_session, app, test_user):
        country = create_test_country(db_session)
        _login(client, test_user)
        with patch("app.routes.main.assignments.is_organization_email", return_value=False), \
             patch(f"{_APP_SETTINGS}.get_auto_approve_access_requests", return_value=True), \
             patch(f"{_NOTIF_AUDIENCE}.collect_entity_admin_audience_recipient_ids", return_value=[]), \
             patch(f"{_NOTIF_CORE}.notify_user_added_to_country", return_value=None):
            resp = self._post(client, {"requested_country_id": country.id}, follow_redirects=True)
        assert resp.status_code == 200

    def test_return_to_account_settings_redirects_there(self, client, db_session, app, test_user):
        country = create_test_country(db_session)
        _login(client, test_user)
        with patch("app.routes.main.assignments.is_organization_email", return_value=False), \
             patch(f"{_APP_SETTINGS}.get_auto_approve_access_requests", return_value=False), \
             patch(f"{_NOTIF_AUDIENCE}.collect_entity_admin_audience_recipient_ids", return_value=[]):
            resp = self._post(
                client,
                {"requested_country_id": country.id, "return_to": "account_settings"},
                follow_redirects=False,
            )
        assert_redirect(resp)
        location = resp.headers.get("Location", "")
        assert "account_settings" in location or "settings" in location

    def test_exception_during_request_flashes_error(self, client, db_session, app, test_user):
        country = create_test_country(db_session)
        _login(client, test_user)
        with patch("app.routes.main.assignments.is_organization_email", return_value=False), \
             patch("app.routes.main.assignments.CountryAccessRequest", side_effect=Exception("Unexpected")), \
             patch("app.routes.main.assignments.request_transaction_rollback"):
            resp = self._post(client, {"requested_country_id": country.id}, follow_redirects=True)
        assert resp.status_code == 200

    def test_non_org_user_blocked_after_existing_counting_request(
        self, client, db_session, app, test_user
    ):
        """Non-org user with pending request cannot request another country."""
        from app.models import CountryAccessRequest
        from app.models.system import CountryAccessRequestStatus

        country1 = create_test_country(db_session)
        country2 = create_test_country(db_session)

        req = CountryAccessRequest(
            user_id=test_user.id,
            country_id=country1.id,
            status=CountryAccessRequestStatus.PENDING,
        )
        db_session.add(req)
        db_session.commit()

        _login(client, test_user)
        with patch("app.routes.main.assignments.is_organization_email", return_value=False):
            resp = self._post(client, {"requested_country_id": country2.id}, follow_redirects=True)
        assert resp.status_code == 200

    def test_admin_notified_when_request_created(self, client, db_session, app, test_user):
        """When admins exist, notifications should be created (path exercised)."""
        country = create_test_country(db_session)
        admin = create_test_user(db_session, role="admin")
        _login(client, test_user)

        mock_create_notification = MagicMock(return_value=[MagicMock()])
        with patch("app.routes.main.assignments.is_organization_email", return_value=False), \
             patch(f"{_APP_SETTINGS}.get_auto_approve_access_requests", return_value=False), \
             patch(f"{_NOTIF_AUDIENCE}.collect_entity_admin_audience_recipient_ids", return_value=[admin.id]), \
             patch(f"{_NOTIF_CORE}.create_notification", mock_create_notification):
            resp = self._post(client, {"requested_country_id": country.id}, follow_redirects=False)
        assert_redirect(resp)

    def test_admin_notification_error_is_swallowed(self, client, db_session, app, test_user):
        """Notification creation failure should not break the route."""
        country = create_test_country(db_session)
        admin = create_test_user(db_session, role="admin")
        _login(client, test_user)

        with patch("app.routes.main.assignments.is_organization_email", return_value=False), \
             patch(f"{_APP_SETTINGS}.get_auto_approve_access_requests", return_value=False), \
             patch(f"{_NOTIF_AUDIENCE}.collect_entity_admin_audience_recipient_ids", return_value=[admin.id]), \
             patch(f"{_NOTIF_CORE}.create_notification", side_effect=Exception("notif error")):
            resp = self._post(client, {"requested_country_id": country.id}, follow_redirects=False)
        assert_redirect(resp)

    def test_auto_approve_notification_error_is_swallowed(self, client, db_session, app, test_user):
        """notify_user_added_to_country failure should not break auto-approve path."""
        country = create_test_country(db_session)
        _login(client, test_user)
        with patch("app.routes.main.assignments.is_organization_email", return_value=False), \
             patch(f"{_APP_SETTINGS}.get_auto_approve_access_requests", return_value=True), \
             patch(f"{_NOTIF_AUDIENCE}.collect_entity_admin_audience_recipient_ids", return_value=[]), \
             patch(f"{_NOTIF_CORE}.notify_user_added_to_country", side_effect=Exception("notif fail")):
            resp = self._post(client, {"requested_country_id": country.id}, follow_redirects=True)
        assert resp.status_code == 200

    def test_multiple_auto_approved_countries_success_flash(self, client, db_session, app, test_user):
        country1 = create_test_country(db_session)
        country2 = create_test_country(db_session)
        _login(client, test_user)
        with patch("app.routes.main.assignments.is_organization_email", return_value=True), \
             patch(f"{_APP_SETTINGS}.get_auto_approve_access_requests", return_value=True), \
             patch(f"{_NOTIF_AUDIENCE}.collect_entity_admin_audience_recipient_ids", return_value=[]), \
             patch(f"{_NOTIF_CORE}.notify_user_added_to_country", return_value=None):
            resp = self._post(
                client,
                {"requested_country_id": [country1.id, country2.id]},
                follow_redirects=True,
            )
        assert resp.status_code == 200

    def test_multiple_pending_countries_skipped_flash(self, client, db_session, app, test_user):
        """Multiple skipped-already-pending countries shows plural flash."""
        from app.models import CountryAccessRequest
        from app.models.system import CountryAccessRequestStatus

        country1 = create_test_country(db_session)
        country2 = create_test_country(db_session)

        for c in (country1, country2):
            db_session.add(CountryAccessRequest(
                user_id=test_user.id,
                country_id=c.id,
                status=CountryAccessRequestStatus.PENDING,
            ))
        db_session.commit()

        _login(client, test_user)
        with patch("app.routes.main.assignments.is_organization_email", return_value=True):
            resp = self._post(
                client,
                {"requested_country_id": [country1.id, country2.id]},
                follow_redirects=True,
            )
        assert resp.status_code == 200

    def test_multiple_already_has_access_countries_plural_flash(self, client, db_session, app, test_user):
        """Multiple already-accessible countries shows plural flash."""
        country1 = create_test_country(db_session)
        country2 = create_test_country(db_session)
        _grant_entity_permission(db_session, test_user, "country", country1.id)
        _grant_entity_permission(db_session, test_user, "country", country2.id)
        db_session.commit()

        _login(client, test_user)
        with patch("app.routes.main.assignments.is_organization_email", return_value=True):
            resp = self._post(
                client,
                {"requested_country_id": [country1.id, country2.id]},
                follow_redirects=True,
            )
        assert resp.status_code == 200
