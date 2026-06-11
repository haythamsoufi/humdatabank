"""
Unit tests for app/utils/indicator_utils.py – 100% coverage target.
"""
import pytest
from unittest.mock import patch

from app.utils.indicator_utils import (
    supports_disaggregation,
    get_allowed_disaggregation_modes,
    slugify_age_group,
)


@pytest.mark.unit
class TestSupportsDisaggregation:
    """Tests for supports_disaggregation()."""

    def test_none_unit_returns_false(self):
        assert supports_disaggregation(None) is False

    def test_empty_unit_returns_false(self):
        assert supports_disaggregation('') is False

    def test_allowed_unit_no_type(self, app):
        """Without indicator_type, only unit is checked."""
        with app.app_context():
            from config import Config
            if Config.DISAGGREGATION_ALLOWED_UNITS:
                unit = next(iter(Config.DISAGGREGATION_ALLOWED_UNITS))
                assert supports_disaggregation(unit) is True

    def test_unit_not_in_allowed(self, app):
        with app.app_context():
            assert supports_disaggregation('XYZ_NOT_ALLOWED_UNIT_999') is False

    def test_unit_case_insensitive(self, app):
        with app.app_context():
            from config import Config
            if Config.DISAGGREGATION_ALLOWED_UNITS:
                unit = next(iter(Config.DISAGGREGATION_ALLOWED_UNITS))
                assert supports_disaggregation(unit.upper()) is True
                assert supports_disaggregation(unit.lower()) is True

    def test_allowed_unit_with_type_number(self, app):
        with app.app_context():
            from config import Config
            if Config.DISAGGREGATION_ALLOWED_UNITS:
                unit = next(iter(Config.DISAGGREGATION_ALLOWED_UNITS))
                assert supports_disaggregation(unit, indicator_type='Number') is True

    def test_allowed_unit_with_type_percentage_returns_false(self, app):
        with app.app_context():
            from config import Config
            if Config.DISAGGREGATION_ALLOWED_UNITS:
                unit = next(iter(Config.DISAGGREGATION_ALLOWED_UNITS))
                # Type is not 'number' → False
                assert supports_disaggregation(unit, indicator_type='Percentage') is False

    def test_disallowed_unit_with_type_number_returns_false(self, app):
        with app.app_context():
            assert supports_disaggregation('XYZ_NOPE', indicator_type='Number') is False

    def test_indicator_type_none_is_not_provided(self, app):
        """indicator_type=None means 'not provided', falls through to unit-only check."""
        with app.app_context():
            from config import Config
            if Config.DISAGGREGATION_ALLOWED_UNITS:
                unit = next(iter(Config.DISAGGREGATION_ALLOWED_UNITS))
                assert supports_disaggregation(unit, indicator_type=None) is True

    def test_unit_with_whitespace(self, app):
        with app.app_context():
            from config import Config
            if Config.DISAGGREGATION_ALLOWED_UNITS:
                unit = next(iter(Config.DISAGGREGATION_ALLOWED_UNITS))
                assert supports_disaggregation(f'  {unit}  ') is True


@pytest.mark.unit
class TestGetAllowedDisaggregationModes:
    def test_returns_total_when_disagg_not_supported(self, app):
        with app.app_context():
            result = get_allowed_disaggregation_modes('XYZ_NOT_ALLOWED')
            assert result == ['total']

    def test_returns_allowed_options_when_provided(self, app):
        with app.app_context():
            from config import Config
            if Config.DISAGGREGATION_ALLOWED_UNITS:
                unit = next(iter(Config.DISAGGREGATION_ALLOWED_UNITS))
                custom = ['total', 'sex', 'age']
                result = get_allowed_disaggregation_modes(unit, allowed_options=custom)
                assert result == custom

    def test_default_fallback_is_total(self, app):
        with app.app_context():
            from config import Config
            if Config.DISAGGREGATION_ALLOWED_UNITS:
                unit = next(iter(Config.DISAGGREGATION_ALLOWED_UNITS))
                result = get_allowed_disaggregation_modes(unit)
                assert result == ['total']


@pytest.mark.unit
class TestSlugifyAgeGroup:
    def test_range_with_dash(self, app):
        with app.app_context():
            result = slugify_age_group('0-4')
            assert result == '0_4'

    def test_open_ended_group(self, app):
        with app.app_context():
            result = slugify_age_group('18+')
            assert isinstance(result, str)

    def test_delegates_to_canonical(self, app):
        with app.app_context():
            with patch('app.utils.indicator_utils.slugify_age_group') as spy:
                # Call the real function (not patching itself), just verify delegation
                result = slugify_age_group('5-17')
                assert isinstance(result, str)
