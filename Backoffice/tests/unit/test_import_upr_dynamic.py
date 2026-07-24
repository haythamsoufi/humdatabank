"""Unit tests for UPR import dynamic-indicator fallback and yes/no mapping."""

import sys
from pathlib import Path
from typing import Any, Dict

scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

from import_upr_excel_data import (  # noqa: E402
    UprImportContext,
    _fill_missing_core_yes_no_defaults,
    _master_yes_no_value,
    _queue_dynamic_indicator_entry,
    _queue_other_dynamic_indicator,
    _reporting_aes_ids_from_excel,
    _reporting_indicator_has_import_value,
    _reporting_indicator_import_value,
    _resolve_item_by_bank_and_area,
    _t22_pns_import_cell_value,
    _t22_total_only_breakdown_cell,
)


def _ctx(**kwargs: Any) -> UprImportContext:
    defaults = {
        "template_ids": [33],
        "items_by_bank_id": {33: {619: 9001}},
        "items_by_bank_section": {
            33: {
                619: {
                    "Resilience - Climate and environment": 9001,
                }
            }
        },
        "other_indicators_section_id": 555,
        "indicator_bank_ids": {123, 619},
        "dynamic_indicator_entries": [],
    }
    defaults.update(kwargs)
    ctx = UprImportContext(template_ids=defaults["template_ids"])
    for key, value in defaults.items():
        if key != "template_ids":
            setattr(ctx, key, value)
    return ctx


class TestT22PnsImportCellValue:
    def test_uses_pns_value_when_present(self):
        assert _t22_pns_import_cell_value(50000.0, 123.0) == 123.0

    def test_cleared_when_pns_value_blank(self):
        assert _t22_pns_import_cell_value(50000.0, None) == {
            "original": 50000.0,
            "modified": "",
            "isModified": True,
        }

    def test_skips_when_both_blank(self):
        assert _t22_pns_import_cell_value(None, None) is None


class TestT22TotalOnlyBreakdownCell:
    def test_returns_cleared_cell_when_country_value_present(self):
        staging = {(1, 2, "SP1"): (500.0, None)}
        assert _t22_total_only_breakdown_cell(staging, 1, 2, "SP1") == {
            "original": 500.0,
            "modified": "",
            "isModified": True,
        }
    def test_returns_none_when_no_country_value(self):
        staging = {(1, 2, "SP1"): (None, None)}
        assert _t22_total_only_breakdown_cell(staging, 1, 2, "SP1") is None


class TestResolveItemByBankAndArea:
    def test_resolves_section_scoped_item(self):
        ctx = _ctx()
        item_id = _resolve_item_by_bank_and_area(ctx, 33, 619, "SP1")
        assert item_id == 9001

    def test_returns_none_for_unknown_bank(self):
        ctx = _ctx()
        assert _resolve_item_by_bank_and_area(ctx, 33, 999, "SP1") is None


class TestQueueOtherDynamicIndicator:
    def test_queues_scalar_value(self):
        ctx = _ctx()
        order: Dict[int, float] = {}
        _queue_other_dynamic_indicator(
            ctx,
            aes_id=42,
            indicator_bank_id=123,
            value=7.0,
            data_not_available=False,
            order_counters=order,
        )
        assert len(ctx.dynamic_indicator_entries) == 1
        entry = ctx.dynamic_indicator_entries[0]
        assert entry["aes_id"] == 42
        assert entry["section_id"] == 555
        assert entry["indicator_bank_id"] == 123
        assert entry["value"] == 7.0

    def test_dedupes_same_bank_on_same_assignment(self):
        ctx = _ctx()
        order: Dict[int, float] = {}
        _queue_other_dynamic_indicator(
            ctx,
            aes_id=42,
            indicator_bank_id=123,
            value=1.0,
            data_not_available=False,
            order_counters=order,
        )
        _queue_other_dynamic_indicator(
            ctx,
            aes_id=42,
            indicator_bank_id=123,
            value=2.0,
            data_not_available=False,
            order_counters=order,
        )
        assert len(ctx.dynamic_indicator_entries) == 1
        assert ctx.dynamic_indicator_entries[0]["value"] == 2.0

    def test_warns_when_dynamic_section_missing(self):
        ctx = _ctx(other_indicators_section_id=None)
        _queue_other_dynamic_indicator(
            ctx,
            aes_id=42,
            indicator_bank_id=123,
            value=1.0,
            data_not_available=False,
            order_counters={},
        )
        assert ctx.dynamic_indicator_entries == []
        assert any("Other indicators dynamic section missing" in w for w in ctx.warnings)

    def test_skips_unknown_indicator_bank(self):
        ctx = _ctx(indicator_bank_ids={619})
        _queue_other_dynamic_indicator(
            ctx,
            aes_id=42,
            indicator_bank_id=1050,
            value=1.0,
            data_not_available=False,
            order_counters={},
        )
        assert ctx.dynamic_indicator_entries == []
        assert any("Indicator bank id 1050 not found" in w for w in ctx.warnings)


