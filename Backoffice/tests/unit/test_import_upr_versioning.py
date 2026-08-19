"""Unit tests for UPR import label matching helpers."""

import sys
from pathlib import Path

imports_dir = Path(__file__).resolve().parents[2] / "scripts" / "imports"
if str(imports_dir) not in sys.path:
    sys.path.insert(0, str(imports_dir))

from import_upr_excel_data import (  # noqa: E402
    REPORTING_SPECIAL_ITEM_LABELS,
    t24_funding_offset_from_section,
)
from upr_import_versioning import find_item_by_label  # noqa: E402


class TestFindItemByLabel:
    def test_substring_match(self):
        labels = {"optional breakdown by sp/ef (chf)": 1405, "ns total funding": 1403}
        assert find_item_by_label(labels, "optional breakdown by sp/ef") == 1405
        assert find_item_by_label(labels, "ns total funding") == 1403

    def test_t33_published_labels_match_needles(self):
        labels = {
            "national society [assignment_year] funding (chf)": 1403,
            "national society [assignment_year] expenditure (chf)": 1404,
            "optional breakdown by sp/ef (chf)": 1405,
            "received support": 1407,
        }
        assert find_item_by_label(labels, *REPORTING_SPECIAL_ITEM_LABELS["funding"]) == 1403
        assert find_item_by_label(labels, *REPORTING_SPECIAL_ITEM_LABELS["expenditure"]) == 1404
        assert find_item_by_label(labels, *REPORTING_SPECIAL_ITEM_LABELS["sp_breakdown"]) == 1405
        assert find_item_by_label(labels, *REPORTING_SPECIAL_ITEM_LABELS["support"]) == 1407


class TestT24FundingOffsetFromSection:
    def test_year_offsets(self):
        assert t24_funding_offset_from_section("Funding Requirements for [assignment_period]") == 0
        assert t24_funding_offset_from_section("Funding Requirements for  [[assignment_period]+1]") == 1
        assert t24_funding_offset_from_section("Funding Requirements for  [[assignment_period]+2]") == 2
        assert t24_funding_offset_from_section("People to be reached") is None
