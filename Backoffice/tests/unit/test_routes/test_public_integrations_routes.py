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


class TestPublicErrorExposure:
    LEAK = "psycopg2.errors.SyntaxError at /srv/app/services/public/secret.py line 42"

    @pytest.mark.parametrize(
        "url,target,status",
        [
            ("/api/v1/public/global-trend", "aggregate_global_trend", 400),
            ("/api/v1/public/documents/1", "get_public_document_metadata", 404),
            ("/api/v1/public/documents/1/download", "stream_public_ai_document_download", 404),
            ("/api/v1/public/documents/chunks/1/context", "get_public_document_chunk_context", 404),
            ("/api/v1/public/reports/country?country=Kenya", "build_country_report", 400),
        ],
    )
    def test_incidental_value_error_is_not_echoed(self, client, url, target, status):
        with patch(f"app.routes.api.public_integrations.{target}", side_effect=ValueError(self.LEAK)):
            resp = client.get(url)
        assert resp.status_code == status
        body = resp.get_data(as_text=True)
        assert "secret.py" not in body and "psycopg2" not in body

    def test_client_input_error_message_is_preserved(self, client):
        from app.utils.api_errors import ClientInputError

        with patch(
            "app.routes.api.public_integrations.aggregate_global_trend",
            side_effect=ClientInputError("Provide template_id or indicator_bank_id"),
        ):
            resp = client.get("/api/v1/public/global-trend")
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "Provide template_id or indicator_bank_id"

    def test_search_unavailable_uses_stable_message(self, client):
        from app.services.public.document_service import PublicDocumentSearchUnavailable

        with patch(
            "app.routes.api.public_integrations.search_public_documents",
            side_effect=PublicDocumentSearchUnavailable("dsn=postgres://u:p@db/x failed"),
        ):
            resp = client.get("/api/v1/public/documents/search?query=flood")
        assert resp.status_code == 503
        assert "postgres://" not in resp.get_data(as_text=True)
