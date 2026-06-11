"""
Unit tests for app/utils/plugin_data_processor.py – 100% coverage target.
"""
import json
import pytest
from unittest.mock import MagicMock, patch

from app.utils.plugin_data_processor import (
    PluginDataProcessor,
    process_form_plugin_data,
    plugin_data_processor,
)
from app.utils.schema_validation import SchemaValidationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_processor():
    return PluginDataProcessor()


def _make_form_item(item_type='plugin_interactive_map', plugin_config=None):
    fi = MagicMock()
    fi.item_type = item_type
    fi.plugin_config = plugin_config or {}
    return fi


# ---------------------------------------------------------------------------
# PluginDataProcessor – initialize
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestPluginDataProcessorInitialize:
    def test_initialize_sets_plugin_manager(self):
        proc = _make_processor()
        pm = MagicMock()
        proc.initialize(pm)
        assert proc.plugin_manager is pm

    def test_default_plugin_manager_is_none(self):
        proc = _make_processor()
        assert proc.plugin_manager is None

    def test_processed_cache_starts_empty(self):
        proc = _make_processor()
        assert proc.processed_cache == {}


# ---------------------------------------------------------------------------
# _get_plugin_type_for_field
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestGetPluginTypeForField:
    # FormItem is imported locally inside the method: `from app.models import FormItem`
    # so we patch it in the app.models namespace.

    def test_returns_type_for_plugin_item(self, app):
        with app.app_context():
            proc = _make_processor()
            fi = _make_form_item(item_type='plugin_interactive_map')
            with patch('app.models.FormItem') as MockFI:
                MockFI.query.get.return_value = fi
                result = proc._get_plugin_type_for_field(1)
            assert result == 'interactive_map'

    def test_returns_none_for_non_plugin_item(self, app):
        with app.app_context():
            proc = _make_processor()
            fi = _make_form_item(item_type='text_field')
            with patch('app.models.FormItem') as MockFI:
                MockFI.query.get.return_value = fi
                result = proc._get_plugin_type_for_field(1)
            assert result is None

    def test_returns_none_when_form_item_not_found(self, app):
        with app.app_context():
            proc = _make_processor()
            with patch('app.models.FormItem') as MockFI:
                MockFI.query.get.return_value = None
                result = proc._get_plugin_type_for_field(999)
            assert result is None

    def test_returns_none_on_exception(self, app):
        with app.app_context():
            proc = _make_processor()
            with patch('app.models.FormItem') as MockFI:
                MockFI.query.get.side_effect = Exception('db error')
                result = proc._get_plugin_type_for_field(1)
            assert result is None

    def test_returns_none_when_item_type_is_none(self, app):
        with app.app_context():
            proc = _make_processor()
            fi = MagicMock()
            fi.item_type = None
            with patch('app.models.FormItem') as MockFI:
                MockFI.query.get.return_value = fi
                result = proc._get_plugin_type_for_field(1)
            assert result is None


# ---------------------------------------------------------------------------
# _get_plugin_config
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestGetPluginConfig:
    # FormItem is imported locally inside the method: `from app.models import FormItem`
    # so we patch it in the app.models namespace.

    def test_returns_plugin_config(self, app):
        with app.app_context():
            proc = _make_processor()
            fi = _make_form_item(plugin_config={'key': 'val'})
            with patch('app.models.FormItem') as MockFI:
                MockFI.query.get.return_value = fi
                result = proc._get_plugin_config('interactive_map', 1)
            assert result == {'key': 'val'}

    def test_returns_empty_dict_when_no_plugin_config_attr(self, app):
        with app.app_context():
            proc = _make_processor()
            fi = MagicMock(spec=['item_type'])  # no plugin_config attribute
            with patch('app.models.FormItem') as MockFI:
                MockFI.query.get.return_value = fi
                result = proc._get_plugin_config('interactive_map', 1)
            assert result == {}

    def test_returns_empty_dict_when_form_item_not_found(self, app):
        with app.app_context():
            proc = _make_processor()
            with patch('app.models.FormItem') as MockFI:
                MockFI.query.get.return_value = None
                result = proc._get_plugin_config('interactive_map', 999)
            assert result == {}

    def test_returns_empty_dict_on_exception(self, app):
        with app.app_context():
            proc = _make_processor()
            with patch('app.models.FormItem') as MockFI:
                MockFI.query.get.side_effect = Exception('error')
                result = proc._get_plugin_config('interactive_map', 1)
            assert result == {}


