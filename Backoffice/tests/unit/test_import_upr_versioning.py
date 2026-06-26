"""Unit tests for UPR import version routing."""

import sys
from pathlib import Path

scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

from upr_import_versioning import (  # noqa: E402
    REPORTING_COUNTRY_VERSION_2_MIN_YEAR,
    find_item_by_label,
    resolve_version_bracket,
)


class TestResolveVersionBracket:
    brackets = {"legacy": 101, "current": 202}

    def test_ar25_uses_legacy(self):
        vid = resolve_version_bracket(
            self.brackets,
            period="2025",
            round_code="AR25",
            min_year_v2=REPORTING_COUNTRY_VERSION_2_MIN_YEAR,
        )
        assert vid == 101

    def test_myr25_uses_legacy(self):
        vid = resolve_version_bracket(
            self.brackets,
            period="Jan-Jun 2025",
            round_code="MYR25",
            min_year_v2=REPORTING_COUNTRY_VERSION_2_MIN_YEAR,
        )
        assert vid == 101

    def test_myr26_uses_current(self):
        vid = resolve_version_bracket(
            self.brackets,
            period="Jan-Jun 2026",
            round_code="MYR26",
            min_year_v2=REPORTING_COUNTRY_VERSION_2_MIN_YEAR,
        )
        assert vid == 202

    def test_ar26_uses_current(self):
        vid = resolve_version_bracket(
            self.brackets,
            period="2026",
            round_code="AR26",
            min_year_v2=REPORTING_COUNTRY_VERSION_2_MIN_YEAR,
        )
        assert vid == 202

    def test_single_version_returns_current(self):
        vid = resolve_version_bracket({"current": 55}, period="2025", round_code="AR25")
        assert vid == 55


class TestFindItemByLabel:
    def test_substring_match(self):
        labels = {"optional breakdown by sp/ef (chf)": 1405, "ns total funding": 1403}
        assert find_item_by_label(labels, "optional breakdown by sp/ef") == 1405
        assert find_item_by_label(labels, "ns total funding") == 1403
