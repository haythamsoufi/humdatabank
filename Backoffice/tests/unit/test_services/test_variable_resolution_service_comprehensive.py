"""
Comprehensive tests for VariableResolutionService.

Targets 100% code coverage of:
  app/services/variable_resolution_service.py
"""

import ast
import json
import pytest
from unittest.mock import MagicMock, patch

from app.services.variable_resolution_service import VariableResolutionService


# ---------------------------------------------------------------------------
# _effective_matrix_cell_value
# ---------------------------------------------------------------------------

class TestEffectiveMatrixCellValue:
    def test_none_returns_none(self):
        assert VariableResolutionService._effective_matrix_cell_value(None) is None

    def test_dict_with_modified_returns_modified(self):
        cell = {'modified': '42', 'original': '10', 'isModified': True}
        assert VariableResolutionService._effective_matrix_cell_value(cell) == '42'

    def test_dict_with_none_modified_falls_to_original(self):
        cell = {'modified': None, 'original': '10'}
        assert VariableResolutionService._effective_matrix_cell_value(cell) == '10'

    def test_dict_with_original_only(self):
        cell = {'original': '5'}
        assert VariableResolutionService._effective_matrix_cell_value(cell) == '5'

    def test_dict_empty_returns_empty_dict(self):
        cell = {}
        assert VariableResolutionService._effective_matrix_cell_value(cell) == {}

    def test_scalar_integer(self):
        assert VariableResolutionService._effective_matrix_cell_value(99) == 99

    def test_scalar_string(self):
        assert VariableResolutionService._effective_matrix_cell_value('hello') == 'hello'

    def test_scalar_zero(self):
        assert VariableResolutionService._effective_matrix_cell_value(0) == 0


# ---------------------------------------------------------------------------
# _matrix_row_total
# ---------------------------------------------------------------------------

class TestMatrixRowTotal:
    def test_none_disagg_returns_none(self):
        assert VariableResolutionService._matrix_row_total(None, 5) is None

    def test_empty_dict_returns_none(self):
        assert VariableResolutionService._matrix_row_total({}, 5) is None

    def test_non_dict_returns_none(self):
        assert VariableResolutionService._matrix_row_total("not a dict", 5) is None

    def test_list_returns_none(self):
        assert VariableResolutionService._matrix_row_total([1, 2, 3], 5) is None

    def test_sums_matching_keys(self):
        disagg = {'5_col1': 10, '5_col2': 20, '_table': 'country', '3_col1': 99}
        result = VariableResolutionService._matrix_row_total(disagg, 5)
        assert result == 30.0

    def test_ignores_underscore_prefix_keys(self):
        disagg = {'_table': 'x', '_hidden': 100, '5_col': 5}
        result = VariableResolutionService._matrix_row_total(disagg, 5)
        assert result == 5.0

    def test_returns_none_when_no_prefix_matches(self):
        disagg = {'3_col': 10, '9_col': 20}
        result = VariableResolutionService._matrix_row_total(disagg, 5)
        assert result is None

    def test_handles_variable_column_format_modified(self):
        disagg = {'5_col': {'modified': '15', 'original': '10', 'isModified': True}}
        result = VariableResolutionService._matrix_row_total(disagg, 5)
        assert result == 15.0

    def test_handles_variable_column_format_original(self):
        disagg = {'5_col': {'original': '7'}}
        result = VariableResolutionService._matrix_row_total(disagg, 5)
        assert result == 7.0

    def test_handles_non_numeric_values(self):
        disagg = {'5_col': 'abc', '5_col2': 10}
        result = VariableResolutionService._matrix_row_total(disagg, 5)
        assert result == 10.0

    def test_handles_comma_formatted_numbers(self):
        disagg = {'5_col': '1,000'}
        result = VariableResolutionService._matrix_row_total(disagg, 5)
        assert result == 1000.0

    def test_none_cell_value_skipped(self):
        disagg = {'5_col': None}
        result = VariableResolutionService._matrix_row_total(disagg, 5)
        assert result is None

    def test_zero_total_returns_none(self):
        # falsy total (0) is returned as None
        disagg = {'5_col': 0}
        result = VariableResolutionService._matrix_row_total(disagg, 5)
        assert result is None

    def test_positive_total(self):
        disagg = {'5_a': 1, '5_b': 2, '5_c': 3}
        result = VariableResolutionService._matrix_row_total(disagg, 5)
        assert result == 6.0


# ---------------------------------------------------------------------------
# _evaluate_ast_node
# ---------------------------------------------------------------------------

class TestEvaluateAstNode:
    def test_integer_constant(self):
        node = ast.parse("5", mode='eval').body
        assert VariableResolutionService._evaluate_ast_node(node) == 5

    def test_float_constant(self):
        node = ast.parse("3.14", mode='eval').body
        assert VariableResolutionService._evaluate_ast_node(node) == 3.14

    def test_string_constant_raises(self):
        node = ast.parse("'hello'", mode='eval').body
        with pytest.raises(ValueError, match="numeric"):
            VariableResolutionService._evaluate_ast_node(node)

    def test_addition(self):
        node = ast.parse("2 + 3", mode='eval').body
        assert VariableResolutionService._evaluate_ast_node(node) == 5

    def test_subtraction(self):
        node = ast.parse("10 - 3", mode='eval').body
        assert VariableResolutionService._evaluate_ast_node(node) == 7

    def test_multiplication(self):
        node = ast.parse("4 * 3", mode='eval').body
        assert VariableResolutionService._evaluate_ast_node(node) == 12

    def test_division(self):
        node = ast.parse("10 / 4", mode='eval').body
        assert VariableResolutionService._evaluate_ast_node(node) == 2.5

    def test_power(self):
        node = ast.parse("2 ** 3", mode='eval').body
        assert VariableResolutionService._evaluate_ast_node(node) == 8

    def test_unary_plus(self):
        node = ast.parse("+5", mode='eval').body
        assert VariableResolutionService._evaluate_ast_node(node) == 5

    def test_unary_minus(self):
        node = ast.parse("-5", mode='eval').body
        assert VariableResolutionService._evaluate_ast_node(node) == -5

    def test_unsupported_node_raises(self):
        node = ast.parse("x", mode='eval').body  # Name node
        with pytest.raises(ValueError, match="Unsupported"):
            VariableResolutionService._evaluate_ast_node(node)


# ---------------------------------------------------------------------------
# _safe_eval_expression
# ---------------------------------------------------------------------------

class TestSafeEvalExpression:
    def test_valid_addition(self):
        assert VariableResolutionService._safe_eval_expression("2 + 3") == 5

    def test_invalid_syntax_raises_value_error(self):
        with pytest.raises(ValueError, match="syntax"):
            VariableResolutionService._safe_eval_expression("2 +")

    def test_order_of_operations(self):
        result = VariableResolutionService._safe_eval_expression("2 + 3 * 4")
        assert result == 14

    def test_complex_expression(self):
        result = VariableResolutionService._safe_eval_expression("10.5 - 0.5")
        assert result == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# _has_nonempty_scalar
# ---------------------------------------------------------------------------

class TestHasNonemptyScalar:
    def test_none_is_empty(self):
        assert VariableResolutionService._has_nonempty_scalar(None) is False

    def test_empty_string_is_empty(self):
        assert VariableResolutionService._has_nonempty_scalar("") is False

    def test_whitespace_only_is_empty(self):
        assert VariableResolutionService._has_nonempty_scalar("   ") is False

    def test_nonempty_string(self):
        assert VariableResolutionService._has_nonempty_scalar("hello") is True

    def test_zero_is_nonempty(self):
        assert VariableResolutionService._has_nonempty_scalar(0) is True

    def test_false_is_nonempty(self):
        assert VariableResolutionService._has_nonempty_scalar(False) is True

    def test_positive_number(self):
        assert VariableResolutionService._has_nonempty_scalar(42) is True

    def test_negative_number(self):
        assert VariableResolutionService._has_nonempty_scalar(-1) is True


# ---------------------------------------------------------------------------
# format_variable_value
# ---------------------------------------------------------------------------

class TestFormatVariableValue:
    def test_none_returns_empty(self):
        assert VariableResolutionService.format_variable_value(None, {}) == ''

    def test_non_numeric_string_returned_as_is(self):
        assert VariableResolutionService.format_variable_value("hello world", {}) == "hello world"

    def test_whole_number_auto(self):
        result = VariableResolutionService.format_variable_value(42, {})
        assert result == "42"

    def test_float_auto_preserves_decimals(self):
        result = VariableResolutionService.format_variable_value(3.14, {})
        assert result == "3.14"

    def test_whole_decimal_mode(self):
        result = VariableResolutionService.format_variable_value(42.7, {'format_decimal_places': 'whole'})
        assert result == "43"

    def test_fixed_decimal_places(self):
        result = VariableResolutionService.format_variable_value(3.14159, {'format_decimal_places': 2})
        assert result == "3.14"

    def test_fixed_decimal_places_zero(self):
        result = VariableResolutionService.format_variable_value(3.7, {'format_decimal_places': 0})
        assert result == "3"

    def test_thousands_separator_no_decimal(self):
        result = VariableResolutionService.format_variable_value(1234567, {'format_thousands_separator': True})
        assert result == "1,234,567"

    def test_thousands_separator_with_fixed_decimals(self):
        result = VariableResolutionService.format_variable_value(
            1234.56, {'format_thousands_separator': True, 'format_decimal_places': 2}
        )
        assert result == "1,234.56"

    def test_invalid_decimal_places_defaults_to_zero(self):
        result = VariableResolutionService.format_variable_value(3.7, {'format_decimal_places': 'bad'})
        assert result == "3"

    def test_negative_decimal_places_defaults_to_zero(self):
        result = VariableResolutionService.format_variable_value(3.7, {'format_decimal_places': -1})
        assert result == "3"

    def test_trailing_zeros_removed(self):
        result = VariableResolutionService.format_variable_value(3.10, {'format_decimal_places': 2})
        assert result == "3.1"

    def test_whole_float_auto(self):
        result = VariableResolutionService.format_variable_value(5.0, {})
        assert result == "5"

    def test_thousands_separator_with_whole_decimal_mode(self):
        result = VariableResolutionService.format_variable_value(
            1234.6, {'format_thousands_separator': True, 'format_decimal_places': 'whole'}
        )
        assert result == "1,235"

    def test_auto_decimal_with_decimal_part(self):
        # 3.14 has 2 decimal places
        result = VariableResolutionService.format_variable_value(3.14, {'format_decimal_places': 'auto'})
        assert result == "3.14"

    def test_auto_decimal_for_whole(self):
        result = VariableResolutionService.format_variable_value(7.0, {'format_decimal_places': 'auto'})
        assert result == "7"


