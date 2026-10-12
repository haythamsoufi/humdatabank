"""Matrix column code validation."""

import json

from app.services.forms.matrix_column_validation import (
    validate_matrix_columns,
    validate_matrix_config,
)


def _cols(*codes):
    return [{'name': code} for code in codes]


class TestValidateMatrixColumns:
    def test_valid_codes_pass(self):
        assert validate_matrix_columns(_cols('SP1', 'SP2', 'Total Funding', 'SP1_[assignment_period]')) == []

    def test_duplicate_code_is_reported_once(self):
        errors = validate_matrix_columns(_cols('SP1', 'SP2', 'SP1', 'SP1'))
        assert len(errors) == 1
        assert '"SP1"' in errors[0] and 'unique' in errors[0]

    def test_duplicates_ignore_surrounding_whitespace(self):
        assert validate_matrix_columns(_cols('SP1', ' SP1 '))

    def test_case_differences_are_distinct_codes(self):
        assert validate_matrix_columns(_cols('SP1', 'sp1')) == []

    def test_reserved_codes(self):
        assert validate_matrix_columns(_cols('Total'))
        assert validate_matrix_columns(_cols('total'))
        assert validate_matrix_columns(_cols('_row_total'))

    def test_pipe_is_rejected(self):
        assert validate_matrix_columns(_cols('a|b'))

    def test_unbalanced_brackets_are_rejected(self):
        assert validate_matrix_columns(_cols('SP1_[assignment_period'))
        assert validate_matrix_columns(_cols('SP1_assignment_period]'))

    def test_label_without_code_is_rejected(self):
        columns = [{'name': '', 'name_translations': {'en': 'Planned'}}]
        assert validate_matrix_columns(columns)

    def test_empty_code_without_a_label_is_ignored(self):
        assert validate_matrix_columns([{'name': ''}, {'name': ''}]) == []

    def test_variable_column_may_have_no_code(self):
        columns = [{'name': '', 'is_variable': True, 'name_translations': {'en': 'Funding'}}]
        assert validate_matrix_columns(columns) == []

    def test_non_dict_columns_and_none_are_ignored(self):
        assert validate_matrix_columns(['a', None, 3]) == []
        assert validate_matrix_columns(None) == []


class TestValidateMatrixConfig:
    def test_accepts_dict_or_json_string(self):
        config = {'columns': _cols('A', 'A')}
        assert validate_matrix_config(config)
        assert validate_matrix_config(json.dumps(config))

    def test_bad_input_is_not_an_error_here(self):
        assert validate_matrix_config('{not json') == []
        assert validate_matrix_config(None) == []
        assert validate_matrix_config([]) == []
        assert validate_matrix_config({'rows': []}) == []
