"""Unit tests for disability question processing in FormItemProcessor."""
from __future__ import annotations

from types import SimpleNamespace

from app.services.form_processing_service import FormItemProcessor


def _indicator(**config_overrides):
    cfg = {
        "allow_disability_questions": True,
        "allowed_disaggregation_options": ["total"],
        "indirect_reach": False,
    }
    cfg.update(config_overrides)
    return SimpleNamespace(
        field_type_for_js="number",
        type="number",
        label="People reached",
        allow_disability_questions=cfg["allow_disability_questions"],
        allowed_disaggregation_options=cfg["allowed_disaggregation_options"],
        indirect_reach=cfg["indirect_reach"],
        effective_sex_categories=[],
        effective_age_groups=[],
        config=cfg,
    )


def test_disability_yes_no_stored_in_disagg_data_without_main_value():
    item = _indicator()
    form_data = {
        "indicator_42_disability_disaggregated": "no",
    }
    value, has_value, dna, na = FormItemProcessor._process_indicator_data(item, form_data, "indicator_42")
    assert has_value is True
    assert value == {"mode": "total", "values": {"disability": {"disaggregated_by_disability": False}}}
    assert dna is False and na is False


def test_disability_yes_with_washington_group_merged_with_numeric_total():
    item = _indicator()
    form_data = {
        "indicator_7_total_value": "100",
        "indicator_7_disability_disaggregated": "yes",
        "indicator_7_disability_washington_group": "yes",
    }
    value, has_value, _, _ = FormItemProcessor._process_indicator_data(item, form_data, "indicator_7")
    assert has_value is True
    assert value["mode"] == "total"
    assert value["values"]["total"] == "100"
    assert value["values"]["disability"] == {
        "disaggregated_by_disability": True,
        "washington_group_compliant": True,
    }


def test_disability_questions_ignored_when_flag_disabled():
    item = _indicator(allow_disability_questions=False)
    form_data = {
        "indicator_1_disability_disaggregated": "yes",
        "indicator_1_disability_washington_group": "yes",
    }
    value, has_value, _, _ = FormItemProcessor._process_indicator_data(item, form_data, "indicator_1")
    assert has_value is False
    assert value is None
