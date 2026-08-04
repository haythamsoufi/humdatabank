"""Tests for databank_analytics."""

from unittest.mock import patch

import pytest

from databank_analytics import (
    aggregate_global_trend,
    dedupe_rows,
    parse_num_value,
    resolve_indicator,
    search_indicators_ranked,
    slim_public_data_response,
)


class TestParseNumValue:
    def test_num_value(self):
        assert parse_num_value({"num_value": 42.0}) == 42.0

    def test_string_value(self):
        assert parse_num_value({"value": "1,234"}) == 1234.0


class TestDedupeRows:
    def test_keeps_latest_submission(self):
        rows = [
            {
                "country_id": 1,
                "period_name": "2024",
                "submission_id": 10,
                "data_status": "available",
                "num_value": 100,
            },
            {
                "country_id": 1,
                "period_name": "2024",
                "submission_id": 20,
                "data_status": "available",
                "num_value": 200,
            },
            {
                "country_id": 2,
                "period_name": "2024",
                "submission_id": 5,
                "data_status": "available",
                "num_value": 50,
            },
        ]
        out = dedupe_rows(rows)
        assert len(out) == 2
        by_country = {r["country_id"]: r["num_value"] for r in out}
        assert by_country[1] == 200
        assert by_country[2] == 50

    def test_skips_non_available(self):
        rows = [
            {"country_id": 1, "period_name": "2024", "submission_id": 1, "data_status": "missing"},
        ]
        assert dedupe_rows(rows) == []


class TestSlimPublicData:
    def test_strips_dimensions_by_default(self):
        payload = {
            "data": [{"id": 1}],
            "countries": [{"id": 1, "name": "X"}],
            "indicator_bank": [{"id": 1}],
            "total_items": 1,
        }
        slim = slim_public_data_response(payload)
        assert "data" in slim
        assert "total_items" in slim
        assert "countries" not in slim
        assert "indicator_bank" not in slim


class TestResolveIndicator:
    def test_numeric_id(self):
        with patch("databank_analytics.get_indicator") as mock_get:
            mock_get.return_value = {
                "id": 724,
                "name": "Number of people volunteering.",
                "type": "number",
                "unit": "volunteers",
                "fdrs_kpi_code": "KPI_PeopleVol",
                "tags": ["FDRS"],
            }
            out = resolve_indicator("724")
        assert out["best_match"]["id"] == 724
        assert out["best_match"]["confidence"] == 1.0

    def test_canonical_volunteers_alias(self):
        with patch("databank_analytics.get_indicator") as mock_get:
            mock_get.return_value = {
                "id": 724,
                "name": "Number of people volunteering.",
                "type": "number",
                "unit": "volunteers",
                "fdrs_kpi_code": "KPI_PeopleVol",
                "tags": ["FDRS"],
            }
            out = resolve_indicator("total volunteers")
        assert out["canonical_metric"] == "volunteers"
        assert out["best_match"]["id"] == 724
        assert out["best_match"]["match_reason"] == "canonical_alias"


class TestSearchIndicatorsRanked:
    def test_limits_and_ranks(self):
        indicators = [
            {"id": 1, "name": "Number of volunteers covered by accident insurance.", "type": "number", "unit": "volunteers", "tags": ["FDRS"]},
            {"id": 724, "name": "Number of people volunteering.", "type": "number", "unit": "volunteers", "fdrs_kpi_code": "KPI_PeopleVol", "tags": ["FDRS"]},
        ]
        with patch("databank_analytics.search_indicators") as mock_search:
            mock_search.return_value = {"indicators": indicators, "count": 2}
            out = search_indicators_ranked(search="volunteers", limit=1)
        assert out["count"] == 1
        assert out["total_matches"] == 2
        assert out["indicators"][0]["id"] == 724


class TestAggregateGlobalTrend:
    def test_aggregates_by_period(self):
        raw = {
            "data": [
                {"country_id": 1, "period_name": "2023", "submission_id": 1, "data_status": "available", "num_value": 100},
                {"country_id": 1, "period_name": "2023", "submission_id": 2, "data_status": "available", "num_value": 999},
                {"country_id": 2, "period_name": "2023", "submission_id": 1, "data_status": "available", "num_value": 50},
                {"country_id": 1, "period_name": "2024", "submission_id": 1, "data_status": "available", "num_value": 120},
            ],
            "truncated": False,
        }
        with patch("databank_analytics.get_indicator") as mock_ind, patch(
            "databank_analytics.get_public_data_all_pages"
        ) as mock_data:
            mock_ind.return_value = {"id": 724, "name": "Number of people volunteering.", "type": "number", "unit": "volunteers"}
            mock_data.return_value = raw
            out = aggregate_global_trend(indicator_bank_id=724)
        assert out["rows_after_dedupe"] == 3
        by_period = {p["period_name"]: p for p in out["by_period"]}
        assert by_period["2023"]["total"] == 1049  # 999 + 50 after dedupe
        assert by_period["2023"]["countries_reporting"] == 2
        assert by_period["2024"]["total"] == 120

    def test_query_resolution(self):
        with patch("databank_analytics.resolve_indicator") as mock_resolve, patch(
            "databank_analytics.get_public_data_all_pages"
        ) as mock_data:
            mock_resolve.return_value = {
                "best_match": {"id": 724, "name": "Number of people volunteering.", "confidence": 1.0},
            }
            mock_data.return_value = {"data": [], "truncated": False}
            out = aggregate_global_trend(query="volunteers")
        assert out["indicator_bank_id"] == 724
        mock_resolve.assert_called_once()
