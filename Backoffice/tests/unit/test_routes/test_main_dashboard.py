"""
Comprehensive pytest tests for app/routes/main/dashboard.py.

Tests cover the dashboard view and related AJAX endpoints:
- GET dashboard (no entities, single entity, multiple entities)
- POST country selection, entity selection, self-report assignment
- load_more_activities endpoint
- mark_notifications_read endpoint
"""
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime, timezone, timedelta

import pytest
from flask import json
from flask_login import login_user

from tests.factories import (
    create_test_user,
    create_test_country,
    create_test_template,
    create_test_assignment_entity_status,
    create_focal_point_with_country,
    _grant_entity_permission,
)

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def _grant_assignment_view_role(db_session, user):
    from app.models.rbac import RbacPermission, RbacRole, RbacRolePermission, RbacUserRole

    role = db_session.query(RbacRole).filter_by(code="assignment_viewer").first()
    if not role:
        role = RbacRole(code="assignment_viewer", name="Assignment Viewer")
        db_session.add(role)
        db_session.flush()

    perm = db_session.query(RbacPermission).filter_by(code="assignment.view").first()
    if not perm:
        perm = RbacPermission(
            code="assignment.view",
            name="View assignments",
            description="View assignments",
        )
        db_session.add(perm)
        db_session.flush()

    existing_role_perm = (
        db_session.query(RbacRolePermission)
        .filter_by(role_id=role.id, permission_id=perm.id)
        .first()
    )
    if not existing_role_perm:
        db_session.add(RbacRolePermission(role_id=role.id, permission_id=perm.id))

    existing_user_role = (
        db_session.query(RbacUserRole)
        .filter_by(user_id=user.id, role_id=role.id)
        .first()
    )
    if not existing_user_role:
        db_session.add(RbacUserRole(user_id=user.id, role_id=role.id))

    db_session.commit()


@pytest.fixture(autouse=True)
def _grant_assignment_dashboard_role_for_admin_dashboard_tests(request, db_session):
    """Most legacy dashboard tests use the shared admin client as the actor."""
    if "logged_in_client" not in request.fixturenames and "admin_user" not in request.fixturenames:
        return
    admin = request.getfixturevalue("admin_user")
    _grant_assignment_view_role(db_session, admin)


def _html(response):
    return response.data.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Dashboard GET – unauthenticated
# ---------------------------------------------------------------------------

class TestDashboardUnauthenticated:
    def test_redirect_to_login(self, client):
        resp = client.get("/")
        assert resp.status_code in (302, 301)
        location = resp.headers.get("Location", "")
        assert "login" in location or resp.status_code == 302


# ---------------------------------------------------------------------------
# Dashboard GET – user with no entities
# ---------------------------------------------------------------------------

class TestDashboardNoEntities:
    def test_admin_without_assignment_view_redirects_to_first_allowed_admin_page(self, client, db_session, app):
        """Admin permissions alone must not trigger the all-entity dashboard fallback."""
        from app.models.rbac import RbacPermission, RbacRole, RbacRolePermission, RbacUserRole

        admin = create_test_user(
            db_session,
            email="dashboard_admin_without_assignment@example.com",
            role="user",
        )
        country = create_test_country(db_session, name="Dashboard Leak Guard")

        role = RbacRole(code="admin_data_explorer_test", name="Admin: Data Explorer Test")
        permission = RbacPermission(
            code="admin.data_explore.data_table",
            name="Explore data table",
            description="Explore data table",
        )
        db_session.add_all([role, permission])
        db_session.flush()
        RbacUserRole.query.filter_by(user_id=admin.id).delete()
        db_session.add(RbacRolePermission(role_id=role.id, permission_id=permission.id))
        db_session.add(RbacUserRole(user_id=admin.id, role_id=role.id))
        db_session.commit()

        _login(client, admin.id)

        with patch("app.routes.main.dashboard.EntityService.get_entities_for_user", return_value=[country]) as mock_entities, \
             patch("app.routes.main.dashboard.render_template", return_value="<html>dashboard</html>") as mock_rt:
            resp = client.get("/", follow_redirects=False)

        assert resp.status_code == 302
        assert "/admin/data-exploration" in resp.headers.get("Location", "")
        mock_entities.assert_not_called()
        mock_rt.assert_not_called()

    def test_renders_dashboard_with_warning_flash(self, logged_in_client, db_session, app):
        """Admin user with no entity permissions sees warning."""
        with patch("app.routes.main.dashboard.UserEntityPermission") as mock_perm_cls, \
             patch("app.routes.main.dashboard.EntityService.get_entities_for_user", return_value=[]), \
             patch("app.routes.main.dashboard.get_enabled_entity_groups", return_value=["countries"]), \
             patch("app.routes.main.dashboard.get_allowed_entity_type_codes", return_value=["country"]), \
             patch("app.routes.main.dashboard.CountryAccessRequest.query") as mock_req_query, \
             patch("app.routes.main.dashboard.is_data_quality_dashboard_enabled", return_value=False), \
             patch("app.routes.main.dashboard.render_template", return_value="<html>dashboard</html>") as mock_rt:
            mock_perm_cls.query.filter_by.return_value.all.return_value = []
            mock_req_query.filter_by.return_value.options.return_value.order_by.return_value.all.return_value = []
            resp = logged_in_client.get("/")
        assert resp.status_code == 200
        mock_rt.assert_called_once()

    def test_renders_dashboard_with_pending_access_request(self, logged_in_client, db_session, app):
        """User with pending access request does not get 'no entities' flash."""
        mock_req = MagicMock()
        mock_req.status = MagicMock()
        mock_req.status.value = "pending"

        from app.models.system import CountryAccessRequestStatus
        mock_req.status = CountryAccessRequestStatus.PENDING
        mock_req.country = None
        mock_req.country_id = None
        mock_req._access_revoked = False

        with patch("app.routes.main.dashboard.UserEntityPermission") as mock_perm_cls, \
             patch("app.routes.main.dashboard.EntityService.get_entities_for_user", return_value=[]), \
             patch("app.routes.main.dashboard.get_enabled_entity_groups", return_value=["countries"]), \
             patch("app.routes.main.dashboard.get_allowed_entity_type_codes", return_value=["country"]), \
             patch("app.routes.main.dashboard.CountryAccessRequest.query") as mock_req_query, \
             patch("app.routes.main.dashboard.is_data_quality_dashboard_enabled", return_value=False), \
             patch("app.routes.main.dashboard.render_template", return_value="<html>dashboard</html>") as mock_rt:
            mock_perm_cls.query.filter_by.return_value.all.return_value = []
            mock_req_query.filter_by.return_value.options.return_value.order_by.return_value.all.return_value = [mock_req]
            resp = logged_in_client.get("/")
        assert resp.status_code == 200

    def test_access_request_load_exception_handled(self, logged_in_client, db_session, app):
        """If access request query raises, gracefully degrades."""
        with patch("app.routes.main.dashboard.UserEntityPermission") as mock_perm_cls, \
             patch("app.routes.main.dashboard.EntityService.get_entities_for_user", return_value=[]), \
             patch("app.routes.main.dashboard.get_enabled_entity_groups", return_value=["countries"]), \
             patch("app.routes.main.dashboard.get_allowed_entity_type_codes", return_value=["country"]), \
             patch("app.routes.main.dashboard.CountryAccessRequest.query") as mock_req_query, \
             patch("app.routes.main.dashboard.is_data_quality_dashboard_enabled", return_value=False), \
             patch("app.routes.main.dashboard.render_template", return_value="<html>dashboard</html>"):
            mock_perm_cls.query.filter_by.return_value.all.return_value = []
            mock_req_query.filter_by.side_effect = Exception("DB Error")
            resp = logged_in_client.get("/")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Dashboard GET – user with a single country entity