# ---------------------------------------------------------------------------
# _evaluate_formula
# ---------------------------------------------------------------------------

class TestEvaluateFormula:
    def test_none_value_returns_none(self):
        assert VariableResolutionService._evaluate_formula("+1", None) is None

    def test_non_numeric_value_returns_as_is(self):
        result = VariableResolutionService._evaluate_formula("+1", "not_a_number")
        assert result == "not_a_number"

    def test_add(self):
        assert VariableResolutionService._evaluate_formula("+5", 10) == 15

    def test_subtract(self):
        assert VariableResolutionService._evaluate_formula("-3", 10) == 7

    def test_multiply(self):
        assert VariableResolutionService._evaluate_formula("*2", 5) == 10

    def test_divide(self):
        assert VariableResolutionService._evaluate_formula("/4", 8) == 2

    def test_result_is_int_when_whole(self):
        result = VariableResolutionService._evaluate_formula("+0", 5)
        assert result == 5
        assert isinstance(result, int)

    def test_result_is_float_when_fractional(self):
        result = VariableResolutionService._evaluate_formula("/3", 10)
        assert isinstance(result, float)
        assert abs(result - 3.333333) < 0.001

    def test_unsafe_characters_returns_original(self):
        result = VariableResolutionService._evaluate_formula("__import__('os')", 5)
        assert result == 5

    def test_variable_placeholder_replacement(self):
        result = VariableResolutionService._evaluate_formula("[variable]+1", 10)
        assert result == 11

    def test_formula_with_spaces_stripped(self):
        result = VariableResolutionService._evaluate_formula("  +5  ", 10)
        assert result == 15

    def test_division_by_zero_returns_original(self):
        result = VariableResolutionService._evaluate_formula("/0", 5)
        assert result == 5

    def test_float_value_input(self):
        result = VariableResolutionService._evaluate_formula("+1", 2.5)
        assert result == pytest.approx(3.5)


# ---------------------------------------------------------------------------
# replace_variables_if_placeholders
# ---------------------------------------------------------------------------

class TestReplaceVariablesIfPlaceholders:
    def test_none_text_returns_none(self):
        assert VariableResolutionService.replace_variables_if_placeholders(None, {"x": 1}) is None

    def test_empty_text_returns_empty(self):
        assert VariableResolutionService.replace_variables_if_placeholders("", {"x": 1}) == ""

    def test_no_brackets_returns_unchanged(self):
        result = VariableResolutionService.replace_variables_if_placeholders("hello", {"var": 1})
        assert result == "hello"

    def test_no_resolved_vars_returns_unchanged(self):
        result = VariableResolutionService.replace_variables_if_placeholders("[var]", {})
        assert result == "[var]"

    def test_replaces_known_variable(self):
        result = VariableResolutionService.replace_variables_if_placeholders("[x]", {"x": 42})
        assert result == "42"

    def test_delegates_to_replace_variables_in_text(self):
        with patch.object(VariableResolutionService, 'replace_variables_in_text', return_value='replaced') as mock_fn:
            result = VariableResolutionService.replace_variables_if_placeholders("[x]", {"x": 1}, {"x": {}})
            mock_fn.assert_called_once()
        assert result == 'replaced'


# ---------------------------------------------------------------------------
# replace_variables_in_text
# ---------------------------------------------------------------------------

class TestReplaceVariablesInText:
    def test_none_text_returns_none(self):
        assert VariableResolutionService.replace_variables_in_text(None, {}) is None

    def test_empty_text_returns_empty(self):
        assert VariableResolutionService.replace_variables_in_text("", {}) == ""

    def test_no_brackets_returns_unchanged(self):
        result = VariableResolutionService.replace_variables_in_text("No placeholders here", {"x": 1})
        assert result == "No placeholders here"

    def test_simple_variable_replacement(self):
        result = VariableResolutionService.replace_variables_in_text("[amount]", {"amount": 100})
        assert result == "100"

    def test_unknown_variable_stays_unchanged(self):
        result = VariableResolutionService.replace_variables_in_text("[unknown]", {"other": 1})
        assert result == "[unknown]"

    def test_none_value_becomes_empty_string(self):
        result = VariableResolutionService.replace_variables_in_text("[amount]", {"amount": None})
        assert result == ""

    def test_none_value_uses_default(self):
        configs = {"amount": {"default_value": "999"}}
        result = VariableResolutionService.replace_variables_in_text(
            "[amount]", {"amount": None}, configs
        )
        assert result == "999"

    def test_none_value_empty_default_becomes_empty(self):
        configs = {"amount": {"default_value": ""}}
        result = VariableResolutionService.replace_variables_in_text(
            "[amount]", {"amount": None}, configs
        )
        assert result == ""

    def test_formula_replacement(self):
        result = VariableResolutionService.replace_variables_in_text("[[period]+1]", {"period": 2024})
        assert result == "2025"

    def test_formula_multiply(self):
        result = VariableResolutionService.replace_variables_in_text("[[count]*2]", {"count": 5})
        assert result == "10"

    def test_formula_unknown_variable_stays_unchanged(self):
        result = VariableResolutionService.replace_variables_in_text("[[unknown]+1]", {"other": 1})
        assert result == "[[unknown]+1]"

    def test_formula_none_value_with_numeric_default(self):
        configs = {"period": {"default_value": "2024"}}
        result = VariableResolutionService.replace_variables_in_text(
            "[[period]+1]", {"period": None}, configs
        )
        assert result == "2025"

    def test_formula_none_value_no_default_stays_unchanged(self):
        result = VariableResolutionService.replace_variables_in_text("[[period]+1]", {"period": None})
        assert result == "[[period]+1]"

    def test_formula_none_value_non_numeric_default_stays_unchanged(self):
        configs = {"period": {"default_value": "text"}}
        result = VariableResolutionService.replace_variables_in_text(
            "[[period]+1]", {"period": None}, configs
        )
        assert result == "[[period]+1]"

    def test_value_with_thousands_formatting(self):
        configs = {"amount": {"format_thousands_separator": True}}
        result = VariableResolutionService.replace_variables_in_text(
            "[amount]", {"amount": 1234567}, configs
        )
        assert result == "1,234,567"

    def test_value_with_decimal_formatting(self):
        configs = {"amount": {"format_decimal_places": 2}}
        result = VariableResolutionService.replace_variables_in_text(
            "[amount]", {"amount": 3.14159}, configs
        )
        assert result == "3.14"

    def test_formula_with_thousands_formatting(self):
        configs = {"amount": {"format_thousands_separator": True}}
        result = VariableResolutionService.replace_variables_in_text(
            "[[amount]+0]", {"amount": 1234567}, configs
        )
        assert "1,234,567" in result

    def test_default_with_numeric_formatting(self):
        configs = {"amount": {"default_value": "5000", "format_thousands_separator": True}}
        result = VariableResolutionService.replace_variables_in_text(
            "[amount]", {"amount": None}, configs
        )
        assert result == "5,000"

    def test_default_non_numeric_with_formatting_attempts(self):
        configs = {"amount": {"default_value": "N/A", "format_thousands_separator": True}}
        result = VariableResolutionService.replace_variables_in_text(
            "[amount]", {"amount": None}, configs
        )
        assert result == "N/A"

    def test_multiple_variables(self):
        result = VariableResolutionService.replace_variables_in_text(
            "[a] and [b]", {"a": 1, "b": 2}
        )
        assert result == "1 and 2"

    def test_plugin_label_variable_untouched(self):
        result = VariableResolutionService.replace_variables_in_text("Section [EO1]", {})
        assert "[EO1]" in result

    def test_text_unchanged_when_no_matches(self):
        result = VariableResolutionService.replace_variables_in_text("[x]", {"y": 5})
        assert result == "[x]"

    def test_formula_error_returns_original_match(self):
        # Provide a formula where evaluation itself raises
        with patch.object(VariableResolutionService, '_evaluate_formula', side_effect=Exception("boom")):
            result = VariableResolutionService.replace_variables_in_text("[[val]+1]", {"val": 5})
        assert "[[val]+1]" in result


# ---------------------------------------------------------------------------
# _resolve_metadata_variable
# ---------------------------------------------------------------------------

