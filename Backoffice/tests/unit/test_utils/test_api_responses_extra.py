"""
Additional tests to reach 100% coverage on api_responses.py.

Covers the functions not exercised by test_api_responses.py:
  json_form_errors, json_ok_result, json_select_options, json_error_handler.
"""
import pytest
from unittest.mock import MagicMock, patch

from app.utils.api_responses import (
    json_form_errors,
    json_ok_result,
    json_select_options,
    json_error_handler,
)


# ---------------------------------------------------------------------------
# json_form_errors
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestJsonFormErrors:
    def test_default_message_and_400_status(self, app):
        with app.test_request_context():
            form = MagicMock()
            form.errors = {'name': ['Required'], 'email': ['Invalid email']}
            resp, status = json_form_errors(form)
            assert status == 400
            data = resp.get_json()
            assert data['error'] == 'Validation failed'
            assert data['errors'] == {'name': ['Required'], 'email': ['Invalid email']}
            assert data['success'] is False

    def test_custom_message(self, app):
        with app.test_request_context():
            form = MagicMock()
            form.errors = {}
            resp, status = json_form_errors(form, message='Please fix the form.')
            assert resp.get_json()['error'] == 'Please fix the form.'

    def test_form_without_errors_attribute_uses_empty_dict(self, app):
        with app.test_request_context():
            form = object()  # no .errors attribute
            resp, status = json_form_errors(form)
            assert status == 400
            data = resp.get_json()
            assert data['errors'] == {}

    def test_errors_dict_included_verbatim(self, app):
        with app.test_request_context():
            form = MagicMock()
            form.errors = {'field1': ['Too short', 'Invalid'], 'field2': ['Required']}
            resp, status = json_form_errors(form)
            data = resp.get_json()
            assert data['errors']['field1'] == ['Too short', 'Invalid']


# ---------------------------------------------------------------------------
# json_ok_result
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestJsonOkResult:
    def test_dict_without_success_key_merged_into_response(self, app):
        with app.test_request_context():
            resp, status = json_ok_result({'count': 5, 'items': [1, 2]})
            assert status == 200
            data = resp.get_json()
            assert data['success'] is True
            assert data['count'] == 5
            assert data['items'] == [1, 2]

    def test_dict_with_success_key_wrapped_in_data(self, app):
        with app.test_request_context():
            # When result has 'success', goes through json_ok(data=result)
            resp, status = json_ok_result({'success': True, 'count': 3})
            assert status == 200
            data = resp.get_json()
            assert data['success'] is True
            # The result dict itself is wrapped under 'data'
            assert data.get('data') == {'success': True, 'count': 3}

    def test_non_dict_result_wrapped_in_data(self, app):
        with app.test_request_context():
            resp, status = json_ok_result([1, 2, 3])
            assert status == 200
            data = resp.get_json()
            assert data['data'] == [1, 2, 3]

    def test_none_result_wrapped_in_data(self, app):
        with app.test_request_context():
            resp, status = json_ok_result(None)
            assert status == 200
            data = resp.get_json()
            assert data['success'] is True

    def test_extra_kwargs_merged_into_merged_response(self, app):
        with app.test_request_context():
            resp, status = json_ok_result({'count': 1}, page=2, total=10)
            data = resp.get_json()
            assert data['page'] == 2
            assert data['total'] == 10

    def test_extra_kwargs_on_non_dict_result(self, app):
        with app.test_request_context():
            resp, status = json_ok_result('some string', label='test')
            data = resp.get_json()
            assert data['label'] == 'test'


# ---------------------------------------------------------------------------
# json_select_options
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestJsonSelectOptions:
    def test_returns_200_with_serialized_options(self, app):
        with app.test_request_context():
            item1 = MagicMock()
            item1.id = 1
            item1.name = 'Option Alpha'
            item2 = MagicMock()
            item2.id = 2
            item2.name = 'Option Beta'

            resp, status = json_select_options([item1, item2])
            assert status == 200
            data = resp.get_json()
            assert len(data) == 2
            assert data[0]['id'] == 1
            assert data[0]['name'] == 'Option Alpha'
            assert data[1]['id'] == 2

    def test_empty_list_returns_empty_array(self, app):
        with app.test_request_context():
            resp, status = json_select_options([])
            assert status == 200
            assert resp.get_json() == []

    def test_custom_fields(self, app):
        with app.test_request_context():
            item = MagicMock()
            item.id = 10
            item.code = 'XYZ'
            resp, status = json_select_options([item], fields=('id', 'code'))
            data = resp.get_json()
            assert data[0]['code'] == 'XYZ'
            assert 'name' not in data[0]


# ---------------------------------------------------------------------------
# json_error_handler  (decorator)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestJsonErrorHandlerDecorator:
    def test_successful_view_passes_through(self, app):
        with app.test_request_context():
            @json_error_handler('TestRoute')
            def my_view():
                return 'ok', 200

            result = my_view()
            assert result == ('ok', 200)

    def test_exception_returns_500_json(self, app):
        with app.test_request_context():
            @json_error_handler('TestRoute')
            def failing_view():
                raise RuntimeError('boom')

            with patch('app.utils.api_responses.request_transaction_rollback') as mock_rb:
                resp, status = failing_view()
                mock_rb.assert_called_once_with(reason='json_error_handler')
            assert status == 500
            data = resp.get_json()
            assert 'error' in data

    def test_preserves_wrapped_function_name(self):
        @json_error_handler('SomePrefix')
        def my_named_view():
            pass

        assert my_named_view.__name__ == 'my_named_view'

    def test_custom_log_prefix_used(self, app):
        with app.test_request_context():
            @json_error_handler('MyPrefix')
            def bad_view():
                raise ValueError('oops')

            with patch('app.utils.api_responses.request_transaction_rollback'):
                resp, status = bad_view()
            assert status == 500

    def test_view_with_args_and_kwargs(self, app):
        with app.test_request_context():
            @json_error_handler('TestRoute')
            def parameterized(a, b=None):
                return {'a': a, 'b': b}, 200

            result = parameterized(1, b=2)
            assert result == ({'a': 1, 'b': 2}, 200)
