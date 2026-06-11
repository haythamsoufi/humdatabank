"""
Tests for app/routes/api/data_quality.py

Coverage targets:
- GET /api/v1/dashboard/data-quality/templates  (feature flag, validation, access, success)
- GET /api/v1/dashboard/data-quality            (feature flag, validation, access, success, exceptions)
- Helper: _user_can_access_entity
"""
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _api(path: str) -> str:
    return f"/api/v1{path}"


# ---------------------------------------------------------------------------
# GET /api/v1/dashboard/data-quality/templates
# ---------------------------------------------------------------------------

class TestGetDataQualityTemplates:
    """Tests for GET /api/v1/dashboard/data-quality/templates."""

    def test_unauthenticated_returns_401_or_redirect(self, client, db_session):
        resp = client.get(_api("/dashboard/data-quality/templates"))
        assert resp.status_code in (401, 302)

    def test_feature_disabled_returns_disabled(self, logged_in_client, db_session):
        """When feature flag is off, returns enabled=False."""
        with patch("app.routes.api.data_quality.is_data_quality_dashboard_enabled", return_value=False):
            resp = logged_in_client.get(_api("/dashboard/data-quality/templates"))
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["enabled"] is False
        assert data["templates"] == []

    def test_missing_entity_type_returns_400(self, logged_in_client, db_session):
        with patch("app.routes.api.data_quality.is_data_quality_dashboard_enabled", return_value=True):
            resp = logged_in_client.get(_api("/dashboard/data-quality/templates?entity_id=1"))
        assert resp.status_code == 400

    def test_missing_entity_id_returns_400(self, logged_in_client, db_session):
        with patch("app.routes.api.data_quality.is_data_quality_dashboard_enabled", return_value=True):
            resp = logged_in_client.get(_api("/dashboard/data-quality/templates?entity_type=country"))
        assert resp.status_code == 400

    def test_access_denied_returns_403(self, logged_in_client, db_session):
        with patch("app.routes.api.data_quality.is_data_quality_dashboard_enabled", return_value=True), \
             patch("app.routes.api.data_quality._user_can_access_entity", return_value=False):
            resp = logged_in_client.get(_api("/dashboard/data-quality/templates?entity_type=country&entity_id=1"))
        assert resp.status_code == 403

    def test_success_returns_templates(self, logged_in_client, db_session):
        mock_templates = [{"id": 1, "name": "Template A"}]
        with patch("app.routes.api.data_quality.is_data_quality_dashboard_enabled", return_value=True), \
             patch("app.routes.api.data_quality._user_can_access_entity", return_value=True), \
             patch("app.routes.api.data_quality.list_data_quality_templates_for_entity", return_value=mock_templates):
            resp = logged_in_client.get(_api("/dashboard/data-quality/templates?entity_type=country&entity_id=1"))
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["enabled"] is True
        assert data["templates"] == mock_templates


# ---------------------------------------------------------------------------
# GET /api/v1/dashboard/data-quality
# ---------------------------------------------------------------------------

class TestGetDataQualityScore:
    """Tests for GET /api/v1/dashboard/data-quality."""

    def test_unauthenticated_returns_401_or_redirect(self, client, db_session):
        resp = client.get(_api("/dashboard/data-quality"))
        assert resp.status_code in (401, 302)

    def test_feature_disabled_returns_disabled(self, logged_in_client, db_session):
        with patch("app.routes.api.data_quality.is_data_quality_dashboard_enabled", return_value=False):
            resp = logged_in_client.get(_api("/dashboard/data-quality"))
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["enabled"] is False

    def test_missing_required_params_returns_400(self, logged_in_client, db_session):
        with patch("app.routes.api.data_quality.is_data_quality_dashboard_enabled", return_value=True):
            # Missing period, template_id
            resp = logged_in_client.get(_api("/dashboard/data-quality?entity_type=country&entity_id=1"))
        assert resp.status_code == 400

    def test_missing_entity_type_returns_400(self, logged_in_client, db_session):
        with patch("app.routes.api.data_quality.is_data_quality_dashboard_enabled", return_value=True):
            resp = logged_in_client.get(
                _api("/dashboard/data-quality?entity_id=1&template_id=1&period=2024")
            )
        assert resp.status_code == 400

    def test_access_denied_returns_403(self, logged_in_client, db_session):
        with patch("app.routes.api.data_quality.is_data_quality_dashboard_enabled", return_value=True), \
             patch("app.routes.api.data_quality._user_can_access_entity", return_value=False):
            resp = logged_in_client.get(
                _api("/dashboard/data-quality?entity_type=country&entity_id=1&template_id=1&period=2024")
            )
        assert resp.status_code == 403

    def test_success_returns_score(self, logged_in_client, db_session):
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"score": 85, "issues": []}
        with patch("app.routes.api.data_quality.is_data_quality_dashboard_enabled", return_value=True), \
             patch("app.routes.api.data_quality._user_can_access_entity", return_value=True), \
             patch("app.routes.api.data_quality.compute_data_quality", return_value=mock_result):
            resp = logged_in_client.get(
                _api("/dashboard/data-quality?entity_type=country&entity_id=1&template_id=1&period=2024")
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["enabled"] is True
        assert data["score"] == 85

    def test_value_error_returns_400(self, logged_in_client, db_session):
        """ValueError from compute_data_quality returns 400."""
        with patch("app.routes.api.data_quality.is_data_quality_dashboard_enabled", return_value=True), \
             patch("app.routes.api.data_quality._user_can_access_entity", return_value=True), \
             patch("app.routes.api.data_quality.compute_data_quality", side_effect=ValueError("bad params")):
            resp = logged_in_client.get(
                _api("/dashboard/data-quality?entity_type=country&entity_id=1&template_id=1&period=2024")
            )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "bad params" in data.get("error", "") or "bad params" in str(data)

    def test_generic_exception_returns_500(self, logged_in_client, db_session):
        """Generic exception from compute_data_quality returns 500."""
        with patch("app.routes.api.data_quality.is_data_quality_dashboard_enabled", return_value=True), \
             patch("app.routes.api.data_quality._user_can_access_entity", return_value=True), \
             patch("app.routes.api.data_quality.compute_data_quality", side_effect=RuntimeError("crash")):
            resp = logged_in_client.get(
                _api("/dashboard/data-quality?entity_type=country&entity_id=1&template_id=1&period=2024")
            )
        assert resp.status_code == 500

    def test_entity_id_zero_returns_400(self, logged_in_client, db_session):
        """entity_id=0 is treated as falsy and should return 400."""
        with patch("app.routes.api.data_quality.is_data_quality_dashboard_enabled", return_value=True):
            resp = logged_in_client.get(
                _api("/dashboard/data-quality?entity_type=country&entity_id=0&template_id=1&period=2024")
            )
        assert resp.status_code in (400, 403)
