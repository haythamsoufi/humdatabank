"""
Unit tests for api_helpers (get_json_safe).
"""
import pytest

from app.utils.api_helpers import get_json_safe


@pytest.mark.unit
class TestGetJsonSafe:
    """Test get_json_safe parsing."""

    def test_valid_json_dict(self, app):
        with app.test_request_context(
            path='/api/foo',
            method='POST',
            data='{"a": 1, "b": "x"}',
            content_type='application/json'
        ):
            result = get_json_safe()
            assert result == {'a': 1, 'b': 'x'}

    def test_empty_json_object(self, app):
        with app.test_request_context(
            path='/api/foo',
            method='POST',
            data='{}',
            content_type='application/json'
        ):
            result = get_json_safe()
            assert result == {}

    def test_not_json_returns_empty_dict(self, app):
        with app.test_request_context(path='/api/foo'):
            result = get_json_safe()
            assert result == {}

    def test_invalid_json_returns_empty_dict(self, app):
        with app.test_request_context(
            path='/api/foo',
            method='POST',
            data='not valid json',
            content_type='application/json'
        ):
            result = get_json_safe()
            assert result == {}

    def test_json_array_returns_default(self, app):
        with app.test_request_context(
            path='/api/foo',
            method='POST',
            data='[1, 2, 3]',
            content_type='application/json'
        ):
            result = get_json_safe()
            assert result == {}

    def test_json_array_with_custom_default(self, app):
        with app.test_request_context(
            path='/api/foo',
            method='POST',
            data='[1, 2]',
            content_type='application/json'
        ):
            # default=None means "no default" - returns {} when body is not a dict
            result = get_json_safe(default=None)
            assert result == {}
            # explicit default is used when body is not a dict
            result2 = get_json_safe(default={'items': []})
            assert result2 == {'items': []}

    def test_custom_default_when_not_json(self, app):
        with app.test_request_context(path='/api/foo'):
            result = get_json_safe(default={'fallback': True})
            assert result == {'fallback': True}
