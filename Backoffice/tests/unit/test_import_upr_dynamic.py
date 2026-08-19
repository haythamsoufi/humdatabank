"""Unit tests for UPR import dynamic-indicator fallback and yes/no mapping."""

import sys
from pathlib import Path
from typing import Any, Dict

imports_dir = Path(__file__).resolve().parents[2] / "scripts" / "imports"
if str(imports_dir) not in sys.path:
    sys.path.insert(0, str(imports_dir))

from import_upr_excel_data import (  # noqa: E402
    UprImportContext,
    _disaggregation_overwrite_warning,
    _fill_missing_core_yes_no_defaults,
    _has_real_disagg_breakdown,
    _master_yes_no_value,
    _percentage_scalar_range_warning,
    _queue_dynamic_indicator_entry,
    _queue_other_dynamic_indicator,
    _reporting_aes_ids_from_excel,
    _reporting_indicator_has_import_value,
    _reporting_indicator_import_value,
    _resolve_item_by_bank_and_area,
    _t22_pns_import_cell_value,
    _t22_total_only_breakdown_cell,
    collect_percentage_unit_interval_keys,
    normalize_imported_percentage_value,
    scale_imported_percentage_payload,
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


class TestPercentageRangeWarning:
    """UPR Master 'ValueNum' out of the plausible 0-100% range for a
    percentage-type indicator (e.g. 450 entered instead of 45) must be
    surfaced as a warning, not silently imported with no trace."""

    def test_out_of_range_value_is_flagged_and_still_returned_unchanged(self):
        ctx = _ctx(percentage_bank_ids={500})
        value = _reporting_indicator_import_value(
            ctx, 500, 450, iso3="PAK", rnd="AR2025", label="Coverage %"
        )
        assert value == 450  # non-blocking: the value still imports as entered
        assert len(ctx.warnings) == 1
        assert "450" in ctx.warnings[0]
        assert "Coverage %" in ctx.warnings[0]
        assert "PAK" in ctx.warnings[0]

    def test_in_range_value_is_silent(self):
        ctx = _ctx(percentage_bank_ids={500})
        assert _reporting_indicator_import_value(ctx, 500, 45) == 45
        assert ctx.warnings == []

    def test_negative_value_is_flagged(self):
        ctx = _ctx(percentage_bank_ids={500})
        _reporting_indicator_import_value(ctx, 500, -10)
        assert len(ctx.warnings) == 1
        assert "-10" in ctx.warnings[0]

    def test_allow_over_100_override_permits_high_value_but_not_negative(self):
        ctx = _ctx(percentage_bank_ids={500}, percentage_allow_over_100_bank_ids={500})
        assert _reporting_indicator_import_value(ctx, 500, 250) == 250
        assert ctx.warnings == []
        _reporting_indicator_import_value(ctx, 500, -1)
        assert len(ctx.warnings) == 1

    def test_non_percentage_bank_id_is_never_flagged(self):
        ctx = _ctx(percentage_bank_ids={500})
        assert _reporting_indicator_import_value(ctx, 724, 999) == 999
        assert ctx.warnings == []

    def test_yes_no_resolution_short_circuits_before_percentage_check(self):
        ctx = _ctx(yes_no_bank_ids={631}, percentage_bank_ids={631})
        assert _reporting_indicator_import_value(ctx, 631, 1) == "yes"
        assert ctx.warnings == []

    def test_none_value_never_flagged(self):
        ctx = _ctx(percentage_bank_ids={500})
        assert _percentage_scalar_range_warning(ctx, 500, None) is None

    def test_unit_interval_fraction_is_scaled_to_stored_percent(self):
        ctx = _ctx(percentage_bank_ids={500})
        assert _reporting_indicator_import_value(ctx, 500, 0.45, rnd="AR23") == 45
        assert ctx.warnings == []

    def test_already_whole_percent_is_unchanged(self):
        ctx = _ctx(percentage_bank_ids={500})
        assert _reporting_indicator_import_value(ctx, 500, 45, rnd="AR25") == 45
        assert ctx.warnings == []

    def test_zero_and_one_percent_stay_when_round_is_0_100(self):
        ctx = _ctx(percentage_bank_ids={500})
        assert _reporting_indicator_import_value(ctx, 500, 0, rnd="AR25") == 0
        assert _reporting_indicator_import_value(ctx, 500, 1, rnd="AR25") == 1
        assert ctx.warnings == []

    def test_one_becomes_100_when_the_round_is_unit_interval(self):
        ctx = _ctx(
            percentage_bank_ids={500},
            percentage_unit_interval_keys={(500, "AR23")},
        )
        assert _reporting_indicator_import_value(ctx, 500, 1, rnd="AR23") == 100
        assert _reporting_indicator_import_value(ctx, 500, 0.25, rnd="AR23") == 25


class TestPercentageUnitIntervalDetection:
    def test_past_round_0_1_is_unit_interval_even_when_later_round_is_0_100(self):
        rows = [
            {"indicatorId": 500, "Round": "AR23", "ValueNum": 0.25},
            {"indicatorId": 500, "Round": "AR23", "ValueNum": 1},
            {"indicatorId": 500, "Round": "AR25", "ValueNum": 45},
        ]
        keys = collect_percentage_unit_interval_keys(rows, {500})
        assert (500, "AR23") in keys
        assert (500, "AR25") not in keys

    def test_normalize_scales_fractions_and_optional_one(self):
        assert normalize_imported_percentage_value(0.2) == 20
        assert normalize_imported_percentage_value(0.2, scale_one_to_hundred=True) == 20
        assert normalize_imported_percentage_value(1) == 1
        assert normalize_imported_percentage_value(1, scale_one_to_hundred=True) == 100
        assert normalize_imported_percentage_value(45) == 45
        assert normalize_imported_percentage_value(0) == 0

    def test_scale_payload_walks_disagg_trees(self):
        payload = {"mode": "sex", "values": {"male": 0.4, "female": 0.6}}
        scaled = scale_imported_percentage_payload(payload, scale_one_to_hundred=False)
        assert scaled["values"]["male"] == 40
        assert scaled["values"]["female"] == 60


class TestHasRealDisaggBreakdown:
    """UPR Master's 'UPR Data' sheet is flat (single ValueNum, no Male/Female/Age
    columns), so the importer must recognise when an existing DB row already has a
    real sex/age breakdown so it doesn't blindly flatten it into a scalar."""

    def test_sex_age_mode_with_values_is_real(self):
        assert _has_real_disagg_breakdown(
            {"mode": "sex_age", "values": {"direct": {"male__5": 10, "female_5_17": 4}}}
        )

    def test_sex_mode_with_values_is_real(self):
        assert _has_real_disagg_breakdown({"mode": "sex", "values": {"male": 5, "female": 3}})

    def test_total_mode_is_not_a_breakdown(self):
        assert not _has_real_disagg_breakdown({"mode": "total", "values": {"total": 42}})

    def test_none_is_not_a_breakdown(self):
        assert not _has_real_disagg_breakdown(None)

    def test_empty_values_dict_is_not_a_breakdown(self):
        assert not _has_real_disagg_breakdown({"mode": "sex_age", "values": {"direct": {}}})

    def test_non_dict_is_not_a_breakdown(self):
        assert not _has_real_disagg_breakdown("male__5:10")


class TestDisaggregationOverwriteGuard:
    """UPR Master must never silently flatten an indicator that already has a real
    sex/age breakdown (entered via the T33 per-country Excel import or the web form)
    into a bare scalar total — FormData/DynamicIndicatorData.set_simple_value()
    unconditionally clears disagg_data, so this must be caught before that call."""

    def test_warns_and_would_skip_when_static_key_has_existing_breakdown(self):
        ctx = _ctx(existing_disagg_static_keys={(10, 9001)})
        warning = _disaggregation_overwrite_warning(
            ctx, value_num=100, is_dna=False, static_key=(10, 9001), iso3="PAK", rnd="AR2025", label="Reached"
        )
        assert warning is not None
        assert "Reached" in warning
        assert "PAK" in warning
        assert "100" in warning

    def test_warns_when_dynamic_key_has_existing_breakdown(self):
        ctx = _ctx(existing_disagg_dynamic_keys={(10, 555, 619, None)})
        warning = _disaggregation_overwrite_warning(
            ctx, value_num=50, is_dna=False, dynamic_key=(10, 555, 619, None),
        )
        assert warning is not None

    def test_no_warning_when_key_has_no_existing_breakdown(self):
        ctx = _ctx(existing_disagg_static_keys={(10, 9001)})
        assert _disaggregation_overwrite_warning(
            ctx, value_num=100, is_dna=False, static_key=(10, 9999),
        ) is None

    def test_data_not_available_bypasses_the_guard(self):
        # DNA is a deliberate status from the master sheet — it's allowed to clear
        # an existing breakdown, unlike an incidental flat scalar.
        ctx = _ctx(existing_disagg_static_keys={(10, 9001)})
        assert _disaggregation_overwrite_warning(
            ctx, value_num=None, is_dna=True, static_key=(10, 9001),
        ) is None

    def test_none_value_bypasses_the_guard(self):
        ctx = _ctx(existing_disagg_static_keys={(10, 9001)})
        assert _disaggregation_overwrite_warning(
            ctx, value_num=None, is_dna=False, static_key=(10, 9001),
        ) is None

    def test_no_keys_provided_is_never_a_conflict(self):
        ctx = _ctx(existing_disagg_static_keys={(10, 9001)}, existing_disagg_dynamic_keys={(10, 555, 619, None)})
        assert _disaggregation_overwrite_warning(ctx, value_num=100, is_dna=False) is None


class TestLoadExistingDisaggregatedKeysDb:
    """End-to-end DB check: _load_existing_disaggregated_keys must find real
    FormData/DynamicIndicatorData rows with a sex/age breakdown, and must not treat
    a plain 'total' mode (or no disagg at all) as a breakdown worth protecting."""

    def test_finds_static_and_dynamic_breakdowns_but_not_total_mode(self, app, db_session):
        from import_upr_excel_data import _load_existing_disaggregated_keys
        from app.models.forms import DynamicIndicatorData, FormData
        from app.models.indicator_bank import IndicatorBank
        from tests.factories import (
            create_test_assignment_entity_status,
            create_test_item,
            create_test_section,
            create_test_template,
            create_test_user,
        )

        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            breakdown_item = create_test_item(db_session, section, template, item_type="indicator")
            total_only_item = create_test_item(db_session, section, template, item_type="indicator")
            aes = create_test_assignment_entity_status(db_session, template=template)
            user = create_test_user(db_session)
            bank = IndicatorBank(name="__test_disagg_guard_bank__", type="number")
            db_session.add(bank)
            db_session.flush()

            db_session.add(FormData(
                assignment_entity_status_id=aes.id,
                form_item_id=breakdown_item.id,
                disagg_data={"mode": "sex_age", "values": {"direct": {"male__5": 10, "female_5_17": 4}}},
            ))
            db_session.add(FormData(
                assignment_entity_status_id=aes.id,
                form_item_id=total_only_item.id,
                disagg_data={"mode": "total", "values": {"total": 99}},
            ))
            dyn_row = DynamicIndicatorData(
                assignment_entity_status_id=aes.id,
                section_id=section.id,
                indicator_bank_id=bank.id,
                repeat_instance_number=None,
                added_by_user_id=user.id,
            )
            dyn_row.set_disaggregated_data("sex", {"male": 3, "female": 7})
            db_session.add(dyn_row)
            db_session.commit()

            static_keys, dynamic_keys = _load_existing_disaggregated_keys({aes.id})

            assert (aes.id, breakdown_item.id) in static_keys
            assert (aes.id, total_only_item.id) not in static_keys
            assert (aes.id, section.id, bank.id, None) in dynamic_keys

    def test_empty_aes_ids_returns_empty_sets_without_querying(self, app):
        from import_upr_excel_data import _load_existing_disaggregated_keys

        with app.app_context():
            static_keys, dynamic_keys = _load_existing_disaggregated_keys(set())
            assert static_keys == set()
            assert dynamic_keys == set()


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
