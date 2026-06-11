"""Tests for app/services/data_quality/types.py.

Targets 100% coverage of DataQualityResult including the to_dict() method
with all field combinations, especially the missing branch around
non-empty trend/warnings/validation_summary.
"""
from __future__ import annotations

import pytest

from app.services.data_quality.types import DataQualityResult


class TestDataQualityResultDefaults:
    def test_default_fields_are_empty_collections(self):
        result = DataQualityResult(
            overall_pct=50.0,
            methodology="fdrs_v1",
            template_id=21,
            entity_type="country",
            entity_id=1,
            period_name="2024",
        )

        assert result.pillars == {}
        assert result.sub_pillars == {}
        assert result.component_details == {}
        assert result.trend == []
        assert result.warnings == []
        assert result.validation_summary == {}

    def test_fields_are_independently_mutable(self):
        r1 = DataQualityResult(
            overall_pct=10.0,
            methodology="fdrs_v1",
            template_id=1,
            entity_type="country",
            entity_id=1,
            period_name="2024",
        )
        r2 = DataQualityResult(
            overall_pct=20.0,
            methodology="fdrs_v1",
            template_id=2,
            entity_type="country",
            entity_id=2,
            period_name="2024",
        )
        r1.warnings.append("warn1")
        assert r2.warnings == []


class TestDataQualityResultToDict:
    def test_minimal_to_dict(self):
        result = DataQualityResult(
            overall_pct=75.123,
            methodology="fdrs_v1",
            template_id=21,
            entity_type="country",
            entity_id=1,
            period_name="FDRS 2024",
        )

        d = result.to_dict()

        assert d["overall_pct"] == 75.1
        assert d["methodology"] == "fdrs_v1"
        assert d["template_id"] == 21
        assert d["entity_type"] == "country"
        assert d["entity_id"] == 1
        assert d["period_name"] == "FDRS 2024"
        assert d["pillars"] == {}
        assert d["sub_pillars"] == {}
        assert d["component_details"] == {}
        assert d["trend"] == []
        assert d["warnings"] == []
        assert d["validation_summary"] == {}

    def test_to_dict_rounds_overall_pct_to_one_decimal(self):
        result = DataQualityResult(
            overall_pct=66.6666,
            methodology="fdrs_v1",
            template_id=1,
            entity_type="country",
            entity_id=1,
            period_name="2024",
        )

        assert result.to_dict()["overall_pct"] == 66.7

    def test_to_dict_with_populated_collections(self):
        result = DataQualityResult(
            overall_pct=80.0,
            methodology="fdrs_v1",
            template_id=21,
            entity_type="country",
            entity_id=5,
            period_name="FDRS 2023",
            pillars={"documents": 100.0, "reporting": 80.0},
            sub_pillars={"documents": {"annual_report": 1.0}},
            component_details={"reporting": {"finance_partnership": {}}},
            trend=[{"period": "FDRS 2022", "overall_pct": 70.0, "pillars": {}}],
            warnings=["disability_data_gap: no _ddd/_wgq KPI data in form_data."],
            validation_summary={"asked": 5, "answered": 4, "open": 1, "waived": 0},
        )

        d = result.to_dict()

        assert d["overall_pct"] == 80.0
        assert d["pillars"]["documents"] == 100.0
        assert d["sub_pillars"]["documents"]["annual_report"] == 1.0
        assert len(d["trend"]) == 1
        assert d["trend"][0]["period"] == "FDRS 2022"
        assert len(d["warnings"]) == 1
        assert d["validation_summary"]["asked"] == 5

    def test_to_dict_returns_new_dict_each_call(self):
        result = DataQualityResult(
            overall_pct=60.0,
            methodology="fdrs_v1",
            template_id=21,
            entity_type="country",
            entity_id=1,
            period_name="2024",
        )

        d1 = result.to_dict()
        d2 = result.to_dict()

        # They should be equal in content but not the same object
        assert d1 == d2
        assert d1 is not d2

    def test_to_dict_zero_overall_pct(self):
        result = DataQualityResult(
            overall_pct=0.0,
            methodology="fdrs_v1",
            template_id=21,
            entity_type="country",
            entity_id=1,
            period_name="2024",
        )

        assert result.to_dict()["overall_pct"] == 0.0

    def test_to_dict_100_overall_pct(self):
        result = DataQualityResult(
            overall_pct=100.0,
            methodology="fdrs_v1",
            template_id=21,
            entity_type="country",
            entity_id=1,
            period_name="2024",
        )

        assert result.to_dict()["overall_pct"] == 100.0

    def test_to_dict_negative_pct_preserved(self):
        # Edge case: if scoring ever goes negative, ensure to_dict works
        result = DataQualityResult(
            overall_pct=-1.5,
            methodology="fdrs_v1",
            template_id=21,
            entity_type="country",
            entity_id=1,
            period_name="2024",
        )
        assert result.to_dict()["overall_pct"] == -1.5

    def test_all_keys_present_in_to_dict_output(self):
        result = DataQualityResult(
            overall_pct=55.5,
            methodology="fdrs_v1",
            template_id=21,
            entity_type="country",
            entity_id=1,
            period_name="2024",
        )
        d = result.to_dict()

        expected_keys = {
            "overall_pct",
            "methodology",
            "template_id",
            "entity_type",
            "entity_id",
            "period_name",
            "pillars",
            "sub_pillars",
            "component_details",
            "trend",
            "warnings",
            "validation_summary",
        }
        assert set(d.keys()) == expected_keys