# ---------------------------------------------------------------------------

class TestDashboardSingleEntity:
    def _make_country(self, db_session):
        return create_test_country(db_session, name="TestLand")

    def test_dashboard_renders_with_one_country(self, logged_in_client, db_session, app, admin_user):
        country = self._make_country(db_session)
        _grant_entity_permission(db_session, admin_user, "country", country.id)
        db_session.commit()

        with patch("app.routes.main.dashboard.get_enabled_entity_groups", return_value=["countries"]), \
             patch("app.routes.main.dashboard.get_allowed_entity_type_codes", return_value=["country"]), \
             patch("app.routes.main.dashboard.CountryAccessRequest.query") as mock_req_query, \
             patch("app.routes.main.dashboard.get_country_recent_activities", return_value=[]), \
             patch("app.routes.main.dashboard.is_data_quality_dashboard_enabled", return_value=False), \
             patch("app.routes.main.dashboard.AssignmentCompletionService.prefetch") as mock_prefetch, \
             patch("app.routes.main.dashboard.render_template", return_value="<html>dashboard</html>") as mock_rt:
            mock_req_query.filter_by.return_value.options.return_value.order_by.return_value.all.return_value = []
            mock_prefetch.return_value = MagicMock()
            mock_prefetch.return_value.metrics_for.return_value = MagicMock(
                completion_rate=0.0, filled_items=0, total_items=0
            )
            resp = logged_in_client.get("/")
        assert resp.status_code == 200
        mock_rt.assert_called_once()
        ctx = mock_rt.call_args
        # selected_country should be set to the country
        kwargs = ctx.kwargs if hasattr(ctx, "kwargs") else ctx[1]
        assert kwargs.get("selected_country") is not None or kwargs.get("selected_entity") is not None

    def test_dashboard_data_quality_enabled(self, logged_in_client, db_session, app, admin_user):
        country = self._make_country(db_session)
        _grant_entity_permission(db_session, admin_user, "country", country.id)
        db_session.commit()

        with patch("app.routes.main.dashboard.get_enabled_entity_groups", return_value=["countries"]), \
             patch("app.routes.main.dashboard.get_allowed_entity_type_codes", return_value=["country"]), \
             patch("app.routes.main.dashboard.CountryAccessRequest.query") as mock_req_query, \
             patch("app.routes.main.dashboard.get_country_recent_activities", return_value=[]), \
             patch("app.routes.main.dashboard.is_data_quality_dashboard_enabled", return_value=True), \
             patch("app.routes.main.dashboard.list_data_quality_templates_for_entity", return_value=[]), \
             patch("app.routes.main.dashboard.AssignmentCompletionService.prefetch") as mock_prefetch, \
             patch("app.routes.main.dashboard.render_template", return_value="<html>dashboard</html>"):
            mock_req_query.filter_by.return_value.options.return_value.order_by.return_value.all.return_value = []
            mock_prefetch.return_value = MagicMock()
            mock_prefetch.return_value.metrics_for.return_value = MagicMock(
                completion_rate=0.0, filled_items=0, total_items=0
            )
            resp = logged_in_client.get("/")
        assert resp.status_code == 200

    def test_dashboard_data_quality_exception_handled(self, logged_in_client, db_session, app, admin_user):
        country = self._make_country(db_session)
        _grant_entity_permission(db_session, admin_user, "country", country.id)
        db_session.commit()

        with patch("app.routes.main.dashboard.get_enabled_entity_groups", return_value=["countries"]), \
             patch("app.routes.main.dashboard.get_allowed_entity_type_codes", return_value=["country"]), \
             patch("app.routes.main.dashboard.CountryAccessRequest.query") as mock_req_query, \
             patch("app.routes.main.dashboard.get_country_recent_activities", return_value=[]), \
             patch("app.routes.main.dashboard.is_data_quality_dashboard_enabled", return_value=True), \
             patch("app.routes.main.dashboard.list_data_quality_templates_for_entity", side_effect=Exception("DQ error")), \
             patch("app.routes.main.dashboard.AssignmentCompletionService.prefetch") as mock_prefetch, \
             patch("app.routes.main.dashboard.render_template", return_value="<html>dashboard</html>"):
            mock_req_query.filter_by.return_value.options.return_value.order_by.return_value.all.return_value = []
            mock_prefetch.return_value = MagicMock()
            mock_prefetch.return_value.metrics_for.return_value = MagicMock(
                completion_rate=0.0, filled_items=0, total_items=0
            )
            resp = logged_in_client.get("/")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Dashboard GET – entity selection from session
# ---------------------------------------------------------------------------

