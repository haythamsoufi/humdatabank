"""
Unit tests for api_formatting utilities.

Covers: choices_from_query, serialize_select_options, format_answer_value,
format_form_data_response, serialize_form_data_item.
"""
import pytest
import json
from datetime import datetime
from unittest.mock import MagicMock, patch

from app.utils.api_formatting import (
    choices_from_query,
    serialize_select_options,
    format_answer_value,
    format_form_data_response,
    serialize_form_data_item,
)


# ---------------------------------------------------------------------------
# choices_from_query
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestChoicesFromQuery:
    def _query(self, items):
        q = MagicMock()
        q.all.return_value = items
        return q

    def test_basic_id_name_choices(self):
        item1 = MagicMock(); item1.id = 1; item1.name = 'Alpha'
        item2 = MagicMock(); item2.id = 2; item2.name = 'Beta'
        result = choices_from_query(self._query([item1, item2]))
        assert result == [(1, 'Alpha'), (2, 'Beta')]

    def test_empty_query_returns_empty_list(self):
        result = choices_from_query(self._query([]))
        assert result == []

    def test_with_empty_option_prepended(self):
        item = MagicMock(); item.id = 1; item.name = 'Item'
        result = choices_from_query(self._query([item]), empty_option=('', 'Select...'))
        assert result[0] == ('', 'Select...')
        assert len(result) == 2

    def test_custom_value_attr(self):
        item = MagicMock(); item.code = 'US'; item.name = 'United States'
        result = choices_from_query(self._query([item]), value_attr='code')
        assert result[0][0] == 'US'

    def test_custom_label_attr(self):
        item = MagicMock(); item.id = 1; item.full_name = 'Full Name'
        result = choices_from_query(self._query([item]), label_attr='full_name')
        assert result[0][1] == 'Full Name'

    def test_label_func_overrides_label_attr(self):
        item = MagicMock(); item.id = 5; item.code = 'TST'; item.name = 'Test'
        result = choices_from_query(
            self._query([item]),
            label_func=lambda i: f'{i.code} — {i.name}'
        )
        assert result[0][1] == 'TST — Test'

    def test_label_converted_to_string(self):
        item = MagicMock(); item.id = 1; item.name = 42  # numeric name
        result = choices_from_query(self._query([item]))
        assert result[0][1] == '42'
        assert isinstance(result[0][1], str)

    def test_empty_option_alone_when_query_empty(self):
        result = choices_from_query(self._query([]), empty_option=('', '-- None --'))
        assert result == [('', '-- None --')]


# ---------------------------------------------------------------------------
# serialize_select_options
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestSerializeSelectOptions:
    def test_basic_id_name_serialization(self):
        item1 = MagicMock(); item1.id = 1; item1.name = 'Alpha'
        item2 = MagicMock(); item2.id = 2; item2.name = 'Beta'
        result = serialize_select_options([item1, item2])
        assert result == [{'id': 1, 'name': 'Alpha'}, {'id': 2, 'name': 'Beta'}]

    def test_empty_items_returns_empty_list(self):
        result = serialize_select_options([])
        assert result == []

    def test_custom_fields(self):
        item = MagicMock(); item.id = 10; item.code = 'XYZ'; item.label = 'My Label'
        result = serialize_select_options([item], fields=('id', 'code', 'label'))
        assert result == [{'id': 10, 'code': 'XYZ', 'label': 'My Label'}]

    def test_missing_attr_skipped(self):
        item = MagicMock(spec=['id'])  # only 'id' attribute
        item.id = 99
        result = serialize_select_options([item], fields=('id', 'name'))
        assert result == [{'id': 99}]  # 'name' absent because not in spec

    def test_returns_list_of_dicts(self):
        item = MagicMock(); item.id = 5; item.name = 'Test'
        result = serialize_select_options([item])
        assert isinstance(result, list)
        assert isinstance(result[0], dict)


