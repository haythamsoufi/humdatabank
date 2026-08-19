"""Unit tests for API percentage 0–100 → 0–1 scaling."""
import pytest

from app.utils.api_percentage import (
    apply_api_percentage_scale,
    is_percentage_type,
    orm_item_is_percentage,
    scale_percentage_fact_row,
    scale_percentage_rows,
    to_api_percentage_decimal,
)


@pytest.mark.unit
class TestIsPercentageType:
    def test_matches_common_spellings(self):
        assert is_percentage_type("percentage") is True
        assert is_percentage_type("Percentage") is True
        assert is_percentage_type("PERCENT") is True
        assert is_percentage_type("pct") is True
        assert is_percentage_type(" percent ") is True

    def test_rejects_other_types(self):
        assert is_percentage_type("number") is False
        assert is_percentage_type("yesno") is False
        assert is_percentage_type(None) is False
        assert is_percentage_type("") is False


@pytest.mark.unit
class TestToApiPercentageDecimal:
    def test_none_stays_none(self):
        assert to_api_percentage_decimal(None) is None

    def test_zero(self):
        assert to_api_percentage_decimal(0) == 0.0
        assert to_api_percentage_decimal("0") == 0.0

    def test_quarter(self):
        assert to_api_percentage_decimal(25) == 0.25
        assert to_api_percentage_decimal("25") == 0.25
        assert to_api_percentage_decimal("25.0") == 0.25

    def test_one_hundred(self):
        assert to_api_percentage_decimal(100) == 1.0

    def test_allow_over_100(self):
        assert to_api_percentage_decimal(150) == 1.5

    def test_non_numeric_string_unchanged(self):
        assert to_api_percentage_decimal("n/a") == "n/a"

    def test_bool_not_treated_as_number(self):
        assert to_api_percentage_decimal(True) is True
        assert to_api_percentage_decimal(False) is False

    def test_nested_disagg_values(self):
        scaled = to_api_percentage_decimal({
            "mode": "sex",
            "values": {"male": 40, "female": "60"},
        })
        assert scaled["mode"] == "sex"
        assert scaled["values"]["male"] == 0.4
        assert scaled["values"]["female"] == 0.6


@pytest.mark.unit
class TestScalePercentageFactRow:
    def test_scales_value_and_num_value(self):
        row = {"value": "25", "num_value": 25.0, "data_status": "available"}
        scale_percentage_fact_row(row)
        assert row["value"] == 0.25
        assert row["num_value"] == 0.25
        assert row["data_status"] == "available"

    def test_scales_disaggregation_and_aliases(self):
        row = {
            "value": 50,
            "num_value": 50,
            "disaggregation_data": {"mode": "total", "values": {"total": 50}},
            "prefilled_disagg_data": {"values": {"total": 10}},
        }
        scale_percentage_fact_row(row)
        assert row["disaggregation_data"]["values"]["total"] == 0.5
        assert row["prefilled_disagg_data"]["values"]["total"] == 0.1

    def test_missing_value_clears_num_value(self):
        row = {"value": None, "num_value": 25}
        scale_percentage_fact_row(row)
        assert row["value"] is None
        assert row["num_value"] is None


@pytest.mark.unit
class TestScalePercentageRows:
    def test_only_matching_form_item_ids(self):
        rows = [
            {"form_item_id": 1, "value": "25", "num_value": 25},
            {"form_item_id": 2, "value": "25", "num_value": 25},
        ]
        scale_percentage_rows(rows, form_item_ids={1})
        assert rows[0]["num_value"] == 0.25
        assert rows[1]["num_value"] == 25

    def test_matches_indicator_bank_id(self):
        rows = [{"indicator_bank_id": 9, "value": 100, "num_value": 100}]
        scale_percentage_rows(rows, bank_ids={9})
        assert rows[0]["num_value"] == 1.0


@pytest.mark.unit
class TestOrmAndApply:
    def test_orm_item_uses_type(self):
        class _Item:
            type = "percentage"
            field_type_for_js = "percentage"
            indicator_bank = None

        assert orm_item_is_percentage(_Item()) is True

    def test_orm_item_uses_bank_type(self):
        class _Bank:
            type = "Percentage"

        class _Item:
            type = "number"
            field_type_for_js = "number"
            indicator_bank = _Bank()

        assert orm_item_is_percentage(_Item()) is True

    def test_apply_skips_non_percentage(self):
        class _Item:
            type = "number"
            field_type_for_js = "number"
            indicator_bank = None

        row = {"value": 25, "num_value": 25}
        apply_api_percentage_scale(row, form_item=_Item())
        assert row["num_value"] == 25
