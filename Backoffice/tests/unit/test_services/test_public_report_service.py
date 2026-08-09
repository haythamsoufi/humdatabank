"""Tests for public_report_service (country report builder + design templates).

Mirrors humanitarian-databank-mcp/tests/test_databank_report.py, adapted for
in-process service calls: dependencies are patched at the
app.services.public.report_service module boundary (aggregate_submission_coverage,
fetch_public_scoped_rows, resolve_country_query, search_public_documents) instead
of an HTTP client, and headline KPI resolution is a direct IndicatorBank query
instead of a whole-catalog fetch.
"""

from unittest.mock import patch

import pytest

import app.services.public.report_service as public_report_service
from app.services.public.report_service import (
    FDRS_TEMPLATE_ID,
    _build_narrative,
    _build_trend,
    _extract_year,
    _fetch_kpi_series,
    _is_midyear_hint,
    build_country_report,
    get_report_template,
    list_report_styles,
    resolve_period_for_country,
)

pytestmark = [pytest.mark.unit]


@pytest.fixture(autouse=True)
def _reset_kpi_cache():
    """The fdrs_kpi_code -> id index is cached at module scope; keep tests isolated."""
    public_report_service._kpi_code_index_cache = None
    yield
    public_report_service._kpi_code_index_cache = None


class TestHintParsing:
    def test_extract_year_found(self):
        assert _extract_year("2026 midyear") == 2026

    def test_extract_year_missing(self):
        assert _extract_year("latest data please") is None

    @pytest.mark.parametrize(
        "text",
        ["2026 midyear", "Jan-Jun 2026", "H1 2026", "half-year review", "MYR 2025", "mid-year"],
    )
    def test_is_midyear_hint_true(self, text):
        assert _is_midyear_hint(text) is True

    @pytest.mark.parametrize("text", ["Annual 2024", "2026", ""])
    def test_is_midyear_hint_false(self, text):
        assert _is_midyear_hint(text) is False


class TestResolvePeriodForCountry:
    def test_no_public_data_at_all(self, app):
        with app.app_context():
            with patch(
                "app.services.public.report_service.aggregate_submission_coverage",
                return_value={"by_period": []},
            ):
                out = resolve_period_for_country(country_id=1, period_hint="2026 midyear")
        assert out["resolved_period"] is None
        assert "No public FDRS data" in out["match_note"]

    def test_exact_year_and_midyear_match(self, app):
        by_period = [
            {"period_name": "Annual 2024", "countries_submitted": 1},
            {"period_name": "Annual 2025", "countries_submitted": 1},
            {"period_name": "Jan-Jun 2026", "countries_submitted": 1},
        ]
        with app.app_context():
            with patch(
                "app.services.public.report_service.aggregate_submission_coverage",
                return_value={"by_period": by_period},
            ):
                out = resolve_period_for_country(country_id=1, period_hint="2026 midyear")
        assert out["resolved_period"] == "Jan-Jun 2026"
        assert out["prior_period"] == "Annual 2025"
        assert out["requested_year"] == 2026
        assert out["match_note"] is None

    def test_midyear_requested_falls_back_to_annual_with_note(self, app):
        by_period = [
            {"period_name": "Annual 2025", "countries_submitted": 1},
            {"period_name": "Annual 2026", "countries_submitted": 1},
        ]
        with app.app_context():
            with patch(
                "app.services.public.report_service.aggregate_submission_coverage",
                return_value={"by_period": by_period},
            ):
                out = resolve_period_for_country(country_id=1, period_hint="2026 midyear")
        assert out["resolved_period"] == "Annual 2026"
        assert "No dedicated mid-year period" in out["match_note"]

    def test_requested_year_not_available(self, app):
        by_period = [{"period_name": "Annual 2023", "countries_submitted": 1}]
        with app.app_context():
            with patch(
                "app.services.public.report_service.aggregate_submission_coverage",
                return_value={"by_period": by_period},
            ):
                out = resolve_period_for_country(country_id=1, period_hint="2026")
        assert out["resolved_period"] is None
        assert "No public FDRS data for 2026" in out["match_note"]

    def test_no_hint_picks_latest(self, app):
        by_period = [
            {"period_name": "Annual 2023", "countries_submitted": 1},
            {"period_name": "Annual 2024", "countries_submitted": 1},
        ]
        with app.app_context():
            with patch(
                "app.services.public.report_service.aggregate_submission_coverage",
                return_value={"by_period": by_period},
            ):
                out = resolve_period_for_country(country_id=1, period_hint="")
        assert out["resolved_period"] == "Annual 2024"
        assert out["prior_period"] == "Annual 2023"

    def test_coverage_error_is_non_fatal(self, app):
        with app.app_context():
            with patch(
                "app.services.public.report_service.aggregate_submission_coverage",
                side_effect=RuntimeError("boom"),
            ):
                out = resolve_period_for_country(country_id=1, period_hint="2026")
        assert out["resolved_period"] is None
        assert "Could not load submission coverage" in out["match_note"]