# ---------------------------------------------------------------------------
# format_answer_value
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFormatAnswerValue:
    def test_none_returns_none(self):
        assert format_answer_value(None) is None

    def test_string_returned_unchanged(self):
        assert format_answer_value('hello') == 'hello'

    def test_empty_string_returned_unchanged(self):
        assert format_answer_value('') == ''

    def test_integer_returned_unchanged(self):
        assert format_answer_value(42) == 42

    def test_float_returned_unchanged(self):
        assert format_answer_value(3.14) == 3.14

    def test_bool_true_returned_unchanged(self):
        assert format_answer_value(True) is True

    def test_bool_false_returned_unchanged(self):
        assert format_answer_value(False) is False

    def test_list_returned_unchanged(self):
        val = [1, 2, 3]
        assert format_answer_value(val) is val

    def test_dict_returned_unchanged(self):
        val = {'key': 'value'}
        assert format_answer_value(val) is val

    def test_tuple_json_serializable_returned(self):
        # tuple is not str/int/float/bool/list/dict, but IS json-serializable
        val = (1, 2, 3)
        result = format_answer_value(val)
        # Should be returned as-is (json.dumps succeeds)
        assert result == val

    def test_non_serializable_object_converted_to_string(self):
        class MyObj:
            def __str__(self):
                return 'my-object-str'

        result = format_answer_value(MyObj())
        assert result == 'my-object-str'

    def test_datetime_converted_to_string(self):
        dt = datetime(2024, 1, 15, 10, 30)
        result = format_answer_value(dt)
        # datetime is not json-serializable -> str()
        assert isinstance(result, str)
        assert '2024' in result

    def test_json_object_string_returned_as_string(self):
        # Even though it looks like JSON, strings pass through fast path unchanged
        val = '{"key": "value"}'
        result = format_answer_value(val)
        assert result == val

    def test_json_array_string_returned_as_string(self):
        val = '[1, 2, 3]'
        result = format_answer_value(val)
        assert result == val

    def test_plain_text_string_returned_as_is(self):
        val = 'some plain text'
        result = format_answer_value(val)
        assert result == val


# ---------------------------------------------------------------------------
# format_form_data_response
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFormatFormDataResponse:
    def _item(self, data_not_available=None, not_applicable=None, value=None, disagg_data=None):
        item = MagicMock()
        item.data_not_available = data_not_available
        item.not_applicable = not_applicable
        item.value = value
        item.disagg_data = disagg_data
        return item

    def test_both_flags_none_is_available(self):
        item = self._item(data_not_available=None, not_applicable=None, value=42)
        result = format_form_data_response(item)
        assert result['data_status'] == 'available'
        assert result['answer_value'] == 42

    def test_data_not_available_true(self):
        item = self._item(data_not_available=True, not_applicable=None)
        result = format_form_data_response(item)
        assert result['data_status'] == 'data_not_available'
        assert result['answer_value'] is None

    def test_not_applicable_true(self):
        item = self._item(data_not_available=False, not_applicable=True)
        result = format_form_data_response(item)
        assert result['data_status'] == 'not_applicable'
        assert result['answer_value'] is None

    def test_has_flags_but_both_false_is_available(self):
        # data_not_available=False is not None -> has_flags=True
        # but neither flag is True -> falls through to 'available'
        item = self._item(data_not_available=False, not_applicable=False, value='text')
        result = format_form_data_response(item)
        assert result['data_status'] == 'available'
        assert result['answer_value'] == 'text'

    def test_disagg_data_dict_formatted(self):
        disagg = {'mode': 'age_group', 'values': {'0-18': 5, '18+': 10}}
        item = self._item(disagg_data=disagg)
        result = format_form_data_response(item)
        assert result['disaggregation_data'] is not None
        assert result['disaggregation_data']['mode'] == 'age_group'
        assert result['disaggregation_data']['values'] == {'0-18': 5, '18+': 10}

    def test_disagg_data_none_is_none(self):
        item = self._item(disagg_data=None)
        result = format_form_data_response(item)
        assert result['disaggregation_data'] is None

    def test_disagg_data_non_dict_truthy(self):
        # truthy but not dict -> mode=None, values={}
        item = self._item(disagg_data='invalid-string')
        result = format_form_data_response(item)
        assert result['disaggregation_data'] is not None
        assert result['disaggregation_data']['mode'] is None
        assert result['disaggregation_data']['values'] == {}

    def test_all_expected_keys_present(self):
        item = self._item()
        result = format_form_data_response(item)
        expected_keys = {'answer_value', 'disaggregation_data', 'data_status',
                         'data_not_available', 'not_applicable'}
        assert expected_keys.issubset(result.keys())

    def test_flags_passed_through_in_result(self):
        item = self._item(data_not_available=True, not_applicable=None)
        result = format_form_data_response(item)
        assert result['data_not_available'] is True
        assert result['not_applicable'] is None


