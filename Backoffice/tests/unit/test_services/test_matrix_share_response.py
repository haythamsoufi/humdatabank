"""Tests for matrix share summary and table payload inference."""

from app.services.ai.planning.payload_inference import infer_payloads
from app.services.ai.planning.query_intent_helpers import build_matrix_share_text_response


_SAMPLE_PAYLOAD = {
    "success": True,
    "count": 2,
    "countries_with_data": 187,
    "field_label_resolved": "Income Sources",
    "template_name": "FDRS",
    "min_share_pct": 75,
    "matrix_share_rows": ["Home Government", "Foreign Government"],
    "denominator_kpi_code": "KPI_IncomeLC_CHF",
    "organization_name": "IFRC",
    "rows": [
        {
            "country_name": "Alpha",
            "iso3": "ALP",
            "region": "Europe & CA",
            "period_used": "2024",
            "share_denominator": 1000,
            "home_government_pct": 80.0,
            "foreign_government_pct": 5.0,
            "matching_sources": ["Home Government"],
            "max_share_pct": 80.0,
            "share_breakdown": {
                "Home Government": {"amount": 800, "share_pct": 80.0},
                "Foreign Government": {"amount": 50, "share_pct": 5.0},
            },
        },
        {
            "country_name": "Beta",
            "iso3": "BET",
            "region": "Africa",
            "period_used": "2023",
            "share_denominator": 500,
            "home_government_pct": 90.0,
            "foreign_government_pct": 0.0,
            "matching_sources": ["Home Government"],
            "max_share_pct": 90.0,
            "share_breakdown": {
                "Home Government": {"amount": 450, "share_pct": 90.0},
                "Foreign Government": {"amount": 0, "share_pct": 0.0},
            },
        },
    ],
}


class TestMatrixShareTextResponse:
    def test_build_matrix_share_text_response_is_concise(self):
        text = build_matrix_share_text_response(_SAMPLE_PAYLOAD)
        assert "**2** National Societies" in text
        assert "**187**" in text
        assert "Home Government" in text
        assert "Top 5" not in text
        assert "Bottom 5" not in text
        assert "## Sources" in text
        assert "IFRC" in text

    def test_infer_payloads_builds_matrix_share_table(self):
        steps = [
            {
                "action": "get_form_field_values_for_all_countries",
                "observation": {"result": _SAMPLE_PAYLOAD},
            }
        ]
        payloads = infer_payloads(steps, query="FDRS income sources >75%")
        table = payloads.get("table_payload") or {}
        assert table.get("table_kind") == "matrix_share"
        assert len(table.get("rows") or []) == 2
        assert payloads.get("output_hint") == "table"
