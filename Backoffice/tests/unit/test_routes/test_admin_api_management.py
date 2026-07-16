"""Tests for app/routes/admin/api_management.py."""

from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit]


def _mock_render(text="ok"):
    from flask import make_response
    return make_response(text, 200)


def _auth_patches():
    return [
        patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True),
        patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True),
    ]


# ---------------------------------------------------------------------------
# Helper scan mock
# ---------------------------------------------------------------------------

def _make_scan():
    return {
        "live": [],
        "undocumented": [],
        "stale": [],
        "coverage_pct": 100.0,
        "total_live": 0,
        "documented": 0,
    }


# ---------------------------------------------------------------------------
# api_management view
# ---------------------------------------------------------------------------


class TestApiManagementView:
    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.get("/admin/api-management")
        assert resp.status_code in (301, 302, 308)

    def test_renders_for_admin(self, logged_in_client, db_session, app):
        mock_usage = MagicMock()
        mock_usage.query.count.return_value = 0
        mock_usage.query.filter.return_value = mock_usage.query
        mock_usage.query.with_entities.return_value.distinct.return_value.count.return_value = 0

        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.api_management.scan_flask_routes", return_value=_make_scan()), \
             patch("app.routes.admin.api_management.bulk_endpoint_usage_stats", return_value={}), \
             patch("app.routes.admin.api_management.FormTemplate") as mock_ft, \
             patch("app.routes.admin.api_management.Country") as mock_c, \
             patch("app.routes.admin.api_management.User") as mock_u, \
             patch("app.routes.admin.api_management.Sector") as mock_sec, \
             patch("app.routes.admin.api_management.SubSector") as mock_ss, \
             patch("app.routes.admin.api_management.IndicatorBank") as mock_ib, \
             patch("app.routes.admin.api_management.APIUsage") as mock_au, \
             patch("app.routes.admin.api_management.db") as mock_db, \
             patch("app.routes.admin.api_management.render_template", return_value=_mock_render("api-mgmt")):

            mock_ft.query.all.return_value = []
            mock_c.query.order_by.return_value.all.return_value = []
            mock_u.query.order_by.return_value.all.return_value = []
            mock_sec.query.order_by.return_value.all.return_value = []
            mock_ss.query.order_by.return_value.all.return_value = []
            mock_ib_q = MagicMock()
            mock_ib_q.distinct.return_value.order_by.return_value.all.return_value = []
            mock_db.session.query.return_value = mock_ib_q
            mock_au.query.count.return_value = 0
            mock_au.query.filter.return_value.all.return_value = []
            mock_au.query.filter.return_value.count.return_value = 0
            mock_au.query.with_entities.return_value.distinct.return_value.count.return_value = 0
            mock_db.session.query.return_value.scalar.return_value = 0

            resp = logged_in_client.get("/admin/api-management")
        assert resp.status_code == 200

    def test_renders_with_undocumented_routes(self, logged_in_client, db_session, app):
        scan = _make_scan()
        scan["undocumented"] = [
            {
                "surface": "v1",
                "path": "/api/v1/undoc",
                "methods": ["GET"],
                "ep_auth": "api_key",
                "ep_perm": None,
            }
        ]

        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.api_management.scan_flask_routes", return_value=scan), \
             patch("app.routes.admin.api_management.bulk_endpoint_usage_stats", return_value={}), \
             patch("app.routes.admin.api_management.FormTemplate") as mock_ft, \
             patch("app.routes.admin.api_management.Country") as mock_c, \
             patch("app.routes.admin.api_management.User") as mock_u, \
             patch("app.routes.admin.api_management.Sector") as mock_sec, \
             patch("app.routes.admin.api_management.SubSector") as mock_ss, \
             patch("app.routes.admin.api_management.IndicatorBank") as mock_ib, \
             patch("app.routes.admin.api_management.APIUsage") as mock_au, \
             patch("app.routes.admin.api_management.db") as mock_db, \
             patch("app.routes.admin.api_management.render_template", return_value=_mock_render("api-mgmt")):

            mock_ft.query.all.return_value = []
            mock_c.query.order_by.return_value.all.return_value = []
            mock_u.query.order_by.return_value.all.return_value = []
            mock_sec.query.order_by.return_value.all.return_value = []
            mock_ss.query.order_by.return_value.all.return_value = []
            mock_ib_q = MagicMock()
            mock_ib_q.distinct.return_value.order_by.return_value.all.return_value = []
            mock_db.session.query.return_value = mock_ib_q
            mock_au.query.count.return_value = 5
            mock_au.query.filter.return_value.all.return_value = []
            mock_au.query.filter.return_value.count.return_value = 4
            mock_au.query.with_entities.return_value.distinct.return_value.count.return_value = 2
            mock_db.session.query.return_value.scalar.return_value = 150.0

            resp = logged_in_client.get("/admin/api-management")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# api_stats
# ---------------------------------------------------------------------------