# ---------------------------------------------------------------------------
# _extract_essential_plugin_data
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestExtractEssentialPluginData:
    def test_interactive_map_extracts_markers(self):
        proc = _make_processor()
        data = {'markers': [{'lat': 1, 'lng': 2}], 'metadata': 'strip me'}
        result = proc._extract_essential_plugin_data(data, 'interactive_map')
        assert result == {'markers': [{'lat': 1, 'lng': 2}]}

    def test_interactive_map_empty_markers(self):
        proc = _make_processor()
        result = proc._extract_essential_plugin_data({}, 'interactive_map')
        assert result == {'markers': []}

    def test_emergency_operations_returns_none(self):
        proc = _make_processor()
        result = proc._extract_essential_plugin_data({'ops': [1, 2]}, 'emergency_operations')
        assert result is None

    def test_other_plugin_strips_metadata_fields(self):
        proc = _make_processor()
        data = {
            'value': 42,
            '_schema_version': '1.0',
            '_plugin_type': 'test',
            '_processed_at': 'now',
            'data_not_available': True,
            'not_applicable': False,
            'metadata': {},
        }
        result = proc._extract_essential_plugin_data(data, 'custom_plugin')
        assert 'value' in result
        assert '_schema_version' not in result
        assert '_plugin_type' not in result
        assert 'metadata' not in result

    def test_non_dict_data_returned_as_is(self):
        proc = _make_processor()
        result = proc._extract_essential_plugin_data([1, 2, 3], 'some_plugin')
        assert result == [1, 2, 3]


# ---------------------------------------------------------------------------
# _process_generic_plugin_data
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestProcessGenericPluginData:
    def test_basic_success(self):
        proc = _make_processor()
        ok, val, err = proc._process_generic_plugin_data({'key': 'x'}, 'custom', {})
        assert ok is True
        assert err is None
        parsed = json.loads(val)
        assert parsed == {'key': 'x'}

    def test_emergency_operations_returns_none_value(self):
        proc = _make_processor()
        ok, val, err = proc._process_generic_plugin_data({}, 'emergency_operations', {})
        assert ok is True
        assert val is None

    def test_size_exceeded_returns_false(self):
        proc = _make_processor()
        pm = MagicMock()
        pm.get_field_type_config.return_value = {
            'data_storage_config': {'max_size': 5}  # very small limit
        }
        proc.initialize(pm)
        large_data = {'key': 'a' * 1000}
        ok, val, err = proc._process_generic_plugin_data(large_data, 'custom', {})
        assert ok is False
        assert 'size limit' in err.lower()

    def test_none_max_size_defaults_to_10000(self):
        proc = _make_processor()
        pm = MagicMock()
        pm.get_field_type_config.return_value = {
            'data_storage_config': {'max_size': None}
        }
        proc.initialize(pm)
        small_data = {'k': 'v'}
        ok, val, err = proc._process_generic_plugin_data(small_data, 'custom', {})
        assert ok is True

    def test_invalid_max_size_defaults_to_10000(self):
        proc = _make_processor()
        pm = MagicMock()
        pm.get_field_type_config.return_value = {
            'data_storage_config': {'max_size': 'not_a_number'}
        }
        proc.initialize(pm)
        ok, val, err = proc._process_generic_plugin_data({'k': 'v'}, 'custom', {})
        assert ok is True

    def test_zero_max_size_defaults_to_10000(self):
        proc = _make_processor()
        pm = MagicMock()
        pm.get_field_type_config.return_value = {
            'data_storage_config': {'max_size': 0}
        }
        proc.initialize(pm)
        ok, val, err = proc._process_generic_plugin_data({'k': 'v'}, 'custom', {})
        assert ok is True

    def test_schema_validation_failure_sanitizes(self):
        proc = _make_processor()
        pm = MagicMock()
        schema = {'type': 'object', 'properties': {'name': {'type': 'string'}}}
        pm.get_field_type_config.return_value = {
            'data_storage_config': {'schema': schema}
        }
        proc.initialize(pm)
        with patch('app.utils.plugin_data_processor.validate_plugin_data',
                   side_effect=SchemaValidationError('bad')), \
             patch('app.utils.plugin_data_processor.sanitize_plugin_data',
                   return_value={'name': 'clean'}) as mock_sanitize:
            ok, val, err = proc._process_generic_plugin_data({'name': 123}, 'custom', {})
        assert ok is True
        mock_sanitize.assert_called_once()

    def test_no_plugin_manager_still_returns_success(self):
        proc = _make_processor()
        ok, val, err = proc._process_generic_plugin_data({'k': 'v'}, 'custom', {})
        assert ok is True

    def test_exception_returns_false(self):
        proc = _make_processor()
        with patch.object(proc, '_extract_essential_plugin_data', side_effect=Exception('boom')):
            ok, val, err = proc._process_generic_plugin_data({'k': 'v'}, 'custom', {})
        assert ok is False