class TestResolveMetadataVariable:

    def _aes(self, entity_type='country', entity_id=42):
        aes = MagicMock()
        aes.entity_type = entity_type
        aes.entity_id = entity_id
        return aes

    def test_missing_metadata_type_returns_none(self):
        result = VariableResolutionService._resolve_metadata_variable({}, self._aes(), None)
        assert result is None

    def test_entity_id(self):
        aes = self._aes(entity_id=99)
        result = VariableResolutionService._resolve_metadata_variable({'metadata_type': 'entity_id'}, aes, None)
        assert result == '99'

    def test_entity_type(self):
        aes = self._aes(entity_type='country')
        result = VariableResolutionService._resolve_metadata_variable({'metadata_type': 'entity_type'}, aes, None)
        assert result == 'country'

    def test_entity_name(self):
        aes = self._aes()
        with patch('app.services.entity_service.EntityService.get_localized_entity_name', return_value='France'):
            result = VariableResolutionService._resolve_metadata_variable({'metadata_type': 'entity_name'}, aes, None)
        assert result == 'France'

    def test_entity_name_hierarchy(self):
        aes = self._aes()
        with patch('app.services.entity_service.EntityService.get_localized_entity_name', return_value='EU > France'):
            result = VariableResolutionService._resolve_metadata_variable({'metadata_type': 'entity_name_hierarchy'}, aes, None)
        assert result == 'EU > France'

    def test_template_name_from_version(self):
        aes = self._aes()
        tv = MagicMock()
        tv.name = 'My Template'
        result = VariableResolutionService._resolve_metadata_variable({'metadata_type': 'template_name'}, aes, tv)
        assert result == 'My Template'

    def test_template_name_fallback_to_parent(self):
        aes = self._aes()
        tv = MagicMock()
        tv.name = None
        tv.template = MagicMock()
        tv.template.name = 'Parent Template'
        result = VariableResolutionService._resolve_metadata_variable({'metadata_type': 'template_name'}, aes, tv)
        assert result == 'Parent Template'

    def test_template_name_no_version_returns_none(self):
        aes = self._aes()
        result = VariableResolutionService._resolve_metadata_variable({'metadata_type': 'template_name'}, aes, None)
        assert result is None

    def test_assignment_period(self):
        aes = self._aes()
        aes.assigned_form = MagicMock()
        aes.assigned_form.period_name = '2024'
        result = VariableResolutionService._resolve_metadata_variable({'metadata_type': 'assignment_period'}, aes, None)
        assert result == '2024'

    def test_assignment_period_no_assigned_form(self):
        aes = self._aes()
        aes.assigned_form = None
        result = VariableResolutionService._resolve_metadata_variable({'metadata_type': 'assignment_period'}, aes, None)
        assert result is None

    def test_national_society_name_with_country(self):
        aes = self._aes()
        mock_country = MagicMock()
        with patch('app.services.entity_service.EntityService.get_country_for_entity', return_value=mock_country), \
             patch('app.utils.form_localization.get_localized_national_society_name', return_value='French Red Cross'):
            result = VariableResolutionService._resolve_metadata_variable({'metadata_type': 'national_society_name'}, aes, None)
        assert result == 'French Red Cross'

    def test_national_society_name_no_country(self):
        aes = self._aes()
        with patch('app.services.entity_service.EntityService.get_country_for_entity', return_value=None):
            result = VariableResolutionService._resolve_metadata_variable({'metadata_type': 'national_society_name'}, aes, None)
        assert result is None

    def test_national_society_name_ns_name_none(self):
        aes = self._aes()
        mock_country = MagicMock()
        with patch('app.services.entity_service.EntityService.get_country_for_entity', return_value=mock_country), \
             patch('app.utils.form_localization.get_localized_national_society_name', return_value=None):
            result = VariableResolutionService._resolve_metadata_variable({'metadata_type': 'national_society_name'}, aes, None)
        assert result is None

    def test_unknown_metadata_type_returns_none(self):
        aes = self._aes()
        result = VariableResolutionService._resolve_metadata_variable({'metadata_type': 'unknown_type'}, aes, None)
        assert result is None

    def test_entity_name_exception_returns_none(self):
        aes = self._aes()
        with patch('app.services.entity_service.EntityService.get_localized_entity_name', side_effect=Exception("DB error")):
            result = VariableResolutionService._resolve_metadata_variable({'metadata_type': 'entity_name'}, aes, None)
        assert result is None


# ---------------------------------------------------------------------------
# _resolve_builtin_metadata_variables
# ---------------------------------------------------------------------------

class TestResolveBuiltinMetadataVariables:
    def test_all_builtin_tokens_present(self):
        aes = MagicMock()
        with patch.object(VariableResolutionService, '_resolve_metadata_variable', return_value='val'):
            result = VariableResolutionService._resolve_builtin_metadata_variables(aes, None)
        expected = {'entity_name', 'entity_name_hierarchy', 'entity_id', 'entity_type',
                    'national_society_name', 'template_name', 'assignment_period'}
        assert expected == set(result.keys())
        assert all(v == 'val' for v in result.values())

    def test_exception_in_token_returns_none_for_that_token(self):
        aes = MagicMock()
        with patch.object(VariableResolutionService, '_resolve_metadata_variable', side_effect=Exception("error")):
            result = VariableResolutionService._resolve_builtin_metadata_variables(aes, None)
        assert all(v is None for v in result.values())
        assert len(result) == 7


# ---------------------------------------------------------------------------
# _get_entity_statuses_for_scope
# ---------------------------------------------------------------------------

class TestGetEntityStatusesForScope:

    def _af(self, id=1):
        af = MagicMock()
        af.id = id
        return af

    def _cur_aes(self, entity_type='country', entity_id=42):
        aes = MagicMock()
        aes.entity_type = entity_type
        aes.entity_id = entity_id
        return aes

    @patch('app.services.variable_resolution_service.AssignmentEntityStatus')
    def test_same_scope_found(self, mock_aes_cls):
        af = self._af()
        cur_aes = self._cur_aes()
        mock_status = MagicMock()
        mock_status.id = 10
        mock_aes_cls.query.filter_by.return_value.first.return_value = mock_status
        result = VariableResolutionService._get_entity_statuses_for_scope(af, cur_aes, 'same', {})
        assert result == [mock_status]

    @patch('app.services.variable_resolution_service.AssignmentEntityStatus')
    def test_same_scope_not_found(self, mock_aes_cls):
        af = self._af()
        cur_aes = self._cur_aes()
        mock_aes_cls.query.filter_by.return_value.first.return_value = None
        result = VariableResolutionService._get_entity_statuses_for_scope(af, cur_aes, 'same', {})
        assert result == []

    @patch('app.services.variable_resolution_service.AssignmentEntityStatus')
    def test_any_scope_returns_all(self, mock_aes_cls):
        af = self._af()
        cur_aes = self._cur_aes()
        mock_statuses = [MagicMock(), MagicMock()]
        mock_aes_cls.query.filter_by.return_value.all.return_value = mock_statuses
        result = VariableResolutionService._get_entity_statuses_for_scope(af, cur_aes, 'any', {})
        assert result == mock_statuses

    @patch('app.services.variable_resolution_service.AssignmentEntityStatus')
    def test_specific_scope_found(self, mock_aes_cls):
        af = self._af()
        cur_aes = self._cur_aes()
        config = {'specific_entity_type': 'ns', 'specific_entity_id': 88}
        mock_status = MagicMock()
        mock_aes_cls.query.filter_by.return_value.first.return_value = mock_status
        result = VariableResolutionService._get_entity_statuses_for_scope(af, cur_aes, 'specific', config)
        assert result == [mock_status]

    @patch('app.services.variable_resolution_service.AssignmentEntityStatus')
    def test_specific_scope_not_found(self, mock_aes_cls):
        af = self._af()
        cur_aes = self._cur_aes()
        config = {'specific_entity_type': 'ns', 'specific_entity_id': 88}
        mock_aes_cls.query.filter_by.return_value.first.return_value = None
        result = VariableResolutionService._get_entity_statuses_for_scope(af, cur_aes, 'specific', config)
        assert result == []

    def test_specific_scope_missing_entity_type(self):
        af = self._af()
        cur_aes = self._cur_aes()
        config = {'specific_entity_id': 88}  # missing specific_entity_type
        result = VariableResolutionService._get_entity_statuses_for_scope(af, cur_aes, 'specific', config)
        assert result == []

    def test_specific_scope_missing_entity_id(self):
        af = self._af()
        cur_aes = self._cur_aes()
        config = {'specific_entity_type': 'ns'}  # missing specific_entity_id
        result = VariableResolutionService._get_entity_statuses_for_scope(af, cur_aes, 'specific', config)
        assert result == []

    def test_unknown_scope_returns_empty(self):
        af = self._af()
        cur_aes = self._cur_aes()
        result = VariableResolutionService._get_entity_statuses_for_scope(af, cur_aes, 'unknown_scope', {})
        assert result == []

    @patch('app.services.variable_resolution_service.AssignmentEntityStatus')
    def test_entities_containing_no_source_form_item_id(self, mock_aes_cls):
        af = self._af()
        cur_aes = self._cur_aes(entity_id=88)
        mock_aes_cls.query.filter_by.return_value.all.return_value = []
        result = VariableResolutionService._get_entity_statuses_for_scope(af, cur_aes, 'entities_containing', {})
        assert result == []

    @patch('app.services.variable_resolution_service.FormData')
    @patch('app.services.variable_resolution_service.AssignmentEntityStatus')
    def test_entities_containing_scope_matches_correct_entities(self, mock_aes_cls, mock_fd_cls):
        af = self._af()
        cur_aes = self._cur_aes(entity_id=88)

        aes1 = MagicMock()
        aes1.id = 1
        aes1.entity_type = 'country'
        aes1.entity_id = 10
        aes2 = MagicMock()
        aes2.id = 2
        aes2.entity_type = 'country'
        aes2.entity_id = 20
        mock_aes_cls.query.filter_by.return_value.all.return_value = [aes1, aes2]

        fd1 = MagicMock()
        fd1.assignment_entity_status_id = 1
        fd1.disagg_data = {'88_col1': 1, '_table': 'ns'}
        fd2 = MagicMock()
        fd2.assignment_entity_status_id = 2
        fd2.disagg_data = {'99_col1': 1}
        mock_fd_cls.query.filter.return_value.order_by.return_value.all.return_value = [fd1, fd2]

        config = {'source_form_item_id': 5}
        result = VariableResolutionService._get_entity_statuses_for_scope(af, cur_aes, 'entities_containing', config)
        assert aes1 in result
        assert aes2 not in result

    @patch('app.services.variable_resolution_service.FormData')
    @patch('app.services.variable_resolution_service.AssignmentEntityStatus')
    def test_entities_containing_no_disagg_data(self, mock_aes_cls, mock_fd_cls):
        af = self._af()
        cur_aes = self._cur_aes(entity_id=88)

        aes1 = MagicMock()
        aes1.id = 1
        mock_aes_cls.query.filter_by.return_value.all.return_value = [aes1]

        fd1 = MagicMock()
        fd1.assignment_entity_status_id = 1
        fd1.disagg_data = None  # no disagg_data
        mock_fd_cls.query.filter.return_value.order_by.return_value.all.return_value = [fd1]

        config = {'source_form_item_id': 5}
        result = VariableResolutionService._get_entity_statuses_for_scope(af, cur_aes, 'entities_containing', config)
        assert result == []

    @patch('app.services.variable_resolution_service.FormData')
    @patch('app.services.variable_resolution_service.AssignmentEntityStatus')
    def test_entities_containing_non_dict_disagg_data(self, mock_aes_cls, mock_fd_cls):
        af = self._af()
        cur_aes = self._cur_aes(entity_id=88)

        aes1 = MagicMock()
        aes1.id = 1
        mock_aes_cls.query.filter_by.return_value.all.return_value = [aes1]

        fd1 = MagicMock()
        fd1.assignment_entity_status_id = 1
        fd1.disagg_data = "not a dict"
        mock_fd_cls.query.filter.return_value.order_by.return_value.all.return_value = [fd1]

        config = {'source_form_item_id': 5}
        result = VariableResolutionService._get_entity_statuses_for_scope(af, cur_aes, 'entities_containing', config)
        assert result == []


# ---------------------------------------------------------------------------
# _resolve_entities_containing
# ---------------------------------------------------------------------------