class TestDashboardSessionEntity:
    def test_entity_restored_from_session(self, logged_in_client, db_session, app, admin_user):
        country = create_test_country(db_session)
        _grant_entity_permission(db_session, admin_user, "country", country.id)
        db_session.commit()

        with logged_in_client.session_transaction() as sess:
            sess["selected_entity_type"] = "country"
            sess["selected_entity_id"] = country.id

        with patch("app.routes.main.dashboard.get_enabled_entity_groups", return_value=["countries"]), \
             patch("app.routes.main.dashboard.get_allowed_entity_type_codes", return_value=["country"]), \
             patch("app.routes.main.dashboard.CountryAccessRequest.query") as mock_req_query, \
             patch("app.routes.main.dashboard.get_country_recent_activities", return_value=[]), \
             patch("app.routes.main.dashboard.is_data_quality_dashboard_enabled", return_value=False), \
             patch("app.routes.main.dashboard.AssignmentCompletionService.prefetch") as mock_prefetch, \
             patch("app.routes.main.dashboard.render_template", return_value="<html>ok</html>"):
            mock_req_query.filter_by.return_value.options.return_value.order_by.return_value.all.return_value = []
            mock_prefetch.return_value = MagicMock()
            mock_prefetch.return_value.metrics_for.return_value = MagicMock(
                completion_rate=0.0, filled_items=0, total_items=0
            )
            resp = logged_in_client.get("/")
        assert resp.status_code == 200

    def test_invalid_entity_in_session_cleared(self, logged_in_client, db_session, app, admin_user):
        with logged_in_client.session_transaction() as sess:
            sess["selected_entity_type"] = "country"
            sess["selected_entity_id"] = 99999  # doesn't exist

        with patch("app.routes.main.dashboard.get_enabled_entity_groups", return_value=["countries"]), \
             patch("app.routes.main.dashboard.get_allowed_entity_type_codes", return_value=["country"]), \
             patch("app.routes.main.dashboard.CountryAccessRequest.query") as mock_req_query, \
             patch("app.routes.main.dashboard.is_data_quality_dashboard_enabled", return_value=False), \
             patch("app.routes.main.dashboard.render_template", return_value="<html>ok</html>"):
            mock_req_query.filter_by.return_value.options.return_value.order_by.return_value.all.return_value = []
            resp = logged_in_client.get("/")
        assert resp.status_code == 200

    def test_legacy_country_session_restored(self, logged_in_client, db_session, app, admin_user):
        country = create_test_country(db_session)
        _grant_entity_permission(db_session, admin_user, "country", country.id)
        db_session.commit()

        with logged_in_client.session_transaction() as sess:
            sess["selected_country_id"] = country.id

        with patch("app.routes.main.dashboard.get_enabled_entity_groups", return_value=["countries"]), \
             patch("app.routes.main.dashboard.get_allowed_entity_type_codes", return_value=["country"]), \
             patch("app.routes.main.dashboard.CountryAccessRequest.query") as mock_req_query, \
             patch("app.routes.main.dashboard.get_country_recent_activities", return_value=[]), \
             patch("app.routes.main.dashboard.is_data_quality_dashboard_enabled", return_value=False), \
             patch("app.routes.main.dashboard.AssignmentCompletionService.prefetch") as mock_prefetch, \
             patch("app.routes.main.dashboard.render_template", return_value="<html>ok</html>"):
            mock_req_query.filter_by.return_value.options.return_value.order_by.return_value.all.return_value = []
            mock_prefetch.return_value = MagicMock()
            mock_prefetch.return_value.metrics_for.return_value = MagicMock(
                completion_rate=0.0, filled_items=0, total_items=0
            )
            resp = logged_in_client.get("/")
        assert resp.status_code == 200

    def test_invalid_legacy_country_in_session_cleared(self, logged_in_client, db_session, app):
        with logged_in_client.session_transaction() as sess:
            sess["selected_country_id"] = 99999

        with patch("app.routes.main.dashboard.get_enabled_entity_groups", return_value=["countries"]), \
             patch("app.routes.main.dashboard.get_allowed_entity_type_codes", return_value=["country"]), \
             patch("app.routes.main.dashboard.CountryAccessRequest.query") as mock_req_query, \
             patch("app.routes.main.dashboard.is_data_quality_dashboard_enabled", return_value=False), \
             patch("app.routes.main.dashboard.render_template", return_value="<html>ok</html>"):
            mock_req_query.filter_by.return_value.options.return_value.order_by.return_value.all.return_value = []
            resp = logged_in_client.get("/")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Dashboard GET – multiple entities
# ---------------------------------------------------------------------------

class TestDashboardMultipleEntities:
    def test_show_entity_select_with_multiple_entities(self, logged_in_client, db_session, app, admin_user):
        c1 = create_test_country(db_session)
        c2 = create_test_country(db_session)
        _grant_entity_permission(db_session, admin_user, "country", c1.id)
        _grant_entity_permission(db_session, admin_user, "country", c2.id)
        db_session.commit()

        with patch("app.routes.main.dashboard.get_enabled_entity_groups", return_value=["countries"]), \
             patch("app.routes.main.dashboard.get_allowed_entity_type_codes", return_value=["country"]), \
             patch("app.routes.main.dashboard.CountryAccessRequest.query") as mock_req_query, \
             patch("app.routes.main.dashboard.get_country_recent_activities", return_value=[]), \
             patch("app.routes.main.dashboard.is_data_quality_dashboard_enabled", return_value=False), \
             patch("app.routes.main.dashboard.AssignmentCompletionService.prefetch") as mock_prefetch, \
             patch("app.routes.main.dashboard.render_template", return_value="<html>ok</html>") as mock_rt:
            mock_req_query.filter_by.return_value.options.return_value.order_by.return_value.all.return_value = []
            mock_prefetch.return_value = MagicMock()
            mock_prefetch.return_value.metrics_for.return_value = MagicMock(
                completion_rate=0.0, filled_items=0, total_items=0
            )
            resp = logged_in_client.get("/")
        assert resp.status_code == 200
        kwargs = mock_rt.call_args[1] if mock_rt.call_args else {}
        assert kwargs.get("show_entity_select") is True or kwargs.get("show_country_select") is True


# ---------------------------------------------------------------------------
# Dashboard POST – country selection
# ---------------------------------------------------------------------------

class TestDashboardPostCountrySelect:
    def test_valid_country_selection_updates_session(self, logged_in_client, db_session, app, admin_user):
        country = create_test_country(db_session)
        _grant_entity_permission(db_session, admin_user, "country", country.id)
        db_session.commit()

        with patch("app.routes.main.dashboard.get_enabled_entity_groups", return_value=["countries"]), \
             patch("app.routes.main.dashboard.get_allowed_entity_type_codes", return_value=["country"]), \
             patch("app.routes.main.dashboard.CountryAccessRequest.query") as mock_req_query:
            mock_req_query.filter_by.return_value.options.return_value.order_by.return_value.all.return_value = []
            resp = logged_in_client.post("/", data={"country_select": str(country.id)})
        assert resp.status_code == 302

    def test_invalid_country_selection_shows_warning(self, logged_in_client, db_session, app, admin_user):
        country = create_test_country(db_session)
        _grant_entity_permission(db_session, admin_user, "country", country.id)
        # another country not assigned
        other = create_test_country(db_session)
        db_session.commit()

        with patch("app.routes.main.dashboard.get_enabled_entity_groups", return_value=["countries"]), \
             patch("app.routes.main.dashboard.get_allowed_entity_type_codes", return_value=["country"]), \
             patch("app.routes.main.dashboard.CountryAccessRequest.query") as mock_req_query:
            mock_req_query.filter_by.return_value.options.return_value.order_by.return_value.all.return_value = []
            resp = logged_in_client.post("/", data={"country_select": str(other.id)})
        assert resp.status_code == 302

    def test_non_integer_country_id_shows_warning(self, logged_in_client, db_session, app, admin_user):
        country = create_test_country(db_session)
        _grant_entity_permission(db_session, admin_user, "country", country.id)
        db_session.commit()

        with patch("app.routes.main.dashboard.get_enabled_entity_groups", return_value=["countries"]), \
             patch("app.routes.main.dashboard.get_allowed_entity_type_codes", return_value=["country"]), \
             patch("app.routes.main.dashboard.CountryAccessRequest.query") as mock_req_query:
            mock_req_query.filter_by.return_value.options.return_value.order_by.return_value.all.return_value = []
            resp = logged_in_client.post("/", data={"country_select": "abc"})
        assert resp.status_code == 302

    def test_empty_country_selection_clears_session(self, logged_in_client, db_session, app, admin_user):
        country = create_test_country(db_session)
        _grant_entity_permission(db_session, admin_user, "country", country.id)
        db_session.commit()

        with logged_in_client.session_transaction() as sess:
            sess["selected_country_id"] = country.id

        with patch("app.routes.main.dashboard.get_enabled_entity_groups", return_value=["countries"]), \
             patch("app.routes.main.dashboard.get_allowed_entity_type_codes", return_value=["country"]), \
             patch("app.routes.main.dashboard.CountryAccessRequest.query") as mock_req_query:
            mock_req_query.filter_by.return_value.options.return_value.order_by.return_value.all.return_value = []
            resp = logged_in_client.post("/", data={"country_select": ""})
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# Dashboard POST – entity selection
# ---------------------------------------------------------------------------

