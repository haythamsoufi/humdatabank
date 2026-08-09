"""Report routes auth and CRUD smoke tests."""

from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.api]

API = "/admin/reports/api"
JSON_HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}


class TestReportsRouteAuth:
    def test_list_requires_auth(self, client):
        resp = client.get("/admin/reports")
        assert resp.status_code in (301, 302, 303, 307, 308, 401)

    def test_api_create_requires_auth(self, client):
        resp = client.post(API, data=json.dumps({"title": "T"}), headers=JSON_HEADERS)
        assert resp.status_code in (301, 302, 303, 307, 308, 401)

    def test_list_ok_for_system_manager(self, logged_in_sm_client):
        resp = logged_in_sm_client.get("/admin/reports")
        assert resp.status_code == 200

    def test_list_denied_for_authenticated_user_without_reports_permission(self, logged_in_focal_client):
        """Reports routes carry a permission_required_any(REPORTS_VIEW, REPORTS_EDIT)
        guard (see startup RBAC route-guard audit) in addition to the in-body
        _forbidden_if_no_view() check — a focal point with no report permission must
        still be denied. Plain browser GET (no JSON/AJAX signal) is redirected, not
        shown a raw JSON error."""
        resp = logged_in_focal_client.get("/admin/reports")
        assert resp.status_code in (301, 302, 303, 307, 308)

    def test_metadata_route_denied_for_authenticated_user_without_reports_permission(self, logged_in_focal_client):
        """Same guard on the JSON metadata endpoints returns a 403 JSON body
        (path contains an /api/ segment, so is_json_request() is true)."""
        resp = logged_in_focal_client.get(f"{API}/metadata/templates")
        assert resp.status_code == 403
        assert "error" in resp.get_json()


class TestReportsRbacAudit:
    """Regression test for the exact signal that originally flagged these routes:
    the startup static RBAC guard audit (app.startup_tasks.audit_admin_route_guards).
    Mirrors its "protected" check against the real registered routes so a future
    /admin/reports/* route added without a guard decorator fails fast in CI instead
    of only surfacing as a runtime warning log."""

    def test_no_reports_routes_flagged_by_static_rbac_audit(self, app):
        unprotected = []
        for rule in app.url_map.iter_rules():
            path = str(rule.rule or "")
            if not path.startswith("/admin/reports"):
                continue
            view = app.view_functions.get(str(rule.endpoint or ""))
            if view is None or getattr(view, "_rbac_guard_audit_exempt", False):
                continue
            protected = bool(
                getattr(view, "_rbac_admin_required", False)
                or getattr(view, "_rbac_system_manager_required", False)
                or (getattr(view, "_rbac_permissions_required", None) not in (None, [], ()))
                or (getattr(view, "_rbac_permissions_any_required", None) not in (None, [], ()))
            )
            if not protected:
                unprotected.append(f"{path} -> {rule.endpoint}")
        assert unprotected == []


class TestReportsApiCrud:
    def test_create_and_get_report(self, logged_in_sm_client):
        definition = {
            "schema_version": 1,
            "filters": {"template_ids": [], "period_names": [], "assignment_statuses": ["approved"]},
            "sections": [],
        }
        create = logged_in_sm_client.post(
            API,
            data=json.dumps({"title": "Test report", "definition": definition}),
            headers=JSON_HEADERS,
        )
        assert create.status_code == 200
        report_id = create.get_json()["report"]["id"]

        get_resp = logged_in_sm_client.get(f"{API}/{report_id}", headers=JSON_HEADERS)
        assert get_resp.status_code == 200
        assert get_resp.get_json()["report"]["title"] == "Test report"

        delete = logged_in_sm_client.delete(f"{API}/{report_id}", headers=JSON_HEADERS)
        assert delete.status_code == 200
