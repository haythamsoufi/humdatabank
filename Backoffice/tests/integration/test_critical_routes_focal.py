"""Smoke tests for critical focal-point production routes."""

from unittest.mock import patch

import pytest

from app.models import AssignmentEntityStatus, FormItem, FormSection
from app.models.enums import EntityType

from tests.factories import (
    create_focal_point_with_country,
    create_test_assignment_entity_status,
    create_test_country,
    create_test_public_submission,
    create_test_template,
    create_test_user,
)
from tests.helpers import get_csrf_headers, login_session


@pytest.mark.integration
@pytest.mark.critical
class TestCriticalDashboardRoutes:
    def test_dashboard_requires_auth(self, client):
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code in (301, 302, 303, 307, 308)

    def test_dashboard_happy_path(self, logged_in_focal_client, focal_point_user, app):
        period = focal_point_user["period_name"]
        with patch(
            "app.routes.main.dashboard.get_country_recent_activities",
            return_value=[],
        ):
            resp = logged_in_focal_client.get("/")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert period in body or "Dashboard" in body or "dashboard" in body.lower()

    def test_select_country_post_redirects(self, logged_in_focal_client, focal_point_user, app):
        country_id = focal_point_user["country_id"]
        resp = logged_in_focal_client.post(
            f"/select_country/{country_id}",
            follow_redirects=False,
        )
        assert resp.status_code in (301, 302, 303, 307, 308)
        location = (resp.headers.get("Location") or "").lower()
        assert location.endswith("/") or "dashboard" in location


@pytest.mark.integration
@pytest.mark.critical
class TestCriticalAssignmentFormRoutes:
    def test_assignment_form_requires_auth(self, client, db_session, app):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session)
            aes_id = aes.id
        resp = client.get(f"/forms/assignment/{aes_id}", follow_redirects=False)
        assert resp.status_code in (301, 302, 303, 307, 308)

    def test_assignment_form_happy_path_focal_point(
        self, logged_in_focal_client, focal_point_user, app
    ):
        aes_id = focal_point_user["aes_id"]
        resp = logged_in_focal_client.get(f"/forms/assignment/{aes_id}")
        assert resp.status_code == 200

    def test_assignment_form_save_via_http(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            template = create_test_template(db_session)
            section = FormSection(
                template_id=template.id,
                version_id=template.published_version_id,
                name="Section 1",
                order=1,
            )
            db_session.add(section)
            db_session.flush()
            item = FormItem(
                section_id=section.id,
                template_id=template.id,
                version_id=template.published_version_id,
                item_type="question",
                label="Test Q",
                order=1,
            )
            db_session.add(item)
            db_session.flush()
            aes = create_test_assignment_entity_status(
                db_session, country=country, template=template, commit=False
            )
            db_session.commit()
            aes_id = aes.id
            item_id = item.id

        resp = logged_in_client.post(
            f"/forms/assignment/{aes_id}",
            data={"action": "save", f"field_value[{item_id}]": "42"},
            follow_redirects=False,
        )
        assert resp.status_code in (200, 301, 302, 303, 307, 308)

    def test_assignment_form_submit_via_http(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            template = create_test_template(db_session)
            aes = create_test_assignment_entity_status(
                db_session,
                country=country,
                template=template,
                status="in_progress",
            )
            aes_id = aes.id

        resp = logged_in_client.post(
            f"/forms/assignment/{aes_id}",
            data={"action": "submit"},
            follow_redirects=False,
        )
        assert resp.status_code in (200, 301, 302, 303, 307, 308)
        with app.app_context():
            refreshed = AssignmentEntityStatus.query.get(aes_id)
            assert refreshed.status in (
                "submitted",
                "sent_for_review",
                "in_progress",
            )


@pytest.mark.integration
@pytest.mark.critical
class TestCriticalAssignmentLifecycleRoutes:
    def _login_sm(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="system_manager")
            login_session(client, user.id)
            return user

    def test_approve_assignment_happy_path(self, client, db_session, app):
        self._login_sm(client, db_session, app)
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session, status="submitted")
            aes_id = aes.id

        resp = client.post(f"/approve_assignment/{aes_id}", follow_redirects=False)
        assert resp.status_code in (301, 302, 303, 307, 308)
        with app.app_context():
            assert AssignmentEntityStatus.query.get(aes_id).status == "approved"

    def test_return_assignment_for_revision_happy_path(self, client, db_session, app):
        self._login_sm(client, db_session, app)
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session, status="sent_for_review")
            aes_id = aes.id

        resp = client.post(
            f"/return_assignment_for_revision/{aes_id}",
            follow_redirects=False,
        )
        assert resp.status_code in (301, 302, 303, 307, 308)
        with app.app_context():
            assert AssignmentEntityStatus.query.get(aes_id).status == "requires_revision"

    def test_reopen_assignment_happy_path(self, client, db_session, app):
        self._login_sm(client, db_session, app)
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session, status="submitted")
            aes_id = aes.id

        resp = client.post(f"/reopen_assignment/{aes_id}", follow_redirects=False)
        assert resp.status_code in (301, 302, 303, 307, 308)
        with app.app_context():
            assert AssignmentEntityStatus.query.get(aes_id).status == "in_progress"


@pytest.mark.integration
@pytest.mark.critical
class TestCriticalPublicFormRoutes:
    def test_public_form_entry_happy_path(self, client, db_session, app):
        with app.app_context():
            _, assigned_form, token = create_test_public_submission(db_session)
            _ = assigned_form

        resp = client.get(f"/forms/public/{token}")
        assert resp.status_code == 200

    def test_legacy_public_form_redirect(self, client, db_session, app):
        with app.app_context():
            _, _, token = create_test_public_submission(db_session)

        resp = client.get(f"/form/{token}", follow_redirects=False)
        assert resp.status_code in (301, 302, 303, 307, 308)
        assert token in (resp.headers.get("Location") or "")


@pytest.mark.integration
@pytest.mark.critical
class TestCriticalCountryAccessRoute:
    def test_request_country_access_requires_auth(self, client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            country_id = country.id

        resp = client.post(
            "/request_country_access",
            data={"requested_country_id": country_id},
            follow_redirects=False,
        )
        assert resp.status_code in (301, 302, 303, 307, 308)

    def test_request_country_access_happy_path(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="user")
            country = create_test_country(db_session)
            user_id = user.id
            country_id = country.id

        login_session(client, user_id)
        # WTF_CSRF_ENABLED is False in tests; avoid GET /api/v1/csrf-token before POST
        # (that request commits and detaches the ORM user instance Flask-Login may reuse).
        resp = client.post(
            "/request_country_access",
            data={"requested_country_id": str(country_id)},
            follow_redirects=False,
        )
        assert resp.status_code in (301, 302, 303, 307, 308)


@pytest.mark.integration
@pytest.mark.critical
class TestCriticalProfileSummaryRoute:
    def test_profile_summary_requires_auth(self, client):
        resp = client.get("/api/users/profile-summary", follow_redirects=False)
        assert resp.status_code in (301, 302, 401, 403)

    def test_profile_summary_happy_path(self, logged_in_focal_client):
        resp = logged_in_focal_client.get("/api/users/profile-summary")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, dict)