class TestResolveEntitiesContaining:

    def _aes_list(self, ids=None):
        result = []
        for eid in (ids or [10, 20]):
            aes = MagicMock()
            aes.entity_type = 'country'
            aes.entity_id = eid
            result.append(aes)
        return result

    def test_empty_entity_statuses_returns_none(self):
        result = VariableResolutionService._resolve_entities_containing([], {})
        assert result is None

    @patch('app.services.variable_resolution_service.FormData')
    def test_auto_load_format_default(self, mock_fd_cls):
        entity_statuses = self._aes_list([10, 20])
        fd = MagicMock()
        fd.disagg_data = {'_table': 'ns'}
        mock_fd_cls.query.filter_by.return_value.order_by.return_value.first.return_value = fd

        config = {'source_form_item_id': 5}  # default return_format -> auto_load_format
        result = VariableResolutionService._resolve_entities_containing(entity_statuses, config)
        parsed = json.loads(result)
        assert 'entities' in parsed
        assert parsed['entity_type'] == 'ns'
        assert len(parsed['entities']) == 2

    @patch('app.services.variable_resolution_service.FormData')
    def test_auto_load_format_no_disagg(self, mock_fd_cls):
        entity_statuses = self._aes_list([10])
        mock_fd_cls.query.filter_by.return_value.order_by.return_value.first.return_value = None

        config = {'source_form_item_id': 5, 'return_format': 'auto_load_format'}
        result = VariableResolutionService._resolve_entities_containing(entity_statuses, config)
        parsed = json.loads(result)
        assert parsed['entity_type'] is None

    @patch('app.services.variable_resolution_service.FormData')
    def test_ids_comma_format(self, mock_fd_cls):
        entity_statuses = self._aes_list([10, 20])
        mock_fd_cls.query.filter_by.return_value.order_by.return_value.first.return_value = None
        config = {'source_form_item_id': 5, 'return_format': 'ids_comma'}
        result = VariableResolutionService._resolve_entities_containing(entity_statuses, config)
        assert result == '10, 20'

    @patch('app.services.variable_resolution_service.FormData')
    def test_ids_json_format(self, mock_fd_cls):
        entity_statuses = self._aes_list([10, 20])
        mock_fd_cls.query.filter_by.return_value.order_by.return_value.first.return_value = None
        config = {'source_form_item_id': 5, 'return_format': 'ids_json'}
        result = VariableResolutionService._resolve_entities_containing(entity_statuses, config)
        assert json.loads(result) == [10, 20]

    @patch('app.services.variable_resolution_service.FormData')
    def test_names_comma_format(self, mock_fd_cls):
        entity_statuses = self._aes_list([10])
        mock_fd_cls.query.filter_by.return_value.order_by.return_value.first.return_value = None
        config = {'source_form_item_id': 5, 'return_format': 'names_comma'}
        with patch('app.services.entity_service.EntityService.get_localized_entity_name', return_value='France'):
            result = VariableResolutionService._resolve_entities_containing(entity_statuses, config)
        assert result == 'France'

    @patch('app.services.variable_resolution_service.FormData')
    def test_names_comma_format_fallback_when_name_none(self, mock_fd_cls):
        entity_statuses = self._aes_list([10])
        mock_fd_cls.query.filter_by.return_value.order_by.return_value.first.return_value = None
        config = {'source_form_item_id': 5, 'return_format': 'names_comma'}
        with patch('app.services.entity_service.EntityService.get_localized_entity_name', return_value=None):
            result = VariableResolutionService._resolve_entities_containing(entity_statuses, config)
        assert result == 'Entity 10'

    @patch('app.services.variable_resolution_service.FormData')
    def test_ids_and_names_comma_with_name(self, mock_fd_cls):
        entity_statuses = self._aes_list([10])
        mock_fd_cls.query.filter_by.return_value.order_by.return_value.first.return_value = None
        config = {'source_form_item_id': 5, 'return_format': 'ids_and_names_comma'}
        with patch('app.services.entity_service.EntityService.get_localized_entity_name', return_value='France'):
            result = VariableResolutionService._resolve_entities_containing(entity_statuses, config)
        assert result == '10 (France)'

    @patch('app.services.variable_resolution_service.FormData')
    def test_ids_and_names_comma_no_name(self, mock_fd_cls):
        entity_statuses = self._aes_list([10])
        mock_fd_cls.query.filter_by.return_value.order_by.return_value.first.return_value = None
        config = {'source_form_item_id': 5, 'return_format': 'ids_and_names_comma'}
        with patch('app.services.entity_service.EntityService.get_localized_entity_name', return_value=None):
            result = VariableResolutionService._resolve_entities_containing(entity_statuses, config)
        assert result == '10'

    @patch('app.services.variable_resolution_service.FormData')
    def test_unknown_return_format_defaults_to_ids(self, mock_fd_cls):
        entity_statuses = self._aes_list([10, 20])
        mock_fd_cls.query.filter_by.return_value.order_by.return_value.first.return_value = None
        config = {'source_form_item_id': 5, 'return_format': 'invalid_format'}
        result = VariableResolutionService._resolve_entities_containing(entity_statuses, config)
        assert result == '10, 20'

    @patch('app.services.variable_resolution_service.FormData')
    def test_no_source_form_item_id_auto_load(self, mock_fd_cls):
        entity_statuses = self._aes_list([10])
        config = {'return_format': 'auto_load_format'}
        result = VariableResolutionService._resolve_entities_containing(entity_statuses, config)
        parsed = json.loads(result)
        assert parsed['entity_type'] is None


# ---------------------------------------------------------------------------
# _resolve_entities_containing_for_matrix_cell
# ---------------------------------------------------------------------------

class TestResolveEntitiesContainingForMatrixCell:

    def test_empty_entity_statuses_returns_zero(self):
        result = VariableResolutionService._resolve_entities_containing_for_matrix_cell([], 5, {})
        assert result == 0

    def test_no_current_aes_fallback_match(self):
        aes = MagicMock()
        aes.entity_id = 5
        result = VariableResolutionService._resolve_entities_containing_for_matrix_cell([aes], 5, {}, None)
        assert result == 1

    def test_no_current_aes_fallback_no_match(self):
        aes = MagicMock()
        aes.entity_id = 99
        result = VariableResolutionService._resolve_entities_containing_for_matrix_cell([aes], 5, {}, None)
        assert result == 0

    def test_missing_matrix_column_fallback_match(self):
        aes = MagicMock()
        aes.entity_id = 5
        cur_aes = MagicMock()
        cur_aes.entity_id = 10
        result = VariableResolutionService._resolve_entities_containing_for_matrix_cell(
            [aes], 5, {}, cur_aes  # no matrix_column_name
        )
        assert result == 1

    def test_missing_source_form_item_id_fallback(self):
        aes = MagicMock()
        aes.entity_id = 5
        cur_aes = MagicMock()
        cur_aes.entity_id = 10
        config = {'matrix_column_name': 'SP2'}  # no source_form_item_id
        result = VariableResolutionService._resolve_entities_containing_for_matrix_cell(
            [aes], 5, config, cur_aes
        )
        assert result == 1

    @patch('app.services.variable_resolution_service.FormData')
    def test_row_entity_not_in_list_returns_zero(self, mock_fd_cls):
        aes = MagicMock()
        aes.entity_id = 99
        cur_aes = MagicMock()
        cur_aes.entity_id = 10
        config = {'matrix_column_name': 'SP2', 'source_form_item_id': 5}
        result = VariableResolutionService._resolve_entities_containing_for_matrix_cell(
            [aes], 5, config, cur_aes
        )
        assert result == 0

    @patch('app.services.variable_resolution_service.FormData')
    def test_found_numeric_cell_value(self, mock_fd_cls):
        aes = MagicMock()
        aes.id = 1
        aes.entity_id = 5
        cur_aes = MagicMock()
        cur_aes.entity_id = 10

        fd = MagicMock()
        fd.disagg_data = {'10_SP2': 1, '_table': 'ns'}
        mock_fd_cls.query.filter_by.return_value.order_by.return_value.first.return_value = fd

        config = {'matrix_column_name': 'SP2', 'source_form_item_id': 5}
        result = VariableResolutionService._resolve_entities_containing_for_matrix_cell(
            [aes], 5, config, cur_aes
        )
        assert result == 1.0

    @patch('app.services.variable_resolution_service.FormData')
    def test_no_form_data_returns_zero(self, mock_fd_cls):
        aes = MagicMock()
        aes.id = 1
        aes.entity_id = 5
        cur_aes = MagicMock()
        cur_aes.entity_id = 10
        mock_fd_cls.query.filter_by.return_value.order_by.return_value.first.return_value = None

        config = {'matrix_column_name': 'SP2', 'source_form_item_id': 5}
        result = VariableResolutionService._resolve_entities_containing_for_matrix_cell(
            [aes], 5, config, cur_aes
        )
        assert result == 0

    @patch('app.services.variable_resolution_service.FormData')
    def test_no_disagg_data_returns_zero(self, mock_fd_cls):
        aes = MagicMock()
        aes.id = 1
        aes.entity_id = 5
        cur_aes = MagicMock()
        cur_aes.entity_id = 10

        fd = MagicMock()
        fd.disagg_data = None
        mock_fd_cls.query.filter_by.return_value.order_by.return_value.first.return_value = fd

        config = {'matrix_column_name': 'SP2', 'source_form_item_id': 5}
        result = VariableResolutionService._resolve_entities_containing_for_matrix_cell(
            [aes], 5, config, cur_aes
        )
        assert result == 0

    @patch('app.services.variable_resolution_service.FormData')
    def test_key_not_found_in_matrix_returns_zero(self, mock_fd_cls):
        aes = MagicMock()
        aes.id = 1
        aes.entity_id = 5
        cur_aes = MagicMock()
        cur_aes.entity_id = 10

        fd = MagicMock()
        fd.disagg_data = {'99_SP2': 1}  # different entity key
        mock_fd_cls.query.filter_by.return_value.order_by.return_value.first.return_value = fd

        config = {'matrix_column_name': 'SP2', 'source_form_item_id': 5}
        result = VariableResolutionService._resolve_entities_containing_for_matrix_cell(
            [aes], 5, config, cur_aes
        )
        assert result == 0

    @patch('app.services.variable_resolution_service.FormData')
    def test_row_total_mode(self, mock_fd_cls):
        aes = MagicMock()
        aes.id = 1
        aes.entity_id = 5
        cur_aes = MagicMock()
        cur_aes.entity_id = 10

        fd = MagicMock()
        fd.disagg_data = {'10_col1': 5, '10_col2': 3, '_table': 'ns'}
        mock_fd_cls.query.filter_by.return_value.order_by.return_value.first.return_value = fd

        config = {'matrix_column_name': '_row_total', 'source_form_item_id': 5}
        result = VariableResolutionService._resolve_entities_containing_for_matrix_cell(
            [aes], 5, config, cur_aes
        )
        assert result == 8.0

    @patch('app.services.variable_resolution_service.FormData')
    def test_row_total_mode_no_data_returns_zero(self, mock_fd_cls):
        aes = MagicMock()
        aes.id = 1
        aes.entity_id = 5
        cur_aes = MagicMock()
        cur_aes.entity_id = 10

        fd = MagicMock()
        fd.disagg_data = {}  # empty - _matrix_row_total returns None
        mock_fd_cls.query.filter_by.return_value.order_by.return_value.first.return_value = fd

        config = {'matrix_column_name': '_row_total', 'source_form_item_id': 5}
        result = VariableResolutionService._resolve_entities_containing_for_matrix_cell(
            [aes], 5, config, cur_aes
        )
        assert result == 0

    @patch('app.services.variable_resolution_service.FormData')
    def test_non_numeric_cell_value_returned(self, mock_fd_cls):
        aes = MagicMock()
        aes.id = 1
        aes.entity_id = 5
        cur_aes = MagicMock()
        cur_aes.entity_id = 10

        fd = MagicMock()
        fd.disagg_data = {'10_SP2': 'yes'}
        mock_fd_cls.query.filter_by.return_value.order_by.return_value.first.return_value = fd

        config = {'matrix_column_name': 'SP2', 'source_form_item_id': 5}
        result = VariableResolutionService._resolve_entities_containing_for_matrix_cell(
            [aes], 5, config, cur_aes
        )
        assert result == 'yes'

    @patch('app.services.variable_resolution_service.FormData')
    def test_non_dict_disagg_returns_zero(self, mock_fd_cls):
        aes = MagicMock()
        aes.id = 1
        aes.entity_id = 5
        cur_aes = MagicMock()
        cur_aes.entity_id = 10

        fd = MagicMock()
        fd.disagg_data = "not a dict"
        mock_fd_cls.query.filter_by.return_value.order_by.return_value.first.return_value = fd

        config = {'matrix_column_name': 'SP2', 'source_form_item_id': 5}
        result = VariableResolutionService._resolve_entities_containing_for_matrix_cell(
            [aes], 5, config, cur_aes
        )
        assert result == 0


