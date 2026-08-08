"""Tests for humanitarian-databank-mcp."""

import json
from unittest.mock import MagicMock, patch

import pytest

from databank_client import (
    DatabankAPIError,
    get_country_report,
    get_public_data_page,
    get_public_document,
    get_public_documents_catalog,
    get_public_global_trend,
    get_report_template,
    get_submission_coverage,
    resolve_public_country,
    resolve_public_indicator,
    search_indicators,
    search_public_documents,
)


class TestSearchIndicators:
    def test_parses_indicator_list(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"indicators": [{"id": 1, "name": "Test"}]}

        with patch("databank_client.httpx.Client") as client_cls:
            client_cls.return_value.__enter__.return_value.get.return_value = mock_resp
            out = search_indicators(search="volunteers")

        assert out["count"] == 1
        assert out["indicators"][0]["id"] == 1


class TestPublicData:
    def test_requires_scope_filter(self):
        with pytest.raises(DatabankAPIError, match="scope filter"):
            get_public_data_page()

    def test_builds_query(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": [], "total_items": 0}

        with patch("databank_client.httpx.Client") as client_cls:
            mock_get = client_cls.return_value.__enter__.return_value.get
            mock_get.return_value = mock_resp
            get_public_data_page(indicator_bank_id=42, page=1, per_page=100)
            call_kwargs = mock_get.call_args
            assert "/data" in call_kwargs[0][0]
            assert call_kwargs[1]["params"]["indicator_bank_id"] == 42


class TestPublicGlobalTrend:
    def test_calls_public_endpoint(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"by_period": []}

        with patch("databank_client.httpx.Client") as client_cls:
            mock_get = client_cls.return_value.__enter__.return_value.get
            mock_get.return_value = mock_resp
            get_public_global_trend(query="volunteers")
            assert "/public/global-trend" in mock_get.call_args[0][0]
            assert mock_get.call_args[1]["params"]["query"] == "volunteers"

    def test_requires_query_or_id(self):
        with pytest.raises(DatabankAPIError, match="indicator_bank_id or query"):
            get_public_global_trend()


class TestResolvePublicIndicator:
    def test_calls_public_endpoint(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"best_match": {"id": 724}}

        with patch("databank_client.httpx.Client") as client_cls:
            mock_get = client_cls.return_value.__enter__.return_value.get
            mock_get.return_value = mock_resp
            out = resolve_public_indicator("volunteers")
            assert "/public/indicators/resolve" in mock_get.call_args[0][0]
            assert out["best_match"]["id"] == 724


class TestSearchPublicDocuments:
    def test_calls_public_endpoint(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"chunks": [], "count": 0}

        with patch("databank_client.httpx.Client") as client_cls:
            mock_get = client_cls.return_value.__enter__.return_value.get
            mock_get.return_value = mock_resp
            search_public_documents("Syria unified plan 2026", full_coverage=True)
            assert "/public/documents/search" in mock_get.call_args[0][0]
            params = mock_get.call_args[1]["params"]
            assert params["query"] == "Syria unified plan 2026"
            assert params["full_coverage"] == "true"

    def test_requires_query(self):
        with pytest.raises(DatabankAPIError, match="query is required"):
            search_public_documents("  ")


class TestGetPublicDocument:
    def test_calls_public_endpoint_with_id(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": 42, "title": "Kenya Annual Report 2024"}

        with patch("databank_client.httpx.Client") as client_cls:
            mock_get = client_cls.return_value.__enter__.return_value.get
            mock_get.return_value = mock_resp
            out = get_public_document(42)
            assert "/public/documents/42" in mock_get.call_args[0][0]
            assert out["id"] == 42

    def test_raises_on_404(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "Not found"

        with patch("databank_client.httpx.Client") as client_cls:
            client_cls.return_value.__enter__.return_value.get.return_value = mock_resp
            with pytest.raises(DatabankAPIError, match="HTTP 404"):
                get_public_document(999999)


class TestGetPublicDocumentsCatalog:
    def test_default_call_sets_include_documents_false(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"total_documents": 0}

        with patch("databank_client.httpx.Client") as client_cls:
            mock_get = client_cls.return_value.__enter__.return_value.get
            mock_get.return_value = mock_resp
            get_public_documents_catalog()
            assert "/public/documents/catalog" in mock_get.call_args[0][0]
            params = mock_get.call_args[1]["params"]
            assert params["include_documents"] == "false"
            # Optional filters are omitted entirely when unset.
            assert "document_type" not in params
            assert "year" not in params
            assert "country_id" not in params

    def test_passes_all_filters(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"total_documents": 1}

        with patch("databank_client.httpx.Client") as client_cls:
            mock_get = client_cls.return_value.__enter__.return_value.get
            mock_get.return_value = mock_resp
            get_public_documents_catalog(
                document_type="annual_report",
                year=2024,
                country_id=1,
                country_name="Kenya",
                file_type="pdf",
                include_documents=False,
            )
            params = mock_get.call_args[1]["params"]
            assert params["document_type"] == "annual_report"
            assert params["year"] == 2024
            assert params["country_id"] == 1
            assert params["country_name"] == "Kenya"
            assert params["file_type"] == "pdf"
            assert params["include_documents"] == "false"


class TestGetSubmissionCoverage:
    def test_requires_a_scope(self):
        with pytest.raises(DatabankAPIError, match="template_id, indicator_bank_id, or query"):
            get_submission_coverage()

    def test_calls_public_endpoint_with_template_id(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"countries_submitted_total": 10}

        with patch("databank_client.httpx.Client") as client_cls:
            mock_get = client_cls.return_value.__enter__.return_value.get
            mock_get.return_value = mock_resp
            out = get_submission_coverage(template_id=21, period_name="Annual 2024")
            assert "/public/submissions/coverage" in mock_get.call_args[0][0]
            params = mock_get.call_args[1]["params"]
            assert params["template_id"] == 21
            assert params["period_name"] == "Annual 2024"
            assert out["countries_submitted_total"] == 10

    def test_accepts_query_instead_of_ids(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"countries_submitted_total": 5}

        with patch("databank_client.httpx.Client") as client_cls:
            mock_get = client_cls.return_value.__enter__.return_value.get
            mock_get.return_value = mock_resp
            get_submission_coverage(query="volunteers")
            params = mock_get.call_args[1]["params"]
            assert params["query"] == "volunteers"
            assert "template_id" not in params
            assert "indicator_bank_id" not in params


class TestResolvePublicCountry:
    def test_requires_query(self):
        with pytest.raises(DatabankAPIError, match="query is required"):
            resolve_public_country("   ")

    def test_calls_public_endpoint(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"best_match": {"id": 1, "iso3": "KEN"}}

        with patch("databank_client.httpx.Client") as client_cls:
            mock_get = client_cls.return_value.__enter__.return_value.get
            mock_get.return_value = mock_resp
            out = resolve_public_country("Kenya", limit=3)
            assert "/public/countries/resolve" in mock_get.call_args[0][0]
            params = mock_get.call_args[1]["params"]
            assert params["query"] == "Kenya"
            assert params["limit"] == 3
            assert out["best_match"]["iso3"] == "KEN"

    def test_limit_is_capped_at_20(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"best_match": None}

        with patch("databank_client.httpx.Client") as client_cls:
            mock_get = client_cls.return_value.__enter__.return_value.get
            mock_get.return_value = mock_resp
            resolve_public_country("Kenya", limit=100)
            assert mock_get.call_args[1]["params"]["limit"] == 20


class TestGetCountryReport:
    def test_requires_country(self):
        with pytest.raises(DatabankAPIError, match="country is required"):
            get_country_report("   ")

    def test_calls_public_endpoint_with_defaults(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True, "country": {"id": 1, "name": "Syria"}}

        with patch("databank_client.httpx.Client") as client_cls:
            mock_get = client_cls.return_value.__enter__.return_value.get
            mock_get.return_value = mock_resp
            out = get_country_report("Syria")
            assert "/public/reports/country" in mock_get.call_args[0][0]
            params = mock_get.call_args[1]["params"]
            assert params["country"] == "Syria"
            assert params["report_type"] == "combined"
            assert params["include_prior_period"] == "true"
            assert "period_hint" not in params
            assert "template_style" not in params
            assert out["country"]["name"] == "Syria"

    def test_passes_optional_params(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True}

        with patch("databank_client.httpx.Client") as client_cls:
            mock_get = client_cls.return_value.__enter__.return_value.get
            mock_get.return_value = mock_resp
            get_country_report(
                "Syria",
                period_hint="2026 midyear",
                report_type="fdrs",
                include_prior_period=False,
                template_style="default",
            )
            params = mock_get.call_args[1]["params"]
            assert params["period_hint"] == "2026 midyear"
            assert params["report_type"] == "fdrs"
            assert params["include_prior_period"] == "false"
            assert params["template_style"] == "default"


class TestGetReportTemplate:
    def test_calls_public_endpoint_with_default_style(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True, "style": "default"}

        with patch("databank_client.httpx.Client") as client_cls:
            mock_get = client_cls.return_value.__enter__.return_value.get
            mock_get.return_value = mock_resp
            out = get_report_template()
            assert "/public/reports/template" in mock_get.call_args[0][0]
            assert mock_get.call_args[1]["params"]["style"] == "default"
            assert out["style"] == "default"

    def test_passes_custom_style(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": False, "available_styles": ["default"]}

        with patch("databank_client.httpx.Client") as client_cls:
            mock_get = client_cls.return_value.__enter__.return_value.get
            mock_get.return_value = mock_resp
            get_report_template("fancy")
            assert mock_get.call_args[1]["params"]["style"] == "fancy"
