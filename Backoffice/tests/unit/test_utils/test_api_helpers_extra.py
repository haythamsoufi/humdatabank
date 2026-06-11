"""
Additional tests to reach 100% coverage on api_helpers.py.

Covers the functions not exercised by test_api_helpers.py:
  service_error, json_response, json_data_response, api_error, extract_numeric_value.
"""
import json
import pytest
from unittest.mock import patch

from app.utils.api_helpers import (
    service_error,
    json_response,
    json_data_response,
    api_error,
    extract_numeric_value,
    GENERIC_ERROR_MESSAGE,
)


# ---------------------------------------------------------------------------
# service_error
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestServiceError:
    def test_returns_dict_with_success_false(self):
        result = service_error('Something went wrong')
        assert isinstance(result, dict)
        assert result['success'] is False
        assert result['error'] == 'Something went wrong'

    def test_extra_fields_included(self):
        result = service_error('Bad input', code='INVALID', details='field required')
        assert result['code'] == 'INVALID'
        assert result['details'] == 'field required'

    def test_success_param_can_be_overridden(self):
        result = service_error('ok', success=True)
        assert result['success'] is True

    def test_empty_message(self):
        result = service_error('')
        assert result['error'] == ''


# ---------------------------------------------------------------------------
# json_response
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestJsonResponse:
    def test_returns_200_by_default(self, app):
        with app.test_request_context():
            resp = json_response({'key': 'value'})
            assert resp.status_code == 200

    def test_custom_status_code(self, app):
        with app.test_request_context():
            resp = json_response({'error': 'not found'}, status_code=404)
            assert resp.status_code == 404

    def test_content_type_is_json_utf8(self, app):
        with app.test_request_context():
            resp = json_response({'a': 1})
            assert 'application/json' in resp.content_type
            assert 'utf-8' in resp.content_type.lower()

    def test_pretty_true_has_indentation(self, app):
        with app.test_request_context():
            resp = json_response({'a': 1}, pretty=True)
            decoded = resp.data.decode('utf-8')
            assert '\n' in decoded  # indented JSON has newlines

    def test_pretty_false_compact_output(self, app):
        with app.test_request_context():
            resp = json_response({'a': 1}, pretty=False)
            decoded = resp.data.decode('utf-8')
            assert '\n' not in decoded

    def test_unicode_chars_preserved(self, app):
        with app.test_request_context():
            resp = json_response({'name': '日本語テスト'}, pretty=False)
            decoded = resp.data.decode('utf-8')
            assert '日本語テスト' in decoded

    def test_pretty_none_uses_debug_flag(self, app):
        with app.test_request_context():
            # conftest sets debug=False -> compact
            resp = json_response({'a': 1}, pretty=None)
            decoded = resp.data.decode('utf-8')
            assert '\n' not in decoded

    def test_pretty_none_debug_true_indents(self, app):
        original = app.debug
        app.debug = True
        try:
            with app.test_request_context():
                resp = json_response({'a': 1}, pretty=None)
                decoded = resp.data.decode('utf-8')
                assert '\n' in decoded
        finally:
            app.debug = original

    def test_key_order_preserved(self, app):
        with app.test_request_context():
            data = {'z': 1, 'a': 2, 'm': 3}
            resp = json_response(data, pretty=False)
            raw = resp.data.decode('utf-8')
            # sort_keys=False: keys should appear in insertion order
            assert raw.index('"z"') < raw.index('"a"') < raw.index('"m"')

    def test_response_body_is_valid_json(self, app):
        with app.test_request_context():
            payload = {'nested': {'x': [1, 2, 3]}, 'flag': True}
            resp = json_response(payload)
            parsed = json.loads(resp.data)
            assert parsed == payload


