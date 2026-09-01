"""
Comprehensive tests for app/services/form_data_service.py

Targets significant coverage improvement of:
- FormDataService static/class utility methods
- save_simple_field, bulk_save_fields
- _is_public_submission, _get_data_model, _get_data_query_filter
- _calculate_direct_total, _calculate_total_from_values
- _has_meaningful_data
- should_create_data_availability_entry (static)
- create_data_availability_value (static)
- parse_stored_value (static)
- get_english_field_name
- _process_question_value (request-context methods)
- _add_indirect_reach_to_question
- _check_for_field_clearing_signals
- _is_verbose_logging_enabled
- _commit_or_flush
- _clear_ai_validation_for_form_data
- _validate_required_field
- _validate_section
- _validate_for_submission
- _validate_repeat_section
- _is_repeat_instance_complete
- FormDataService._is_auto_managed_request
"""
import base64
import json
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from flask import g


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_form_data_entry(
    value=None,
    numeric_value=None,
    disagg_data=None,
    disagg_type=None,
    data_not_available=False,
    not_applicable=False,
    prefilled_value=None,
    prefilled_disagg_data=None,
    imputed_value=None,
    imputed_disagg_data=None,
):
    entry = MagicMock()
    entry.value = value
    entry.numeric_value = numeric_value
    entry.disagg_data = disagg_data
    entry.disagg_type = disagg_type
    entry.data_not_available = data_not_available
    entry.not_applicable = not_applicable
    entry.prefilled_value = prefilled_value
    entry.prefilled_disagg_data = prefilled_disagg_data
    entry.imputed_value = imputed_value
    entry.imputed_disagg_data = imputed_disagg_data
    entry.id = 99
    entry.get_effective_value = MagicMock(return_value=value)
    return entry


def _make_mock_oes(name="AssignmentEntityStatus"):
    """Create a mock assignment entity status or public submission."""
    obj = MagicMock()
    obj.__class__.__name__ = name
    obj.id = 1
    obj.status = "in_progress"
    return obj


# ─────────────────────────────────────────────────────────────────────────────
# get_english_field_name
# ─────────────────────────────────────────────────────────────────────────────

class TestGetEnglishFieldName:
    def test_returns_label(self):
        from app.services.forms.data_service import get_english_field_name
        item = MagicMock()
        item.label = "My Field"
        assert get_english_field_name(item) == "My Field"

    def test_returns_none_when_label_none(self):
        from app.services.forms.data_service import get_english_field_name
        item = MagicMock()
        item.label = None
        assert get_english_field_name(item) is None


# ─────────────────────────────────────────────────────────────────────────────
# FormDataService static utility methods
# ─────────────────────────────────────────────────────────────────────────────

class TestFormDataServiceStaticMethods:
    def test_should_create_data_availability_entry_with_value(self):
        from app.services.forms.data_service import FormDataService
        assert FormDataService.should_create_data_availability_entry("hello", False, False) is True

    def test_should_create_data_availability_entry_none_value_no_flags(self):
        from app.services.forms.data_service import FormDataService
        assert FormDataService.should_create_data_availability_entry(None, False, False) is False

    def test_should_create_data_availability_entry_data_not_available_flag(self):
        from app.services.forms.data_service import FormDataService
        assert FormDataService.should_create_data_availability_entry(None, True, False) is True

    def test_should_create_data_availability_entry_not_applicable_flag(self):
        from app.services.forms.data_service import FormDataService
        assert FormDataService.should_create_data_availability_entry(None, False, True) is True

    def test_create_data_availability_value_data_not_available(self):
        from app.services.forms.data_service import FormDataService
        assert FormDataService.create_data_availability_value("X", True, False) == "data_not_available"

    def test_create_data_availability_value_not_applicable(self):
        from app.services.forms.data_service import FormDataService
        assert FormDataService.create_data_availability_value("X", False, True) == "not_applicable"

    def test_create_data_availability_value_returns_value(self):
        from app.services.forms.data_service import FormDataService
        assert FormDataService.create_data_availability_value("42", False, False) == "42"

    def test_parse_stored_value_none(self):
        from app.services.forms.data_service import FormDataService
        assert FormDataService.parse_stored_value(None) is None

    def test_parse_stored_value_data_not_available(self):
        from app.services.forms.data_service import FormDataService
        result = FormDataService.parse_stored_value("data_not_available")
        assert result == {"data_not_available": True}

    def test_parse_stored_value_not_applicable(self):
        from app.services.forms.data_service import FormDataService
        result = FormDataService.parse_stored_value("not_applicable")
        assert result == {"not_applicable": True}

    def test_parse_stored_value_regular_value(self):
        from app.services.forms.data_service import FormDataService
        result = FormDataService.parse_stored_value("42")
        assert result == "42"


# ─────────────────────────────────────────────────────────────────────────────
# FormDataService._is_public_submission
# ─────────────────────────────────────────────────────────────────────────────

class TestIsPublicSubmission:
    def test_public_submission_returns_true(self):
        from app.services.forms.data_service import FormDataService
        obj = _make_mock_oes("PublicSubmission")
        assert FormDataService._is_public_submission(obj) is True

    def test_assignment_entity_status_returns_false(self):
        from app.services.forms.data_service import FormDataService
        obj = _make_mock_oes("AssignmentEntityStatus")
        assert FormDataService._is_public_submission(obj) is False

    def test_other_class_returns_false(self):
        from app.services.forms.data_service import FormDataService
        obj = _make_mock_oes("SomeOtherClass")
        assert FormDataService._is_public_submission(obj) is False


# ─────────────────────────────────────────────────────────────────────────────
# FormDataService._get_submission_id
# ─────────────────────────────────────────────────────────────────────────────

class TestGetSubmissionId:
    def test_public_submission_returns_id(self):
        from app.services.forms.data_service import FormDataService
        obj = _make_mock_oes("PublicSubmission")
        obj.id = 42
        assert FormDataService._get_submission_id(obj) == 42

    def test_assignment_entity_status_returns_id(self):
        from app.services.forms.data_service import FormDataService
        obj = _make_mock_oes("AssignmentEntityStatus")
        obj.id = 17
        assert FormDataService._get_submission_id(obj) == 17


# ─────────────────────────────────────────────────────────────────────────────
# FormDataService._get_data_model
# ─────────────────────────────────────────────────────────────────────────────

class TestGetDataModel:
    def test_returns_form_data_for_aes(self, app):
        from app.services.forms.data_service import FormDataService
        from app.models import FormData
        with app.app_context():
            obj = _make_mock_oes("AssignmentEntityStatus")
            model = FormDataService._get_data_model(obj)
            assert model is FormData

    def test_returns_form_data_for_public_submission(self, app):
        from app.services.forms.data_service import FormDataService
        from app.models import FormData
        with app.app_context():
            obj = _make_mock_oes("PublicSubmission")
            model = FormDataService._get_data_model(obj)
            assert model is FormData


# ─────────────────────────────────────────────────────────────────────────────
# FormDataService._get_data_query_filter
# ─────────────────────────────────────────────────────────────────────────────

class TestGetDataQueryFilter:
    def test_aes_filter_uses_assignment_entity_status_id(self):
        from app.services.forms.data_service import FormDataService
        obj = _make_mock_oes("AssignmentEntityStatus")
        obj.id = 5
        result = FormDataService._get_data_query_filter(obj, form_item_id=10)
        assert result == {"assignment_entity_status_id": 5, "form_item_id": 10}

    def test_public_submission_filter_uses_public_submission_id(self):
        from app.services.forms.data_service import FormDataService
        obj = _make_mock_oes("PublicSubmission")
        obj.id = 7
        result = FormDataService._get_data_query_filter(obj, form_item_id=15)
        assert result == {"public_submission_id": 7, "form_item_id": 15}


# ─────────────────────────────────────────────────────────────────────────────
# FormDataService._calculate_direct_total
# ─────────────────────────────────────────────────────────────────────────────

class TestCalculateDirectTotal:
    def test_dict_values_summed(self):
        from app.services.forms.data_service import FormDataService
        result = FormDataService._calculate_direct_total({"male": 30, "female": 70})
        assert result == 100

    def test_dict_with_non_numeric_skipped(self):
        from app.services.forms.data_service import FormDataService
        result = FormDataService._calculate_direct_total({"male": 30, "label": "N/A"})
        assert result == 30

    def test_numeric_value_returned_directly(self):
        from app.services.forms.data_service import FormDataService
        assert FormDataService._calculate_direct_total(100) == 100
        assert FormDataService._calculate_direct_total(3.14) == 3.14

    def test_none_returns_zero(self):
        from app.services.forms.data_service import FormDataService
        assert FormDataService._calculate_direct_total(None) == 0

    def test_string_returns_zero(self):
        from app.services.forms.data_service import FormDataService
        assert FormDataService._calculate_direct_total("not_a_number") == 0


