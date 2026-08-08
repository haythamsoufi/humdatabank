"""Tests for the /api/v1/public/reports/* routes in public_integrations.py.

Service-layer logic (build_country_report, get_report_template) is covered by
tests/unit/test_services/test_public_report_service.py — these tests isolate
route-level concerns: query param parsing, status codes, and headers.
"""
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.unit]


class TestPublicCountryReportRoute:
    def test_requires_country_param(self, client):
        resp = client.get("/api/v1/public/reports/country")
        assert resp.status_code == 400

    def test_returns_report_payload(self, client):
        payload = {"ok": True, "country": {"id": 1, "name": "Kenya"}, "headline_kpis": []}
        with patch(
            "app.routes.api.public_integrations.build_country_report", return_value=payload
        ) as mock_build:
            resp = client.get("/api/v1/public/reports/country?country=Kenya&period_hint=2026")
        assert resp.status_code == 200
        assert resp.get_json()["country"]["name"] == "Kenya"
        assert resp.headers.get("X-Public-Data-Access") == "true"
        mock_build.assert_called_once()
        call_kwargs = mock_build.call_args.kwargs
        assert call_kwargs["country"] == "Kenya"
        assert call_kwargs["period_hint"] == "2026"

    def test_embeds_template_when_style_requested(self, client):
        report_payload = {"ok": True, "country": {"id": 1, "name": "Kenya"}}
        template_payload = {"ok": True, "style": "default", "html_template": "<html></html>"}
        with patch(
            "app.routes.api.public_integrations.build_country_report", return_value=report_payload
        ), patch(
            "app.routes.api.public_integrations.get_report_template", return_value=template_payload
        ) as mock_template:
            resp = client.get("/api/v1/public/reports/country?country=Kenya&template_style=default")
        assert resp.status_code == 200
        assert resp.get_json()["design_template"]["style"] == "default"
        mock_template.assert_called_once_with("default")

    def test_skips_template_when_country_unresolved(self, client):
        report_payload = {"ok": False, "error": "Could not resolve country"}
        with patch(
            "app.routes.api.public_integrations.build_country_report", return_value=report_payload
        ), patch("app.routes.api.public_integrations.get_report_template") as mock_template:
            resp = client.get("/api/v1/public/reports/country?country=Nowhereland&template_style=default")
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is False
        mock_template.assert_not_called()

    def test_unexpected_error_returns_500(self, client):
        with patch(
            "app.routes.api.public_integrations.build_country_report",
            side_effect=RuntimeError("boom"),
        ):
            resp = client.get("/api/v1/public/reports/country?country=Kenya")
        assert resp.status_code == 500


class TestPublicReportTemplateRoute:
    def test_defaults_to_default_style(self, client):
        payload = {"ok": True, "style": "default", "html_template": "<html></html>"}
        with patch(
            "app.routes.api.public_integrations.get_report_template", return_value=payload
        ) as mock_template:
            resp = client.get("/api/v1/public/reports/template")
        assert resp.status_code == 200
        assert resp.get_json()["style"] == "default"
        mock_template.assert_called_once_with("default")

    def test_passes_through_style_param(self, client):
        payload = {"ok": False, "error": "Unknown template style 'x'.", "available_styles": ["default"]}
        with patch(
            "app.routes.api.public_integrations.get_report_template", return_value=payload
        ) as mock_template:
            resp = client.get("/api/v1/public/reports/template?style=x")
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is False
        mock_template.assert_called_once_with("x")
