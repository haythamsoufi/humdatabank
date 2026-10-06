"""Unit tests for UPR import label matching helpers."""

import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_plugin_scripts = _HERE.parents[1] / "scripts"
_core_imports = _HERE.parents[3] / "scripts" / "imports"
for _p in (_plugin_scripts, _core_imports):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from unittest.mock import patch

from import_upr_excel_data import (  # noqa: E402
    REPORTING_SPECIAL_ITEM_LABELS,
    T22_STAFF_MATRIX_LABELS,
    UprImportContext,
    _resolve_t22_staff_item_id,
    t22_matrix_is_staff,
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

    def test_t22_staff_label_matches_published_and_legacy(self):
        published = {"staff contributions": 1314, "funding requirements": 1303}
        legacy = {"pns staff contributions": 1434}
        assert find_item_by_label(published, *T22_STAFF_MATRIX_LABELS) == 1314
        assert find_item_by_label(legacy, *T22_STAFF_MATRIX_LABELS) == 1434
        assert find_item_by_label(published, "pns staff contributions") is None


def _matrix_item(item_id, label, columns):
    return type(
        "Item",
        (),
        {
            "id": item_id,
            "label": label,
            "config": {"matrix_config": {"columns": [{"name": name} for name in columns]}},
        },
    )()


class TestT22StaffMatrixResolution:
    def test_staff_column_identifies_matrix(self):
        staff = _matrix_item(1314, "Staff contributions", ["intl_delegates_hns"])
        funding = _matrix_item(1303, "Funding Requirements", ["SP1", "EFs"])
        assert t22_matrix_is_staff(staff) is True
        assert t22_matrix_is_staff(funding) is False

    def test_resolves_published_staff_contributions_label(self):
        staff = _matrix_item(
            1314,
            "Staff contributions",
            ["intl_delegates_hns", "intl_delegates_ifrc"],
        )
        funding = _matrix_item(1303, "Funding Requirements", ["SP1", "SP2", "EFs"])
        ctx = UprImportContext(template_ids=[22])
        ctx.published_version_ids = {22: 22}
        with patch(
            "import_upr_excel_data._resolve_published_stable_item",
            return_value=None,
        ), patch(
            "import_upr_excel_data._load_published_form_items",
            return_value=[funding, staff],
        ):
            assert _resolve_t22_staff_item_id(ctx) == 1314

    def test_resolves_by_stable_key_before_label(self):
        ctx = UprImportContext(template_ids=[22])
        ctx.published_version_ids = {22: 22}
        with patch(
            "import_upr_excel_data._resolve_published_stable_item",
            return_value=1434,
        ) as resolve, patch(
            "import_upr_excel_data._load_published_form_items",
        ) as load_items:
            assert _resolve_t22_staff_item_id(ctx) == 1434
        resolve.assert_called_once()
        load_items.assert_not_called()

    def test_resolves_by_staff_column_when_label_does_not_match(self):
        staff = _matrix_item(1314, "Delegates", ["intl_delegates_hns"])
        ctx = UprImportContext(template_ids=[22])
        ctx.published_version_ids = {22: 22}
        with patch(
            "import_upr_excel_data._resolve_published_stable_item",
            return_value=None,
        ), patch(
            "import_upr_excel_data._load_published_form_items",
            return_value=[staff],
        ):
            assert _resolve_t22_staff_item_id(ctx) == 1314


class TestT24FundingOffsetFromSection:
    def test_year_offsets(self):
        assert t24_funding_offset_from_section("Funding Requirements for [assignment_period]") == 0
        assert t24_funding_offset_from_section("Funding Requirements for  [[assignment_period]+1]") == 1
        assert t24_funding_offset_from_section("Funding Requirements for  [[assignment_period]+2]") == 2
        assert t24_funding_offset_from_section("People to be reached") is None