# ─────────────────────────────────────────────────────────────────────────────
# FormDataService._calculate_total_from_values
# ─────────────────────────────────────────────────────────────────────────────

class TestCalculateTotalFromValues:
    def test_sums_values_excluding_indirect(self):
        from app.services.forms.data_service import FormDataService
        result = FormDataService._calculate_total_from_values(
            {"male": 30, "female": 70, "indirect": 50}
        )
        assert result == 100

    def test_sums_values_excluding_disability(self):
        from app.services.forms.data_service import FormDataService
        result = FormDataService._calculate_total_from_values(
            {"total": 100, "disability": {"d": True}}
        )
        assert result == 100

    def test_empty_dict_returns_zero(self):
        from app.services.forms.data_service import FormDataService
        assert FormDataService._calculate_total_from_values({}) == 0

    def test_non_numeric_skipped(self):
        from app.services.forms.data_service import FormDataService
        result = FormDataService._calculate_total_from_values(
            {"a": "text", "b": 10}
        )
        assert result == 10


# ─────────────────────────────────────────────────────────────────────────────
# FormDataService._has_meaningful_data
# ─────────────────────────────────────────────────────────────────────────────

class TestHasMeaningfulData:
    def test_none_entry_returns_false(self):
        from app.services.forms.data_service import FormDataService
        assert FormDataService._has_meaningful_data(None) is False

    def test_data_not_available_flag_is_meaningful(self):
        from app.services.forms.data_service import FormDataService
        entry = _make_form_data_entry(data_not_available=True)
        assert FormDataService._has_meaningful_data(entry) is True

    def test_not_applicable_flag_is_meaningful(self):
        from app.services.forms.data_service import FormDataService
        entry = _make_form_data_entry(not_applicable=True)
        assert FormDataService._has_meaningful_data(entry) is True

    def test_none_value_no_flags_returns_false(self):
        from app.services.forms.data_service import FormDataService
        entry = _make_form_data_entry(value=None)
        assert FormDataService._has_meaningful_data(entry) is False

    def test_string_value_is_meaningful(self):
        from app.services.forms.data_service import FormDataService
        entry = _make_form_data_entry(value="100")
        assert FormDataService._has_meaningful_data(entry) is True

    def test_empty_string_value_not_meaningful(self):
        from app.services.forms.data_service import FormDataService
        entry = _make_form_data_entry(value="")
        assert FormDataService._has_meaningful_data(entry) is False

    def test_none_string_value_not_meaningful(self):
        from app.services.forms.data_service import FormDataService
        entry = _make_form_data_entry(value="None")
        assert FormDataService._has_meaningful_data(entry) is False

    def test_null_string_value_not_meaningful(self):
        from app.services.forms.data_service import FormDataService
        entry = _make_form_data_entry(value="null")
        assert FormDataService._has_meaningful_data(entry) is False

    def test_disagg_data_dict_with_values_is_meaningful(self):
        from app.services.forms.data_service import FormDataService
        entry = _make_form_data_entry(disagg_data={"male": 10, "female": 20})
        assert FormDataService._has_meaningful_data(entry) is True

    def test_disagg_data_empty_dict_not_meaningful(self):
        from app.services.forms.data_service import FormDataService
        entry = _make_form_data_entry(disagg_data={})
        assert FormDataService._has_meaningful_data(entry) is False

    def test_prefilled_value_is_meaningful(self):
        from app.services.forms.data_service import FormDataService
        entry = _make_form_data_entry(prefilled_value="100")
        assert FormDataService._has_meaningful_data(entry) is True

    def test_imputed_value_is_meaningful(self):
        from app.services.forms.data_service import FormDataService
        entry = _make_form_data_entry(imputed_value="50")
        assert FormDataService._has_meaningful_data(entry) is True

    def test_prefilled_disagg_data_is_meaningful(self):
        from app.services.forms.data_service import FormDataService
        entry = _make_form_data_entry(prefilled_disagg_data={"mode": "total", "values": {"total": 10}})
        assert FormDataService._has_meaningful_data(entry) is True

    def test_imputed_disagg_data_is_meaningful(self):
        from app.services.forms.data_service import FormDataService
        entry = _make_form_data_entry(imputed_disagg_data={"mode": "total", "values": {"total": 5}})
        assert FormDataService._has_meaningful_data(entry) is True

    def test_zero_integer_is_meaningful(self):
        from app.services.forms.data_service import FormDataService
        entry = _make_form_data_entry(disagg_data=0)
        # 0 as a number is meaningful
        assert FormDataService._has_meaningful_data(entry) is True

    def test_value_with_json_structure_parsed(self):
        from app.services.forms.data_service import FormDataService
        entry = _make_form_data_entry(
            value='{"mode": "total", "values": {"total": 100}}'
        )
        assert FormDataService._has_meaningful_data(entry) is True

    def test_value_with_empty_json_list_not_meaningful(self):
        from app.services.forms.data_service import FormDataService
        entry = _make_form_data_entry(value='[]')
        assert FormDataService._has_meaningful_data(entry) is False

    def test_value_with_json_list_is_meaningful(self):
        from app.services.forms.data_service import FormDataService
        entry = _make_form_data_entry(value='["option_a"]')
        assert FormDataService._has_meaningful_data(entry) is True

    def test_disagg_data_list_with_items_meaningful(self):
        from app.services.forms.data_service import FormDataService
        entry = _make_form_data_entry(disagg_data=["a", "b"])
        assert FormDataService._has_meaningful_data(entry) is True

    def test_disagg_data_empty_list_not_meaningful(self):
        from app.services.forms.data_service import FormDataService
        entry = _make_form_data_entry(disagg_data=[])
        assert FormDataService._has_meaningful_data(entry) is False

    def test_disagg_data_with_nested_values_struct(self):
        from app.services.forms.data_service import FormDataService
        entry = _make_form_data_entry(
            disagg_data={"values": {"total": 42}}
        )
        assert FormDataService._has_meaningful_data(entry) is True

    def test_disagg_data_with_nested_empty_values_struct(self):
        from app.services.forms.data_service import FormDataService
        entry = _make_form_data_entry(
            disagg_data={"values": {}}
        )
        assert FormDataService._has_meaningful_data(entry) is False


# ─────────────────────────────────────────────────────────────────────────────
# FormDataService._is_verbose_logging_enabled
# ─────────────────────────────────────────────────────────────────────────────

class TestIsVerboseLoggingEnabled:
    def test_returns_false_outside_request_context(self):
        from app.services.forms.data_service import FormDataService
        # Not in request context
        assert FormDataService._is_verbose_logging_enabled() is False

    def test_returns_false_when_config_false(self, app):
        from app.services.forms.data_service import FormDataService
        with app.app_context():
            with app.test_request_context('/'):
                app.config['VERBOSE_FORM_DATA_LOGGING'] = False
                assert FormDataService._is_verbose_logging_enabled() is False

    def test_returns_true_when_config_true(self, app):
        from app.services.forms.data_service import FormDataService
        with app.app_context():
            with app.test_request_context('/'):
                app.config['VERBOSE_FORM_DATA_LOGGING'] = True
                result = FormDataService._is_verbose_logging_enabled()
                assert result is True
                # Reset
                app.config['VERBOSE_FORM_DATA_LOGGING'] = False


# ─────────────────────────────────────────────────────────────────────────────
# FormDataService._is_auto_managed_request
# ─────────────────────────────────────────────────────────────────────────────

class TestIsAutoManagedRequest:
    def test_returns_false_outside_request_context(self):
        from app.services.forms.data_service import FormDataService
        assert FormDataService._is_auto_managed_request() is False

    def test_returns_false_when_not_auto_managed(self, app):
        from app.services.forms.data_service import FormDataService
        with app.app_context():
            with app.test_request_context('/'):
                assert FormDataService._is_auto_managed_request() is False

    def test_returns_true_when_auto_managed(self, app):
        from app.services.forms.data_service import FormDataService
        with app.app_context():
            with app.test_request_context('/'):
                g._auto_txn_managed = True
                assert FormDataService._is_auto_managed_request() is True


# ─────────────────────────────────────────────────────────────────────────────
# FormDataService._process_question_value
# ─────────────────────────────────────────────────────────────────────────────

