"""Tests for app/routes/admin/governance_dashboard.py."""

from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.unit]


def _mock_render(text="ok"):
    from flask import make_response
    return make_response(text, 200)


def _sample_report():
    return {
        "summary": {"open": 1, "accepted": 0, "effective": 11, "not_applicable": 1, "unknown": 0, "controls": 12},
        "issues": [],
        "recently_resolved": [],
        "domains": [],
        "ownership": {},
    }


class TestGovernanceDashboard:
    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.get("/admin/governance")
        assert resp.status_code in (301, 302, 308)

    def test_renders_for_permitted_user(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.governance_dashboard.build_governance_report", return_value=_sample_report()), \
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

    def test_returns_the_control_register(self, logged_in_client, db_session, app):
        report = _sample_report()
        with patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.governance_dashboard.build_governance_report", return_value=report):
            resp = logged_in_client.get("/admin/governance/api/metrics")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["summary"]["open"] == 1
        assert data["summary"]["controls"] == 12

    def test_denied_without_permission(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=False):
            resp = logged_in_client.get("/admin/governance/api/metrics")
        assert resp.status_code in (302, 403)


class TestGovernanceDecisions:
    def test_accept_requires_manage_permission(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=False):
            resp = logged_in_client.post("/admin/governance/issues/1/accept", data={
                "reason": "Regional office will assign owners next quarter.",
                "accepted_until": "2026-12-01",
            })
        assert resp.status_code in (302, 403)
