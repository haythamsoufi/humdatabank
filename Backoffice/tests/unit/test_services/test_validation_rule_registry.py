"""Tests for validation rule registry metadata."""

import pytest

from app.services.validation.rule_registry import (
    CORE_RULES,
    FDRS_MATRIX_V1_RULES,
    RULES_BY_CODE,
    list_rule_definitions,
    list_registered_rule_packs,
)
from app.utils.data_quality_constants import RULE_PACK_CORE, RULE_PACK_FDRS_MATRIX_V1

pytestmark = [pytest.mark.unit]


def test_fdrs_matrix_keeps_product_rules():
    assert len(FDRS_MATRIX_V1_RULES) == 13
    assert all(rule.rule_pack == RULE_PACK_FDRS_MATRIX_V1 for rule in FDRS_MATRIX_V1_RULES)


def test_core_rules_cover_missing_data_and_variation():
    codes = {rule.code for rule in CORE_RULES}
    assert codes == {
        "indicator_not_reported",
        "not_reported",
        "past_year_threshold",
        "past_3years_avg",
    }
    assert all(rule.rule_pack == RULE_PACK_CORE for rule in CORE_RULES)


def test_variation_rules_are_configurable():
    for code in ("past_year_threshold", "past_3years_avg"):
        assert RULES_BY_CODE[code].configurable is True
        assert RULES_BY_CODE[code].rule_pack == RULE_PACK_CORE


def test_list_rule_definitions_includes_core_checks_with_product_pack():
    rows = list_rule_definitions(rule_pack=RULE_PACK_FDRS_MATRIX_V1)
    assert len(rows) == 17
    core_codes = {row["code"] for row in rows if row["rule_pack"] == RULE_PACK_CORE}
    assert "past_year_threshold" in core_codes
    assert "indicator_not_reported" in core_codes
    assert sum(1 for row in rows if row["rule_pack"] == RULE_PACK_FDRS_MATRIX_V1) == 13


def test_list_registered_rule_packs():
    packs = list_registered_rule_packs()
    assert any(p["code"] == RULE_PACK_FDRS_MATRIX_V1 for p in packs)
    assert any(p["code"] == RULE_PACK_CORE for p in packs)