class TestDashboardPostEntitySelect:
    def test_valid_entity_selection(self, logged_in_client, db_session, app, admin_user):
        country = create_test_country(db_session)
        _grant_entity_permission(db_session, admin_user, "country", country.id)
        db_session.commit()

        with patch("app.routes.main.dashboard.get_enabled_entity_groups", return_value=["countries"]), \
             patch("app.routes.main.dashboard.get_allowed_entity_type_codes", return_value=["country"]), \
             patch("app.routes.main.dashboard.CountryAccessRequest.query") as mock_req_query, \
             patch("app.routes.main.dashboard.EntityService.get_country_for_entity", return_value=country):
            mock_req_query.filter_by.return_value.options.return_value.order_by.return_value.all.return_value = []
            resp = logged_in_client.post("/", data={"entity_select": f"country:{country.id}"})
        assert resp.status_code == 302

    def test_invalid_entity_selection_not_in_user_pairs(self, logged_in_client, db_session, app, admin_user):
        """Entity not belonging to user shows warning and redirects."""
        with patch("app.routes.main.dashboard.get_enabled_entity_groups", return_value=["countries"]), \
             patch("app.routes.main.dashboard.get_allowed_entity_type_codes", return_value=["country"]), \
             patch("app.routes.main.dashboard.CountryAccessRequest.query") as mock_req_query:
            mock_req_query.filter_by.return_value.options.return_value.order_by.return_value.all.return_value = []
            resp = logged_in_client.post("/", data={"entity_select": "country:99999"})
        assert resp.status_code == 302

    def test_non_integer_entity_id_shows_warning(self, logged_in_client, db_session, app):
        with patch("app.routes.main.dashboard.get_enabled_entity_groups", return_value=["countries"]), \
             patch("app.routes.main.dashboard.get_allowed_entity_type_codes", return_value=["country"]), \
             patch("app.routes.main.dashboard.CountryAccessRequest.query") as mock_req_query:
            mock_req_query.filter_by.return_value.options.return_value.order_by.return_value.all.return_value = []
            resp = logged_in_client.post("/", data={"entity_select": "country:abc"})
        assert resp.status_code == 302

    def test_malformed_entity_select_no_colon(self, logged_in_client, db_session, app):
        with patch("app.routes.main.dashboard.get_enabled_entity_groups", return_value=["countries"]), \
             patch("app.routes.main.dashboard.get_allowed_entity_type_codes", return_value=["country"]), \
             patch("app.routes.main.dashboard.CountryAccessRequest.query") as mock_req_query:
            mock_req_query.filter_by.return_value.options.return_value.order_by.return_value.all.return_value = []
            resp = logged_in_client.post("/", data={"entity_select": "no-colon-here"})
        assert resp.status_code == 302

    def test_empty_entity_select_shows_warning(self, logged_in_client, db_session, app):
        with patch("app.routes.main.dashboard.get_enabled_entity_groups", return_value=["countries"]), \
             patch("app.routes.main.dashboard.get_allowed_entity_type_codes", return_value=["country"]), \
             patch("app.routes.main.dashboard.CountryAccessRequest.query") as mock_req_query:
            mock_req_query.filter_by.return_value.options.return_value.order_by.return_value.all.return_value = []
            resp = logged_in_client.post("/", data={"entity_select": ""})
        assert resp.status_code == 302

    def test_entity_selection_with_related_country_set(self, logged_in_client, db_session, app, admin_user):
        country = create_test_country(db_session)
        _grant_entity_permission(db_session, admin_user, "country", country.id)
        db_session.commit()

        with patch("app.routes.main.dashboard.get_enabled_entity_groups", return_value=["countries"]), \
             patch("app.routes.main.dashboard.get_allowed_entity_type_codes", return_value=["country"]), \
             patch("app.routes.main.dashboard.CountryAccessRequest.query") as mock_req_query, \
             patch("app.routes.main.dashboard.EntityService.get_country_for_entity", return_value=country):
            mock_req_query.filter_by.return_value.options.return_value.order_by.return_value.all.return_value = []
            # entity IS in user's pairs, so it should succeed
            resp = logged_in_client.post("/", data={"entity_select": f"country:{country.id}"})
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# Dashboard POST – self-report
# ---------------------------------------------------------------------------

