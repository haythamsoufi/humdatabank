"""Tests for app/routes/admin/validation_rules.py."""

from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.unit]


def _mock_render(text="ok"):
    from flask import make_response
    return make_response(text, 200)


def _perm_patch():
    return patch("app.services.authorization_service.AuthorizationService.has_rbac_permission", return_value=True)


class TestValidationRulesAdmin:
    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.get("/admin/validation-rules")
        assert resp.status_code in (301, 302, 308)

    def test_renders_for_permitted_user(self, logged_in_client, db_session, app):
        with _perm_patch(), \
             patch("app.routes.admin.validation_rules.template_options", return_value=[]), \
             patch("app.routes.admin.validation_rules.list_countries_for_picker", return_value=[]), \
             patch("app.routes.admin.validation_rules.list_rule_catalog", return_value=[]), \
             patch("app.routes.admin.validation_rules.registry_bootstrap", return_value={
                 "rule_packs": [], "check_type_options": [], "kpi_codes": [],
             }), \
             patch("app.routes.admin.validation_rules.render_template", return_value=_mock_render("vr")):
            resp = logged_in_client.get("/admin/validation-rules")
        assert resp.status_code == 200

    def test_denied_without_permission(self, logged_in_client, db_session, app):
        with patch("app.services.authorization_service.AuthorizationService.has_rbac_permission", return_value=False):
            resp = logged_in_client.get("/admin/validation-rules")
        assert resp.status_code in (302, 403)


class TestValidationRulesCatalogApi:
    def test_returns_catalog(self, logged_in_client, db_session, app):
        with _perm_patch(), \
             patch("app.routes.admin.validation_rules.list_rule_catalog", return_value=[{"code": "fiscal_year"}]):
            resp = logged_in_client.get("/admin/validation-rules/api/catalog")
        assert resp.status_code == 200
        assert resp.get_json()["rules"][0]["code"] == "fiscal_year"


class TestValidationRulesThresholdsApi:
    def test_list_thresholds(self, logged_in_client, db_session, app):
        with _perm_patch(), \
             patch("app.routes.admin.validation_rules.list_threshold_rows", return_value=[]):
            resp = logged_in_client.get("/admin/validation-rules/api/thresholds?template_id=21")
        assert resp.status_code == 200
        assert resp.get_json()["rows"] == []

    def test_upsert_threshold(self, logged_in_client, db_session, app):
        with _perm_patch(), \
             patch("app.routes.admin.validation_rules.enforce_csrf_json", return_value=None), \
             patch("app.routes.admin.validation_rules.upsert_threshold", return_value={"id": 1}):
            resp = logged_in_client.post(
                "/admin/validation-rules/api/thresholds",
                json={"country_id": 1, "kpi_code": "KPI_GB", "threshold_fraction": 0.25, "template_id": 21},
            )
        assert resp.status_code == 200
        assert resp.get_json()["row"]["id"] == 1

    def test_delete_threshold(self, logged_in_client, db_session, app):
        with _perm_patch(), \
             patch("app.routes.admin.validation_rules.enforce_csrf_json", return_value=None), \
             patch("app.routes.admin.validation_rules.delete_threshold") as mock_delete:
            resp = logged_in_client.delete("/admin/validation-rules/api/thresholds/5")
        assert resp.status_code == 200
        mock_delete.assert_called_once_with(5)