class TestProcessQuestionValue:
    def _make_question(self, question_type):
        q = MagicMock()
        q.type = question_type
        q.label = "Test Question"
        return q

    def test_none_returns_none(self, app):
        from app.services.forms.data_service import FormDataService
        with app.test_request_context('/'):
            q = self._make_question("text")
            assert FormDataService._process_question_value(q, None, "field") is None

    def test_text_type(self, app):
        from app.services.forms.data_service import FormDataService
        with app.test_request_context('/'):
            q = self._make_question("text")
            result = FormDataService._process_question_value(q, "hello", "field")
            assert result == "hello"

    def test_text_type_empty_string_returns_none(self, app):
        from app.services.forms.data_service import FormDataService
        with app.test_request_context('/'):
            q = self._make_question("text")
            result = FormDataService._process_question_value(q, "   ", "field")
            assert result is None

    def test_number_type_valid(self, app):
        from app.services.forms.data_service import FormDataService
        with app.test_request_context('/'):
            q = self._make_question("number")
            result = FormDataService._process_question_value(q, "42", "field")
            assert result == "42"

    def test_number_type_invalid_returns_none(self, app):
        from app.services.forms.data_service import FormDataService
        with app.test_request_context('/'):
            q = self._make_question("number")
            result = FormDataService._process_question_value(q, "abc", "field")
            assert result is None

    def test_percentage_type_valid(self, app):
        from app.services.forms.data_service import FormDataService
        with app.test_request_context('/'):
            q = self._make_question("percentage")
            result = FormDataService._process_question_value(q, "75.5", "field")
            assert result == "75.5"

    def test_percentage_type_invalid_returns_none(self, app):
        from app.services.forms.data_service import FormDataService
        with app.test_request_context('/'):
            q = self._make_question("percentage")
            result = FormDataService._process_question_value(q, "not_a_number", "field")
            assert result is None

    def test_checkbox_type_true(self, app):
        from app.services.forms.data_service import FormDataService
        with app.test_request_context('/'):
            q = self._make_question("CHECKBOX")
            result = FormDataService._process_question_value(q, "on", "field")
            assert result == "true"

    def test_checkbox_type_false(self, app):
        from app.services.forms.data_service import FormDataService
        with app.test_request_context('/'):
            q = self._make_question("CHECKBOX")
            result = FormDataService._process_question_value(q, "", "field")
            assert result == "false"

    def test_multiple_choice_type(self, app):
        from app.services.forms.data_service import FormDataService
        with app.test_request_context('/test', data={"field": ["opt_a", "opt_b"]}, method="POST"):
            q = self._make_question("multiple_choice")
            result = FormDataService._process_question_value(q, "opt_a", "field")
            parsed = json.loads(result)
            assert "opt_a" in parsed
            assert "opt_b" in parsed

    def test_multiple_choice_empty_returns_none(self, app):
        from app.services.forms.data_service import FormDataService
        with app.test_request_context('/test', method="POST"):
            q = self._make_question("multiple_choice")
            result = FormDataService._process_question_value(q, "opt_a", "field_with_no_list")
            # No items in the list
            assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# FormDataService emergency operations metadata
# ─────────────────────────────────────────────────────────────────────────────

class TestEmergencyOperationsMetadata:
    def _make_emergency_question(self):
        q = MagicMock()
        q.is_question = True
        q.lookup_list_id = 'emergency_operations'
        q.id = 1313
        return q

    def test_parse_emergency_metadata_from_display_with_code(self, app):
        from app.services.forms.data_service import FormDataService

        with app.app_context():
            meta = FormDataService._parse_emergency_metadata_from_display(
                'Afghanistan - Earthquake (MDRAF019)'
            )
            assert meta == {'name': 'Afghanistan - Earthquake', 'code': 'MDRAF019'}

    def test_parse_emergency_metadata_from_display_without_code(self, app):
        from app.services.forms.data_service import FormDataService

        with app.app_context():
            meta = FormDataService._parse_emergency_metadata_from_display('Some Operation')
            assert meta == {'name': 'Some Operation', 'code': ''}

    def test_get_emergency_metadata_from_request_standard_field(self, app):
        from app.services.forms.data_service import FormDataService

        payload = json.dumps({'name': 'Appeal A', 'code': 'MDRAF001'})
        with app.test_request_context('/test', method='POST', data={
            'field_disagg_metadata[1313]': payload,
        }):
            meta = FormDataService._get_emergency_metadata_from_request(form_item_id=1313)
            assert meta == {'name': 'Appeal A', 'code': 'MDRAF001'}

    def test_get_emergency_metadata_from_request_repeat_field(self, app):
        from app.services.forms.data_service import FormDataService

        payload = json.dumps({'name': 'Appeal B', 'code': 'MDRAF002'})
        with app.test_request_context('/test', method='POST', data={
            'repeat_390_2_field_0_emergency_metadata': payload,
        }):
            meta = FormDataService._get_emergency_metadata_from_request(
                section_id=390,
                instance_number=2,
                field_index=0,
            )
            assert meta == {'name': 'Appeal B', 'code': 'MDRAF002'}

    def test_get_emergency_metadata_from_request_accepts_b64_json(self, app):
        from app.services.forms.data_service import FormDataService

        payload = json.dumps({'name': 'Morocco - Earthquake', 'code': 'MDRMA010'})
        wrapped = 'b64:' + base64.b64encode(payload.encode('utf-8')).decode('ascii')
        with app.test_request_context('/test', method='POST', data={
            'repeat_415_1_field_0_emergency_metadata': wrapped,
        }):
            meta = FormDataService._get_emergency_metadata_from_request(
                section_id=415,
                instance_number=1,
                field_index=0,
            )
            assert meta == {'name': 'Morocco - Earthquake', 'code': 'MDRMA010'}

    def test_get_emergency_metadata_from_request_corrupt_b64_returns_none(self, app):
        from app.services.forms.data_service import FormDataService

        with app.test_request_context('/test', method='POST', data={
            'field_disagg_metadata[1313]': 'b64:not-valid-base64!!!',
        }):
            assert FormDataService._get_emergency_metadata_from_request(form_item_id=1313) is None

    def test_find_field_value_ignores_emergency_metadata(self, app):
        from app.services.forms.data_service import FormDataService

        with app.app_context():
            field_values = {
                'field_0_0': '',
                'field_0_emergency_metadata': '{"name":"[object Object]","code":""}',
            }
            value = FormDataService._find_field_value(field_values, 0, ['0'])
            assert value is None

    def test_apply_emergency_operation_disagg(self, app):
        from app.models.forms import RepeatGroupData
        from app.services.forms.data_service import FormDataService

        with app.app_context():
            entry = RepeatGroupData()
            FormDataService._apply_emergency_operation_disagg(
                entry,
                'Afghanistan - Floods (MDRAF015)',
                {'name': 'Afghanistan - Floods', 'code': 'MDRAF015'},
            )
            assert entry.value is None
            assert entry.disagg_type == 'emergency_operation'
            assert entry.disagg_data == {'name': 'Afghanistan - Floods', 'code': 'MDRAF015'}

    def test_emergency_operation_values_equal_dict_vs_display(self, app):
        from app.models.forms import RepeatGroupData
        from app.services.forms.data_service import FormDataService

        with app.app_context():
            entry = RepeatGroupData()
            entry.value = 'Cuba - Hurricane (MDRCU013)'
            entry.disagg_data = {'name': 'Cuba - Hurricane', 'code': 'MDRCU013'}
            entry.disagg_type = 'emergency_operation'

            assert FormDataService._emergency_operation_values_equal(
                {'name': 'Cuba - Hurricane', 'code': 'MDRCU013'},
                'Cuba - Hurricane (MDRCU013)',
                old_entry=entry,
                new_metadata={'name': 'Cuba - Hurricane', 'code': 'MDRCU013'},
            )

    def test_emergency_operation_values_equal_metadata_only_old_entry(self, app):
        from app.models.forms import RepeatGroupData
        from app.services.forms.data_service import FormDataService

        with app.app_context():
            entry = RepeatGroupData()
            entry.value = None
            entry.disagg_data = {'name': 'Cuba - Hurricane', 'code': 'MDRCU013'}
            entry.disagg_type = 'emergency_operation'

            assert FormDataService._emergency_operation_values_equal(
                entry.disagg_data,
                'Cuba - Hurricane (MDRCU013)',
                old_entry=entry,
                new_metadata={'name': 'Cuba - Hurricane', 'code': 'MDRCU013'},
            )

    def test_store_scalar_question_value_applies_emergency_disagg(self, app):
        from app.models.forms import FormData
        from app.services.forms.data_service import FormDataService

        payload = json.dumps({'name': 'Appeal C', 'code': 'MDRAF003'})
        with app.test_request_context('/test', method='POST', data={
            'field_disagg_metadata[1313]': payload,
        }):
            question = self._make_emergency_question()
            entry = FormData()
            FormDataService._store_scalar_question_value(
                entry,
                question,
                'Appeal C (MDRAF003)',
            )
            assert entry.value == 'Appeal C (MDRAF003)'
            assert entry.disagg_type == 'emergency_operation'
            assert entry.disagg_data == {'name': 'Appeal C', 'code': 'MDRAF003'}