# ---------------------------------------------------------------------------
# process_plugin_field_data
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestProcessPluginFieldData:
    def test_non_plugin_field_returned_unchanged(self, app):
        with app.app_context():
            proc = _make_processor()
            with patch.object(proc, '_get_plugin_type_for_field', return_value=None):
                ok, val, err = proc.process_plugin_field_data('field_value[1]', 'hello', 1)
            assert ok is True
            assert val == 'hello'

    def test_non_json_text_field_returned_as_is(self, app):
        with app.app_context():
            proc = _make_processor()
            with patch.object(proc, '_get_plugin_type_for_field', return_value='interactive_map'), \
                 patch.object(proc, '_get_plugin_config', return_value={}):
                ok, val, err = proc.process_plugin_field_data('field_value[1]', 'plain text', 1)
            assert ok is True
            assert val == 'plain text'

    def test_empty_data_for_emergency_ops_returns_none(self, app):
        with app.app_context():
            proc = _make_processor()
            with patch.object(proc, '_get_plugin_type_for_field', return_value='emergency_operations'), \
                 patch.object(proc, '_get_plugin_config', return_value={}):
                ok, val, err = proc.process_plugin_field_data('field_value[1]', '', 1)
            assert ok is True
            assert val is None

    def test_empty_string_value_processed_as_empty_dict(self, app):
        with app.app_context():
            proc = _make_processor()
            with patch.object(proc, '_get_plugin_type_for_field', return_value='interactive_map'), \
                 patch.object(proc, '_get_plugin_config', return_value={}):
                ok, val, err = proc.process_plugin_field_data('field_value[1]', '', 1)
            assert ok is True

    def test_no_plugin_config_returns_field_value(self, app):
        with app.app_context():
            proc = _make_processor()
            with patch.object(proc, '_get_plugin_type_for_field', return_value='interactive_map'), \
                 patch.object(proc, '_get_plugin_config', return_value=None):
                ok, val, err = proc.process_plugin_field_data('field_value[1]', '{}', 1)
            assert ok is True
            assert val == '{}'

    def test_exception_returns_false(self, app):
        with app.app_context():
            proc = _make_processor()
            with patch.object(proc, '_get_plugin_type_for_field', side_effect=Exception('boom')):
                ok, val, err = proc.process_plugin_field_data('field_value[1]', '{}', 1)
            assert ok is False
            assert err is not None

    def test_valid_json_data_processed(self, app):
        with app.app_context():
            proc = _make_processor()
            data = json.dumps({'markers': [{'lat': 10, 'lng': 20}]})
            with patch.object(proc, '_get_plugin_type_for_field', return_value='interactive_map'), \
                 patch.object(proc, '_get_plugin_config', return_value={}):
                ok, val, err = proc.process_plugin_field_data('field_value[1]', data, 1)
            assert ok is True
            assert err is None


# ---------------------------------------------------------------------------
# process_form_plugin_data
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestProcessFormPluginData:
    def test_non_plugin_fields_unchanged(self, app):
        with app.app_context():
            form_data = {'name': 'John', 'email': 'j@j.com'}
            result = process_form_plugin_data(form_data)
            assert result['name'] == 'John'
            assert result['email'] == 'j@j.com'

    def test_field_without_closing_bracket_skipped(self, app):
        with app.app_context():
            form_data = {'field_value[abc': 'value'}
            result = process_form_plugin_data(form_data)
            # Doesn't match regex → stays unchanged
            assert 'field_value[abc' in result

    def test_plugin_field_processed_with_valid_return(self, app):
        with app.app_context():
            with patch.object(
                plugin_data_processor, 'process_plugin_field_data',
                return_value=(True, '{"markers": []}', None)
            ):
                form_data = {'field_value[10]': '{"markers": []}'}
                result = process_form_plugin_data(form_data)
            assert result.get('field_value[10]') == '{"markers": []}'

    def test_none_processed_value_leaves_original(self, app):
        """When processed_value is None, the original dict-copy value is preserved unchanged."""
        with app.app_context():
            with patch.object(
                plugin_data_processor, 'process_plugin_field_data',
                return_value=(True, None, None)
            ):
                form_data = {'field_value[10]': '{}', 'other': 'x'}
                result = process_form_plugin_data(form_data)
            # processed_value was None → the original copy value stays
            assert result.get('field_value[10]') == '{}'

    def test_invalid_plugin_field_adds_error(self, app):
        with app.app_context():
            with patch.object(
                plugin_data_processor, 'process_plugin_field_data',
                return_value=(False, '{}', 'Plugin data processing failed.')
            ):
                form_data = {'field_value[10]': '{}'}
                result = process_form_plugin_data(form_data)
            assert '_plugin_errors' in result

    def test_exception_during_processing_adds_error(self, app):
        with app.app_context():
            with patch.object(
                plugin_data_processor, 'process_plugin_field_data',
                side_effect=Exception('crash')
            ):
                form_data = {'field_value[10]': '{}'}
                result = process_form_plugin_data(form_data)
            assert '_plugin_errors' in result

    def test_no_errors_no_error_key(self, app):
        with app.app_context():
            form_data = {'plain_field': 'value'}
            result = process_form_plugin_data(form_data)
            assert '_plugin_errors' not in result

    def test_returns_copy_not_mutating_original(self, app):
        with app.app_context():
            form_data = {'field_value[10]': '{}'}
            with patch.object(
                plugin_data_processor, 'process_plugin_field_data',
                return_value=(True, '{}', None)
            ):
                result = process_form_plugin_data(form_data)
            # Original not mutated
            assert form_data == {'field_value[10]': '{}'}