class TestHeadlineKpiResolution:
    def test_resolves_only_known_codes(self, app):
        rows = [("KPI_PeopleVol", 724), ("KPI_PStaff", 900)]
        with app.app_context():
            with patch("app.models.IndicatorBank.query") as mock_query:
                mock_query.filter.return_value.with_entities.return_value.all.return_value = rows
                out = public_report_service._resolve_headline_kpi_ids()
        assert out == {"KPI_PeopleVol": 724, "KPI_PStaff": 900}

    def test_caches_across_calls(self, app):
        with app.app_context():
            with patch("app.models.IndicatorBank.query") as mock_query:
                mock_query.filter.return_value.with_entities.return_value.all.return_value = [
                    ("KPI_PeopleVol", 724)
                ]
                public_report_service._resolve_headline_kpi_ids()
                public_report_service._resolve_headline_kpi_ids()
            assert mock_query.filter.call_count == 1

    def test_db_error_propagates(self, app):
        """Unlike the MCP tool's whole-catalog HTTP fetch, a DB failure here has no
        separate degraded state to fall back to — it surfaces as a route-level 500."""
        with app.app_context():
            with patch("app.models.IndicatorBank.query") as mock_query:
                mock_query.filter.side_effect = RuntimeError("db down")
                with pytest.raises(RuntimeError):
                    public_report_service._resolve_headline_kpi_ids()


class TestFetchKpiSeries:
    def test_dedupes_by_highest_submission_id_per_period(self, app):
        rows = [
            {"country_id": 1, "period_name": "Annual 2024", "data_status": "available", "num_value": 100, "submission_id": 1},
            {"country_id": 1, "period_name": "Annual 2024", "data_status": "available", "num_value": 150, "submission_id": 2},
            {"country_id": 1, "period_name": "Annual 2023", "data_status": "available", "value": "42", "submission_id": 1},
            {"country_id": 1, "period_name": "Annual 2022", "data_status": "not_applicable", "num_value": 5, "submission_id": 1},
        ]
        with app.app_context():
            with patch(
                "app.services.public.report_service.fetch_public_scoped_rows",
                return_value=(rows, False),
            ) as mock_fetch:
                values, truncated = _fetch_kpi_series(1, 724)
        assert values == {"Annual 2024": 150.0, "Annual 2023": 42.0}
        assert truncated is False
        call_kwargs = mock_fetch.call_args.kwargs
        assert call_kwargs["indicator_bank_id"] == 724
        assert call_kwargs["template_id"] == FDRS_TEMPLATE_ID
        assert call_kwargs["country_id"] == 1

    def test_error_returns_empty(self, app):
        with app.app_context():
            with patch(
                "app.services.public.report_service.fetch_public_scoped_rows",
                side_effect=RuntimeError("down"),
            ):
                values, truncated = _fetch_kpi_series(1, 724)
        assert values == {}
        assert truncated is False


class TestBuildTrend:
    def test_builds_sorted_series_from_shared_lookup(self):
        series_by_code = {"KPI_PeopleVol": ({"2024": 12.0, "2023": 8.0}, False)}
        out = _build_trend({"KPI_PeopleVol": 724}, series_by_code)
        assert out["included"] is True
        assert out["series"] == [
            {"period_name": "2023", "value": 8.0},
            {"period_name": "2024", "value": 12.0},
        ]

    def test_missing_indicator_id_not_included(self):
        out = _build_trend({}, {})
        assert out == {"included": False}


class TestBuildNarrative:
    def test_no_document_found_for_current_year_no_retry(self, app):
        import datetime as _dt

        current_year = _dt.datetime.now(_dt.timezone.utc).year
        with app.app_context():
            with patch(
                "app.services.public.report_service.search_public_documents",
                return_value={"chunks": []},
            ) as mock_search:
                out = _build_narrative(167, "Syria", current_year, True)
        assert out["included"] is False
        assert "Syria" in out["reason"]
        mock_search.assert_called_once()
        assert str(current_year) not in mock_search.call_args.args[0]

    def test_finds_document_on_first_snapshot_search(self, app):
        chunks = [
            {
                "content": "Focus on migration.",
                "document_title": "Syria 2026 Unified Plan",
                "page_number": 2,
                "document_url": "https://x/1",
            },
        ]
        with app.app_context():
            with patch(
                "app.services.public.report_service.search_public_documents",
                return_value={"chunks": chunks},
            ) as mock_search:
                out = _build_narrative(167, "Syria", 2026, True)
        assert out["included"] is True
        assert out["themes"][0]["document_title"] == "Syria 2026 Unified Plan"
        call_kwargs = mock_search.call_args.kwargs
        assert call_kwargs["country_id"] == 167
        assert "2026" not in mock_search.call_args.args[0]

    def test_historical_year_retries_with_year_in_query_when_snapshot_misses(self, app):
        with app.app_context():
            with patch(
                "app.services.public.report_service.search_public_documents",
                side_effect=[
                    {"chunks": []},
                    {"chunks": [{"content": "2019 highlights.", "document_title": "Syria 2019 Annual Report", "page_number": 1}]},
                ],
            ) as mock_search:
                out = _build_narrative(167, "Syria", 2019, False)
        assert out["included"] is True
        assert mock_search.call_count == 2
        assert "2019" in out["query_used"]

    def test_search_error_is_non_fatal(self, app):
        with app.app_context():
            with patch(
                "app.services.public.report_service.search_public_documents",
                side_effect=RuntimeError("down"),
            ):
                out = _build_narrative(167, "Syria", 2026, False)
        assert out["included"] is False
        assert "Document search failed" in out["reason"]


