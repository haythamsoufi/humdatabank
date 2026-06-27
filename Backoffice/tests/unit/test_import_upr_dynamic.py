"""Unit tests for UPR import dynamic-indicator fallback and yes/no mapping."""

import sys
from pathlib import Path
from typing import Any, Dict

scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

from import_upr_excel_data import (  # noqa: E402
    UprImportContext,
    _master_yes_no_value,
    _queue_other_dynamic_indicator,
    _reporting_indicator_has_import_value,
    _reporting_indicator_import_value,
    _resolve_item_by_bank_and_area,
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
        "dynamic_indicator_entries": [],
    }
    defaults.update(kwargs)
    ctx = UprImportContext(template_ids=defaults["template_ids"])
    for key, value in defaults.items():
        if key != "template_ids":
            setattr(ctx, key, value)
    return ctx


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