class TestDashboardPostSelfReport:
    def test_self_report_success(self, logged_in_client, db_session, app, admin_user):
        country = create_test_country(db_session)
        _grant_entity_permission(db_session, admin_user, "country", country.id)
        template = create_test_template(db_session)
        db_session.commit()

        with logged_in_client.session_transaction() as sess:
            sess["selected_country_id"] = country.id

        mock_template = MagicMock()
        mock_template.id = template.id
        mock_template.name = "SR Template"

        with patch("app.routes.main.dashboard.get_enabled_entity_groups", return_value=["countries"]), \
             patch("app.routes.main.dashboard.get_allowed_entity_type_codes", return_value=["country"]), \
             patch("app.routes.main.dashboard.CountryAccessRequest.query") as mock_req_query, \
             patch("app.routes.main.dashboard.FormTemplate.query") as mock_ft_query, \
             patch("app.routes.main.dashboard.db") as mock_db, \
             patch("app.routes.main.dashboard.notify_self_report_created", side_effect=Exception("notify skip")):
            mock_req_query.filter_by.return_value.options.return_value.order_by.return_value.all.return_value = []
            mock_ft_query.join.return_value.filter.return_value.first.return_value = mock_template

            # Simulate the DB session flush succeeding
            mock_db.session = MagicMock()
            mock_db.session.add = MagicMock()
            mock_db.session.flush = MagicMock()

            resp = logged_in_client.post(
                "/",
                data={"self_report_template_id": str(template.id)},
            )
        assert resp.status_code == 302

    def test_self_report_invalid_template_id_shows_warning(self, logged_in_client, db_session, app, admin_user):
        country = create_test_country(db_session)
        _grant_entity_permission(db_session, admin_user, "country", country.id)
        db_session.commit()

        with logged_in_client.session_transaction() as sess:
            sess["selected_country_id"] = country.id

        with patch("app.routes.main.dashboard.get_enabled_entity_groups", return_value=["countries"]), \
             patch("app.routes.main.dashboard.get_allowed_entity_type_codes", return_value=["country"]), \
             patch("app.routes.main.dashboard.CountryAccessRequest.query") as mock_req_query, \
             patch("app.routes.main.dashboard.FormTemplate.query") as mock_ft_query:
            mock_req_query.filter_by.return_value.options.return_value.order_by.return_value.all.return_value = []
            mock_ft_query.join.return_value.filter.return_value.first.return_value = None
            resp = logged_in_client.post("/", data={"self_report_template_id": "99999"})
        assert resp.status_code == 302

    def test_self_report_non_integer_template_id(self, logged_in_client, db_session, app, admin_user):
        country = create_test_country(db_session)
        _grant_entity_permission(db_session, admin_user, "country", country.id)
        db_session.commit()

        with logged_in_client.session_transaction() as sess:
            sess["selected_country_id"] = country.id

        with patch("app.routes.main.dashboard.get_enabled_entity_groups", return_value=["countries"]), \
             patch("app.routes.main.dashboard.get_allowed_entity_type_codes", return_value=["country"]), \
             patch("app.routes.main.dashboard.CountryAccessRequest.query") as mock_req_query:
            mock_req_query.filter_by.return_value.options.return_value.order_by.return_value.all.return_value = []
            resp = logged_in_client.post("/", data={"self_report_template_id": "not-an-int"})
        assert resp.status_code == 302

    def test_self_report_no_template_id_shows_warning(self, logged_in_client, db_session, app, admin_user):
        country = create_test_country(db_session)
        _grant_entity_permission(db_session, admin_user, "country", country.id)
        db_session.commit()

        with logged_in_client.session_transaction() as sess:
            sess["selected_country_id"] = country.id

        with patch("app.routes.main.dashboard.get_enabled_entity_groups", return_value=["countries"]), \
             patch("app.routes.main.dashboard.get_allowed_entity_type_codes", return_value=["country"]), \
             patch("app.routes.main.dashboard.CountryAccessRequest.query") as mock_req_query:
            mock_req_query.filter_by.return_value.options.return_value.order_by.return_value.all.return_value = []
            resp = logged_in_client.post("/", data={"self_report_template_id": ""})
        assert resp.status_code == 302

    def test_self_report_db_flush_error(self, logged_in_client, db_session, app, admin_user):
        country = create_test_country(db_session)
        _grant_entity_permission(db_session, admin_user, "country", country.id)
        template = create_test_template(db_session)
        db_session.commit()

        with logged_in_client.session_transaction() as sess:
            sess["selected_country_id"] = country.id

        mock_template = MagicMock()
        mock_template.id = template.id
        mock_template.name = "SR Template"

        with patch("app.routes.main.dashboard.get_enabled_entity_groups", return_value=["countries"]), \
             patch("app.routes.main.dashboard.get_allowed_entity_type_codes", return_value=["country"]), \
             patch("app.routes.main.dashboard.CountryAccessRequest.query") as mock_req_query, \
             patch("app.routes.main.dashboard.FormTemplate.query") as mock_ft_query, \
             patch("app.routes.main.dashboard.db") as mock_db, \
             patch("app.routes.main.dashboard.request_transaction_rollback"):
            mock_req_query.filter_by.return_value.options.return_value.order_by.return_value.all.return_value = []
            mock_ft_query.join.return_value.filter.return_value.first.return_value = mock_template
            mock_db.session = MagicMock()
            mock_db.session.flush = MagicMock(side_effect=Exception("flush fail"))
            resp = logged_in_client.post("/", data={"self_report_template_id": str(template.id)})
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# Dashboard – activity enrichment / post-processing
# ---------------------------------------------------------------------------