class TestBuildCountryReport:
    def test_unresolvable_country_returns_error_shape(self, app):
        with app.app_context():
            with patch(
                "app.services.public.report_service.resolve_country_query",
                return_value={"best_match": None, "alternatives": [{"name": "Syrian Arab Republic"}]},
            ):
                out = build_country_report(country="Syriaaa")
        assert out["ok"] is False
        assert "alternatives" in out

    def test_happy_path_combined_report(self, app):
        country_payload = {
            "best_match": {"id": 1, "name": "Syria", "iso2": "SY", "iso3": "SYR", "region": "MENA"},
            "alternatives": [],
        }
        coverage_payload = {
            "by_period": [
                {"period_name": "Annual 2025", "countries_submitted": 1},
                {"period_name": "Jan-Jun 2026", "countries_submitted": 1},
            ]
        }
        # Only one headline KPI resolves in this test, so _fetch_all_kpi_series makes
        # exactly one scoped fetch (shared by headline_kpis and trend).
        kpi_rows = [
            {"country_id": 1, "period_name": "Annual 2025", "data_status": "available", "num_value": 180, "submission_id": 1},
            {"country_id": 1, "period_name": "Jan-Jun 2026", "data_status": "available", "num_value": 200, "submission_id": 1},
        ]
        search_payload = {
            "chunks": [
                {"content": "Migration response scaled up.", "document_title": "Syria MYR 2026", "page_number": 3, "document_url": None}
            ]
        }

        with app.app_context():
            with patch(
                "app.services.public.report_service.resolve_country_query", return_value=country_payload
            ), patch(
                "app.services.public.report_service.aggregate_submission_coverage", return_value=coverage_payload
            ), patch(
                "app.services.public.report_service._resolve_headline_kpi_ids",
                return_value={"KPI_PeopleVol": 724},
            ), patch(
                "app.services.public.report_service.fetch_public_scoped_rows",
                return_value=(kpi_rows, False),
            ) as mock_fetch, patch(
                "app.services.public.report_service.search_public_documents", return_value=search_payload
            ):
                out = build_country_report(country="Syria", period_hint="2026 midyear")

        assert mock_fetch.call_count == 1
        assert out["ok"] is True
        assert out["country"]["iso3"] == "SYR"
        assert out["period"]["resolved"] == "Jan-Jun 2026"
        assert out["period"]["prior"] == "Annual 2025"
        assert out["headline_kpis"][0]["value"] == 200
        assert out["headline_kpis"][0]["prior_value"] == 180
        assert out["headline_kpis"][0]["change_pct"] == pytest.approx(11.1, abs=0.1)
        assert out["trend"]["included"] is True
        assert out["narrative"]["included"] is True
        assert out["coverage"]["fdrs_data_available"] is True
        assert out["coverage"]["narrative_available"] is True

    def test_fdrs_only_skips_narrative(self, app):
        country_payload = {"best_match": {"id": 1, "name": "Kenya", "iso3": "KEN"}, "alternatives": []}
        with app.app_context():
            with patch(
                "app.services.public.report_service.resolve_country_query", return_value=country_payload
            ), patch(
                "app.services.public.report_service.aggregate_submission_coverage", return_value={"by_period": []}
            ), patch(
                "app.services.public.report_service.search_public_documents"
            ) as mock_search:
                out = build_country_report(country="Kenya", report_type="fdrs")
        assert out["narrative"] == {"included": False}
        mock_search.assert_not_called()

    def test_upr_only_skips_headline_kpis(self, app):
        country_payload = {"best_match": {"id": 1, "name": "Kenya", "iso3": "KEN"}, "alternatives": []}
        with app.app_context():
            with patch(
                "app.services.public.report_service.resolve_country_query", return_value=country_payload
            ), patch(
                "app.services.public.report_service.aggregate_submission_coverage"
            ) as mock_coverage, patch(
                "app.services.public.report_service.search_public_documents", return_value={"chunks": []}
            ):
                out = build_country_report(country="Kenya", report_type="upr")
        assert out["headline_kpis"] == []
        assert out["trend"] == {"included": False}
        mock_coverage.assert_not_called()


class TestReportTemplates:
    def test_list_report_styles_includes_default(self):
        assert "default" in list_report_styles()

    def test_get_default_template(self):
        out = get_report_template("default")
        assert out["ok"] is True
        assert "{{COUNTRY_NAME}}" in out["html_template"]
        assert out["design_tokens"]["colors"]["primary"]
        assert "default" in out["available_styles"]

    def test_unknown_style_lists_available(self):
        out = get_report_template("does-not-exist")
        assert out["ok"] is False
        assert "default" in out["available_styles"]

    def test_defaults_to_default_style(self):
        out = get_report_template("")
        assert out["ok"] is True
        assert out["style"] == "default"