# ─────────────────────────────────────────────────────────────────────────────
# FormDataService._add_indirect_reach_to_question
# ─────────────────────────────────────────────────────────────────────────────

class TestAddIndirectReachToQuestion:
    def _make_question(self, question_type):
        q = MagicMock()
        q.id = 10
        q.type = question_type
        q.label = "Test Q"
        return q

    def test_no_indirect_reach_returns_value_unchanged(self, app):
        from app.services.forms.data_service import FormDataService
        with app.test_request_context('/test', method='POST', data={}):
            q = self._make_question("text")
            result = FormDataService._add_indirect_reach_to_question(q, "some_value")
            assert result == "some_value"

    def test_indirect_reach_empty_string_returns_value_unchanged(self, app):
        from app.services.forms.data_service import FormDataService
        with app.test_request_context('/test', method='POST', data={"question_10_indirect_reach": ""}):
            q = self._make_question("number")
            result = FormDataService._add_indirect_reach_to_question(q, "100")
            assert result == "100"

    def test_indirect_reach_with_value_returns_disagg_structure(self, app):
        from app.services.forms.data_service import FormDataService
        with app.test_request_context(
            '/test', method='POST',
            data={"question_10_indirect_reach": "50"}
        ):
            q = self._make_question("number")
            result = FormDataService._add_indirect_reach_to_question(q, "100")
        assert isinstance(result, dict)
        assert result["values"]["indirect"] == 50
        assert result["values"]["total"] == "100"

    def test_indirect_reach_none_final_value_returns_value_unchanged(self, app):
        from app.services.forms.data_service import FormDataService
        with app.test_request_context(
            '/test', method='POST',
            data={"question_10_indirect_reach": "50"}
        ):
            q = self._make_question("number")
            result = FormDataService._add_indirect_reach_to_question(q, None)
        assert result is None

    def test_indirect_reach_percentage_type(self, app):
        from app.services.forms.data_service import FormDataService
        with app.test_request_context(
            '/test', method='POST',
            data={"question_10_indirect_reach": "25.5"}
        ):
            q = self._make_question("percentage")
            result = FormDataService._add_indirect_reach_to_question(q, "75.0")
        assert isinstance(result, dict)
        assert result["values"]["indirect"] == 25.5

    def test_indirect_reach_invalid_returns_value_unchanged(self, app):
        from app.services.forms.data_service import FormDataService
        with app.test_request_context(
            '/test', method='POST',
            data={"question_10_indirect_reach": "not_a_number"}
        ):
            q = self._make_question("number")
            result = FormDataService._add_indirect_reach_to_question(q, "100")
        assert result == "100"


# ─────────────────────────────────────────────────────────────────────────────
# FormDataService._check_for_field_clearing_signals
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckForFieldClearingSignals:
    def test_no_clear_signal_returns_false(self, app):
        from app.services.forms.data_service import FormDataService
        with app.test_request_context('/test', method='POST', data={}):
            assert FormDataService._check_for_field_clearing_signals(10) is False

    def test_indicator_standard_value_clear_signal(self, app):
        from app.services.forms.data_service import FormDataService
        data = {"indicator_10_standard_value_clear_field": "CLEAR_FIELD_VALUE"}
        with app.test_request_context('/test', method='POST', data=data):
            assert FormDataService._check_for_field_clearing_signals(10) is True

    def test_field_value_clear_signal(self, app):
        from app.services.forms.data_service import FormDataService
        data = {"field_value[10]_clear_field": "CLEAR_FIELD_VALUE"}
        with app.test_request_context('/test', method='POST', data=data):
            assert FormDataService._check_for_field_clearing_signals(10) is True

    def test_wrong_value_does_not_trigger(self, app):
        from app.services.forms.data_service import FormDataService
        data = {"indicator_10_standard_value_clear_field": "something_else"}
        with app.test_request_context('/test', method='POST', data=data):
            assert FormDataService._check_for_field_clearing_signals(10) is False

    def test_different_item_id_no_match(self, app):
        from app.services.forms.data_service import FormDataService
        data = {"indicator_99_standard_value_clear_field": "CLEAR_FIELD_VALUE"}
        with app.test_request_context('/test', method='POST', data=data):
            assert FormDataService._check_for_field_clearing_signals(10) is False


# ─────────────────────────────────────────────────────────────────────────────
# FormDataService._should_preserve_existing_on_empty_save
# ─────────────────────────────────────────────────────────────────────────────

class TestShouldPreserveExistingOnEmptySave:
    def test_question_empty_save_does_not_preserve(self, app):
        from app.services.forms.data_service import FormDataService
        entry = _make_form_data_entry(value="previous notes")
        with app.test_request_context('/test', method='POST', data={'action': 'save'}):
            assert FormDataService._should_preserve_existing_on_empty_save(
                10, entry, is_presave=False, field_cleared=False
            ) is False

    def test_simple_indicator_empty_save_does_not_preserve(self, app):
        from app.services.forms.data_service import FormDataService
        indicator = MagicMock()
        indicator.id = 10
        indicator.allowed_disaggregation_options = ['total']
        indicator.indirect_reach = False
        entry = _make_form_data_entry(value="previous text")
        with app.test_request_context('/test', method='POST', data={'action': 'save'}):
            assert FormDataService._should_preserve_existing_on_empty_save(
                10,
                entry,
                is_presave=False,
                field_cleared=False,
                indicator=indicator,
                field_prefix='indicator_10',
            ) is False

    def test_disagg_indicator_preserves_when_only_empty_total_posted(self, app):
        from app.services.forms.data_service import FormDataService
        indicator = MagicMock()
        indicator.id = 10
        indicator.allowed_disaggregation_options = ['total', 'sex_age']
        indicator.indirect_reach = False
        indicator.effective_sex_categories = ['Female', 'Male']
        indicator.effective_age_groups = ['5-17', '18-49']
        entry = _make_form_data_entry(
            disagg_data={'mode': 'sex_age', 'values': {'direct': {'female_5_17': 3}}}
        )
        with app.test_request_context(
            '/test',
            method='POST',
            data={
                'action': 'save',
                'indicator_10_reporting_mode': 'sex_age',
                'indicator_10_total_value': '',
            },
        ):
            assert FormDataService._should_preserve_existing_on_empty_save(
                10,
                entry,
                is_presave=False,
                field_cleared=False,
                indicator=indicator,
                field_prefix='indicator_10',
            ) is True


# ─────────────────────────────────────────────────────────────────────────────
# FormDataService._clear_ai_validation_for_form_data
# ─────────────────────────────────────────────────────────────────────────────

class TestClearAiValidationForFormData:
    def test_does_nothing_when_entry_is_none(self, app):
        from app.services.forms.data_service import FormDataService
        with app.app_context():
            # Should not raise
            FormDataService._clear_ai_validation_for_form_data(None)

    def test_does_nothing_when_entry_has_no_id(self, app):
        from app.services.forms.data_service import FormDataService
        with app.app_context():
            entry = MagicMock()
            entry.id = None
            # Should not raise
            FormDataService._clear_ai_validation_for_form_data(entry)


# ─────────────────────────────────────────────────────────────────────────────
# FormDataService._validate_required_field
# ─────────────────────────────────────────────────────────────────────────────