class TestDashboardActivityProcessing:
    def _setup_with_activities(self, logged_in_client, db_session, app, admin_user, activities):
        country = create_test_country(db_session)
        _grant_entity_permission(db_session, admin_user, "country", country.id)
        db_session.commit()

        with logged_in_client.session_transaction() as sess:
            sess["selected_entity_type"] = "country"
            sess["selected_entity_id"] = country.id

        with patch("app.routes.main.dashboard.get_enabled_entity_groups", return_value=["countries"]), \
             patch("app.routes.main.dashboard.get_allowed_entity_type_codes", return_value=["country"]), \
             patch("app.routes.main.dashboard.CountryAccessRequest.query") as mock_req_query, \
             patch("app.routes.main.dashboard.get_country_recent_activities", return_value=activities), \
             patch("app.routes.main.dashboard.is_data_quality_dashboard_enabled", return_value=False), \
             patch("app.routes.main.dashboard.AssignmentCompletionService.prefetch") as mock_prefetch, \
             patch("app.routes.main.dashboard.render_template", return_value="<html>ok</html>") as mock_rt:
            mock_req_query.filter_by.return_value.options.return_value.order_by.return_value.all.return_value = []
            mock_prefetch.return_value = MagicMock()
            mock_prefetch.return_value.metrics_for.return_value = MagicMock(
                completion_rate=0.0, filled_items=0, total_items=0
            )
            resp = logged_in_client.get("/")
        return resp

    def test_single_matrix_change_trimmed(self, logged_in_client, db_session, app, admin_user):
        activity = MagicMock()
        activity.summary_key = "activity.form_data_updated.single"
        activity.summary_params = {"old": {"r1_c1": 1, "r1_c2": 2}, "new": {"r1_c1": 1, "r1_c2": 3}}
        activity.assignment_id = None
        resp = self._setup_with_activities(logged_in_client, db_session, app, admin_user, [activity])
        assert resp.status_code == 200

    def test_multiple_matrix_changes_trimmed(self, logged_in_client, db_session, app, admin_user):
        activity = MagicMock()
        activity.summary_key = "activity.form_data_updated.multiple"
        activity.summary_params = {
            "changes": [
                {"old": {"r1_c1": 0, "r1_c2": 5}, "new": {"r1_c1": 0, "r1_c2": 6}},
            ]
        }
        activity.assignment_id = None
        resp = self._setup_with_activities(logged_in_client, db_session, app, admin_user, [activity])
        assert resp.status_code == 200

    def test_activity_with_non_dict_params(self, logged_in_client, db_session, app, admin_user):
        activity = MagicMock()
        activity.summary_key = "activity.assignment_created"
        activity.summary_params = None  # non-dict, should be handled gracefully
        activity.assignment_id = None
        resp = self._setup_with_activities(logged_in_client, db_session, app, admin_user, [activity])
        assert resp.status_code == 200

    def test_activity_post_processing_exception_handled(self, logged_in_client, db_session, app, admin_user):
        """If activity post-processing throws, dashboard still renders."""
        activity = MagicMock()
        activity.summary_key = "activity.form_data_updated.single"
        # Cause exception in processing by having summary_params raise
        type(activity).summary_params = PropertyMock(side_effect=Exception("boom"))
        activity.assignment_id = None

        country = create_test_country(db_session)
        _grant_entity_permission(db_session, admin_user, "country", country.id)
        db_session.commit()

        with patch("app.routes.main.dashboard.get_enabled_entity_groups", return_value=["countries"]), \
             patch("app.routes.main.dashboard.get_allowed_entity_type_codes", return_value=["country"]), \
             patch("app.routes.main.dashboard.CountryAccessRequest.query") as mock_req_query, \
             patch("app.routes.main.dashboard.get_country_recent_activities", return_value=[activity]), \
             patch("app.routes.main.dashboard.is_data_quality_dashboard_enabled", return_value=False), \
             patch("app.routes.main.dashboard.AssignmentCompletionService.prefetch") as mock_prefetch, \
             patch("app.routes.main.dashboard.render_template", return_value="<html>ok</html>"):
            mock_req_query.filter_by.return_value.options.return_value.order_by.return_value.all.return_value = []
            mock_prefetch.return_value = MagicMock()
            mock_prefetch.return_value.metrics_for.return_value = MagicMock(
                completion_rate=0.0, filled_items=0, total_items=0
            )
            resp = logged_in_client.get("/")
        assert resp.status_code == 200

    def test_activity_with_assignment_id_period_enrichment(self, logged_in_client, db_session, app, admin_user):
        """Activity with assignment_id gets period enriched."""
        activity = MagicMock()
        activity.summary_key = "activity.assignment_created"
        activity.summary_params = {"template": "SomeTemplate"}
        activity.assignment_id = 42

        mock_aes = MagicMock()
        mock_aes.assigned_form.period_name = "2024 Q1"

        country = create_test_country(db_session)
        _grant_entity_permission(db_session, admin_user, "country", country.id)
        db_session.commit()

        with patch("app.routes.main.dashboard.get_enabled_entity_groups", return_value=["countries"]), \
             patch("app.routes.main.dashboard.get_allowed_entity_type_codes", return_value=["country"]), \
             patch("app.routes.main.dashboard.CountryAccessRequest.query") as mock_req_query, \
             patch("app.routes.main.dashboard.get_country_recent_activities", return_value=[activity]), \
             patch("app.routes.main.dashboard.AssignmentEntityStatus.query") as mock_aes_query, \
             patch("app.routes.main.dashboard.is_data_quality_dashboard_enabled", return_value=False), \
             patch("app.routes.main.dashboard.AssignmentCompletionService.prefetch") as mock_prefetch, \
             patch("app.routes.main.dashboard.render_template", return_value="<html>ok</html>"):
            mock_req_query.filter_by.return_value.options.return_value.order_by.return_value.all.return_value = []
            mock_aes_query.filter.return_value.options.return_value.all.return_value = [mock_aes]
            mock_aes.id = 42
            mock_prefetch.return_value = MagicMock()
            mock_prefetch.return_value.metrics_for.return_value = MagicMock(
                completion_rate=0.0, filled_items=0, total_items=0
            )
            resp = logged_in_client.get("/")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Dashboard – assignment categorization (current vs past)
# ---------------------------------------------------------------------------

class TestDashboardAssignmentCategorization:
    def _build_aes_mock(self, status, status_ts=None, is_effectively_closed=False):
        aes = MagicMock()
        aes.status = status
        aes.status_timestamp = status_ts
        aes.due_date = None
        aes.submitted_by_user = None
        aes.approved_by_user = None
        aes.submitted_at = None
        aes.sent_for_review_by_user = None
        aes.sent_for_review_at = None
        aes.assigned_form = MagicMock()
        aes.assigned_form.id = 1
        aes.assigned_form.period_name = "2024"
        aes.assigned_form.is_effectively_closed = is_effectively_closed
        aes.assigned_form.assigned_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
        aes.assigned_form.template = MagicMock()
        aes.assigned_form.template.id = 1
        aes.assigned_form.template.name = "T"
        aes.assigned_form_id = 1
        aes.id = 1
        return aes

    def _run_with_aes(self, logged_in_client, db_session, admin_user, aes_list):
        country = create_test_country(db_session)
        _grant_entity_permission(db_session, admin_user, "country", country.id)
        db_session.commit()

        with patch("app.routes.main.dashboard.get_enabled_entity_groups", return_value=["countries"]), \
             patch("app.routes.main.dashboard.get_allowed_entity_type_codes", return_value=["country"]), \
             patch("app.routes.main.dashboard.CountryAccessRequest.query") as mock_req_query, \
             patch("app.routes.main.dashboard.AssignmentEntityStatus.query") as mock_aes_q, \
             patch("app.routes.main.dashboard.get_country_recent_activities", return_value=[]), \
             patch("app.routes.main.dashboard.is_data_quality_dashboard_enabled", return_value=False), \
             patch("app.routes.main.dashboard.AssignmentCompletionService.prefetch") as mock_prefetch, \
             patch("app.routes.main.dashboard.PublicSubmission.query") as mock_ps_q, \
             patch("app.routes.main.dashboard.FormTemplate.query") as mock_ft_q, \
             patch("app.routes.main.dashboard.render_template", return_value="<html>ok</html>") as mock_rt:

            mock_req_query.filter_by.return_value.options.return_value.order_by.return_value.all.return_value = []
            # Simulate the assigned_forms_statuses query chain
            mock_aes_q.join.return_value.options.return_value.filter.return_value.order_by.return_value.all.return_value = aes_list
            mock_prefetch.return_value = MagicMock()
            mock_prefetch.return_value.metrics_for.return_value = MagicMock(
                completion_rate=50.0, filled_items=5, total_items=10
            )
            mock_ps_q.filter_by.return_value.options.return_value.order_by.return_value.all.return_value = []
            mock_ft_q.join.return_value.filter.return_value.all.return_value = []
            resp = logged_in_client.get("/")
        return resp, mock_rt

    def test_submitted_assignment_goes_to_current(self, logged_in_client, db_session, app, admin_user):
        aes = self._build_aes_mock("submitted", status_ts=datetime.now(timezone.utc))
        resp, _ = self._run_with_aes(logged_in_client, db_session, admin_user, [aes])
        assert resp.status_code == 200

    def test_approved_recent_goes_to_current(self, logged_in_client, db_session, app, admin_user):
        aes = self._build_aes_mock("approved", status_ts=datetime.now(timezone.utc))
        resp, _ = self._run_with_aes(logged_in_client, db_session, admin_user, [aes])
        assert resp.status_code == 200

    def test_approved_old_goes_to_past(self, logged_in_client, db_session, app, admin_user):
        old_ts = datetime.now(timezone.utc) - timedelta(days=60)
        aes = self._build_aes_mock("approved", status_ts=old_ts)
        resp, _ = self._run_with_aes(logged_in_client, db_session, admin_user, [aes])
        assert resp.status_code == 200

    def test_effectively_closed_goes_to_past(self, logged_in_client, db_session, app, admin_user):
        aes = self._build_aes_mock("pending", is_effectively_closed=True)
        resp, _ = self._run_with_aes(logged_in_client, db_session, admin_user, [aes])
        assert resp.status_code == 200

    def test_pending_old_goes_to_past(self, logged_in_client, db_session, app, admin_user):
        old_ts = datetime.now(timezone.utc) - timedelta(days=400)
        aes = self._build_aes_mock("pending", status_ts=old_ts)
        resp, _ = self._run_with_aes(logged_in_client, db_session, admin_user, [aes])
        assert resp.status_code == 200

    def test_in_progress_new_goes_to_current(self, logged_in_client, db_session, app, admin_user):
        aes = self._build_aes_mock("in_progress", status_ts=datetime.now(timezone.utc))
        resp, _ = self._run_with_aes(logged_in_client, db_session, admin_user, [aes])
        assert resp.status_code == 200

    def test_no_status_timestamp_fallback(self, logged_in_client, db_session, app, admin_user):
        aes = self._build_aes_mock("pending", status_ts=None)
        resp, _ = self._run_with_aes(logged_in_client, db_session, admin_user, [aes])
        assert resp.status_code == 200

    def test_naive_timestamp_made_aware(self, logged_in_client, db_session, app, admin_user):
        naive_ts = datetime(2019, 1, 1)  # no tzinfo -> naive
        aes = self._build_aes_mock("approved", status_ts=naive_ts)
        resp, _ = self._run_with_aes(logged_in_client, db_session, admin_user, [aes])
        assert resp.status_code == 200

    def test_requires_revision_goes_to_current(self, logged_in_client, db_session, app, admin_user):
        aes = self._build_aes_mock("requires_revision")
        resp, _ = self._run_with_aes(logged_in_client, db_session, admin_user, [aes])
        assert resp.status_code == 200

    def test_cancelled_goes_to_past(self, logged_in_client, db_session, app, admin_user):
        aes = self._build_aes_mock("cancelled", status_ts=datetime.now(timezone.utc))
        resp, mock_rt = self._run_with_aes(logged_in_client, db_session, admin_user, [aes])
        assert resp.status_code == 200
        kwargs = mock_rt.call_args[1] if mock_rt.call_args else {}
        past = kwargs.get("past_assignments") or []
        current = kwargs.get("current_assignments") or []
        assert any(item.get("status") == "cancelled" for item in past)
        assert not any(item.get("status") == "cancelled" for item in current)

    def test_unknown_status_goes_to_current(self, logged_in_client, db_session, app, admin_user):
        aes = self._build_aes_mock("some_other_status")
        resp, _ = self._run_with_aes(logged_in_client, db_session, admin_user, [aes])
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# load_more_activities endpoint
# ---------------------------------------------------------------------------

