"""Unit tests for matrix share analysis helpers."""

from app.services.data_retrieval.form_helpers import (
    amount_from_breakdown,
    apply_matrix_share_analysis,
    matrix_breakdown_sum,
)


class TestMatrixShareHelpers:
    def test_amount_from_breakdown_row_column(self):
        breakdown = {
            "Home Government_Funding": 750.0,
            "Foreign Government_Funding": 250.0,
            "Individuals_Funding": 100.0,
        }
        assert amount_from_breakdown(breakdown, "Home Government", "Funding") == 750.0
        assert amount_from_breakdown(breakdown, "Foreign Government", "Funding") == 250.0

    def test_matrix_breakdown_sum_ignores_underscore_keys(self):
        breakdown = {
            "_meta": 999.0,
            "Home Government_Funding": 100.0,
            "Foreign Government_Funding": 200.0,
        }
        assert matrix_breakdown_sum(breakdown) == 300.0

    def test_apply_matrix_share_analysis_enriches_and_filters(self):
        rows = [
            {
                "country_name": "Alpha",
                "breakdown": {
                    "Home Government_Funding": 800.0,
                    "Foreign Government_Funding": 200.0,
                },
            },
            {
                "country_name": "Beta",
                "breakdown": {
                    "Home Government_Funding": 100.0,
                    "Foreign Government_Funding": 900.0,
                },
            },
        ]
        enriched = apply_matrix_share_analysis(
            rows,
            matrix_share_rows=["Home Government", "Foreign Government"],
            matrix_share_column="Funding",
            min_share_pct=75.0,
            share_match="any",
        )
        assert len(enriched) == 2
        names = {r["country_name"] for r in enriched}
        assert names == {"Alpha", "Beta"}
        alpha = next(r for r in enriched if r["country_name"] == "Alpha")
        assert alpha["share_breakdown"]["Home Government"]["share_pct"] == 80.0
        assert alpha["share_denominator"] == 1000.0
        assert alpha["share_denominator_source"] == "matrix_sum"

    def test_apply_matrix_share_analysis_uses_kpi_denominator(self):
        rows = [
            {
                "country_name": "Gamma",
                "submission_id": 42,
                "breakdown": {"Home Government_Funding": 400.0, "Foreign Government_Funding": 100.0},
            },
        ]
        enriched = apply_matrix_share_analysis(
            rows,
            matrix_share_rows=["Home Government", "Foreign Government"],
            matrix_share_column="Funding",
            denominator_by_submission={42: 2000.0},
        )
        assert enriched[0]["share_breakdown"]["Home Government"]["share_pct"] == 20.0
        assert enriched[0]["share_denominator_source"] == "kpi"

    def test_apply_matrix_share_analysis_share_match_all(self):
        rows = [
            {
                "country_name": "Delta",
                "breakdown": {
                    "Home Government_Funding": 450.0,
                    "Foreign Government_Funding": 450.0,
                    "Individuals_Funding": 100.0,
                },
            },
            {
                "country_name": "Epsilon",
                "breakdown": {
                    "Home Government_Funding": 450.0,
                    "Foreign Government_Funding": 100.0,
                    "Individuals_Funding": 450.0,
                },
            },
        ]
        filtered = apply_matrix_share_analysis(
            rows,
            matrix_share_rows=["Home Government", "Foreign Government"],
            matrix_share_column="Funding",
            min_share_pct=40.0,
            share_match="all",
        )
        assert len(filtered) == 1
        assert filtered[0]["country_name"] == "Delta"