# ---------------------------------------------------------------------------
# _resolve_single_variable
# ---------------------------------------------------------------------------

class TestResolveSingleVariable:

    def _aes(self, entity_type='country', entity_id=1):
        aes = MagicMock()
        aes.entity_type = entity_type
        aes.entity_id = entity_id
        return aes

    def test_missing_source_template_id(self):
        aes = self._aes()
        result = VariableResolutionService._resolve_single_variable(
            {'source_assignment_period': '2023', 'source_form_item_id': 5}, aes
        )
        assert result is None

    def test_missing_source_period(self):
        aes = self._aes()
        result = VariableResolutionService._resolve_single_variable(
            {'source_template_id': 1, 'source_form_item_id': 5}, aes
        )
        assert result is None

    def test_missing_source_form_item_id(self):
        aes = self._aes()
        result = VariableResolutionService._resolve_single_variable(
            {'source_template_id': 1, 'source_assignment_period': '2023'}, aes
        )
        assert result is None

    @patch('app.services.variable_resolution_service.AssignedForm')
    def test_no_assigned_form_returns_none(self, mock_af):
        aes = self._aes()
        mock_af.query.filter_by.return_value.first.return_value = None
        result = VariableResolutionService._resolve_single_variable(
            {'source_template_id': 1, 'source_assignment_period': '2023', 'source_form_item_id': 5}, aes
        )
        assert result is None

    @patch('app.services.variable_resolution_service.AssignmentEntityStatus')
    @patch('app.services.variable_resolution_service.AssignedForm')
    def test_no_entity_statuses_returns_none(self, mock_af, mock_aes_cls):
        aes = self._aes()
        af = MagicMock()
        af.id = 1
        mock_af.query.filter_by.return_value.first.return_value = af
        mock_aes_cls.query.filter_by.return_value.first.return_value = None

        result = VariableResolutionService._resolve_single_variable(
            {'source_template_id': 1, 'source_assignment_period': '2023', 'source_form_item_id': 5}, aes
        )
        assert result is None

    @patch('app.services.variable_resolution_service.FormData')
    @patch('app.services.variable_resolution_service.AssignmentEntityStatus')
    @patch('app.services.variable_resolution_service.AssignedForm')
    def test_no_form_data_returns_none(self, mock_af, mock_aes_cls, mock_fd_cls):
        aes = self._aes()
        af = MagicMock()
        af.id = 1
        mock_af.query.filter_by.return_value.first.return_value = af
        entity_status = MagicMock()
        entity_status.id = 10
        mock_aes_cls.query.filter_by.return_value.first.return_value = entity_status
        mock_fd_cls.query.filter.return_value.order_by.return_value.all.return_value = []

        result = VariableResolutionService._resolve_single_variable(
            {'source_template_id': 1, 'source_assignment_period': '2023', 'source_form_item_id': 5}, aes
        )
        assert result is None

    @patch('app.services.variable_resolution_service.FormData')
    @patch('app.services.variable_resolution_service.AssignmentEntityStatus')
    @patch('app.services.variable_resolution_service.AssignedForm')
    def test_indicator_numeric_value(self, mock_af, mock_aes_cls, mock_fd_cls):
        aes = self._aes()
        af = MagicMock()
        af.id = 1
        mock_af.query.filter_by.return_value.first.return_value = af
        es = MagicMock()
        es.id = 10
        mock_aes_cls.query.filter_by.return_value.first.return_value = es

        entry = MagicMock()
        entry.value = '42'
        entry.disagg_data = None
        entry.form_item = MagicMock()
        entry.form_item.is_indicator = True
        mock_fd_cls.query.filter.return_value.order_by.return_value.all.return_value = [entry]

        result = VariableResolutionService._resolve_single_variable(
            {'source_template_id': 1, 'source_assignment_period': '2023', 'source_form_item_id': 5}, aes
        )
        assert result == 42.0

    @patch('app.services.variable_resolution_service.FormData')
    @patch('app.services.variable_resolution_service.AssignmentEntityStatus')
    @patch('app.services.variable_resolution_service.AssignedForm')
    def test_indicator_comma_formatted_value(self, mock_af, mock_aes_cls, mock_fd_cls):
        aes = self._aes()
        af = MagicMock()
        af.id = 1
        mock_af.query.filter_by.return_value.first.return_value = af
        es = MagicMock()
        es.id = 10
        mock_aes_cls.query.filter_by.return_value.first.return_value = es

        entry = MagicMock()
        entry.value = '1,234'
        entry.disagg_data = None
        entry.form_item = MagicMock()
        entry.form_item.is_indicator = True
        mock_fd_cls.query.filter.return_value.order_by.return_value.all.return_value = [entry]

        result = VariableResolutionService._resolve_single_variable(
            {'source_template_id': 1, 'source_assignment_period': '2023', 'source_form_item_id': 5}, aes
        )
        assert result == 1234.0

    @patch('app.services.variable_resolution_service.FormData')
    @patch('app.services.variable_resolution_service.AssignmentEntityStatus')
    @patch('app.services.variable_resolution_service.AssignedForm')
    def test_indicator_non_numeric_value_returned_as_is(self, mock_af, mock_aes_cls, mock_fd_cls):
        aes = self._aes()
        af = MagicMock()
        af.id = 1
        mock_af.query.filter_by.return_value.first.return_value = af
        es = MagicMock()
        es.id = 10
        mock_aes_cls.query.filter_by.return_value.first.return_value = es

        entry = MagicMock()
        entry.value = 'N/A'
        entry.disagg_data = None
        entry.form_item = MagicMock()
        entry.form_item.is_indicator = True
        mock_fd_cls.query.filter.return_value.order_by.return_value.all.return_value = [entry]

        result = VariableResolutionService._resolve_single_variable(
            {'source_template_id': 1, 'source_assignment_period': '2023', 'source_form_item_id': 5}, aes
        )
        assert result == 'N/A'

    @patch('app.services.variable_resolution_service.FormData')
    @patch('app.services.variable_resolution_service.AssignmentEntityStatus')
    @patch('app.services.variable_resolution_service.AssignedForm')
    def test_indicator_disagg_sum(self, mock_af, mock_aes_cls, mock_fd_cls):
        aes = self._aes()
        af = MagicMock()
        af.id = 1
        mock_af.query.filter_by.return_value.first.return_value = af
        es = MagicMock()
        es.id = 10
        mock_aes_cls.query.filter_by.return_value.first.return_value = es

        entry = MagicMock()
        entry.value = None
        entry.disagg_data = {'values': {'cat1': '10', 'cat2': '20'}}
        entry.form_item = MagicMock()
        entry.form_item.is_indicator = True
        mock_fd_cls.query.filter.return_value.order_by.return_value.all.return_value = [entry]

        result = VariableResolutionService._resolve_single_variable(
            {'source_template_id': 1, 'source_assignment_period': '2023', 'source_form_item_id': 5}, aes
        )
        assert result == 30.0

    @patch('app.services.variable_resolution_service.FormData')
    @patch('app.services.variable_resolution_service.AssignmentEntityStatus')
    @patch('app.services.variable_resolution_service.AssignedForm')
    def test_indicator_empty_disagg_returns_none(self, mock_af, mock_aes_cls, mock_fd_cls):
        aes = self._aes()
        af = MagicMock()
        af.id = 1
        mock_af.query.filter_by.return_value.first.return_value = af
        es = MagicMock()
        es.id = 10
        mock_aes_cls.query.filter_by.return_value.first.return_value = es

        entry = MagicMock()
        entry.value = None
        entry.disagg_data = {'values': {}}
        entry.form_item = MagicMock()
        entry.form_item.is_indicator = True
        entry.data_not_available = False
        entry.not_applicable = False
        mock_fd_cls.query.filter.return_value.order_by.return_value.all.return_value = [entry]

        result = VariableResolutionService._resolve_single_variable(
            {'source_template_id': 1, 'source_assignment_period': '2023', 'source_form_item_id': 5}, aes
        )
        assert result is None

    @patch('app.services.variable_resolution_service.FormData')
    @patch('app.services.variable_resolution_service.AssignmentEntityStatus')
    @patch('app.services.variable_resolution_service.AssignedForm')
    def test_question_value_returned(self, mock_af, mock_aes_cls, mock_fd_cls):
        aes = self._aes()
        af = MagicMock()
        af.id = 1
        mock_af.query.filter_by.return_value.first.return_value = af
        es = MagicMock()
        es.id = 10
        mock_aes_cls.query.filter_by.return_value.first.return_value = es

        entry = MagicMock()
        entry.value = "text answer"
        entry.form_item = MagicMock()
        entry.form_item.is_indicator = False
        mock_fd_cls.query.filter.return_value.order_by.return_value.all.return_value = [entry]

        result = VariableResolutionService._resolve_single_variable(
            {'source_template_id': 1, 'source_assignment_period': '2023', 'source_form_item_id': 5}, aes
        )
        assert result == "text answer"

    @patch('app.services.variable_resolution_service.FormData')
    @patch('app.services.variable_resolution_service.AssignmentEntityStatus')
    @patch('app.services.variable_resolution_service.AssignedForm')
    def test_matrix_cell_lookup(self, mock_af, mock_aes_cls, mock_fd_cls):
        aes = self._aes()
        af = MagicMock()
        af.id = 1
        mock_af.query.filter_by.return_value.first.return_value = af
        es = MagicMock()
        es.id = 10
        mock_aes_cls.query.filter_by.return_value.first.return_value = es

        entry = MagicMock()
        entry.disagg_data = {'5_col1': 99}
        entry.form_item = MagicMock()
        entry.form_item.is_indicator = True
        mock_fd_cls.query.filter.return_value.order_by.return_value.all.return_value = [entry]

        result = VariableResolutionService._resolve_single_variable(
            {'source_template_id': 1, 'source_assignment_period': '2023', 'source_form_item_id': 5,
             'matrix_column_name': 'col1', '_row_entity_id': 5}, aes
        )
        assert result == 99.0

    @patch('app.services.variable_resolution_service.FormData')
    @patch('app.services.variable_resolution_service.AssignmentEntityStatus')
    @patch('app.services.variable_resolution_service.AssignedForm')
    def test_matrix_row_total(self, mock_af, mock_aes_cls, mock_fd_cls):
        aes = self._aes()
        af = MagicMock()
        af.id = 1
        mock_af.query.filter_by.return_value.first.return_value = af
        es = MagicMock()
        es.id = 10
        mock_aes_cls.query.filter_by.return_value.first.return_value = es

        entry = MagicMock()
        entry.disagg_data = {'5_col1': 10, '5_col2': 20}
        entry.form_item = MagicMock()
        mock_fd_cls.query.filter.return_value.order_by.return_value.all.return_value = [entry]

        result = VariableResolutionService._resolve_single_variable(
            {'source_template_id': 1, 'source_assignment_period': '2023', 'source_form_item_id': 5,
             'matrix_column_name': '_row_total', '_row_entity_id': 5}, aes
        )
        assert result == 30.0

    @patch('app.services.variable_resolution_service.AssignmentEntityStatus')
    @patch('app.services.variable_resolution_service.AssignedForm')
    def test_entities_containing_no_row_entity_id(self, mock_af, mock_aes_cls):
        aes = self._aes()
        af = MagicMock()
        af.id = 1
        mock_af.query.filter_by.return_value.first.return_value = af

        with patch.object(VariableResolutionService, '_get_entity_statuses_for_scope', return_value=[MagicMock()]), \
             patch.object(VariableResolutionService, '_resolve_entities_containing', return_value='result'):
            result = VariableResolutionService._resolve_single_variable(
                {'source_template_id': 1, 'source_assignment_period': '2023', 'source_form_item_id': 5,
                 'entity_scope': 'entities_containing'}, aes
            )
        assert result == 'result'

    @patch('app.services.variable_resolution_service.AssignmentEntityStatus')
    @patch('app.services.variable_resolution_service.AssignedForm')
    def test_entities_containing_with_row_entity_id(self, mock_af, mock_aes_cls):
        aes = self._aes()
        af = MagicMock()
        af.id = 1
        mock_af.query.filter_by.return_value.first.return_value = af

        with patch.object(VariableResolutionService, '_get_entity_statuses_for_scope', return_value=[MagicMock()]), \
             patch.object(VariableResolutionService, '_resolve_entities_containing_for_matrix_cell', return_value=1):
            result = VariableResolutionService._resolve_single_variable(
                {'source_template_id': 1, 'source_assignment_period': '2023', 'source_form_item_id': 5,
                 'entity_scope': 'entities_containing', '_row_entity_id': 5}, aes
            )
        assert result == 1

    @patch('app.services.variable_resolution_service.FormData')
    @patch('app.services.variable_resolution_service.AssignmentEntityStatus')
    @patch('app.services.variable_resolution_service.AssignedForm')
    def test_disagg_values_non_numeric_skipped(self, mock_af, mock_aes_cls, mock_fd_cls):
        aes = self._aes()
        af = MagicMock()
        af.id = 1
        mock_af.query.filter_by.return_value.first.return_value = af
        es = MagicMock()
        es.id = 10
        mock_aes_cls.query.filter_by.return_value.first.return_value = es

        entry = MagicMock()
        entry.value = None
        entry.disagg_data = {'values': {'cat1': None, 'cat2': 'abc', 'cat3': 10}}
        entry.form_item = MagicMock()
        entry.form_item.is_indicator = True
        mock_fd_cls.query.filter.return_value.order_by.return_value.all.return_value = [entry]

        result = VariableResolutionService._resolve_single_variable(
            {'source_template_id': 1, 'source_assignment_period': '2023', 'source_form_item_id': 5}, aes
        )
        assert result == 10.0