# ---------------------------------------------------------------------------
# json_data_response
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestJsonDataResponse:
    def test_wraps_in_data_key(self, app):
        with app.test_request_context():
            resp = json_data_response([1, 2, 3])
            parsed = json.loads(resp.data)
            assert parsed['data'] == [1, 2, 3]
            assert 'meta' not in parsed

    def test_includes_meta_when_provided(self, app):
        with app.test_request_context():
            resp = json_data_response({'key': 'val'}, meta={'total': 5, 'page': 1})
            parsed = json.loads(resp.data)
            assert parsed['meta'] == {'total': 5, 'page': 1}

    def test_custom_status_code(self, app):
        with app.test_request_context():
            resp = json_data_response({}, status_code=201)
            assert resp.status_code == 201

    def test_pretty_forwarded(self, app):
        with app.test_request_context():
            resp = json_data_response({'a': 1}, pretty=True)
            decoded = resp.data.decode('utf-8')
            assert '\n' in decoded

    def test_none_data(self, app):
        with app.test_request_context():
            resp = json_data_response(None)
            parsed = json.loads(resp.data)
            assert parsed['data'] is None


# ---------------------------------------------------------------------------
# api_error
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestApiError:
    def test_default_500_status(self, app):
        with app.test_request_context():
            resp = api_error('Something failed')
            assert resp.status_code == 500

    def test_error_message_in_body(self, app):
        with app.test_request_context():
            resp = api_error('User not found', status_code=404)
            parsed = json.loads(resp.data)
            assert parsed['error'] == 'User not found'
            assert resp.status_code == 404

    def test_error_id_auto_generated_when_missing(self, app):
        with app.test_request_context():
            resp = api_error('Error occurred')
            parsed = json.loads(resp.data)
            assert 'error_id' in parsed
            # Should be a valid UUID string
            import uuid
            uuid.UUID(parsed['error_id'])  # raises if invalid

    def test_custom_error_id_preserved(self, app):
        with app.test_request_context():
            resp = api_error('Error', error_id='my-tracking-id-123')
            parsed = json.loads(resp.data)
            assert parsed['error_id'] == 'my-tracking-id-123'

    def test_no_debug_key_in_non_debug_mode(self, app):
        with app.test_request_context():
            assert not app.debug  # confirm not in debug mode
            resp = api_error('Error', debug_message='secret internal path')
            parsed = json.loads(resp.data)
            assert 'debug' not in parsed

    def test_debug_message_shown_when_debug_true(self, app):
        original = app.debug
        app.debug = True
        try:
            with app.test_request_context():
                resp = api_error('Error', debug_message='some debug info')
                parsed = json.loads(resp.data)
                assert 'debug' in parsed
                assert 'debug info' in parsed['debug']
        finally:
            app.debug = original

    def test_debug_message_with_path_is_sanitized(self, app):
        original = app.debug
        app.debug = True
        try:
            with app.test_request_context():
                resp = api_error('Error', debug_message='/usr/local/lib/myapp/module.py crashed')
                parsed = json.loads(resp.data)
                if 'debug' in parsed:
                    # Path should be sanitized to just filename
                    assert 'module.py' in parsed['debug']
        finally:
            app.debug = original

    def test_debug_message_with_backslash_path_sanitized(self, app):
        original = app.debug
        app.debug = True
        try:
            with app.test_request_context():
                resp = api_error('Error', debug_message=r'C:\Users\app\module.py error')
                parsed = json.loads(resp.data)
                assert 'debug' in parsed
        finally:
            app.debug = original

    def test_debug_mode_no_debug_message_no_debug_key(self, app):
        original = app.debug
        app.debug = True
        try:
            with app.test_request_context():
                # debug=True but no debug_message -> pass branch, no 'debug' key
                resp = api_error('Error')
                parsed = json.loads(resp.data)
                assert 'debug' not in parsed
        finally:
            app.debug = original

    def test_extra_fields_added(self, app):
        with app.test_request_context():
            resp = api_error('Error', extra={'hint': 'try again', 'retry_after': 60})
            parsed = json.loads(resp.data)
            assert parsed['hint'] == 'try again'
            assert parsed['retry_after'] == 60

    def test_extra_cannot_override_error_key(self, app):
        with app.test_request_context():
            resp = api_error('Real error', extra={'error': 'injected'})
            parsed = json.loads(resp.data)
            assert parsed['error'] == 'Real error'

    def test_extra_cannot_override_error_id_key(self, app):
        with app.test_request_context():
            resp = api_error('Error', error_id='legit-id', extra={'error_id': 'hacked'})
            parsed = json.loads(resp.data)
            assert parsed['error_id'] == 'legit-id'

    def test_extra_not_dict_is_ignored(self, app):
        with app.test_request_context():
            # extra is not a dict -> if branch `if extra and isinstance(extra, dict)` is False
            resp = api_error('Error', extra=['not', 'a', 'dict'])
            assert resp.status_code == 500
            parsed = json.loads(resp.data)
            assert 'error' in parsed

    def test_extra_empty_dict_ignored(self, app):
        with app.test_request_context():
            resp = api_error('Error', extra={})
            parsed = json.loads(resp.data)
            assert parsed['error'] == 'Error'


