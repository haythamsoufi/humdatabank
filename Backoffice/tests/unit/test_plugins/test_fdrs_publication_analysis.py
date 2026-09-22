"""Unit tests for FDRS publication analysis (variations / outliers)."""
from __future__ import annotations

import pytest

from plugins.fdrs.services.fdrs_publication_analysis import (
    REASON_CLEARED,
    REASON_FROM_ZERO,
    REASON_GLOBAL_IMPACT,
    REASON_GLOBAL_SHARE,
    REASON_LARGE_VARIATION,
    REASON_OUTLIER,
    analyze_publication_rows,
    coerce_numeric,
    iqr_outlier_mask,
    relative_change,
    variation_severity,
)

pytestmark = [pytest.mark.unit]


class TestCoerceNumeric:
    def test_none_and_blank(self):
        assert coerce_numeric(None) is None
        assert coerce_numeric("") is None
        assert coerce_numeric("  ") is None

    def test_bool_is_not_numeric(self):
        assert coerce_numeric(True) is None

    def test_int_float_and_string(self):
        assert coerce_numeric(10) == 10.0
        assert coerce_numeric(2.5) == 2.5
        assert coerce_numeric("1,200") == 1200.0

    def test_non_numeric_string(self):
        assert coerce_numeric("n/a") is None


class TestRelativeChangeAndSeverity:
    def test_doubling_is_high(self):
        assert relative_change(20, 10) == 1.0
        assert variation_severity(1.0) == "high"

    def test_fifty_percent_is_medium(self):
        assert variation_severity(0.5) == "medium"
        assert variation_severity(-0.5) == "medium"

    def test_small_change_is_ignored(self):
        assert variation_severity(0.33) is None

    def test_zero_baseline_is_undefined(self):
        assert relative_change(12, 0) is None


class TestIqrOutlierMask:
    def test_too_few_peers(self):
        assert iqr_outlier_mask([0.1, 0.2, 5.0]) == [False, False, False]

    def test_extreme_peer_is_flagged(self):
        peers = [0.05, 0.08, 0.09, 0.10, 0.11, 0.12, 0.13, 5.0]
        mask = iqr_outlier_mask(peers)
        assert mask[-1] is True
        assert mask.count(True) == 1

    def test_identical_values_are_not_outliers(self):
        assert iqr_outlier_mask([0.1] * 8) == [False] * 8


def _row(**overrides):
    base = {
        "assignment_entity_status_id": 1,
        "country_id": 10,
        "country_name": "Alpha",
        "country_iso3": "ALP",
        "form_item_id": 100,
        "label": "Volunteers",
        "kind": "changed",
        "current_value": "20",
        "published_value": "15",
        "current_numeric": 20,
        "published_numeric": 15,
    }
    base.update(overrides)
    return base


