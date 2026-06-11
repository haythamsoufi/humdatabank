"""Tests for app/routes/admin/governance_dashboard.py."""

from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit]


def _mock_render(text="ok"):
    from flask import make_response
    return make_response(text, 200)


def _sample_metrics():
    return {
        "focal_coverage": {"covered": 10, "total": 12},
        "access_control": {"users_with_roles": 5},
        "quality": {"flags_open": 2},
    }


class TestGovernanceDashboard:
    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.get("/admin/governance")
        assert resp.status_code in (301, 302, 308)

    def test_renders_for_permitted_user(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.governance_dashboard.get_governance_metrics", return_value=_sample_metrics()), \
             patch("app.routes.admin.governance_dashboard.render_template", return_value=_mock_render("governance")):
            resp = logged_in_client.get("/admin/governance")
        assert resp.status_code == 200

    def test_denied_without_permission(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=False):
            resp = logged_in_client.get("/admin/governance")
        assert resp.status_code in (302, 403)


class TestGovernanceApiMetrics:
    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.get("/admin/governance/api/metrics")
        assert resp.status_code in (301, 302, 308)

    def test_returns_dict_metrics_as_json(self, logged_in_client, db_session, app):
        metrics = _sample_metrics()
        with patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.governance_dashboard.get_governance_metrics", return_value=metrics):
            resp = logged_in_client.get("/admin/governance/api/metrics")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "focal_coverage" in data

    def test_returns_non_dict_metrics_as_json(self, logged_in_client, db_session, app):
        """When metrics is not a dict, json_ok(data=metrics) is used."""
        with patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.governance_dashboard.get_governance_metrics", return_value=["list_item"]):
            resp = logged_in_client.get("/admin/governance/api/metrics")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "data" in data

    def test_denied_without_permission(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=False):
            resp = logged_in_client.get("/admin/governance/api/metrics")
        assert resp.status_code in (302, 403)