class TestValidateRequiredField:
    def _make_field(self, item_type="indicator", label="My Field"):
        field = MagicMock()
        field.id = 1
        field.label = label
        field.is_document_field = (item_type == "document_field")
        field.is_indicator = (item_type == "indicator")
        field.form_section = MagicMock()
        field.form_section.name = "Test Section"
        return field

    def test_missing_form_data_returns_invalid(self, app):
        from app.services.forms.data_service import FormDataService
        with app.app_context():
            field = self._make_field()
            aes = _make_mock_oes("AssignmentEntityStatus")

            # Patch FormData.query.filter_by to return None
            with patch("app.services.forms.data_service.FormDataService._get_data_model") as mock_model, \
                 patch("app.services.forms.data_service.FormDataService._get_data_query_filter") as mock_filter:
                mock_model_class = MagicMock()
                # _validate_required_field does DataModel.query.filter_by(...).first() —
                # DataModel is the mock's return value, so `.query` must be configured too.
                mock_model_class.query.filter_by.return_value.first.return_value = None
                mock_model.return_value = mock_model_class
                mock_filter.return_value = {}

                result = FormDataService._validate_required_field(field, aes)

        assert result["is_valid"] is False
        assert "missing" in result["error"].lower() or "empty" in result["error"].lower()

    def test_has_meaningful_data_returns_valid(self, app):
        from app.services.forms.data_service import FormDataService
        with app.app_context():
            field = self._make_field()
            aes = _make_mock_oes("AssignmentEntityStatus")
            entry = _make_form_data_entry(value="100")

            with patch("app.services.forms.data_service.FormDataService._get_data_model") as mock_model, \
                 patch("app.services.forms.data_service.FormDataService._get_data_query_filter") as mock_filter, \
                 patch("app.services.forms.data_service.FormDataService._has_meaningful_data", return_value=True):
                mock_model_class = MagicMock()
                mock_model_class.query.filter_by.return_value.first.return_value = entry
                mock_model.return_value = mock_model_class
                mock_filter.return_value = {}

                result = FormDataService._validate_required_field(field, aes)

        assert result["is_valid"] is True

    def test_document_field_no_submitted_doc_returns_invalid(self, app):
        from app.services.forms.data_service import FormDataService
        with app.app_context():
            field = self._make_field(item_type="document_field", label="My Doc")
            aes = _make_mock_oes("AssignmentEntityStatus")

            with patch("app.services.forms.data_service.SubmittedDocument") as mock_doc:
                mock_doc.query.filter_by.return_value.first.return_value = None
                result = FormDataService._validate_required_field(field, aes)

        assert result["is_valid"] is False

    def test_document_field_has_submitted_doc_returns_valid(self, app):
        from app.services.forms.data_service import FormDataService
        with app.app_context():
            field = self._make_field(item_type="document_field", label="My Doc")
            aes = _make_mock_oes("AssignmentEntityStatus")

            with patch("app.services.forms.data_service.SubmittedDocument") as mock_doc:
                mock_doc.query.filter_by.return_value.first.return_value = MagicMock()
                result = FormDataService._validate_required_field(field, aes)

        assert result["is_valid"] is True

    def test_public_submission_document_field(self, app):
        from app.services.forms.data_service import FormDataService
        with app.app_context():
            field = self._make_field(item_type="document_field", label="Public Doc")
            aes = _make_mock_oes("PublicSubmission")

            with patch("app.services.forms.data_service.SubmittedDocument") as mock_doc:
                mock_doc.query.filter_by.return_value.first.return_value = None
                result = FormDataService._validate_required_field(field, aes)

        assert result["is_valid"] is False


# ─────────────────────────────────────────────────────────────────────────────
# FormDataService._validate_section
# ─────────────────────────────────────────────────────────────────────────────

class TestValidateSection:
    def test_section_without_fields_ordered_returns_valid(self, app):
        from app.services.forms.data_service import FormDataService
        with app.app_context():
            with app.test_request_context('/'):
                section = MagicMock(spec=["section_type"])
                section.section_type = "standard"
                # No fields_ordered attribute
                aes = _make_mock_oes()
                result = FormDataService._validate_section(section, aes)
        assert result["is_valid"] is True

    def test_repeat_section_delegates_to_validate_repeat(self, app):
        from app.services.forms.data_service import FormDataService
        with app.app_context():
            with app.test_request_context('/'):
                section = MagicMock()
                section.section_type = "repeat"
                aes = _make_mock_oes()
                with patch.object(
                    FormDataService, "_validate_repeat_section",
                    return_value={"is_valid": True, "errors": []}
                ) as mock_repeat:
                    result = FormDataService._validate_section(section, aes)
        assert result["is_valid"] is True
        mock_repeat.assert_called_once()

    def test_required_field_missing_invalidates_section(self, app):
        from app.services.forms.data_service import FormDataService
        with app.app_context():
            with app.test_request_context('/'):
                field = MagicMock()
                field.id = 1
                field.is_required_for_js = True
                # Must be explicit: getattr(field, 'is_image', False) on a bare MagicMock
                # auto-vivifies a truthy attribute instead of falling back to the default,
                # which would wrongly skip this field as an "image" and mask the assertion below.
                field.is_image = False

                section = MagicMock()
                section.section_type = "standard"
                section.fields_ordered = [field]

                aes = _make_mock_oes()
                with patch.object(
                    FormDataService, "_validate_required_field",
                    return_value={"is_valid": False, "error": "Required field missing"}
                ):
                    result = FormDataService._validate_section(section, aes)

        assert result["is_valid"] is False
        assert len(result["errors"]) > 0

    def test_hidden_field_not_validated(self, app):
        from app.services.forms.data_service import FormDataService
        with app.app_context():
            with app.test_request_context('/'):
                field = MagicMock()
                field.id = 5
                field.is_required_for_js = True

                section = MagicMock()
                section.section_type = "standard"
                section.fields_ordered = [field]

                aes = _make_mock_oes()
                result = FormDataService._validate_section(section, aes, hidden_field_ids={5})

        assert result["is_valid"] is True

    def test_optional_field_missing_is_valid(self, app):
        from app.services.forms.data_service import FormDataService
        with app.app_context():
            with app.test_request_context('/'):
                field = MagicMock()
                field.id = 2
                field.is_required_for_js = False

                section = MagicMock()
                section.section_type = "standard"
                section.fields_ordered = [field]

                aes = _make_mock_oes()
                result = FormDataService._validate_section(section, aes)

        assert result["is_valid"] is True


# ─────────────────────────────────────────────────────────────────────────────
# FormDataService._validate_for_submission
# ─────────────────────────────────────────────────────────────────────────────

class TestValidateForSubmission:
    def test_all_valid_sections_returns_valid(self, app):
        from app.services.forms.data_service import FormDataService
        with app.app_context():
            with app.test_request_context('/'):
                section = MagicMock()
                section.fields_ordered = []
                aes = _make_mock_oes()

                result = FormDataService._validate_for_submission([section], aes)

        assert result["is_valid"] is True
        assert result["errors"] == []

    def test_invalid_section_propagates_errors(self, app):
        from app.services.forms.data_service import FormDataService
        with app.app_context():
            with app.test_request_context('/'):
                section = MagicMock()
                section.fields_ordered = []
                aes = _make_mock_oes()

                with patch.object(
                    FormDataService, "_validate_section",
                    return_value={"is_valid": False, "errors": ["Field X is required"]}
                ):
                    result = FormDataService._validate_for_submission([section], aes)

        assert result["is_valid"] is False
        assert "Field X is required" in result["errors"]

    def test_hidden_fields_param_parsed(self, app):
        from app.services.forms.data_service import FormDataService
        with app.app_context():
            with app.test_request_context(
                '/test', method='POST',
                data={"hidden_fields_to_clear": "1,2,3"}
            ):
                section = MagicMock()
                section.fields_ordered = []
                aes = _make_mock_oes()

                with patch.object(
                    FormDataService, "_validate_section",
                    return_value={"is_valid": True, "errors": []}
                ) as mock_validate:
                    result = FormDataService._validate_for_submission([section], aes)

        assert result["is_valid"] is True

    def test_section_without_fields_ordered_skipped(self, app):
        from app.services.forms.data_service import FormDataService
        with app.app_context():
            with app.test_request_context('/'):
                section = MagicMock(spec=["section_type"])
                section.section_type = "standard"
                aes = _make_mock_oes()
                result = FormDataService._validate_for_submission([section], aes)

        assert result["is_valid"] is True


# ─────────────────────────────────────────────────────────────────────────────
# FormDataService._validate_repeat_section
# ─────────────────────────────────────────────────────────────────────────────