class TestAnalyzePublicationRows:
    def test_small_change_not_flagged(self):
        result = analyze_publication_rows([_row()])
        assert result["flag_count"] == 0

    def test_large_change_flagged(self):
        result = analyze_publication_rows([_row(current_numeric=40, current_value="40")])
        assert result["flag_count"] == 1
        assert result["flags"][0]["severity"] == "high"
        assert result["flags"][0]["reasons"][0]["code"] == REASON_LARGE_VARIATION

    def test_removed_is_always_flagged(self):
        result = analyze_publication_rows([
            _row(kind="removed", current_value=None, current_numeric=None, published_numeric=99),
        ])
        assert result["flag_count"] == 1
        assert result["flags"][0]["reasons"][0]["code"] == REASON_CLEARED

    def test_from_zero_is_high(self):
        result = analyze_publication_rows([
            _row(current_numeric=50, published_numeric=0, published_value="0"),
        ])
        assert result["flags"][0]["severity"] == "high"
        assert any(r["code"] == REASON_FROM_ZERO for r in result["flags"][0]["reasons"])

    def test_source_and_unchanged_without_prior_or_global_not_flagged(self):
        result = analyze_publication_rows([
            _row(kind="source"),
            _row(kind="unchanged", assignment_entity_status_id=2),
        ])
        assert result["flag_count"] == 0

    def test_unchanged_published_value_flagged_vs_prior_period(self):
        result = analyze_publication_rows(
            [_row(
                kind="unchanged",
                current_numeric=40,
                current_value="40",
                published_numeric=40,
                published_value="40",
            )],
            prior_numeric_by_key={(10, 100): 10.0},
            prior_period_name="2023",
        )
        assert result["flag_count"] == 1
        assert any(
            r["code"] == REASON_LARGE_VARIATION and r["vs"] == "prior"
            for r in result["flags"][0]["reasons"]
        )
        assert not any(r.get("vs") == "published" for r in result["flags"][0]["reasons"])

    def test_unchanged_published_major_global_share_is_flagged(self):
        result = analyze_publication_rows(
            [_row(
                kind="unchanged",
                country_name="India",
                current_numeric=4_000_000,
                current_value="4000000",
                published_numeric=4_000_000,
                published_value="4000000",
            )],
            global_totals_by_item={100: 18_000_000},
            global_reporters_by_item={100: 12},
        )
        assert result["flag_count"] == 1
        assert any(r["code"] == REASON_GLOBAL_SHARE for r in result["flags"][0]["reasons"])

    def test_prior_period_variation(self):
        result = analyze_publication_rows(
            [_row(kind="new", published_value=None, published_numeric=None, current_numeric=30)],
            prior_numeric_by_key={(10, 100): 10.0},
            prior_period_name="2023",
        )
        assert result["prior_period_name"] == "2023"
        assert result["flag_count"] == 1
        assert any(
            r["code"] == REASON_LARGE_VARIATION and r["vs"] == "prior"
            for r in result["flags"][0]["reasons"]
        )

    def test_peer_outlier_without_large_variation(self):
        # 5–13% swings stay under the 50% variation cut; 40% is an IQR outlier.
        currents = [105, 108, 109, 110, 111, 112, 113, 140]
        rows = [
            _row(
                assignment_entity_status_id=i + 1,
                country_id=i + 1,
                country_name=f"C{i}",
                form_item_id=100,
                published_numeric=100,
                current_numeric=current,
                current_value=str(current),
                published_value="100",
            )
            for i, current in enumerate(currents)
        ]
        result = analyze_publication_rows(rows)
        outlier_flags = [f for f in result["flags"] if any(r["code"] == REASON_OUTLIER for r in f["reasons"])]
        assert len(outlier_flags) == 1
        assert outlier_flags[0]["country_id"] == 8
        assert not any(r["code"] == REASON_LARGE_VARIATION for r in outlier_flags[0]["reasons"])

    def test_major_global_contributor_is_flagged_even_for_small_change(self):
        # India-style: 4M of 18M (~22%) with only a 5% figure change.
        result = analyze_publication_rows(
            [_row(
                country_name="India",
                current_numeric=4_000_000,
                current_value="4000000",
                published_numeric=3_800_000,
                published_value="3800000",
            )],
            global_totals_by_item={100: 18_000_000},
            global_reporters_by_item={100: 12},
        )
        assert result["flag_count"] == 1
        assert result["flags"][0]["severity"] == "high"
        share = next(r for r in result["flags"][0]["reasons"] if r["code"] == REASON_GLOBAL_SHARE)
        assert share["share"] == pytest.approx(4_000_000 / 18_000_000)
        assert not any(r["code"] == REASON_LARGE_VARIATION for r in result["flags"][0]["reasons"])

    def test_small_share_of_global_total_is_not_flagged(self):
        result = analyze_publication_rows(
            [_row(current_numeric=50_000, published_numeric=48_000)],
            global_totals_by_item={100: 18_000_000},
            global_reporters_by_item={100: 12},
        )
        assert result["flag_count"] == 0

    def test_global_share_requires_enough_reporting_countries(self):
        result = analyze_publication_rows(
            [_row(current_numeric=4_000_000, published_numeric=3_800_000)],
            global_totals_by_item={100: 18_000_000},
            global_reporters_by_item={100: 3},
        )
        assert result["flag_count"] == 0

    def test_change_that_moves_the_global_total_is_flagged(self):
        # Small share after the change, but the jump itself is 8% of the world total.
        result = analyze_publication_rows(
            [_row(
                current_numeric=1_600_000,
                current_value="1600000",
                published_numeric=400_000,
                published_value="400000",
            )],
            global_totals_by_item={100: 18_000_000},
            global_reporters_by_item={100: 12},
        )
        assert any(r["code"] == REASON_GLOBAL_IMPACT for r in result["flags"][0]["reasons"])
        impact = next(r for r in result["flags"][0]["reasons"] if r["code"] == REASON_GLOBAL_IMPACT)
        assert impact["pct"] == pytest.approx(1_200_000 / 18_000_000)