# ---------------------------------------------------------------------------
# _resolve_single_variable_cached
# ---------------------------------------------------------------------------

class TestResolveSingleVariableCached:

    def _aes(self):
        aes = MagicMock()
        aes.entity_type = 'country'
        aes.entity_id = 1
        return aes

    def test_missing_required_config_returns_none(self):
        aes = self._aes()
        result = VariableResolutionService._resolve_single_variable_cached({}, aes)
        assert result is None

    def test_missing_period_returns_none(self):
        aes = self._aes()
        config = {'source_template_id': 1, 'source_form_item_id': 5}
        result = VariableResolutionService._resolve_single_variable_cached(config, aes)
        assert result is None

    @patch('app.services.variable_resolution_service.AssignedForm')
    def test_no_assigned_form_returns_none(self, mock_af):
        aes = self._aes()
        mock_af.query.filter_by.return_value.first.return_value = None
        config = {
            'source_template_id': 1, 'source_assignment_period': '2023', 'source_form_item_id': 5,
            '_form_data_cache': {}, '_assigned_form_cache': {}, '_entity_statuses_cache': {}
        }
        result = VariableResolutionService._resolve_single_variable_cached(config, aes)
        assert result is None

    def test_uses_cached_form_data_for_indicator(self):
        aes = self._aes()
        mock_af = MagicMock()
        mock_af.id = 1
        mock_aes_obj = MagicMock()
        mock_aes_obj.id = 10

        mock_entry = MagicMock()
        mock_entry.value = '100'
        mock_entry.disagg_data = None
        mock_entry.form_item = MagicMock()
        mock_entry.form_item.is_indicator = True

        config = {
            'source_template_id': 1, 'source_assignment_period': '2023', 'source_form_item_id': 5,
            '_form_data_cache': {10: mock_entry},
            '_assigned_form_cache': {(1, '2023'): mock_af},
            '_entity_statuses_cache': {(1, 'same'): [mock_aes_obj]},
            'entity_scope': 'same'
        }
        result = VariableResolutionService._resolve_single_variable_cached(config, aes)
        assert result == 100.0

    def test_entities_containing_with_row_entity_id(self):
        aes = self._aes()
        mock_af = MagicMock()
        mock_af.id = 1
        mock_aes_entity = MagicMock()
        mock_aes_entity.id = 10

        config = {
            'source_template_id': 1, 'source_assignment_period': '2023', 'source_form_item_id': 5,
            '_form_data_cache': {},
            '_assigned_form_cache': {(1, '2023'): mock_af},
            '_entity_statuses_cache': {(1, 'entities_containing'): [mock_aes_entity]},
            'entity_scope': 'entities_containing',
            '_row_entity_id': 5
        }
        with patch.object(VariableResolutionService, '_resolve_entities_containing_for_matrix_cell', return_value=1):
            result = VariableResolutionService._resolve_single_variable_cached(config, aes)
        assert result == 1

    def test_entities_containing_no_row_entity_id(self):
        aes = self._aes()
        mock_af = MagicMock()
        mock_af.id = 1
        mock_aes_entity = MagicMock()
        mock_aes_entity.id = 10

        config = {
            'source_template_id': 1, 'source_assignment_period': '2023', 'source_form_item_id': 5,
            '_form_data_cache': {},
            '_assigned_form_cache': {(1, '2023'): mock_af},
            '_entity_statuses_cache': {(1, 'entities_containing'): [mock_aes_entity]},
            'entity_scope': 'entities_containing',
        }
        with patch.object(VariableResolutionService, '_resolve_entities_containing', return_value='ids_result'):
            result = VariableResolutionService._resolve_single_variable_cached(config, aes)
        assert result == 'ids_result'

    @patch('app.services.variable_resolution_service.FormData')
    def test_cache_miss_fallback_to_query(self, mock_fd_cls):
        aes = self._aes()
        mock_af = MagicMock()
        mock_af.id = 1
        mock_aes_obj = MagicMock()
        mock_aes_obj.id = 10

        mock_entry = MagicMock()
        mock_entry.disagg_data = {'5_col1': 99}
        mock_entry.form_item = MagicMock()
        mock_entry.form_item.is_indicator = True
        mock_entry.value = None
        mock_fd_cls.query.filter.return_value.order_by.return_value.all.return_value = [mock_entry]

        config = {
            'source_template_id': 1, 'source_assignment_period': '2023', 'source_form_item_id': 5,
            '_form_data_cache': {},  # empty - will fall back to query
            '_assigned_form_cache': {(1, '2023'): mock_af},
            '_entity_statuses_cache': {(1, 'same'): [mock_aes_obj]},
            'entity_scope': 'same',
            'matrix_column_name': 'col1',
            '_row_entity_id': 5
        }
        result = VariableResolutionService._resolve_single_variable_cached(config, aes)
        assert result == 99.0

    def test_no_entity_statuses_returns_none(self):
        aes = self._aes()
        mock_af = MagicMock()
        mock_af.id = 1

        config = {
            'source_template_id': 1, 'source_assignment_period': '2023', 'source_form_item_id': 5,
            '_form_data_cache': {},
            '_assigned_form_cache': {(1, '2023'): mock_af},
            '_entity_statuses_cache': {(1, 'same'): []},  # empty entity statuses
            'entity_scope': 'same'
        }
        result = VariableResolutionService._resolve_single_variable_cached(config, aes)
        assert result is None


