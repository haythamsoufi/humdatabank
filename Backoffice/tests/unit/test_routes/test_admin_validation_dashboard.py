"""Tests for app/routes/admin/validation_dashboard.py."""

import json
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit]


def _mock_render(text="ok"):
    from flask import make_response
    return make_response(text, 200)


def _perm_patch():
    return patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True)


# ---------------------------------------------------------------------------
# validation_dashboard (GET)
# ---------------------------------------------------------------------------


class TestValidationDashboard:
    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.get("/admin/validation-dashboard")
        assert resp.status_code in (301, 302, 308)

    def test_renders_for_permitted_user(self, logged_in_client, db_session, app):
        with _perm_patch(), \
             patch("app.routes.admin.validation_dashboard.template_options", return_value=[]), \
             patch("app.routes.admin.validation_dashboard.render_template", return_value=_mock_render("vd")):
            resp = logged_in_client.get("/admin/validation-dashboard")
        assert resp.status_code == 200

    def test_denied_without_permission(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=False):
            resp = logged_in_client.get("/admin/validation-dashboard")
        assert resp.status_code in (302, 403)


# ---------------------------------------------------------------------------
# validation_dashboard_periods_api
# ---------------------------------------------------------------------------


class TestValidationDashboardPeriodsApi:
    def test_missing_template_id_returns_400(self, logged_in_client, db_session, app):
        with _perm_patch():
            resp = logged_in_client.get("/admin/validation-dashboard/api/periods")
        assert resp.status_code == 400

    def test_returns_periods(self, logged_in_client, db_session, app):
        with _perm_patch(), \
             patch("app.routes.admin.validation_dashboard.global_periods_for_template", return_value=["2025", "2024"]):
            resp = logged_in_client.get("/admin/validation-dashboard/api/periods?template_id=1")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "periods" in data
        assert data["periods"] == ["2025", "2024"]


# ---------------------------------------------------------------------------
# validation_dashboard_countries_api
# ---------------------------------------------------------------------------


class TestValidationDashboardCountriesApi:
    def test_missing_params_returns_400(self, logged_in_client, db_session, app):
        with _perm_patch():
            resp = logged_in_client.get("/admin/validation-dashboard/api/countries")
        assert resp.status_code == 400

    def test_missing_period_returns_400(self, logged_in_client, db_session, app):
        with _perm_patch():
            resp = logged_in_client.get("/admin/validation-dashboard/api/countries?template_id=1")
        assert resp.status_code == 400

    def test_returns_countries(self, logged_in_client, db_session, app):
        with _perm_patch(), \
             patch("app.routes.admin.validation_dashboard.list_countries_for_period", return_value=[{"id": 1, "name": "Uganda"}]):
            resp = logged_in_client.get("/admin/validation-dashboard/api/countries?template_id=1&period=2024")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "countries" in data


# ---------------------------------------------------------------------------
# validation_dashboard_tracker_api
# ---------------------------------------------------------------------------


class TestValidationDashboardTrackerApi:
    def test_missing_params_returns_400(self, logged_in_client, db_session, app):
        with _perm_patch():
            resp = logged_in_client.get("/admin/validation-dashboard/api/tracker")
        assert resp.status_code == 400

    def test_returns_tracker_data(self, logged_in_client, db_session, app):
        with _perm_patch(), \
             patch("app.routes.admin.validation_dashboard.build_tracker_data", return_value={"countries": [], "total": 0}):
            resp = logged_in_client.get("/admin/validation-dashboard/api/tracker?template_id=1&period=2024")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "countries" in data


# ---------------------------------------------------------------------------
# validation_dashboard_summary_api
# ---------------------------------------------------------------------------


class TestValidationDashboardSummaryApi:
    def test_missing_params_returns_400(self, logged_in_client, db_session, app):
        with _perm_patch():
            resp = logged_in_client.get("/admin/validation-dashboard/api/summary")
        assert resp.status_code == 400

    def test_returns_summary(self, logged_in_client, db_session, app):
        with _perm_patch(), \
             patch("app.routes.admin.validation_dashboard.summarize_period", return_value={"total": 5, "open": 2}):
            resp = logged_in_client.get("/admin/validation-dashboard/api/summary?template_id=1&period=2024")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "total" in data


# ---------------------------------------------------------------------------
# validation_dashboard_preview_api
# ---------------------------------------------------------------------------


