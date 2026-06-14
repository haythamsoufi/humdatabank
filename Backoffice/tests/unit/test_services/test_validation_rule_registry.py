"""Tests for validation rule registry metadata."""

import pytest

from app.services.validation.rule_registry import (
    FDRS_MATRIX_V1_RULES,
    RULES_BY_CODE,
    list_rule_definitions,
    list_registered_rule_packs,
)
from app.utils.data_quality_constants import RULE_PACK_FDRS_MATRIX_V1

pytestmark = [pytest.mark.unit]


def test_fdrs_matrix_has_seventeen_rules():
    assert len(FDRS_MATRIX_V1_RULES) == 17


def test_variation_rules_are_configurable():
    for code in ("past_year_threshold", "past_3years_avg"):
        assert RULES_BY_CODE[code].configurable is True


def test_list_rule_definitions_filters_by_pack():
    rows = list_rule_definitions(rule_pack=RULE_PACK_FDRS_MATRIX_V1)
    assert len(rows) == 17
    assert all(r["rule_pack"] == RULE_PACK_FDRS_MATRIX_V1 for r in rows)


def test_list_registered_rule_packs():
    packs = list_registered_rule_packs()
    assert any(p["code"] == RULE_PACK_FDRS_MATRIX_V1 for p in packs)
