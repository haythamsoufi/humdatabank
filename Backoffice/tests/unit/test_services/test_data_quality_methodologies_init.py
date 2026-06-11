"""Tests for app/services/data_quality/methodologies/__init__.py.

Covers both happy-path and error-path of `get_methodology`.
"""
from __future__ import annotations

import pytest

from app.services.data_quality.methodologies import METHODOLOGIES, get_methodology
from app.services.data_quality.methodologies.fdrs_v1 import FdrsV1Methodology
from app.utils.data_quality_constants import METHODOLOGY_FDRS_V1


class TestGetMethodology:
    def test_returns_fdrs_v1_instance_for_known_code(self):
        result = get_methodology(METHODOLOGY_FDRS_V1)
        assert isinstance(result, FdrsV1Methodology)

    def test_each_call_returns_fresh_instance(self):
        inst1 = get_methodology(METHODOLOGY_FDRS_V1)
        inst2 = get_methodology(METHODOLOGY_FDRS_V1)
        assert inst1 is not inst2

    def test_raises_value_error_for_unknown_code(self):
        with pytest.raises(ValueError, match="Unknown data quality methodology: nonexistent"):
            get_methodology("nonexistent")

    def test_raises_value_error_for_empty_string(self):
        with pytest.raises(ValueError):
            get_methodology("")

    def test_raises_value_error_for_none_code(self):
        with pytest.raises((ValueError, AttributeError, TypeError)):
            get_methodology(None)


class TestMethodologiesRegistry:
    def test_fdrs_v1_in_registry(self):
        assert METHODOLOGY_FDRS_V1 in METHODOLOGIES

    def test_registry_maps_to_fdrs_v1_class(self):
        assert METHODOLOGIES[METHODOLOGY_FDRS_V1] is FdrsV1Methodology
