"""Unit tests for UPR import warning summarization."""

import sys
from pathlib import Path

imports_dir = Path(__file__).resolve().parents[2] / "scripts" / "imports"
if str(imports_dir) not in sys.path:
    sys.path.insert(0, str(imports_dir))

from upr_import_warnings import summarize_warnings  # noqa: E402


class TestSummarizeWarnings:
    def test_groups_missing_reporting_item_by_area_across_countries_and_banks(self):
        warnings = [
            "No reporting-country form item for bank 592 area 'SP1' (AFG AR25)",
            "No reporting-country form item for bank 307 area 'SP1' (AFG AR25)",
            "No reporting-country form item for bank 592 area 'SP1' (AFG MYR25)",
            "No reporting-country form item for bank 592 area 'SP1' (ALB AR25)",
        ]
        result = summarize_warnings(warnings)
        assert result["warning_count"] == 4
        assert result["warning_unique_count"] == 1
        line = result["warnings"][0]
        assert line.startswith("No reporting-country form item for area 'SP1'")
        assert "×4" in line
        assert "2 countries" in line
        assert "2 indicators" in line
        assert "AR25" in line
        assert "MYR25" in line
        assert "1 country" not in line

    def test_keeps_distinct_areas_separate(self):
        warnings = [
            "No reporting-country form item for bank 592 area 'SP1' (AFG AR25)",
            "No reporting-country form item for bank 638 area 'SP5' (AFG AR25)",
        ]
        result = summarize_warnings(warnings)
        assert result["warning_unique_count"] == 2

    def test_single_occurrence_shows_round_not_one_country(self):
        warnings = [
            "No reporting-country form item for bank 878 area 'SP2' (AFG AR25)",
        ]
        result = summarize_warnings(warnings)
        assert result["warnings"][0] == (
            "No reporting-country form item for area 'SP2' (AR25)"
        )

    def test_exact_dedup_for_ns_not_found(self):
        warnings = ["National Society not found: 'Singapore Red Cross Society'"] * 3
        result = summarize_warnings(warnings)
        assert result["warning_unique_count"] == 1
        assert result["warnings"][0] == "National Society not found: 'Singapore Red Cross Society' (×3)"

    def test_groups_emergency_appeal_code_by_code(self):
        warnings = [
            "Emergency appeal code 'MDRTD022' not found in GO API for TCD",
            "Emergency appeal code 'MDRTD022' not found in GO API for ETH",
        ]
        result = summarize_warnings(warnings)
        assert result["warning_unique_count"] == 1
        assert "MDRTD022" in result["warnings"][0]
        assert "×2" in result["warnings"][0]
        assert "2 countries" in result["warnings"][0]

    def test_groups_percentage_out_of_range_by_indicator_across_countries(self):
        warnings = [
            "Percentage indicator 'Coverage of X' = 450 is outside the valid 0-100% range "
            "(PAK AR2025) — please check for a data-entry mistake (e.g. 500 instead of 50).",
            "Percentage indicator 'Coverage of X' = -5 is outside the valid 0-100% range "
            "(AFG AR2025) — please check for a data-entry mistake (e.g. 500 instead of 50).",
        ]
        result = summarize_warnings(warnings)
        assert result["warning_unique_count"] == 1
        line = result["warnings"][0]
        assert "Coverage of X" in line
        assert "×2" in line
        assert "2 countries" in line
        assert "AR2025" in line

    def test_keeps_distinct_percentage_indicators_separate(self):
        warnings = [
            "Percentage indicator 'Coverage of X' = 450 is outside the valid 0-100% range "
            "(PAK AR2025) — please check for a data-entry mistake (e.g. 500 instead of 50).",
            "Percentage indicator 'Coverage of Y' = 450 is outside the valid 0-100% range "
            "(PAK AR2025) — please check for a data-entry mistake (e.g. 500 instead of 50).",
        ]
        result = summarize_warnings(warnings)
        assert result["warning_unique_count"] == 2