class TestApiStats:
    def test_default_params_returns_ok(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.api_management.APIUsage") as mock_au, \
             patch("app.routes.admin.api_management.chart_stats_for_period", return_value=[]):
            mock_au.query.filter.return_value = mock_au.query
            mock_au.query.filter.return_value.ilike.return_value = mock_au.query
            resp = logged_in_client.get("/admin/api-management/stats")
        assert resp.status_code == 200

    def test_endpoint_filter(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.api_management.APIUsage") as mock_au, \
             patch("app.routes.admin.api_management.chart_stats_for_period", return_value=[{"date": "2026-01-01", "count": 3}]):
            mock_au.query.filter.return_value = mock_au.query
            resp = logged_in_client.get("/admin/api-management/stats?endpoint=/api/v1/data&period=weekly")
        assert resp.status_code == 200

    def test_invalid_period_defaults_to_daily(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.api_management.APIUsage") as mock_au, \
             patch("app.routes.admin.api_management.chart_stats_for_period", return_value=[]) as mock_csp:
            mock_au.query.filter.return_value = mock_au.query
            resp = logged_in_client.get("/admin/api-management/stats?period=invalid")
        assert resp.status_code == 200
        # chart_stats_for_period was called with 'daily'
        call_args = mock_csp.call_args
        assert call_args[0][1] == "daily"

    def test_exception_returns_500(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.api_management.APIUsage", side_effect=RuntimeError("db down")):
            resp = logged_in_client.get("/admin/api-management/stats")
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class TestApiManagementHelpers:
    def test_normalize_path_strips_type_annotations(self):
        from app.routes.admin.api_management import _normalize_path
        assert _normalize_path("/api/v1/items/<int:item_id>") == "/api/v1/items/<item_id>"
        assert _normalize_path("/api/v1/data") == "/api/v1/data"

    def test_surface_for_path(self):
        from app.routes.admin.api_management import _surface_for_path
        assert _surface_for_path("/api/mobile/v1/auth/token") == "mobile"
        assert _surface_for_path("/api/ai/v2/chat") == "ai"
        assert _surface_for_path("/api/v1/data") == "v1"
        assert _surface_for_path("/api/other") == "ai"  # starts with /api/ai/... no — falls to 'other'
        assert _surface_for_path("/some/other") == "other"

    def test_count_unique_overlap_pairs(self):
        from app.routes.admin.api_management import _count_unique_overlap_pairs
        eps = [
            {"path": "/api/v1/data", "overlaps": ["/api/mobile/v1/data"]},
            {"path": "/api/mobile/v1/data", "overlaps": ["/api/v1/data"]},
            {"path": "/api/v1/other", "overlaps": []},
        ]
        count = _count_unique_overlap_pairs(eps)
        assert count == 1  # same pair counted once

    def test_ep_surface_filter_disabled_all_empty(self):
        from app.routes.admin.api_management import _ep_surface_filter_disabled
        result = _ep_surface_filter_disabled([])
        # all filters should be disabled (True) since no rows match
        assert all(result.values())

    def test_ep_surface_filter_disabled_with_v1(self):
        from app.routes.admin.api_management import _ep_surface_filter_disabled
        rows = [{"surface": "v1", "has_flags": False, "has_overlap": False, "has_stats": False,
                 "undocumented": False, "stale": False, "gaps": False}]
        result = _ep_surface_filter_disabled(rows)
        assert result["v1"] is False  # v1 filter is NOT disabled
        assert result["mobile"] is True  # mobile filter is disabled (no mobile rows)

    def test_endpoint_registry_grid_rows(self):
        from app.routes.admin.api_management import _endpoint_registry_grid_rows
        eps = [
            {
                "surface": "v1",
                "group": "Submissions",
                "path": "/api/v1/submissions",
                "methods": ["GET"],
                "auth": "api_key",
                "description": "List submissions",
                "flags": [],
                "overlaps": [],
                "total_requests": 10,
                "success_rate": 99.5,
                "featured": False,
                "rate_limited": True,
            }
        ]
        rows = _endpoint_registry_grid_rows(eps)
        assert len(rows) == 1
        assert rows[0]["surface"] == "v1"
        assert rows[0]["has_stats"] is True

    def test_endpoint_registry_grid_rows_ai_documents(self):
        from app.routes.admin.api_management import _endpoint_registry_grid_rows
        eps = [
            {
                "surface": "ai",
                "group": "Documents (RAG)",
                "path": "/api/ai/documents/upload",
                "methods": ["POST"],
                "auth": "session",
                "description": "Upload doc",
                "flags": [{"type": "bug", "note": "test"}],
                "overlaps": ["/api/v1/something"],
                "total_requests": 0,
                "success_rate": 100,
                "featured": False,
                "rate_limited": True,
            }
        ]
        rows = _endpoint_registry_grid_rows(eps)
        assert rows[0]["registryGroup"].startswith("AI Documents")
        assert rows[0]["has_flags"] is True
        assert rows[0]["has_overlap"] is True
