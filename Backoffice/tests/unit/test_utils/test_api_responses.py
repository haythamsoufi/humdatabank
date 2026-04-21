"""
Unit tests for api_responses helpers.
"""
import pytest

from app.utils.api_responses import (
    json_error,
    json_ok,
    json_bad_request,
    json_forbidden,
    json_not_found,
    json_server_error,
    json_auth_required,
    json_accepted,
    json_created,
    require_json_keys,
    require_json_data,
    require_json_content_type,
)


@pytest.mark.unit
class TestJsonError:
    """Test json_error and status-code variants."""

    def test_json_error_default_status(self, app):
        with app.test_request_context():
            resp, status = json_error('Something went wrong')
            assert status == 400
            data = resp.get_json()
            assert data['error'] == 'Something went wrong'

    def test_json_error_custom_status(self, app):
        with app.test_request_context():
            resp, status = json_error('Unauthorized', status=401)
            assert status == 401
            assert resp.get_json()['error'] == 'Unauthorized'

    def test_json_error_with_extra(self, app):
        with app.test_request_context():
            resp, status = json_error('Bad', status=400, field='id', code='INVALID')
            data = resp.get_json()
            assert data['error'] == 'Bad'
            assert data['field'] == 'id'
            assert data['code'] == 'INVALID'


@pytest.mark.unit
class TestJsonStatusVariants:
    """Test json_bad_request, json_forbidden, etc."""

    def test_json_bad_request(self, app):
        with app.test_request_context():
            resp, status = json_bad_request('Invalid input')
            assert status == 400
            assert resp.get_json()['error'] == 'Invalid input'

    def test_json_forbidden(self, app):
        with app.test_request_context():
            resp, status = json_forbidden('Access denied')
            assert status == 403
            assert resp.get_json()['error'] == 'Access denied'

    def test_json_not_found(self, app):
        with app.test_request_context():
            resp, status = json_not_found('Resource not found')
            assert status == 404
            assert resp.get_json()['error'] == 'Resource not found'

    def test_json_server_error(self, app):
        with app.test_request_context():
            resp, status = json_server_error('Internal error')
            assert status == 500
            assert resp.get_json()['error'] == 'Internal error'

    def test_json_auth_required(self, app):
        with app.test_request_context():
            resp, status = json_auth_required()
            assert status == 401
            assert 'Authentication' in resp.get_json()['error']


@pytest.mark.unit
class TestJsonOk:
    """Test json_ok and json_accepted, json_created."""

    def test_json_ok_no_data(self, app):
        with app.test_request_context():
            resp, status = json_ok()
            assert status == 200
            data = resp.get_json()
            assert data['success'] is True

    def test_json_ok_with_dict_data(self, app):
        with app.test_request_context():
            resp, status = json_ok({'id': 1, 'name': 'test'})
            data = resp.get_json()
            assert data['success'] is True
            assert data['id'] == 1
            assert data['name'] == 'test'

    def test_json_ok_with_non_dict_data(self, app):
        with app.test_request_context():
            resp, status = json_ok([1, 2, 3])
            data = resp.get_json()
            assert data['success'] is True
            assert data['data'] == [1, 2, 3]

    def test_json_accepted(self, app):
        with app.test_request_context():
            resp, status = json_accepted(job_id='abc')
            assert status == 202
            data = resp.get_json()
            assert data['success'] is True
            assert data['job_id'] == 'abc'

    def test_json_created(self, app):
        with app.test_request_context():
            resp, status = json_created(id=42)
            assert status == 201
            data = resp.get_json()
            assert data['success'] is True
            assert data['id'] == 42


@pytest.mark.unit
class TestRequireJsonKeys:
    """Test require_json_keys validation."""

    def test_require_json_keys_valid(self):
        result = require_json_keys({'a': 1, 'b': 2}, ['a', 'b'])
        assert result is None

    def test_require_json_keys_missing(self, app):
        result = require_json_keys({'a': 1}, ['a', 'b'])
        assert result is not None
        resp, status = result
        assert status == 400
        assert 'Missing required' in resp.get_json()['error']
        assert 'b' in resp.get_json()['error']

    def test_require_json_keys_none_value_treated_as_missing(self, app):
        result = require_json_keys({'a': 1, 'b': None}, ['a', 'b'])
        assert result is not None
        resp, status = result
        assert status == 400

    def test_require_json_keys_not_dict(self, app):
        result = require_json_keys('not a dict', ['a'])
        assert result is not None
        resp, status = result
        assert status == 400
        assert 'Invalid request body' in resp.get_json()['error']

    def test_require_json_keys_custom_message(self, app):
        result = require_json_keys({'a': 1}, ['b'], message='Custom error')
        assert result is not None
        resp, status = result
        assert resp.get_json()['error'] == 'Custom error'


@pytest.mark.unit
class TestRequireJsonData:
    """Test require_json_data validation."""

    def test_require_json_data_valid(self):
        result = require_json_data({'key': 'value'})
        assert result is None

    def test_require_json_data_empty_dict(self, app):
        result = require_json_data({})
        assert result is not None
        resp, status = result
        assert status == 400
        assert 'No data' in resp.get_json()['error'] or 'data' in resp.get_json()['error'].lower()

    def test_require_json_data_not_dict(self, app):
        result = require_json_data(None)
        assert result is not None
        resp, status = result
        assert status == 400

    def test_require_json_data_custom_message(self, app):
        result = require_json_data({}, message='Please send a body')
        assert result is not None
        assert result[1] == 400
        assert result[0].get_json()['error'] == 'Please send a body'


@pytest.mark.unit
class TestRequireJsonContentType:
    """Test require_json_content_type."""

    def test_require_json_content_type_valid(self, app):
        with app.test_request_context(
            headers={'Content-Type': 'application/json'}
        ):
            result = require_json_content_type()
            assert result is None

    def test_require_json_content_type_valid_with_charset(self, app):
        with app.test_request_context(
            headers={'Content-Type': 'application/json; charset=utf-8'}
        ):
            result = require_json_content_type()
            assert result is None

    def test_require_json_content_type_missing(self, app):
        with app.test_request_context():
            result = require_json_content_type()
            assert result is not None
            resp, status = result
            assert status == 415
            assert 'application/json' in resp.get_json()['error']

    def test_require_json_content_type_wrong_type(self, app):
        with app.test_request_context(
            headers={'Content-Type': 'text/html'}
        ):
            result = require_json_content_type()
            assert result is not None
            assert result[1] == 415