class TestValidateRepeatSection:
    def test_no_instances_no_required_fields_valid(self, app):
        from app.services.forms.data_service import FormDataService
        from app.models import RepeatGroupInstance
        with app.app_context():
            with app.test_request_context('/'):
                section = MagicMock()
                section.name = "My Repeat Section"
                section.fields_ordered = [MagicMock(is_required_for_js=False)]
                aes = _make_mock_oes()

                with patch("app.services.forms.data_service.RepeatGroupInstance") as mock_rgi:
                    mock_rgi.query.filter_by.return_value.all.return_value = []
                    result = FormDataService._validate_repeat_section(section, aes)

        assert result["is_valid"] is True

    def test_no_instances_with_required_fields_invalid(self, app):
        from app.services.forms.data_service import FormDataService
        with app.app_context():
            with app.test_request_context('/'):
                section = MagicMock()
                section.name = "Repeat Section"
                section.fields_ordered = [MagicMock(is_required_for_js=True, id=1)]
                aes = _make_mock_oes()

                with patch("app.services.forms.data_service.RepeatGroupInstance") as mock_rgi:
                    mock_rgi.query.filter_by.return_value.all.return_value = []
                    result = FormDataService._validate_repeat_section(section, aes)

        assert result["is_valid"] is False

    def test_has_instance_complete_returns_valid(self, app):
        from app.services.forms.data_service import FormDataService
        with app.app_context():
            with app.test_request_context('/'):
                section = MagicMock()
                section.name = "Repeat Section"
                aes = _make_mock_oes()

                instance = MagicMock()
                with patch("app.services.forms.data_service.RepeatGroupInstance") as mock_rgi, \
                     patch.object(FormDataService, "_is_repeat_instance_complete", return_value=True):
                    mock_rgi.query.filter_by.return_value.all.return_value = [instance]
                    result = FormDataService._validate_repeat_section(section, aes)

        assert result["is_valid"] is True

    def test_has_instance_not_complete_returns_invalid(self, app):
        from app.services.forms.data_service import FormDataService
        with app.app_context():
            with app.test_request_context('/'):
                section = MagicMock()
                section.name = "Repeat Section"
                aes = _make_mock_oes()

                instance = MagicMock()
                with patch("app.services.forms.data_service.RepeatGroupInstance") as mock_rgi, \
                     patch.object(FormDataService, "_is_repeat_instance_complete", return_value=False):
                    mock_rgi.query.filter_by.return_value.all.return_value = [instance]
                    result = FormDataService._validate_repeat_section(section, aes)

        assert result["is_valid"] is False

    def test_public_submission_uses_public_id(self, app):
        from app.services.forms.data_service import FormDataService
        with app.app_context():
            with app.test_request_context('/'):
                section = MagicMock()
                section.name = "Public Repeat"
                section.fields_ordered = [MagicMock(is_required_for_js=False)]
                aes = _make_mock_oes("PublicSubmission")

                with patch("app.services.forms.data_service.RepeatGroupInstance") as mock_rgi:
                    mock_rgi.query.filter_by.return_value.all.return_value = []
                    result = FormDataService._validate_repeat_section(section, aes)

                    # Verify it used public_submission_id
                    call_kwargs = mock_rgi.query.filter_by.call_args[1]
                    assert "public_submission_id" in call_kwargs


# ─────────────────────────────────────────────────────────────────────────────
# FormDataService._is_repeat_instance_complete
# ─────────────────────────────────────────────────────────────────────────────

class TestIsRepeatInstanceComplete:
    def test_always_returns_true(self):
        from app.services.forms.data_service import FormDataService
        instance = MagicMock()
        section = MagicMock()
        result = FormDataService._is_repeat_instance_complete(instance, section)
        assert result is True


# ─────────────────────────────────────────────────────────────────────────────
# FormDataService.save_simple_field
# ─────────────────────────────────────────────────────────────────────────────

class TestSaveSimpleField:
    def test_creates_new_entry_when_not_exists(self, db_session, app):
        from app.services.forms.data_service import FormDataService
        from tests.factories import (
            create_test_template, create_test_section, create_test_item,
            create_test_assignment_entity_status
        )
        with app.test_request_context('/'):
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            item = create_test_item(
                db_session, section, template,
                item_type="question", label="Test Q", type="text", order=1
            )
            aes = create_test_assignment_entity_status(db_session, template=template)

            from unittest.mock import patch
            with patch("flask_login.current_user") as mock_user:
                mock_user.is_authenticated = False
                result = FormDataService.save_simple_field(aes, item.id, "test_value")

        assert result["success"] is True

    def test_returns_success_for_none_value_no_existing(self, db_session, app):
        from app.services.forms.data_service import FormDataService
        from tests.factories import (
            create_test_template, create_test_section, create_test_item,
            create_test_assignment_entity_status
        )
        with app.test_request_context('/'):
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            item = create_test_item(
                db_session, section, template,
                item_type="question", label="Test Q2", type="text", order=1
            )
            aes = create_test_assignment_entity_status(db_session, template=template)

            with patch("flask_login.current_user") as mock_user:
                mock_user.is_authenticated = False
                result = FormDataService.save_simple_field(aes, item.id, None)

        assert result["success"] is True


# ─────────────────────────────────────────────────────────────────────────────
# FormDataService.bulk_save_fields
# ─────────────────────────────────────────────────────────────────────────────

