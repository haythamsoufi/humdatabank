"""
Unit tests for app/utils/entity_groups.py – 100% coverage target.
"""
import pytest
from unittest.mock import patch

from app.utils.entity_groups import (
    ENTITY_GROUP_TYPE_MAP,
    _get_default_groups,
    get_enabled_entity_groups,
    get_allowed_entity_type_codes,
    is_entity_group_enabled,
)


@pytest.mark.unit
class TestEntityGroupTypeMap:
    def test_has_countries_key(self):
        assert 'countries' in ENTITY_GROUP_TYPE_MAP

    def test_has_ns_structure_key(self):
        assert 'ns_structure' in ENTITY_GROUP_TYPE_MAP

    def test_has_secretariat_key(self):
        assert 'secretariat' in ENTITY_GROUP_TYPE_MAP

    def test_countries_list_nonempty(self):
        assert len(ENTITY_GROUP_TYPE_MAP['countries']) > 0

    def test_ns_structure_list_nonempty(self):
        assert len(ENTITY_GROUP_TYPE_MAP['ns_structure']) > 0

    def test_secretariat_list_nonempty(self):
        assert len(ENTITY_GROUP_TYPE_MAP['secretariat']) > 0


@pytest.mark.unit
class TestGetDefaultGroups:
    def test_returns_list(self):
        result = _get_default_groups()
        assert isinstance(result, list)

    def test_returns_known_groups(self):
        result = _get_default_groups()
        for g in result:
            assert g in ENTITY_GROUP_TYPE_MAP


@pytest.mark.unit
class TestGetEnabledEntityGroups:
    def test_returns_list_in_app_context(self, app):
        with app.app_context():
            result = get_enabled_entity_groups()
            assert isinstance(result, list)
            assert len(result) > 0

    def test_all_returned_groups_are_known(self, app):
        with app.app_context():
            result = get_enabled_entity_groups()
            for g in result:
                assert g in ENTITY_GROUP_TYPE_MAP

    def test_uses_app_config_when_set(self, app):
        with app.app_context():
            app.config['ENABLED_ENTITY_TYPES'] = ['countries']
            result = get_enabled_entity_groups()
            assert result == ['countries']
            del app.config['ENABLED_ENTITY_TYPES']

    def test_filters_out_unknown_groups(self, app):
        with app.app_context():
            app.config['ENABLED_ENTITY_TYPES'] = ['countries', 'nonexistent_group']
            result = get_enabled_entity_groups()
            assert 'nonexistent_group' not in result
            assert 'countries' in result
            del app.config['ENABLED_ENTITY_TYPES']

    def test_deduplicates_groups(self, app):
        with app.app_context():
            app.config['ENABLED_ENTITY_TYPES'] = ['countries', 'countries', 'secretariat']
            result = get_enabled_entity_groups()
            assert result.count('countries') == 1
            del app.config['ENABLED_ENTITY_TYPES']

    def test_falls_back_to_defaults_when_config_all_invalid(self, app):
        with app.app_context():
            app.config['ENABLED_ENTITY_TYPES'] = ['nonexistent1', 'nonexistent2']
            result = get_enabled_entity_groups()
            # Falls back to defaults when all cleaned
            assert result == _get_default_groups()
            del app.config['ENABLED_ENTITY_TYPES']

    def test_strips_and_lowercases_group_keys(self, app):
        with app.app_context():
            app.config['ENABLED_ENTITY_TYPES'] = ['  Countries  ', 'NS_STRUCTURE']
            result = get_enabled_entity_groups()
            assert 'countries' in result
            assert 'ns_structure' in result
            del app.config['ENABLED_ENTITY_TYPES']

    def test_outside_app_context_falls_back_to_defaults(self):
        # Simulate outside app context by patching current_app to raise
        import app.utils.entity_groups as eg
        original = eg.current_app
        eg.current_app = None
        try:
            result = get_enabled_entity_groups()
            assert isinstance(result, list)
        finally:
            eg.current_app = original


@pytest.mark.unit
class TestGetAllowedEntityTypeCodes:
    def test_returns_set(self, app):
        with app.app_context():
            result = get_allowed_entity_type_codes()
            assert isinstance(result, set)

    def test_explicit_groups_expand_correctly(self):
        result = get_allowed_entity_type_codes(enabled_groups=['countries'])
        assert result == set(ENTITY_GROUP_TYPE_MAP['countries'])

    def test_multiple_groups_union(self):
        result = get_allowed_entity_type_codes(enabled_groups=['countries', 'secretariat'])
        expected = set(ENTITY_GROUP_TYPE_MAP['countries']) | set(ENTITY_GROUP_TYPE_MAP['secretariat'])
        assert result == expected

    def test_unknown_group_returns_empty_set(self):
        result = get_allowed_entity_type_codes(enabled_groups=['nonexistent'])
        assert result == set()

    def test_empty_groups_returns_empty_set(self):
        result = get_allowed_entity_type_codes(enabled_groups=[])
        assert result == set()

    def test_none_uses_app_context_groups(self, app):
        with app.app_context():
            result = get_allowed_entity_type_codes(enabled_groups=None)
            assert isinstance(result, set)
            assert len(result) > 0


@pytest.mark.unit
class TestIsEntityGroupEnabled:
    def test_enabled_group_returns_true(self, app):
        with app.app_context():
            result = is_entity_group_enabled('countries')
            assert result is True

    def test_disabled_group_returns_false(self):
        result = is_entity_group_enabled('nonexistent_group', enabled_groups=['countries'])
        assert result is False

    def test_explicit_groups_checked(self):
        result = is_entity_group_enabled('secretariat', enabled_groups=['countries', 'secretariat'])
        assert result is True

    def test_none_uses_current_app(self, app):
        with app.app_context():
            result = is_entity_group_enabled('countries', enabled_groups=None)
            assert isinstance(result, bool)