class TestQueueDynamicIndicatorEntry:
    def test_skips_missing_bank_before_section_check(self):
        ctx = _ctx(other_indicators_section_id=None, indicator_bank_ids={619})
        _queue_dynamic_indicator_entry(
            ctx,
            section_id=555,
            aes_id=42,
            indicator_bank_id=1050,
            value=1.0,
            data_not_available=False,
            order_counters={},
            order_key=(42,),
        )
        assert ctx.dynamic_indicator_entries == []
        assert any("Indicator bank id 1050 not found" in w for w in ctx.warnings)


class TestMasterYesNoValue:
    def test_one_is_yes(self):
        assert _master_yes_no_value(1) == "yes"
        assert _master_yes_no_value(1.0) == "yes"

    def test_zero_or_missing_is_no(self):
        assert _master_yes_no_value(0) == "no"
        assert _master_yes_no_value(0.0) == "no"
        assert _master_yes_no_value(None) == "no"

    def test_import_value_for_yes_no_bank(self):
        ctx = _ctx(yes_no_bank_ids={631})
        assert _reporting_indicator_import_value(ctx, 631, 1) == "yes"
        assert _reporting_indicator_import_value(ctx, 631, 0) == "no"
        assert _reporting_indicator_has_import_value(ctx, 631, None, is_dna=False) is True
        assert _reporting_indicator_import_value(ctx, 724, 42) == 42


class TestMissingCoreYesNoDefaults:
    def test_fills_no_for_unseen_core_item(self):
        from import_fdrs_form_data import COL_ITEM, COL_VALUE

        ctx = _ctx(core_yes_no_item_ids=[5001, 5002])
        import_rows: list = []
        filled: set = {(10, 5001)}
        _fill_missing_core_yes_no_defaults(
            ctx=ctx,
            import_rows=import_rows,
            filled_core_yes_no=filled,
            target_aes_ids={10},
            aes_meta={10: ("AFG", "Jan-Jun 2025")},
        )
        assert len(import_rows) == 1
        assert import_rows[0][COL_ITEM] == "5002"
        assert import_rows[0][COL_VALUE] == "no"
        assert (10, 5002) in filled

    def test_reporting_aes_ids_from_excel_only_present_rounds(self):
        ctx = UprImportContext(template_ids=[33])
        ctx.assignment_by_template = {
            33: {
                ("Jan-Jun 2025", "AFG"): 1,
                ("Jan-Jun 2026", "AFG"): 2,
                ("2025", "AFG"): 3,
            }
        }
        rows = [
            {"Round": "MYR25", "ISO3": "AFG", "Section": "Core indicators"},
            {"Round": "AR25", "ISO3": "AFG", "Section": "NS Data"},
        ]
        aes = _reporting_aes_ids_from_excel(rows, ctx, template_ids=[33])
        assert aes == {1, 3}
        assert 2 not in aes

    def test_reporting_aes_ids_from_excel_ignores_non_t33_sections(self):
        ctx = UprImportContext(template_ids=[33])
        ctx.assignment_by_template = {33: {("2025", "AFG"): 3}}
        rows = [{"Round": "AR25", "ISO3": "AFG", "Section": "Staff"}]
        assert _reporting_aes_ids_from_excel(rows, ctx, template_ids=[33]) == set()