# ---------------------------------------------------------------------------
# serialize_form_data_item
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestSerializeFormDataItem:
    def _make_assigned_item(self):
        item = MagicMock()
        item.id = 1
        item.form_item_id = 10
        item.data_not_available = None
        item.not_applicable = None
        item.value = 42
        item.disagg_data = None
        item.form_item = None
        item.submitted_at = datetime(2024, 1, 15, 10, 0, 0)

        status = MagicMock()
        status.id = 100
        assigned_form = MagicMock()
        assigned_form.period_name = '2024-Annual'
        status.assigned_form = assigned_form
        status.country = None
        item.assignment_entity_status = status
        return item

    def _make_public_item(self):
        item = MagicMock()
        item.id = 2
        item.form_item_id = 20
        item.data_not_available = None
        item.not_applicable = None
        item.value = 'text answer'
        item.disagg_data = None
        item.form_item = None

        submission = MagicMock()
        submission.id = 200
        submission.submitted_at = datetime(2024, 6, 1, 8, 0, 0)
        submission.country = None

        assignment = MagicMock()
        assignment.id = 50
        assignment.period_name = 'Q2 2024'
        assignment.template_id = 5
        assignment.template = MagicMock()
        assignment.template.name = 'CORE Template'
        submission.assigned_form = assignment
        item.public_submission = submission
        return item

    def test_assigned_submission_type_set(self, app):
        with app.test_request_context():
            with patch('app.utils.api_serialization.format_country_info', return_value=None), \
                 patch('app.utils.api_serialization.format_form_item_info', return_value=None):
                item = self._make_assigned_item()
                result = serialize_form_data_item(item, 'assigned')
        assert result['submission_type'] == 'assigned'
        assert result['id'] == 1

    def test_assigned_period_name(self, app):
        with app.test_request_context():
            with patch('app.utils.api_serialization.format_country_info', return_value=None), \
                 patch('app.utils.api_serialization.format_form_item_info', return_value=None):
                item = self._make_assigned_item()
                result = serialize_form_data_item(item, 'assigned')
        assert result['period_name'] == '2024-Annual'

    def test_assigned_submitted_at_isoformat(self, app):
        with app.test_request_context():
            with patch('app.utils.api_serialization.format_country_info', return_value=None), \
                 patch('app.utils.api_serialization.format_form_item_info', return_value=None):
                item = self._make_assigned_item()
                result = serialize_form_data_item(item, 'assigned')
        assert result['submitted_at'] == '2024-01-15T10:00:00'

    def test_assigned_status_info_none(self, app):
        with app.test_request_context():
            with patch('app.utils.api_serialization.format_country_info', return_value=None), \
                 patch('app.utils.api_serialization.format_form_item_info', return_value=None):
                item = self._make_assigned_item()
                item.assignment_entity_status = None
                result = serialize_form_data_item(item, 'assigned')
        assert result['submission_id'] is None
        assert result['period_name'] is None

    def test_assigned_with_form_item(self, app):
        with app.test_request_context():
            with patch('app.utils.api_serialization.format_country_info', return_value=None), \
                 patch('app.utils.api_serialization.format_form_item_info', return_value={'info': True}):
                item = self._make_assigned_item()
                form_item = MagicMock()
                form_item.form_section = MagicMock()
                form_item.template = MagicMock()
                item.form_item = form_item
                result = serialize_form_data_item(item, 'assigned')
        assert result['form_item_info'] == {'info': True}

    def test_public_submission_type_set(self, app):
        with app.test_request_context():
            with patch('app.utils.api_serialization.format_country_info', return_value=None), \
                 patch('app.utils.api_serialization.format_form_item_info', return_value=None):
                item = self._make_public_item()
                result = serialize_form_data_item(item, 'public')
        assert result['submission_type'] == 'public'
        assert result['id'] == 2

    def test_public_template_info(self, app):
        with app.test_request_context():
            with patch('app.utils.api_serialization.format_country_info', return_value=None), \
                 patch('app.utils.api_serialization.format_form_item_info', return_value=None):
                item = self._make_public_item()
                result = serialize_form_data_item(item, 'public')
        assert result['template_id'] == 5
        assert result['template_name'] == 'CORE Template'

    def test_public_submission_none_fields_are_none(self, app):
        with app.test_request_context():
            with patch('app.utils.api_serialization.format_country_info', return_value=None), \
                 patch('app.utils.api_serialization.format_form_item_info', return_value=None):
                item = self._make_public_item()
                item.public_submission = None
                result = serialize_form_data_item(item, 'public')
        assert result['submission_id'] is None
        assert result['submitted_at'] is None

    def test_public_submitted_at_isoformat(self, app):
        with app.test_request_context():
            with patch('app.utils.api_serialization.format_country_info', return_value=None), \
                 patch('app.utils.api_serialization.format_form_item_info', return_value=None):
                item = self._make_public_item()
                result = serialize_form_data_item(item, 'public')
        assert result['submitted_at'] == '2024-06-01T08:00:00'

    def test_assigned_no_submitted_at(self, app):
        with app.test_request_context():
            with patch('app.utils.api_serialization.format_country_info', return_value=None), \
                 patch('app.utils.api_serialization.format_form_item_info', return_value=None):
                item = self._make_assigned_item()
                item.submitted_at = None
                result = serialize_form_data_item(item, 'assigned')
        assert result['submitted_at'] is None
