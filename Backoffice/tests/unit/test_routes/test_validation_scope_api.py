"""Tests for app/routes/admin/validation_scope_api.py."""

from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.unit]


class TestValidationScopeApiHandlers:
    def test_periods_api_missing_template_id(self, app):
        from app.routes.admin.validation_scope_api import periods_api

        with app.test_request_context("/"):
            resp = periods_api()
        assert resp.status_code == 400

    def test_periods_api_returns_periods(self, app):
        from app.routes.admin.validation_scope_api import periods_api

        with app.test_request_context("/?template_id=1"), \
             patch("app.routes.admin.validation_scope_api.global_periods_for_template", return_value=["2024", "2023"]):
            resp = periods_api()
        assert resp.status_code == 200
        assert resp.get_json()["periods"] == ["2024", "2023"]

    def test_countries_api_missing_params(self, app):
        from app.routes.admin.validation_scope_api import countries_api

        with app.test_request_context("/?template_id=1"):
            resp = countries_api()
        assert resp.status_code == 400

    def test_countries_api_returns_countries(self, app):
        from app.routes.admin.validation_scope_api import countries_api

        with app.test_request_context("/?template_id=1&period=2024"), \
             patch(
                 "app.routes.admin.validation_scope_api.list_countries_for_period",
                 return_value=[{"country_id": 1, "country_name": "Uganda"}],
             ):
            resp = countries_api()
        assert resp.status_code == 200
        assert resp.get_json()["countries"][0]["country_name"] == "Uganda"