class TestValidationDashboardPreviewApi:
    def test_missing_all_params(self, logged_in_client, db_session, app):
        with _perm_patch():
            resp = logged_in_client.get("/admin/validation-dashboard/api/preview")
        assert resp.status_code == 400

    def test_missing_country_id(self, logged_in_client, db_session, app):
        with _perm_patch():
            resp = logged_in_client.get("/admin/validation-dashboard/api/preview?template_id=1&period=2024")
        assert resp.status_code == 400

    def test_returns_preview(self, logged_in_client, db_session, app):
        with _perm_patch(), \
             patch("app.routes.admin.validation_dashboard.preview_country_validation", return_value={"flags": []}):
            resp = logged_in_client.get(
                "/admin/validation-dashboard/api/preview?template_id=1&period=2024&country_id=5"
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "preview" in data

    def test_value_error_returns_400(self, logged_in_client, db_session, app):
        with _perm_patch(), \
             patch("app.routes.admin.validation_dashboard.preview_country_validation", side_effect=ValueError("bad config")):
            resp = logged_in_client.get(
                "/admin/validation-dashboard/api/preview?template_id=1&period=2024&country_id=5"
            )
        assert resp.status_code == 400

    def test_exception_returns_500(self, logged_in_client, db_session, app):
        with _perm_patch(), \
             patch("app.routes.admin.validation_dashboard.preview_country_validation", side_effect=RuntimeError("crash")):
            resp = logged_in_client.get(
                "/admin/validation-dashboard/api/preview?template_id=1&period=2024&country_id=5"
            )
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# validation_dashboard_run_checks
# ---------------------------------------------------------------------------


class TestValidationDashboardRunChecks:
    def _post(self, logged_in_client, data):
        return logged_in_client.post(
            "/admin/validation-dashboard/run-checks",
            data=json.dumps(data),
            content_type="application/json",
        )

    def test_missing_template_id_returns_400(self, logged_in_client, db_session, app):
        with _perm_patch():
            resp = self._post(logged_in_client, {"period_name": "2024", "country_id": 1})
        assert resp.status_code == 400

    def test_missing_period_returns_400(self, logged_in_client, db_session, app):
        with _perm_patch():
            resp = self._post(logged_in_client, {"template_id": 1, "country_id": 1})
        assert resp.status_code == 400

    def test_missing_country_returns_400(self, logged_in_client, db_session, app):
        with _perm_patch():
            resp = self._post(logged_in_client, {"template_id": 1, "period_name": "2024"})
        assert resp.status_code == 400

    def test_success_with_country_id(self, logged_in_client, db_session, app):
        mock_result = MagicMock()
        mock_result.created = 3
        mock_result.updated = 1
        mock_result.resolved = 0

        with _perm_patch(), \
             patch("app.routes.admin.validation_dashboard.run_validation_checks", return_value=mock_result), \
             patch("app.routes.admin.validation_dashboard.enforce_csrf_json", return_value=None):
            resp = self._post(logged_in_client, {"template_id": 1, "period_name": "2024", "country_id": 5})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["created"] == 3

    def test_success_with_country_ids(self, logged_in_client, db_session, app):
        mock_result = MagicMock()
        mock_result.created = 1
        mock_result.updated = 0
        mock_result.resolved = 0

        with _perm_patch(), \
             patch("app.routes.admin.validation_dashboard.run_validation_checks", return_value=mock_result), \
             patch("app.routes.admin.validation_dashboard.enforce_csrf_json", return_value=None):
            resp = self._post(logged_in_client, {
                "template_id": 1, "period_name": "2024", "country_ids": [1, 2]
            })
        assert resp.status_code == 200
        data = resp.get_json()
        assert "created" in data

    def test_value_error_adds_to_errors(self, logged_in_client, db_session, app):
        with _perm_patch(), \
             patch("app.routes.admin.validation_dashboard.run_validation_checks", side_effect=ValueError("bad")), \
             patch("app.routes.admin.validation_dashboard.enforce_csrf_json", return_value=None):
            resp = self._post(logged_in_client, {"template_id": 1, "period_name": "2024", "country_id": 5})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["has_errors"] is True

    def test_exception_adds_to_errors(self, logged_in_client, db_session, app):
        with _perm_patch(), \
             patch("app.routes.admin.validation_dashboard.run_validation_checks", side_effect=RuntimeError("db")), \
             patch("app.routes.admin.validation_dashboard.enforce_csrf_json", return_value=None), \
             patch("app.routes.admin.validation_dashboard.db") as mock_db:
            resp = self._post(logged_in_client, {"template_id": 1, "period_name": "2024", "country_id": 5})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["has_errors"] is True

    def test_csrf_error_returns_error_response(self, logged_in_client, db_session, app):
        from flask import make_response
        csrf_resp = make_response('{"error": "csrf"}', 403)

        with _perm_patch(), \
             patch("app.routes.admin.validation_dashboard.enforce_csrf_json", return_value=csrf_resp):
            resp = self._post(logged_in_client, {"template_id": 1, "period_name": "2024", "country_id": 5})
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# validation_dashboard_dispatch_send
# ---------------------------------------------------------------------------


class TestValidationDashboardDispatchSend:
    def _post(self, logged_in_client, data):
        return logged_in_client.post(
            "/admin/validation-dashboard/dispatch/send",
            data=json.dumps(data),
            content_type="application/json",
        )

    def test_success(self, logged_in_client, db_session, app):
        mock_batch = MagicMock()
        mock_batch.id = 1
        mock_batch.status = "sent"
        mock_batch.summary = {"sent": 3}

        with _perm_patch(), \
             patch("app.routes.admin.validation_dashboard.send_dispatch", return_value=mock_batch), \
             patch("app.routes.admin.validation_dashboard.enforce_csrf_json", return_value=None), \
             patch("app.routes.admin.validation_dashboard.current_user") as cu:
            cu.id = 1
            resp = self._post(logged_in_client, {
                "template_id": 1, "period_name": "2024", "country_id": 5
            })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["batch_id"] == 1

    def test_exception_returns_500(self, logged_in_client, db_session, app):
        with _perm_patch(), \
             patch("app.routes.admin.validation_dashboard.send_dispatch", side_effect=RuntimeError("crash")), \
             patch("app.routes.admin.validation_dashboard.enforce_csrf_json", return_value=None), \
             patch("app.routes.admin.validation_dashboard.db") as mock_db, \
             patch("app.routes.admin.validation_dashboard.current_user") as cu:
            cu.id = 1
            resp = self._post(logged_in_client, {
                "template_id": 1, "period_name": "2024", "country_id": 5
            })
        assert resp.status_code == 500

    def test_csrf_error_short_circuits(self, logged_in_client, db_session, app):
        from flask import make_response
        csrf_resp = make_response('{"error": "csrf"}', 403)

        with _perm_patch(), \
             patch("app.routes.admin.validation_dashboard.enforce_csrf_json", return_value=csrf_resp):
            resp = self._post(logged_in_client, {"template_id": 1, "period_name": "2024"})
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# validation_dashboard_dispatch_preview
# ---------------------------------------------------------------------------


class TestValidationDashboardDispatchPreview:
    def _post(self, logged_in_client, data):
        return logged_in_client.post(
            "/admin/validation-dashboard/dispatch/preview",
            data=json.dumps(data),
            content_type="application/json",
        )

    def test_success(self, logged_in_client, db_session, app):
        mock_preview = MagicMock()
        mock_preview.entities = [{"id": 1, "name": "Uganda"}]
        mock_preview.questions = [{"id": 10}]
        mock_preview.total_recipients = 2

        with _perm_patch(), \
             patch("app.routes.admin.validation_dashboard.preview_dispatch", return_value=mock_preview), \
             patch("app.routes.admin.validation_dashboard.enforce_csrf_json", return_value=None):
            resp = self._post(logged_in_client, {
                "template_id": 1, "period_name": "2024", "country_id": 5
            })
        assert resp.status_code == 200
        data = resp.get_json()
        assert "entities" in data
        assert "questions" in data
        assert data["total_recipients"] == 2

    def test_csrf_error(self, logged_in_client, db_session, app):
        from flask import make_response
        csrf_resp = make_response('{"error": "csrf"}', 403)

        with _perm_patch(), \
             patch("app.routes.admin.validation_dashboard.enforce_csrf_json", return_value=csrf_resp):
            resp = self._post(logged_in_client, {"template_id": 1, "period_name": "2024"})
        assert resp.status_code == 403

    def test_with_entity_id_instead_of_country_id(self, logged_in_client, db_session, app):
        mock_preview = MagicMock()
        mock_preview.entities = []
        mock_preview.questions = []
        mock_preview.total_recipients = 0

        with _perm_patch(), \
             patch("app.routes.admin.validation_dashboard.preview_dispatch", return_value=mock_preview) as mock_pd, \
             patch("app.routes.admin.validation_dashboard.enforce_csrf_json", return_value=None):
            resp = self._post(logged_in_client, {
                "template_id": 1, "period_name": "2024",
                "entity_type": "branch", "entity_id": 99
            })
        assert resp.status_code == 200
        # Verify entity_type was passed through
        call_kwargs = mock_pd.call_args[1]
        assert call_kwargs.get("entity_type") == "branch"