# ---------------------------------------------------------------------------
# resolve_variables
# ---------------------------------------------------------------------------

class TestResolveVariables:

    def _aes(self):
        aes = MagicMock()
        aes.entity_type = 'country'
        aes.entity_id = 1
        aes.assigned_form = MagicMock()
        aes.assigned_form.period_name = '2024'
        return aes

    def test_no_assignment_entity_status(self):
        result = VariableResolutionService.resolve_variables(MagicMock(), None)
        assert result == {}

    def test_no_template_version_returns_builtins(self):
        aes = self._aes()
        with patch.object(VariableResolutionService, '_resolve_builtin_metadata_variables', return_value={'entity_name': 'France'}):
            result = VariableResolutionService.resolve_variables(None, aes)
        assert result.get('entity_name') == 'France'

    def test_template_with_no_variables_returns_builtins(self):
        aes = self._aes()
        tv = MagicMock()
        tv.variables = None
        with patch.object(VariableResolutionService, '_resolve_builtin_metadata_variables', return_value={'entity_id': '1'}):
            result = VariableResolutionService.resolve_variables(tv, aes)
        assert result.get('entity_id') == '1'

    def test_template_with_empty_variables_dict_returns_builtins(self):
        aes = self._aes()
        tv = MagicMock()
        tv.variables = {}
        with patch.object(VariableResolutionService, '_resolve_builtin_metadata_variables', return_value={'entity_type': 'country'}):
            result = VariableResolutionService.resolve_variables(tv, aes)
        assert result.get('entity_type') == 'country'

    def test_plugin_label_variables_skipped(self):
        aes = self._aes()
        tv = MagicMock()
        tv.variables = {'EO1': {'variable_type': 'lookup', 'source_template_id': 1}}
        with patch.object(VariableResolutionService, '_resolve_builtin_metadata_variables', return_value={}):
            result = VariableResolutionService.resolve_variables(tv, aes)
        assert 'EO1' not in result

    def test_metadata_variable(self):
        aes = self._aes()
        tv = MagicMock()
        tv.variables = {'my_var': {'variable_type': 'metadata', 'metadata_type': 'entity_id'}}
        with patch.object(VariableResolutionService, '_resolve_builtin_metadata_variables', return_value={}), \
             patch.object(VariableResolutionService, '_resolve_metadata_variable', return_value='1'):
            result = VariableResolutionService.resolve_variables(tv, aes)
        assert result['my_var'] == '1'

    def test_lookup_variable_match_by_indicator_bank_set_to_none(self):
        aes = self._aes()
        tv = MagicMock()
        tv.variables = {'my_var': {'variable_type': 'lookup', 'match_by_indicator_bank': True}}
        with patch.object(VariableResolutionService, '_resolve_builtin_metadata_variables', return_value={}):
            result = VariableResolutionService.resolve_variables(tv, aes)
        assert result['my_var'] is None

    def test_lookup_variable_resolved(self):
        aes = self._aes()
        tv = MagicMock()
        tv.variables = {'my_var': {'source_template_id': 1, 'source_assignment_period': '2023', 'source_form_item_id': 5}}
        with patch.object(VariableResolutionService, '_resolve_builtin_metadata_variables', return_value={}), \
             patch.object(VariableResolutionService, '_resolve_single_variable', return_value=42):
            result = VariableResolutionService.resolve_variables(tv, aes)
        assert result['my_var'] == 42

    def test_lookup_variable_with_row_entity_id(self):
        aes = self._aes()
        tv = MagicMock()
        tv.variables = {'my_var': {'source_template_id': 1, 'source_assignment_period': '2023', 'source_form_item_id': 5}}
        with patch.object(VariableResolutionService, '_resolve_builtin_metadata_variables', return_value={}), \
             patch.object(VariableResolutionService, '_resolve_single_variable', return_value=42) as mock_resolve:
            result = VariableResolutionService.resolve_variables(tv, aes, row_entity_id=7)
        # Verify that the config passed to _resolve_single_variable has _row_entity_id
        call_cfg = mock_resolve.call_args[0][0]
        assert call_cfg.get('_row_entity_id') == 7
        assert result['my_var'] == 42

    def test_lookup_variable_none_uses_default(self):
        aes = self._aes()
        tv = MagicMock()
        tv.variables = {'my_var': {'source_template_id': 1, 'source_assignment_period': '2023',
                                   'source_form_item_id': 5, 'default_value': '99'}}
        with patch.object(VariableResolutionService, '_resolve_builtin_metadata_variables', return_value={}), \
             patch.object(VariableResolutionService, '_resolve_single_variable', return_value=None):
            result = VariableResolutionService.resolve_variables(tv, aes)
        assert result['my_var'] == '99'

    def test_none_value_empty_default_stays_none(self):
        aes = self._aes()
        tv = MagicMock()
        tv.variables = {'my_var': {'source_template_id': 1, 'source_assignment_period': '2023',
                                   'source_form_item_id': 5, 'default_value': ''}}
        with patch.object(VariableResolutionService, '_resolve_builtin_metadata_variables', return_value={}), \
             patch.object(VariableResolutionService, '_resolve_single_variable', return_value=None):
            result = VariableResolutionService.resolve_variables(tv, aes)
        assert result['my_var'] is None

    def test_exception_uses_default(self):
        aes = self._aes()
        tv = MagicMock()
        tv.variables = {'my_var': {'variable_type': 'lookup', 'default_value': 'fallback'}}
        with patch.object(VariableResolutionService, '_resolve_builtin_metadata_variables', return_value={}), \
             patch.object(VariableResolutionService, '_resolve_single_variable', side_effect=Exception("err")):
            result = VariableResolutionService.resolve_variables(tv, aes)
        assert result['my_var'] == 'fallback'

    def test_exception_no_default_returns_none(self):
        aes = self._aes()
        tv = MagicMock()
        tv.variables = {'my_var': {'variable_type': 'lookup'}}
        with patch.object(VariableResolutionService, '_resolve_builtin_metadata_variables', return_value={}), \
             patch.object(VariableResolutionService, '_resolve_single_variable', side_effect=Exception("err")):
            result = VariableResolutionService.resolve_variables(tv, aes)
        assert result['my_var'] is None

    def test_builtins_merged_without_overriding_user_vars(self):
        aes = self._aes()
        tv = MagicMock()
        tv.variables = {'entity_id': {'source_template_id': 1, 'source_assignment_period': '2023', 'source_form_item_id': 5}}
        with patch.object(VariableResolutionService, '_resolve_builtin_metadata_variables',
                          return_value={'entity_id': 'builtin_val', 'entity_name': 'France'}), \
             patch.object(VariableResolutionService, '_resolve_single_variable', return_value='user_val'):
            result = VariableResolutionService.resolve_variables(tv, aes)
        assert result['entity_id'] == 'user_val'   # user-defined wins
        assert result['entity_name'] == 'France'    # builtin added


# ---------------------------------------------------------------------------
# resolve_variables_batch
# ---------------------------------------------------------------------------

class TestResolveVariablesBatch:

    def _aes(self):
        aes = MagicMock()
        aes.entity_type = 'country'
        aes.entity_id = 1
        return aes

    def test_no_aes_returns_empty(self):
        result = VariableResolutionService.resolve_variables_batch(MagicMock(), None, [1, 2])
        assert result == {}

    def test_empty_row_ids_returns_empty(self):
        result = VariableResolutionService.resolve_variables_batch(MagicMock(), MagicMock(), [])
        assert result == {}

    def test_no_template_version_returns_builtins_per_row(self):
        aes = self._aes()
        with patch.object(VariableResolutionService, '_resolve_builtin_metadata_variables', return_value={'entity_name': 'France'}):
            result = VariableResolutionService.resolve_variables_batch(None, aes, [1, 2])
        assert 1 in result and 2 in result
        assert result[1]['entity_name'] == 'France'
        assert result[2]['entity_name'] == 'France'

    def test_no_variables_in_template_returns_builtins_per_row(self):
        aes = self._aes()
        tv = MagicMock()
        tv.variables = None
        with patch.object(VariableResolutionService, '_resolve_builtin_metadata_variables', return_value={'entity_id': '1'}):
            result = VariableResolutionService.resolve_variables_batch(tv, aes, [10])
        assert result[10]['entity_id'] == '1'

    def test_plugin_labels_skipped_in_batch(self):
        aes = self._aes()
        tv = MagicMock()
        tv.variables = {
            'EO1': {'variable_type': 'lookup', 'source_template_id': 1,
                    'source_assignment_period': '2024', 'source_form_item_id': 5}
        }
        with patch.object(VariableResolutionService, '_resolve_builtin_metadata_variables', return_value={}), \
             patch('app.services.variable_resolution_service.AssignedForm') as mock_af:
            mock_af.query.filter_by.return_value.first.return_value = None
            result = VariableResolutionService.resolve_variables_batch(tv, aes, [1])
        assert 'EO1' not in result.get(1, {})

    def test_metadata_variable_same_for_all_rows(self):
        aes = self._aes()
        tv = MagicMock()
        tv.variables = {'my_var': {'variable_type': 'metadata', 'metadata_type': 'entity_id'}}
        with patch.object(VariableResolutionService, '_resolve_builtin_metadata_variables', return_value={}), \
             patch.object(VariableResolutionService, '_resolve_metadata_variable', return_value='1'):
            result = VariableResolutionService.resolve_variables_batch(tv, aes, [10, 20])
        assert result[10]['my_var'] == '1'
        assert result[20]['my_var'] == '1'

    def test_batch_uses_default_when_value_is_none(self):
        aes = self._aes()
        tv = MagicMock()
        tv.variables = {'my_var': {'variable_type': 'metadata', 'metadata_type': 'entity_id',
                                   'default_value': 'default_val'}}
        with patch.object(VariableResolutionService, '_resolve_builtin_metadata_variables', return_value={}), \
             patch.object(VariableResolutionService, '_resolve_metadata_variable', return_value=None):
            result = VariableResolutionService.resolve_variables_batch(tv, aes, [1])
        assert result[1]['my_var'] == 'default_val'

    def test_batch_exception_uses_default(self):
        aes = self._aes()
        tv = MagicMock()
        tv.variables = {'my_var': {'variable_type': 'metadata', 'default_value': 'err_default'}}
        with patch.object(VariableResolutionService, '_resolve_builtin_metadata_variables', return_value={}), \
             patch.object(VariableResolutionService, '_resolve_metadata_variable', side_effect=Exception("err")):
            result = VariableResolutionService.resolve_variables_batch(tv, aes, [1])
        assert result[1]['my_var'] == 'err_default'

    def test_batch_merges_builtins_per_row(self):
        aes = self._aes()
        tv = MagicMock()
        tv.variables = {'custom': {'variable_type': 'metadata', 'metadata_type': 'entity_id'}}
        with patch.object(VariableResolutionService, '_resolve_builtin_metadata_variables',
                          return_value={'entity_name': 'France'}), \
             patch.object(VariableResolutionService, '_resolve_metadata_variable', return_value='1'):
            result = VariableResolutionService.resolve_variables_batch(tv, aes, [5])
        assert result[5]['custom'] == '1'
        assert result[5]['entity_name'] == 'France'

    @patch('app.services.variable_resolution_service.FormData')
    @patch('app.services.variable_resolution_service.AssignedForm')
    def test_batch_prefetches_form_data(self, mock_af, mock_fd_cls):
        aes = self._aes()
        tv = MagicMock()
        tv.variables = {
            'my_var': {
                'variable_type': 'lookup',
                'source_template_id': 1,
                'source_assignment_period': '2023',
                'source_form_item_id': 5,
                'entity_scope': 'same'
            }
        }
        mock_assigned_form = MagicMock()
        mock_assigned_form.id = 1
        mock_af.query.filter_by.return_value.first.return_value = mock_assigned_form

        with patch.object(VariableResolutionService, '_resolve_builtin_metadata_variables', return_value={}), \
             patch.object(VariableResolutionService, '_get_entity_statuses_for_scope', return_value=[]), \
             patch.object(VariableResolutionService, '_resolve_single_variable_cached', return_value=42):
            result = VariableResolutionService.resolve_variables_batch(tv, aes, [10])
        assert 10 in result