class TestBulkSaveFields:
    def test_bulk_save_empty_dict(self, db_session, app):
        from app.services.forms.data_service import FormDataService
        from tests.factories import create_test_template, create_test_assignment_entity_status
        with app.test_request_context('/'):
            template = create_test_template(db_session)
            aes = create_test_assignment_entity_status(db_session, template=template)

            with patch("flask_login.current_user") as mock_user:
                mock_user.is_authenticated = False
                result = FormDataService.bulk_save_fields(aes, {})

        assert result["success"] is True
        assert result["updated_count"] == 0
        assert result["errors"] == []

    def test_bulk_save_multiple_fields(self, db_session, app):
        from app.services.forms.data_service import FormDataService
        from tests.factories import (
            create_test_template, create_test_section, create_test_item,
            create_test_assignment_entity_status
        )
        with app.test_request_context('/'):
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            item1 = create_test_item(
                db_session, section, template,
                item_type="question", label="Bulk Q1", type="text", order=1
            )
            item2 = create_test_item(
                db_session, section, template,
                item_type="question", label="Bulk Q2", type="text", order=2
            )
            aes = create_test_assignment_entity_status(db_session, template=template)

            with patch("flask_login.current_user") as mock_user:
                mock_user.is_authenticated = False
                result = FormDataService.bulk_save_fields(aes, {
                    item1.id: "value_1",
                    item2.id: "value_2",
                })

        assert result["success"] is True
        assert result["updated_count"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# FormDataService._commit_or_flush
# ─────────────────────────────────────────────────────────────────────────────

class TestCommitOrFlush:
    def test_flushes_in_auto_managed_request(self, app):
        from app.services.forms.data_service import FormDataService
        with app.app_context():
            with app.test_request_context('/'):
                g._auto_txn_managed = True
                with patch("app.services.forms.data_service.db") as mock_db:
                    FormDataService._commit_or_flush()
                    mock_db.session.flush.assert_called_once()
                    mock_db.session.commit.assert_not_called()

    def test_commits_outside_auto_managed_request(self, app):
        from app.services.forms.data_service import FormDataService
        with app.app_context():
            with app.test_request_context('/'):
                # Not auto-managed
                with patch("app.services.forms.data_service.db") as mock_db:
                    FormDataService._commit_or_flush()
                    mock_db.session.commit.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# FormDataService._log_verbose
# ─────────────────────────────────────────────────────────────────────────────

class TestLogVerbose:
    def test_no_log_when_not_verbose(self, app):
        from app.services.forms.data_service import FormDataService
        with app.app_context():
            with app.test_request_context('/'):
                app.config['VERBOSE_FORM_DATA_LOGGING'] = False
                with patch("app.services.forms.data_service.logger") as mock_logger:
                    FormDataService._log_verbose("test message")
                    mock_logger.info.assert_not_called()

    def test_logs_when_verbose(self, app):
        from app.services.forms.data_service import FormDataService
        with app.app_context():
            with app.test_request_context('/'):
                app.config['VERBOSE_FORM_DATA_LOGGING'] = True
                with patch("app.services.forms.data_service.logger") as mock_logger:
                    FormDataService._log_verbose("test message")
                    mock_logger.info.assert_called_once()
                app.config['VERBOSE_FORM_DATA_LOGGING'] = False


# ─────────────────────────────────────────────────────────────────────────────
# FormDataService._rollback_transaction
# ─────────────────────────────────────────────────────────────────────────────

class TestRollbackTransaction:
    def test_calls_request_transaction_rollback(self, app):
        from app.services.forms.data_service import FormDataService
        with app.app_context():
            with patch("app.services.forms.data_service.request_transaction_rollback") as mock_rollback:
                FormDataService._rollback_transaction("test_reason")
                mock_rollback.assert_called_once_with(reason="test_reason")


# ─────────────────────────────────────────────────────────────────────────────
# FormDataService._update_indicator_entry
# ─────────────────────────────────────────────────────────────────────────────

class TestUpdateIndicatorEntry:
    def test_sets_data_availability_flags(self, app):
        from app.services.forms.data_service import FormDataService
        with app.app_context():
            entry = MagicMock()
            indicator = MagicMock()
            FormDataService._update_indicator_entry(entry, indicator, None, True, False)
            entry.set_data_availability.assert_called_with(True, False)

    def test_sets_disaggregated_data_for_dict_value(self, app):
        from app.services.forms.data_service import FormDataService
        with app.app_context():
            entry = MagicMock()
            indicator = MagicMock()
            value = {"mode": "total", "values": {"total": 100}}
            FormDataService._update_indicator_entry(entry, indicator, value, False, False)
            entry.set_disaggregated_data.assert_called_with("total", {"total": 100})

    def test_sets_simple_value_for_plain_value(self, app):
        from app.services.forms.data_service import FormDataService
        with app.app_context():
            entry = MagicMock()
            indicator = MagicMock()
            FormDataService._update_indicator_entry(entry, indicator, "100", False, False)
            entry.set_simple_value.assert_called_with("100")

    def test_sets_none_when_no_value_and_no_flags(self, app):
        from app.services.forms.data_service import FormDataService
        with app.app_context():
            entry = MagicMock()
            indicator = MagicMock()
            FormDataService._update_indicator_entry(entry, indicator, None, False, False)
            entry.set_simple_value.assert_called_with(None)

    def test_does_not_set_value_when_data_not_available(self, app):
        from app.services.forms.data_service import FormDataService
        with app.app_context():
            entry = MagicMock()
            indicator = MagicMock()
            FormDataService._update_indicator_entry(entry, indicator, "100", True, False)
            entry.set_simple_value.assert_not_called()
            entry.set_disaggregated_data.assert_not_called()

    def test_does_not_set_value_when_not_applicable(self, app):
        from app.services.forms.data_service import FormDataService
        with app.app_context():
            entry = MagicMock()
            indicator = MagicMock()
            FormDataService._update_indicator_entry(entry, indicator, "100", False, True)
            entry.set_simple_value.assert_not_called()
            entry.set_disaggregated_data.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# FormDataService._process_matrix_data — field-level base64 WAF workaround
#
# field_value[id] may be posted as "b64:<base64 utf-8 json>" to dodge Application
# Gateway WAF false positives on matrix JSON (see
# docs/runbooks/incidents/waf-403-form-payload-refactor-guide.md). A corrupted
# payload must raise MatrixJsonDecodeError and be treated as a hard failure —
# never silently coerced to "field cleared", which would wipe previously-saved
# data (see decode_b64_matrix_json docstring for the rollout-hazard rationale).
# ─────────────────────────────────────────────────────────────────────────────

class TestProcessMatrixDataB64Safety:
    def _make_matrix(self, item_id=42, label="Funding Matrix"):
        matrix = MagicMock()
        matrix.id = item_id
        matrix.label = label
        matrix.config = {}
        matrix.is_required = False
        return matrix

    def _b64(self, json_str):
        import base64
        return 'b64:' + base64.b64encode(json_str.encode('utf-8')).decode('ascii')

    def test_valid_b64_payload_is_decoded_and_saved(self, app):
        from app.services.forms.data_service import FormDataService

        matrix = self._make_matrix()
        aes = _make_mock_oes()
        existing_entry = _make_form_data_entry(disagg_data={"old_col": 1})
        payload = self._b64('{"1_col": 5}')

        with app.test_request_context(
            '/test', method='POST', data={f'field_value[{matrix.id}]': payload}
        ):
            with patch("app.services.forms.data_service.FormDataService._get_data_model") as mock_model, \
                 patch("app.services.forms.data_service.FormDataService._get_data_query_filter") as mock_filter, \
                 patch("app.models.db.session.add"):
                mock_query = MagicMock()
                mock_query.filter_by.return_value.first.return_value = existing_entry
                mock_model.return_value.query = mock_query
                mock_filter.return_value = {}

                validation_errors = []
                changes = FormDataService._process_matrix_data(matrix, aes, validation_errors)

        assert validation_errors == []
        assert existing_entry.disagg_data == {"1_col": 5}
        assert len(changes) == 1

    def test_raw_json_without_b64_prefix_still_works(self, app):
        """Backwards compatibility: older cached JS / offline draft resubmits post raw JSON."""
        from app.services.forms.data_service import FormDataService

        matrix = self._make_matrix()
        aes = _make_mock_oes()
        existing_entry = _make_form_data_entry(disagg_data=None)

        with app.test_request_context(
            '/test', method='POST', data={f'field_value[{matrix.id}]': '{"1_col": 7}'}
        ):
            with patch("app.services.forms.data_service.FormDataService._get_data_model") as mock_model, \
                 patch("app.services.forms.data_service.FormDataService._get_data_query_filter") as mock_filter, \
                 patch("app.models.db.session.add"):
                mock_query = MagicMock()
                mock_query.filter_by.return_value.first.return_value = existing_entry
                mock_model.return_value.query = mock_query
                mock_filter.return_value = {}

                validation_errors = []
                FormDataService._process_matrix_data(matrix, aes, validation_errors)

        assert validation_errors == []
        assert existing_entry.disagg_data == {"1_col": 7}

    def test_chunked_b64_payload_is_reassembled_and_decoded(self, app):
        """Large matrix values may be split client-side (matrix-field-chunking.js)
        across field_value[id]/__c1/__c2/... to dodge a WAF argument-length rule
        (e.g. OWASP CRS 920370) — see get_possibly_chunked_form_value(). The
        server must reassemble and decode them exactly as if unchunked."""
        from app.services.forms.data_service import FormDataService

        matrix = self._make_matrix()
        aes = _make_mock_oes()
        existing_entry = _make_form_data_entry(disagg_data=None)

        full_payload = self._b64('{"1_col": 5, "2_col": 9}')
        # Split arbitrarily mid-string, the way the client would at a fixed
        # byte threshold — reassembly must not depend on any alignment.
        split_at = len(full_payload) // 3
        chunk0, chunk1, chunk2 = (
            full_payload[:split_at],
            full_payload[split_at:2 * split_at],
            full_payload[2 * split_at:],
        )

        with app.test_request_context(
            '/test', method='POST',
            data={
                f'field_value[{matrix.id}]': chunk0,
                f'field_value[{matrix.id}]__c1': chunk1,
                f'field_value[{matrix.id}]__c2': chunk2,
            },
        ):
            with patch("app.services.forms.data_service.FormDataService._get_data_model") as mock_model, \
                 patch("app.services.forms.data_service.FormDataService._get_data_query_filter") as mock_filter, \
                 patch("app.models.db.session.add"):
                mock_query = MagicMock()
                mock_query.filter_by.return_value.first.return_value = existing_entry
                mock_model.return_value.query = mock_query
                mock_filter.return_value = {}

                validation_errors = []
                changes = FormDataService._process_matrix_data(matrix, aes, validation_errors)

        assert validation_errors == []
        assert existing_entry.disagg_data == {"1_col": 5, "2_col": 9}
        assert len(changes) == 1

    def test_corrupted_b64_payload_preserves_existing_data_and_reports_error(self, app):
        """The core safety guarantee: a decode failure must NOT wipe existing data."""
        from app.services.forms.data_service import FormDataService

        matrix = self._make_matrix()
        aes = _make_mock_oes()
        existing_entry = _make_form_data_entry(disagg_data={"1_col": 999})

        with app.test_request_context(
            '/test', method='POST',
            data={f'field_value[{matrix.id}]': 'b64:not-valid-base64!!!'},
        ):
            with patch("app.services.forms.data_service.FormDataService._get_data_model") as mock_model, \
                 patch("app.services.forms.data_service.FormDataService._get_data_query_filter") as mock_filter, \
                 patch("app.models.db.session.add"):
                mock_query = MagicMock()
                mock_query.filter_by.return_value.first.return_value = existing_entry
                mock_model.return_value.query = mock_query
                mock_filter.return_value = {}

                validation_errors = []
                changes = FormDataService._process_matrix_data(matrix, aes, validation_errors)

        # Existing data must be untouched (not wiped to None) and the caller
        # must be told the save failed rather than getting a false "success".
        assert existing_entry.disagg_data == {"1_col": 999}
        assert changes == []
        assert len(validation_errors) == 1
        assert "could not be decoded" in validation_errors[0]


# ─────────────────────────────────────────────────────────────────────────────
# FormDataService._process_question_data — same base64 convention extended to
# plain text/textarea question answers (narrative text), to close a WAF
# false-positive gap the matrix/plugin fields didn't have: raw free text is
# scanned by REQUEST-941-*/942-* signature rules for XSS/SQLi-shaped
# punctuation. See question-text-waf-encode.js and
# docs/runbooks/incidents/waf-403-form-payload-refactor-guide.md.
# ─────────────────────────────────────────────────────────────────────────────

class TestProcessQuestionDataB64Safety:
    def _make_question(self, item_id=10, label="Narrative Answer", q_type="text"):
        question = MagicMock()
        question.id = item_id
        question.label = label
        question.type = q_type
        question.indirect_reach = False
        # MagicMock attributes are truthy by default — process_form_item_data()
        # dispatches on these flags, so they must be explicit or it would route
        # to _process_indicator_data instead of _process_question_data.
        question.is_indicator = False
        question.is_question = True
        question.is_document_field = False
        return question

    def _b64(self, text):
        import base64
        return 'b64:' + base64.b64encode(text.encode('utf-8')).decode('ascii')

    def test_valid_b64_text_is_decoded_and_saved(self, app):
        from app.services.forms.data_service import FormDataService

        question = self._make_question()
        aes = _make_mock_oes()
        existing_entry = _make_form_data_entry(value="old answer")
        raw_text = 'Report: 50% increase (see Annex 1); "coordinated" response'
        payload = self._b64(raw_text)

        with app.test_request_context(
            '/test', method='POST', data={f'field_value[{question.id}]': payload}
        ):
            with patch("app.services.forms.data_service.FormDataService._get_data_model") as mock_model, \
                 patch("app.services.forms.data_service.FormDataService._get_data_query_filter") as mock_filter, \
                 patch("app.models.db.session.add"):
                mock_query = MagicMock()
                mock_query.filter_by.return_value.first.return_value = existing_entry
                mock_model.return_value.query = mock_query
                mock_filter.return_value = {}

                validation_errors = []
                changes = FormDataService._process_question_data(question, aes, validation_errors)

        assert validation_errors == []
        existing_entry.set_simple_value.assert_called_with(raw_text)
        assert len(changes) == 1

    def test_raw_text_without_b64_prefix_still_works(self, app):
        """Backwards compatibility: older cached JS that hasn't picked up the
        base64-wrapping change yet must keep working."""
        from app.services.forms.data_service import FormDataService

        question = self._make_question()
        aes = _make_mock_oes()
        existing_entry = _make_form_data_entry(value=None)

        with app.test_request_context(
            '/test', method='POST', data={f'field_value[{question.id}]': 'Plain unwrapped answer'}
        ):
            with patch("app.services.forms.data_service.FormDataService._get_data_model") as mock_model, \
                 patch("app.services.forms.data_service.FormDataService._get_data_query_filter") as mock_filter, \
                 patch("app.models.db.session.add"):
                mock_query = MagicMock()
                mock_query.filter_by.return_value.first.return_value = existing_entry
                mock_model.return_value.query = mock_query
                mock_filter.return_value = {}

                validation_errors = []
                FormDataService._process_question_data(question, aes, validation_errors)

        assert validation_errors == []
        existing_entry.set_simple_value.assert_called_with('Plain unwrapped answer')

    def test_corrupted_b64_payload_preserves_existing_data_and_reports_error(self, app):
        """The core safety guarantee: a decode failure must NOT wipe existing data."""
        from app.services.forms.data_service import FormDataService

        question = self._make_question()
        aes = _make_mock_oes()
        existing_entry = _make_form_data_entry(value="previously saved narrative")

        with app.test_request_context(
            '/test', method='POST',
            data={f'field_value[{question.id}]': 'b64:not-valid-base64!!!'},
        ):
            with patch("app.services.forms.data_service.FormDataService._get_data_model") as mock_model, \
                 patch("app.services.forms.data_service.FormDataService._get_data_query_filter") as mock_filter, \
                 patch("app.models.db.session.add"):
                mock_query = MagicMock()
                mock_query.filter_by.return_value.first.return_value = existing_entry
                mock_model.return_value.query = mock_query
                mock_filter.return_value = {}

                validation_errors = []
                changes = FormDataService._process_question_data(question, aes, validation_errors)

        # Existing data must be untouched (not wiped) and the caller must be
        # told the save failed rather than getting a false "success".
        existing_entry.set_simple_value.assert_not_called()
        assert changes == []
        assert len(validation_errors) == 1
        assert "could not be decoded" in validation_errors[0]


# ─────────────────────────────────────────────────────────────────────────────
# RepeatGroupProcessorMixin._process_repeat_matrix_data_comprehensive — same
# base64 convention. Unlike the top-level matrix path, returning None here is
# already safe: the caller only writes a RepeatGroupData row when
# should_create_data_availability_entry() is True, so None = "no meaningful
# data" = existing row left untouched (verified against processing_service.py).
# ─────────────────────────────────────────────────────────────────────────────

class TestProcessRepeatMatrixDataB64Safety:
    def _b64(self, json_str):
        import base64
        return 'b64:' + base64.b64encode(json_str.encode('utf-8')).decode('ascii')

    def _make_field(self, item_id=7):
        field = MagicMock()
        field.id = item_id
        return field

    def test_valid_b64_payload_is_decoded(self, app):
        from app.services.forms.data_service import FormDataService
        field = self._make_field()
        field_values = {'field_0_1': self._b64('{"row1_col": 3}')}
        with app.app_context():
            result = FormDataService._process_repeat_matrix_data_comprehensive(field, field_values, 0)
        assert result == {"row1_col": 3}

    def test_corrupted_b64_returns_none_instead_of_raising(self, app):
        from app.services.forms.data_service import FormDataService
        field = self._make_field()
        field_values = {'field_0_1': 'b64:not-valid-base64!!!'}
        with app.app_context():
            result = FormDataService._process_repeat_matrix_data_comprehensive(field, field_values, 0)
        # None => should_create_data_availability_entry() is False => caller
        # leaves any existing RepeatGroupData row untouched (no silent wipe).
        assert result is None


class TestProcessRepeatQuestionValueB64:
    def _b64(self, text):
        return 'b64:' + base64.b64encode(text.encode('utf-8')).decode('ascii')

    def test_decodes_b64_textarea_and_emergency_display(self, app):
        from app.services.forms.data_service import FormDataService

        field = MagicMock()
        field.id = 8
        notes = '* sex disaggregations are currently not available\n* PNS funding'
        display = 'Morocco - Earthquake (MDRMA010)'
        with app.app_context():
            assert FormDataService._process_question_value_by_type(
                self._b64(notes), 'textarea', field, {}, 0
            ) == notes
            assert FormDataService._process_question_value_by_type(
                self._b64(display), 'single_choice', field, {}, 0
            ) == display

    def test_raw_repeat_text_without_prefix_still_works(self, app):
        from app.services.forms.data_service import FormDataService

        field = MagicMock()
        field.id = 8
        with app.app_context():
            assert FormDataService._process_question_value_by_type(
                'Plain repeat answer', 'text', field, {}, 0
            ) == 'Plain repeat answer'

    def test_corrupt_b64_repeat_question_is_a_no_op(self, app):
        from app.services.forms.data_service import FormDataService

        field = MagicMock()
        field.id = 8
        field.is_indicator = False
        field.is_question = True
        field.is_document_field = False
        field.item_type = 'question'
        field.question_type = MagicMock()
        field.question_type.value = 'textarea'
        field_values = {'field_0_0': 'b64:not-valid-base64!!!'}
        with app.app_context():
            value, dna, na, meaningful = FormDataService._process_repeat_field_data_comprehensive(
                field, field_values, 0, 1
            )
        assert (value, dna, na, meaningful) == (None, False, False, False)


# ─────────────────────────────────────────────────────────────────────────────
# PluginProcessorMixin._process_plugin_fields — same base64 convention applied
# to plugin field JSON (e.g. emergency_operations), which independently calls
# json.loads() on field_value[id] via plugin_data_processor.
# ─────────────────────────────────────────────────────────────────────────────

class TestProcessPluginFieldsB64Safety:
    def _b64(self, json_str):
        import base64
        return 'b64:' + base64.b64encode(json_str.encode('utf-8')).decode('ascii')

    def _make_plugin_field(self, item_id=55, label="Emergency Operation"):
        field = MagicMock()
        field.id = item_id
        field.label = label
        field.item_type = 'plugin_emergency_operations'
        return field

    def test_corrupted_b64_reports_error_and_skips_save(self, app):
        from app.services.forms.data_service import FormDataService

        plugin_field = self._make_plugin_field()
        aes = _make_mock_oes()

        with app.test_request_context(
            '/test', method='POST',
            data={f'field_value[{plugin_field.id}]': 'b64:not-valid-base64!!!'},
        ):
            with patch.object(FormDataService, '_save_plugin_field_data') as mock_save:
                validation_errors = []
                FormDataService._process_plugin_fields(
                    section=MagicMock(id=1),
                    assignment_entity_status=aes,
                    validation_errors=validation_errors,
                    plugin_fields=[plugin_field],
                )

        # Must never reach the save step with a garbage/undecoded value.
        mock_save.assert_not_called()
        assert len(validation_errors) == 1
        assert "could not be decoded" in validation_errors[0]