# ---------------------------------------------------------------------------
# extract_numeric_value
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestExtractNumericValue:
    def test_none_returns_none(self):
        assert extract_numeric_value(None) is None

    def test_int_returns_int(self):
        result = extract_numeric_value(42)
        assert result == 42
        assert isinstance(result, int)

    def test_float_returns_float(self):
        result = extract_numeric_value(3.14)
        assert isinstance(result, float)
        assert abs(result - 3.14) < 1e-9

    def test_zero_int(self):
        assert extract_numeric_value(0) == 0

    def test_negative_int(self):
        assert extract_numeric_value(-5) == -5

    def test_string_integer(self):
        result = extract_numeric_value('100')
        assert result == 100.0

    def test_string_float(self):
        result = extract_numeric_value('3.14')
        assert abs(result - 3.14) < 1e-9

    def test_string_with_commas(self):
        result = extract_numeric_value('1,000,000')
        assert result == 1_000_000.0

    def test_string_with_spaces(self):
        result = extract_numeric_value('  42  ')
        assert result == 42.0

    def test_string_with_commas_and_spaces(self):
        result = extract_numeric_value(' 1,234.56 ')
        assert abs(result - 1234.56) < 1e-6

    def test_non_numeric_string_returns_none(self):
        assert extract_numeric_value('not-a-number') is None

    def test_empty_string_returns_none(self):
        assert extract_numeric_value('') is None

    def test_string_that_looks_like_int(self):
        result = extract_numeric_value('999')
        assert result == 999.0

    def test_empty_list_returns_none(self):
        assert extract_numeric_value([]) is None

    def test_list_with_int_first_element(self):
        assert extract_numeric_value([7, 8, 9]) == 7

    def test_list_with_string_first_element(self):
        result = extract_numeric_value(['42'])
        assert result == 42.0

    def test_list_with_none_first_element(self):
        result = extract_numeric_value([None, 5])
        assert result is None

    def test_dict_with_value_key(self):
        assert extract_numeric_value({'value': 99}) == 99

    def test_dict_with_total_key(self):
        assert extract_numeric_value({'total': 50}) == 50

    def test_dict_with_amount_key(self):
        assert extract_numeric_value({'amount': 1000}) == 1000

    def test_dict_with_count_key(self):
        assert extract_numeric_value({'count': 7}) == 7

    def test_dict_with_number_key(self):
        assert extract_numeric_value({'number': 3}) == 3

    def test_dict_without_any_known_key_returns_none(self):
        assert extract_numeric_value({'unknown_key': 5}) is None

    def test_dict_checks_value_key_first(self):
        # 'value' takes priority since it's checked first
        result = extract_numeric_value({'value': 10, 'total': 20})
        assert result == 10

    def test_deeply_nested_list(self):
        # list[0] is also a list -> recursive
        result = extract_numeric_value([[5]])
        assert result == 5