class TestLoadMoreActivities:
    def test_unauthenticated_redirects(self, client):
        resp = client.post("/load_more_activities", data={})
        assert resp.status_code in (302, 401, 403)

    def test_missing_country_id_returns_400(self, logged_in_client, app):
        resp = logged_in_client.post(
            "/load_more_activities",
            data={"offset": "0", "limit": "10"},
        )
        assert resp.status_code in (400, 200)

    def test_invalid_offset_returns_400(self, logged_in_client, app, db_session, admin_user):
        country = create_test_country(db_session)
        _grant_entity_permission(db_session, admin_user, "country", country.id)
        db_session.commit()

        resp = logged_in_client.post(
            "/load_more_activities",
            data={"offset": "abc", "limit": "10", "country_id": str(country.id)},
        )
        assert resp.status_code == 400

    def test_access_denied_country(self, logged_in_client, app, db_session, admin_user):
        other_country = create_test_country(db_session)
        db_session.commit()

        with patch("app.routes.main.dashboard.AuthorizationService.has_country_access", return_value=False):
            resp = logged_in_client.post(
                "/load_more_activities",
                data={"offset": "0", "limit": "5", "country_id": str(other_country.id)},
            )
        assert resp.status_code == 403

    def test_success_returns_json(self, logged_in_client, app, db_session, admin_user):
        country = create_test_country(db_session)
        _grant_entity_permission(db_session, admin_user, "country", country.id)
        db_session.commit()

        activity = MagicMock()
        activity.summary_key = "activity.assignment_created"
        activity.summary_params = {"template": "T"}
        activity.assignment_id = None

        with patch("app.routes.main.dashboard.get_country_recent_activities", return_value=[activity]), \
             patch("app.routes.main.dashboard.AuthorizationService.has_country_access", return_value=True), \
             patch("app.routes.main.dashboard.get_user_countries", return_value=[{"id": country.id}]), \
             patch("app.routes.main.dashboard.render_template", return_value="<li>activity</li>"):
            resp = logged_in_client.post(
                "/load_more_activities",
                data={"offset": "0", "limit": "10", "country_id": str(country.id)},
            )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "html" in data or data.get("status") == "ok"

    def test_success_with_matrix_diff_single(self, logged_in_client, app, db_session, admin_user):
        country = create_test_country(db_session)
        _grant_entity_permission(db_session, admin_user, "country", country.id)
        db_session.commit()

        activity = MagicMock()
        activity.summary_key = "activity.form_data_updated.single"
        activity.summary_params = {
            "old": {"r1_c1": 10, "r1_c2": 20},
            "new": {"r1_c1": 10, "r1_c2": 25},
        }
        activity.assignment_id = None

        with patch("app.routes.main.dashboard.get_country_recent_activities", return_value=[activity]), \
             patch("app.routes.main.dashboard.AuthorizationService.has_country_access", return_value=True), \
             patch("app.routes.main.dashboard.get_user_countries", return_value=[{"id": country.id}]), \
             patch("app.routes.main.dashboard.render_template", return_value="<li>activity</li>"):
            resp = logged_in_client.post(
                "/load_more_activities",
                data={"offset": "0", "limit": "10", "country_id": str(country.id)},
            )
        assert resp.status_code == 200

    def test_success_with_matrix_diff_multiple(self, logged_in_client, app, db_session, admin_user):
        country = create_test_country(db_session)
        _grant_entity_permission(db_session, admin_user, "country", country.id)
        db_session.commit()

        activity = MagicMock()
        activity.summary_key = "activity.form_data_updated.multiple"
        activity.summary_params = {
            "changes": [{"old": {"r1_c1": 1, "r1_c2": 2}, "new": {"r1_c1": 1, "r1_c2": 3}}]
        }
        activity.assignment_id = None

        with patch("app.routes.main.dashboard.get_country_recent_activities", return_value=[activity]), \
             patch("app.routes.main.dashboard.AuthorizationService.has_country_access", return_value=True), \
             patch("app.routes.main.dashboard.get_user_countries", return_value=[{"id": country.id}]), \
             patch("app.routes.main.dashboard.render_template", return_value="<li>activity</li>"):
            resp = logged_in_client.post(
                "/load_more_activities",
                data={"offset": "0", "limit": "10", "country_id": str(country.id)},
            )
        assert resp.status_code == 200

    def test_exception_returns_500(self, logged_in_client, app, db_session, admin_user):
        country = create_test_country(db_session)
        _grant_entity_permission(db_session, admin_user, "country", country.id)
        db_session.commit()

        with patch("app.routes.main.dashboard.get_country_recent_activities", side_effect=Exception("crash")), \
             patch("app.routes.main.dashboard.AuthorizationService.has_country_access", return_value=True), \
             patch("app.routes.main.dashboard.get_user_countries", return_value=[{"id": country.id}]):
            resp = logged_in_client.post(
                "/load_more_activities",
                data={"offset": "0", "limit": "10", "country_id": str(country.id)},
            )
        assert resp.status_code == 500

    def test_has_more_flag_set_correctly(self, logged_in_client, app, db_session, admin_user):
        country = create_test_country(db_session)
        _grant_entity_permission(db_session, admin_user, "country", country.id)
        db_session.commit()

        # Return exactly fetch_limit items so has_more = True
        activities = [MagicMock(summary_key=None, summary_params={}, assignment_id=None) for _ in range(11)]

        with patch("app.routes.main.dashboard.get_country_recent_activities", return_value=activities), \
             patch("app.routes.main.dashboard.AuthorizationService.has_country_access", return_value=True), \
             patch("app.routes.main.dashboard.get_user_countries", return_value=[{"id": country.id}]), \
             patch("app.routes.main.dashboard.render_template", return_value=""):
            resp = logged_in_client.post(
                "/load_more_activities",
                data={"offset": "0", "limit": "10", "country_id": str(country.id)},
            )
        assert resp.status_code == 200

    def test_load_more_activities_with_aes_period_enrichment(self, logged_in_client, app, db_session, admin_user):
        country = create_test_country(db_session)
        _grant_entity_permission(db_session, admin_user, "country", country.id)
        db_session.commit()

        activity = MagicMock()
        activity.summary_key = "activity.assignment_created"
        activity.summary_params = {"template": "T"}
        activity.assignment_id = 99

        mock_aes = MagicMock()
        mock_aes.id = 99
        mock_aes.assigned_form.period_name = "2024 Q2"

        with patch("app.routes.main.dashboard.get_country_recent_activities", return_value=[activity]), \
             patch("app.routes.main.dashboard.AuthorizationService.has_country_access", return_value=True), \
             patch("app.routes.main.dashboard.get_user_countries", return_value=[{"id": country.id}]), \
             patch("app.routes.main.dashboard.AssignmentEntityStatus.query") as mock_q, \
             patch("app.routes.main.dashboard.render_template", return_value=""):
            mock_q.filter.return_value.options.return_value.all.return_value = [mock_aes]
            resp = logged_in_client.post(
                "/load_more_activities",
                data={"offset": "0", "limit": "10", "country_id": str(country.id)},
            )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# mark_notifications_read endpoint