# ---------------------------------------------------------------------------
# resolve_variable_by_indicator_bank
# ---------------------------------------------------------------------------

class TestResolveVariableByIndicatorBank:

    def _aes(self):
        aes = MagicMock()
        aes.entity_type = 'country'
        aes.entity_id = 1
        return aes

    def test_no_aes_returns_none(self):
        result = VariableResolutionService.resolve_variable_by_indicator_bank({}, None, MagicMock())
        assert result is None

    def test_no_config_returns_none(self):
        result = VariableResolutionService.resolve_variable_by_indicator_bank(None, MagicMock(), MagicMock())
        assert result is None

    def test_non_dict_config_returns_none(self):
        result = VariableResolutionService.resolve_variable_by_indicator_bank("not a dict", MagicMock(), MagicMock())
        assert result is None

    def test_no_form_item_returns_none(self):
        aes = self._aes()
        result = VariableResolutionService.resolve_variable_by_indicator_bank(
            {'source_template_id': 1, 'source_assignment_period': '2023'}, aes, None
        )
        assert result is None

    def test_missing_source_template_id(self):
        aes = self._aes()
        item = MagicMock()
        item.indicator_bank_id = 5
        result = VariableResolutionService.resolve_variable_by_indicator_bank(
            {'source_assignment_period': '2023'}, aes, item
        )
        assert result is None

    def test_missing_source_period(self):
        aes = self._aes()
        item = MagicMock()
        item.indicator_bank_id = 5
        result = VariableResolutionService.resolve_variable_by_indicator_bank(
            {'source_template_id': 1}, aes, item
        )
        assert result is None

    def test_no_indicator_bank_id_returns_none(self):
        aes = self._aes()
        item = MagicMock()
        item.indicator_bank_id = None
        result = VariableResolutionService.resolve_variable_by_indicator_bank(
            {'source_template_id': 1, 'source_assignment_period': '2023'}, aes, item
        )
        assert result is None

    @patch('app.services.variable_resolution_service.FormTemplate')
    def test_no_template_returns_none(self, mock_tmpl_cls):
        aes = self._aes()
        item = MagicMock()
        item.indicator_bank_id = 5
        mock_tmpl_cls.query.get.return_value = None

        result = VariableResolutionService.resolve_variable_by_indicator_bank(
            {'source_template_id': 1, 'source_assignment_period': '2023'}, aes, item
        )
        assert result is None

    @patch('app.services.variable_resolution_service.FormTemplate')
    def test_no_published_version_id_returns_none(self, mock_tmpl_cls):
        aes = self._aes()
        item = MagicMock()
        item.indicator_bank_id = 5
        mock_tmpl = MagicMock()
        mock_tmpl.published_version_id = None
        mock_tmpl_cls.query.get.return_value = mock_tmpl

        result = VariableResolutionService.resolve_variable_by_indicator_bank(
            {'source_template_id': 1, 'source_assignment_period': '2023'}, aes, item
        )
        assert result is None

    @patch('app.services.variable_resolution_service.FormItem')
    @patch('app.services.variable_resolution_service.FormTemplate')
    def test_no_matching_form_item_returns_none(self, mock_tmpl_cls, mock_fi_cls):
        aes = self._aes()
        item = MagicMock()
        item.indicator_bank_id = 5
        mock_tmpl = MagicMock()
        mock_tmpl.published_version_id = 10
        mock_tmpl_cls.query.get.return_value = mock_tmpl
        mock_fi_cls.query.filter_by.return_value.order_by.return_value.first.return_value = None

        result = VariableResolutionService.resolve_variable_by_indicator_bank(
            {'source_template_id': 1, 'source_assignment_period': '2023'}, aes, item
        )
        assert result is None

    @patch('app.services.variable_resolution_service.FormItem')
    @patch('app.services.variable_resolution_service.FormTemplate')
    def test_successful_resolution(self, mock_tmpl_cls, mock_fi_cls):
        aes = self._aes()
        item = MagicMock()
        item.indicator_bank_id = 5
        mock_tmpl = MagicMock()
        mock_tmpl.published_version_id = 10
        mock_tmpl_cls.query.get.return_value = mock_tmpl
        mock_fi = MagicMock()
        mock_fi.id = 99
        mock_fi_cls.query.filter_by.return_value.order_by.return_value.first.return_value = mock_fi

        with patch.object(VariableResolutionService, '_resolve_single_variable', return_value=42):
            result = VariableResolutionService.resolve_variable_by_indicator_bank(
                {'source_template_id': 1, 'source_assignment_period': '2023'}, aes, item
            )
        assert result == 42

    @patch('app.services.variable_resolution_service.FormItem')
    @patch('app.services.variable_resolution_service.FormTemplate')
    def test_entities_containing_scope_changed_to_same(self, mock_tmpl_cls, mock_fi_cls):
        aes = self._aes()
        item = MagicMock()
        item.indicator_bank_id = 5
        mock_tmpl = MagicMock()
        mock_tmpl.published_version_id = 10
        mock_tmpl_cls.query.get.return_value = mock_tmpl
        mock_fi = MagicMock()
        mock_fi.id = 99
        mock_fi_cls.query.filter_by.return_value.order_by.return_value.first.return_value = mock_fi

        captured = []
        def capture(cfg, aes_arg):
            captured.append(dict(cfg))
            return None

        with patch.object(VariableResolutionService, '_resolve_single_variable', side_effect=capture):
            VariableResolutionService.resolve_variable_by_indicator_bank(
                {'source_template_id': 1, 'source_assignment_period': '2023', 'entity_scope': 'entities_containing'},
                aes, item
            )
        assert captured[0]['entity_scope'] == 'same'

    @patch('app.services.variable_resolution_service.FormItem')
    @patch('app.services.variable_resolution_service.FormTemplate')
    def test_cache_reused_on_second_call(self, mock_tmpl_cls, mock_fi_cls):
        aes = self._aes()
        item = MagicMock()
        item.indicator_bank_id = 5
        mock_tmpl = MagicMock()
        mock_tmpl.published_version_id = 10
        mock_tmpl_cls.query.get.return_value = mock_tmpl
        mock_fi = MagicMock()
        mock_fi.id = 99
        mock_fi_cls.query.filter_by.return_value.order_by.return_value.first.return_value = mock_fi

        cache = {}
        config = {'source_template_id': 1, 'source_assignment_period': '2023'}
        with patch.object(VariableResolutionService, '_resolve_single_variable', return_value=None):
            VariableResolutionService.resolve_variable_by_indicator_bank(config, aes, item, cache=cache)
            VariableResolutionService.resolve_variable_by_indicator_bank(config, aes, item, cache=cache)

        # DB should only be queried once for the template
        assert mock_tmpl_cls.query.get.call_count == 1

    def test_exception_returns_none(self):
        aes = self._aes()
        item = MagicMock()
        item.indicator_bank_id = 5
        config = {'source_template_id': 1, 'source_assignment_period': '2023'}

        with patch('app.services.variable_resolution_service.FormTemplate') as mock_tmpl_cls:
            mock_tmpl_cls.query.get.side_effect = Exception("DB error")
            result = VariableResolutionService.resolve_variable_by_indicator_bank(config, aes, item)
        assert result is None

    @patch('app.services.variable_resolution_service.FormItem')
    @patch('app.services.variable_resolution_service.FormTemplate')
    def test_invalid_cache_treated_as_empty(self, mock_tmpl_cls, mock_fi_cls):
        aes = self._aes()
        item = MagicMock()
        item.indicator_bank_id = 5
        mock_tmpl = MagicMock()
        mock_tmpl.published_version_id = 10
        mock_tmpl_cls.query.get.return_value = mock_tmpl
        mock_fi = MagicMock()
        mock_fi.id = 99
        mock_fi_cls.query.filter_by.return_value.order_by.return_value.first.return_value = mock_fi

        with patch.object(VariableResolutionService, '_resolve_single_variable', return_value=None):
            result = VariableResolutionService.resolve_variable_by_indicator_bank(
                {'source_template_id': 1, 'source_assignment_period': '2023'}, aes, item,
                cache="not a dict"  # invalid cache - should be treated as empty
            )
        assert result is None  # No error raised
