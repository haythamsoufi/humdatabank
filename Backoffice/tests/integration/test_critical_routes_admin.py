"""Smoke tests for critical admin production routes."""

import pytest

from tests.factories import create_test_user
from tests.helpers import login_session


ADMIN_HTML_ROUTES = [
    ("/admin/assignments", "assignments list"),
    ("/admin/assignments/new", "new assignment"),
    ("/admin/templates", "templates list"),
    ("/admin/users", "users list"),
    ("/admin/access-requests", "access requests"),
    ("/admin/organization/", "organization"),
    ("/admin/indicator_bank", "indicator bank"),
    ("/admin/public-submissions", "public submissions"),
    ("/admin/api-management", "api management"),
]


@pytest.mark.integration
@pytest.mark.critical
class TestCriticalAdminDashboardRoute:
    def test_admin_dashboard_requires_auth(self, client):
        resp = client.get("/admin/", follow_redirects=False)
        assert resp.status_code in (301, 302, 303, 307, 308)

    def test_admin_dashboard_happy_path_system_manager(self, logged_in_sm_client):
        resp = logged_in_sm_client.get("/admin/", follow_redirects=False)
        assert resp.status_code == 200

    def test_admin_dashboard_denied_for_regular_admin(self, logged_in_admin_client):
        resp = logged_in_admin_client.get("/admin/", follow_redirects=False)
        assert resp.status_code in (301, 302, 303, 307, 308, 403)


@pytest.mark.integration
@pytest.mark.critical
class TestCriticalAdminHtmlRoutes:
    @pytest.mark.parametrize("path,label", ADMIN_HTML_ROUTES)
    def test_admin_route_requires_auth(self, client, path, label):
        resp = client.get(path, follow_redirects=False)
        assert resp.status_code in (301, 302, 303, 307, 308), label

    @pytest.mark.parametrize("path,label", ADMIN_HTML_ROUTES)
    def test_admin_route_happy_path(self, logged_in_admin_client, path, label):
        resp = logged_in_admin_client.get(path, follow_redirects=False)
        assert resp.status_code == 200, label

    @pytest.mark.parametrize("path,label", ADMIN_HTML_ROUTES)
    def test_admin_route_denied_for_regular_user(
        self, client, db_session, app, path, label
    ):
        with app.app_context():
            user = create_test_user(db_session, role="user")
            login_session(client, user.id)

        resp = client.get(path, follow_redirects=False)
        assert resp.status_code in (301, 302, 303, 307, 308, 403), label
