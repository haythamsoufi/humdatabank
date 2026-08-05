"""Tests for databank_analytics."""

from unittest.mock import patch

from databank_analytics import search_indicators_ranked, slim_public_data_response


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


class TestSearchIndicatorsRanked:
    def test_limits_and_ranks(self):
        indicators = [
            {
                "id": 1,
                "name": "Number of volunteers covered by accident insurance.",
                "type": "number",
                "unit": "volunteers",
                "tags": ["FDRS"],
            },
            {
                "id": 724,
                "name": "Number of people volunteering.",
                "type": "number",
                "unit": "volunteers",
                "fdrs_kpi_code": "KPI_PeopleVol",
                "tags": ["FDRS"],
            },
        ]
        with patch("databank_analytics.search_indicators") as mock_search:
            mock_search.return_value = {"indicators": indicators, "count": 2}
            out = search_indicators_ranked(search="volunteers", limit=1)
        assert out["count"] == 1
        assert out["total_matches"] == 2
        assert out["indicators"][0]["id"] == 724