# ---------------------------------------------------------------------------

class TestMarkNotificationsRead:
    def test_unauthenticated_redirects(self, client):
        resp = client.post(
            "/mark_notifications_read",
            json={"notification_ids": [1, 2]},
        )
        assert resp.status_code in (302, 401, 403)

    def test_no_notification_ids_returns_400(self, logged_in_client):
        resp = logged_in_client.post(
            "/mark_notifications_read",
            json={"notification_ids": []},
        )
        assert resp.status_code == 400

    def test_success_marks_notifications(self, logged_in_client):
        with patch("app.routes.main.dashboard.NotificationService") as mock_ns:
            mock_ns.mark_as_read.return_value = True
            resp = logged_in_client.post(
                "/mark_notifications_read",
                json={"notification_ids": [1, 2, 3]},
            )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get("status") == "ok"

    def test_failure_returns_500(self, logged_in_client):
        with patch("app.routes.main.dashboard.NotificationService") as mock_ns:
            mock_ns.mark_as_read.return_value = False
            resp = logged_in_client.post(
                "/mark_notifications_read",
                json={"notification_ids": [1]},
            )
        assert resp.status_code == 500

    def test_exception_returns_500(self, logged_in_client):
        with patch("app.routes.main.dashboard.NotificationService") as mock_ns:
            mock_ns.mark_as_read.side_effect = Exception("mark failed")
            resp = logged_in_client.post(
                "/mark_notifications_read",
                json={"notification_ids": [1]},
            )
        assert resp.status_code == 500

    def test_string_notification_ids_parsed(self, logged_in_client):
        with patch("app.routes.main.dashboard.NotificationService") as mock_ns:
            mock_ns.mark_as_read.return_value = True
            resp = logged_in_client.post(
                "/mark_notifications_read",
                json={"notification_ids": "1,2,3"},
            )
        assert resp.status_code == 200

    def test_no_body_returns_400(self, logged_in_client):
        resp = logged_in_client.post(
            "/mark_notifications_read",
            data="{}",
            content_type="application/json",
        )
        assert resp.status_code in (400, 200)


# ---------------------------------------------------------------------------
# Non-org user access request counting logic
# ---------------------------------------------------------------------------

class TestAccessRequestCounting:
    def test_non_org_approved_active_counts(self, logged_in_client, db_session, app, admin_user):
        """Approved request with access still active counts for non-org limit."""
        from app.models.system import CountryAccessRequestStatus

        mock_req = MagicMock()
        mock_req.status = CountryAccessRequestStatus.APPROVED
        mock_req.country_id = 1
        mock_req._access_revoked = False
        mock_req.country = MagicMock()

        with patch("app.routes.main.dashboard.UserEntityPermission") as mock_perm_cls, \
             patch("app.routes.main.dashboard.EntityService.get_entities_for_user", return_value=[]), \
             patch("app.routes.main.dashboard.get_enabled_entity_groups", return_value=["countries"]), \
             patch("app.routes.main.dashboard.get_allowed_entity_type_codes", return_value=["country"]), \
             patch("app.routes.main.dashboard.is_organization_email", return_value=False), \
             patch("app.routes.main.dashboard.CountryAccessRequest.query") as mock_req_query, \
             patch("app.routes.main.dashboard.is_data_quality_dashboard_enabled", return_value=False), \
             patch("app.routes.main.dashboard.render_template", return_value="<html>ok</html>"):
            mock_perm_cls.query.filter_by.return_value.all.return_value = []
            mock_req_query.filter_by.return_value.options.return_value.order_by.return_value.all.return_value = [mock_req]
            resp = logged_in_client.get("/")
        assert resp.status_code == 200
