"""Unit tests for UPR import warning summarization."""

import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_plugin_scripts = _HERE.parents[1] / "scripts"
_core_imports = _HERE.parents[3] / "scripts" / "imports"
for _p in (_plugin_scripts, _core_imports):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

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
            "Emergency code 'MDRTD022' not found in GO API for TCD — imported using Excel name/code; review in form",
            "Emergency code 'MDRTD022' not found in GO API for ETH — imported using Excel name/code; review in form",
        ]
        result = summarize_warnings(warnings)
        assert result["warning_unique_count"] == 1
        assert "MDRTD022" in result["warnings"][0]
        assert "not found in GO API" in result["warnings"][0]
        assert "×2" in result["warnings"][0]
        assert "TCD" in result["warnings"][0]
        assert "ETH" in result["warnings"][0]

    def test_groups_new_emergency_appeal_wording(self):
        warnings = [
            {
                "message": (
                    "Emergency appeal MDRBD018 is not listed for this country in GO. "
                    "The Excel name and code were imported — please review it on the form."
                ),
                "item_id": 1374,
                "code": "MDRBD018",
                "iso3": "BEN",
            },
            {
                "message": (
                    "Emergency appeal MDRBD018 is not listed for this country in GO. "
                    "The Excel name and code were imported — please review it on the form."
                ),
                "item_id": 1374,
                "code": "MDRBD018",
                "iso3": "BGD",
            },
        ]
        result = summarize_warnings(warnings)
        assert result["warning_unique_count"] == 1
        line = result["warnings"][0]
        assert "MDRBD018" in line
        assert "BEN" in line
        assert "BGD" in line
        assert "is not listed in GO" in line
        assert "please review it on the form" not in line

    def test_emergency_appeal_warning_names_the_assignment(self):
        warnings = [
            {
                "message": (
                    "Emergency appeal MDRTD022 is not listed for this country in GO. "
                    "The Excel name and code were imported — please review it on the form."
                ),
                "code": "MDRTD022",
                "iso3": "TCD",
                "place": "Chad (TCD) — Reporting - Country 2025 (assignment 42)",
            }
        ]
        result = summarize_warnings(warnings)
        line = result["warnings"][0]
        assert "Chad (TCD)" in line
        assert "Reporting - Country 2025" in line
        assert "assignment 42" in line

    def test_dedupe_collapses_matrix_row_warnings_per_field(self):
        from upr_import_warnings import dedupe_upr_import_warnings, warning_text

        warnings = [
            {
                "message": (
                    "The imported row “Resilience - Climate and environment” does not match "
                    "a row on “Optional breakdown by SP/EF (CHF)”. The value was imported "
                    "but may not appear in the table."
                ),
                "item_id": 1405,
            },
            {
                "message": (
                    "The imported row “Resilience - Climate and environment” does not match "
                    "a row on “Optional breakdown by SP/EF (CHF)”. The value was imported "
                    "but may not appear in the table."
                ),
                "item_id": 1405,
            },
            {
                "message": (
                    "The imported row “Enabling functions” does not match "
                    "a row on “Optional breakdown by SP/EF (CHF)”. The value was imported "
                    "but may not appear in the table."
                ),
                "item_id": 1405,
            },
        ]
        result = dedupe_upr_import_warnings(warnings)
        assert len(result) == 1
        text = warning_text(result[0])
        assert "Resilience - Climate and environment" in text
        assert "Enabling functions" in text
        assert result[0]["item_id"] == 1405

    def test_dedupes_emergency_code_warnings_case_insensitively(self):
        from upr_import_warnings import dedupe_upr_import_warnings

        warnings = dedupe_upr_import_warnings([
            "Emergency code 'rfqwerqw' not found in GO API for AFG — imported using Excel name/code; review in form",
            "Emergency code 'RFQWERQW' not found in GO API for AFG — imported using Excel name/code; review in form",
        ])
        assert len(warnings) == 1
        assert warnings[0] == (
            "Emergency code 'RFQWERQW' not found in GO API for AFG — "
            "imported using Excel name/code; review in form"
        )

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

    def test_collapses_repeated_appeal_assignments_to_countries(self):
        places = [
            "Bulgaria (BGR) — Reporting - Country 2024 (assignment 3770)",
            "Bulgaria (BGR) — Reporting - Country 2025 (assignment 3483)",
            "Croatia (HRV) — Reporting - Country 2024 (assignment 3771)",
            "Russian Federation (RUS) — Reporting - Country 2024 (assignment 3784)",
        ]
        warnings = []
        for place in places:
            detail = None
            if place.startswith("Russian Federation"):
                detail = "Possible GO matches for this country: MDRRU028, MDRRU027."
            warnings.append({
                "message": (
                    "Emergency appeal MGR65002 is not listed for this country in GO "
                    f"({place}). The Excel name and code were imported — please review it on the form."
                ),
                "code": "MGR65002",
                "place": place,
                "detail": detail,
            })
        result = summarize_warnings(warnings)
        assert result["warning_unique_count"] == 1
        line = result["warnings"][0]
        assert "assignment 3770" not in line
        assert "Bulgaria (BGR) ×2" in line
        assert "Croatia (HRV)" in line
        assert "Possible GO matches: MDRRU028, MDRRU027" in line
        assert "for this country" not in line
        review = result["warning_groups"][0]
        assert review["id"] == "review"
        assert review["items"][0]["lines"][0].startswith("Bulgaria (BGR)")

    def test_keeps_one_unlisted_assignment_in_full(self):
        place = "Chad (TCD) — Reporting - Country 2025 (assignment 42)"
        result = summarize_warnings([{
            "message": (
                "Emergency appeal MDRTD999 is not listed for this country in GO "
                f"({place}). The Excel name and code were imported — please review it on the form."
            ),
            "code": "MDRTD999",
            "place": place,
        }])
        line = result["warnings"][0]
        assert "assignment 42" in line
        item = result["warning_groups"][0]["items"][0]
        assert item["text"] == "Emergency appeal MDRTD999 is not listed in GO"
        assert item["lines"] == ["Chad (TCD) — Reporting - Country 2025 (assignment 42)"]

    def test_groups_matched_appeals_by_code(self):
        warnings = [
            "Emergency appeal MGR65002 for Moldova, Republic of (MDA) — Reporting - Country 2024 (assignment 3779) was matched to MDRMD007 Ukraine Crisis - Moldova (part of MGR65002) (the country appeal under that group).",
            "Emergency appeal MGR65002 for Moldova, Republic of (MDA) — Reporting - Country 2025 (assignment 3492) was matched to MDRMD007 Ukraine Crisis - Moldova (part of MGR65002) (the country appeal under that group).",
            "Emergency appeal MGR65002 for Poland (POL) — Reporting - Country 2024 (assignment 3782) was matched to MDRPL002 Ukraine Crisis - Poland (part of MGR65002) (the country appeal under that group).",
            "Emergency appeal MDR66001 for Romania (ROU) — Reporting - Country 2025 (assignment 3496) was matched to MDRRO005 Ukraine Crisis - Romania (part of MGR65002) (the same group (MGR65002)).",
        ]
        result = summarize_warnings(warnings)
        assert result["warning_unique_count"] == 2
        grouped = result["warnings"][0]
        assert "assignment 3779" not in grouped
        assert "Moldova, Republic of (MDA) → MDRMD007 Ukraine Crisis - Moldova ×2" in grouped
        assert "Poland (POL) → MDRPL002 Ukraine Crisis - Poland" in grouped
        assert "(part of MGR65002)" not in grouped
        assert result["warning_groups"][0]["id"] == "matched"
        same_group = result["warnings"][1]
        assert "MDR66001" in same_group
        assert "Romania (ROU)" in same_group
        assert "MDRRO005 Ukraine Crisis - Romania" in same_group
        assert "assignment 3496" not in same_group

    def test_review_warnings_are_listed_before_matches(self):
        result = summarize_warnings([
            "Emergency appeal MGR60001 for Angola (AGO) — Reporting - Country 2024 (assignment 1) was matched to MDRAO007 Angola - Hunger Crisis (part of MGR60001) (the country appeal under that group).",
            "National Society not found: 'Hong Kong Red Cross'",
        ])
        assert [group["id"] for group in result["warning_groups"]] == ["review", "matched"]

    def test_keeps_distinct_percentage_indicators_separate(self):
        warnings = [
            "Percentage indicator 'Coverage of X' = 450 is outside the valid 0-100% range "
            "(PAK AR2025) — please check for a data-entry mistake (e.g. 500 instead of 50).",
            "Percentage indicator 'Coverage of Y' = 450 is outside the valid 0-100% range "
            "(PAK AR2025) — please check for a data-entry mistake (e.g. 500 instead of 50).",
        ]
        result = summarize_warnings(warnings)
        assert result["warning_unique_count"] == 2
