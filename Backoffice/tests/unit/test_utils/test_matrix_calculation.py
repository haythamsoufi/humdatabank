"""Shared matrix formula language. Keep cases aligned with tests/js/forms/matrix-calculation.test.js."""

from app.utils.api_serialization import _build_matrix_long_rows_from_values
from app.utils.matrix_calculation import (
    calculation_is_readonly,
    calculation_saves_value,
    column_counts_toward_row_total,
    compile_calculation,
    evaluate_matrix_row,
    format_formula_number,
    matrix_formula_display,
    matrix_formula_number,
    normalize_calculation,
)


def _cols():
    return [
        {'name': 'income', 'type': 'number_whole'},
        {'name': 'grant', 'type': 'number_whole'},
        {'name': 'expenditure', 'type': 'number_whole'},
        {'name': 'done', 'type': 'tick'},
        {'name': 'part', 'type': 'number_whole'},
        {'name': 'whole', 'type': 'number_whole'},
    ]


def _calc(name, operation, **kwargs):
    calculation = {'operation': operation, **kwargs}
    return {'name': name, 'type': 'calculated', 'calculation': calculation}


def _value(columns, inputs, name):
    return evaluate_matrix_row(columns, inputs)[name]


class TestPresets:
    def test_sum_skips_blanks_and_blank_sum_is_zero(self):
        columns = _cols() + [_calc('total', 'sum', sources=['income', 'grant', 'expenditure'])]
        filled = _value(columns, {'income': 1, 'grant': '', 'expenditure': 3}, 'total')
        empty = _value(columns, {}, 'total')
        assert filled.value == 4 and filled.error is None
        assert empty.value == 0 and empty.error is None

    def test_average_min_max_of_blanks_are_blank(self):
        columns = _cols() + [
            _calc('avg', 'average', sources=['income', 'expenditure']),
            _calc('low', 'min', sources=['income', 'expenditure']),
            _calc('high', 'max', sources=['income', 'expenditure']),
        ]
        row = evaluate_matrix_row(columns, {'income': 2, 'expenditure': ''})
        assert row['avg'].value == 2
        assert row['low'].value == 2
        assert row['high'].value == 2
        blank = evaluate_matrix_row(columns, {})
        assert blank['avg'].value is None and blank['avg'].error is None
        assert blank['low'].value is None
        assert blank['high'].value is None

    def test_count_and_counta(self):
        columns = _cols() + [
            _calc('numbers', 'count', sources=['income', 'grant']),
            _calc('filled', 'count_filled', sources=['income', 'grant']),
        ]
        row = evaluate_matrix_row(columns, {'income': 0, 'grant': ''})
        assert row['numbers'].value == 1
        assert row['filled'].value == 1

    def test_tick_counts_as_zero_or_one(self):
        columns = _cols() + [_calc('ticks', 'sum', sources=['done'])]
        assert _value(columns, {}, 'ticks').value == 0
        assert _value(columns, {'done': '1'}, 'ticks').value == 1

    def test_difference_percentage_and_product(self):
        columns = _cols() + [
            _calc('balance', 'difference', sources=['income', 'grant'], subtrahends=['expenditure']),
            _calc('share', 'percentage', sources=['part'], denominators=['whole'], decimals=1),
            _calc('area', 'product', sources=['income', 'grant']),
        ]
        row = evaluate_matrix_row(columns, {
            'income': 10, 'grant': 5, 'expenditure': 3, 'part': 1, 'whole': 4,
        })
        assert row['balance'].value == 12
        assert row['share'].value == 25
        assert row['area'].value == 50
        zero_den = evaluate_matrix_row(columns, {'part': 1, 'whole': 0})
        assert zero_den['share'].value is None and zero_den['share'].error is None

    def test_compile_presets(self):
        assert compile_calculation({
            'operation': 'difference', 'sources': ['income'], 'subtrahends': ['expenditure'],
        }) == 'SUM(income) - SUM(expenditure)'
        assert 'BLANK()' in compile_calculation({
            'operation': 'percentage', 'sources': ['part'], 'denominators': ['whole'],
        })


class TestFormulaLanguage:
    def test_arithmetic_if_round_and_blank_as_zero(self):
        columns = _cols() + [
            {
                'name': 'net',
                'type': 'calculated',
                'calculation': {
                    'operation': 'formula',
                    'formula': 'IF({whole} > 0, ROUND({part} / {whole} * 100, 1), 0)',
                    'blank_as_zero': True,
                },
            },
            {
                'name': 'strict',
                'type': 'calculated',
                'calculation': {
                    'operation': 'formula',
                    'formula': '{income} + {grant}',
                    'blank_as_zero': False,
                },
            },
        ]
        row = evaluate_matrix_row(columns, {'part': 1, 'whole': 4, 'income': 2})
        assert row['net'].value == 25
        assert row['strict'].value is None and row['strict'].error is None
        assert evaluate_matrix_row(columns, {'part': 1, 'whole': 8})['net'].value == 12.5

    def test_bare_column_codes(self):
        columns = [
            {'name': 'income', 'type': 'number_whole'},
            {'name': 'grant', 'type': 'number_whole'},
            {'name': 'total', 'type': 'calculated', 'calculation': {'operation': 'formula', 'formula': 'income + grant'}},
            {'name': 'doubled', 'type': 'calculated', 'calculation': {'operation': 'formula', 'formula': 'SUM(income, grant)'}},
        ]
        row = evaluate_matrix_row(columns, {'income': 2, 'grant': 3})
        assert row['total'].value == 5
        assert row['doubled'].value == 5

    def test_if_skips_the_unused_branch(self):
        columns = [{'name': 'whole', 'type': 'number_whole'}, {
            'name': 'safe',
            'type': 'calculated',
            'calculation': {'operation': 'formula', 'formula': 'IF({whole} = 0, 5, 1 / {whole})'},
        }]
        assert evaluate_matrix_row(columns, {'whole': 0})['safe'].value == 5

    def test_round_half_away_from_zero(self):
        columns = [{
            'name': 'r',
            'type': 'calculated',
            'calculation': {'operation': 'formula', 'formula': 'ROUND(2.5, 0) + ROUND(-1.5, 0)'},
        }]
        assert evaluate_matrix_row(columns, {})['r'].value == 1
        assert format_formula_number(1.25, 1) == '1.3'
        assert format_formula_number(None, 2) == ''

    def test_unknown_column_division_by_zero_and_cycles(self):
        columns = [
            {'name': 'a', 'type': 'calculated', 'calculation': {'operation': 'formula', 'formula': '{missing}'}},
            {'name': 'b', 'type': 'calculated', 'calculation': {'operation': 'formula', 'formula': '1 / 0'}},
            {'name': 'c', 'type': 'calculated', 'calculation': {'operation': 'formula', 'formula': '{d} + 1'}},
            {'name': 'd', 'type': 'calculated', 'calculation': {'operation': 'formula', 'formula': '{c} + 1'}},
        ]
        row = evaluate_matrix_row(columns, {})
        assert row['a'].error == 'Unknown column {missing}'
        assert row['b'].error == 'Division by zero'
        assert row['c'].error == 'Circular reference'
        assert row['d'].error == 'Circular reference'

    def test_calculated_columns_can_reference_each_other(self):
        columns = [
            {'name': 'income', 'type': 'number_whole'},
            _calc('base', 'sum', sources=['income']),
            {
                'name': 'doubled',
                'type': 'calculated',
                'calculation': {'operation': 'formula', 'formula': '{base} * 2'},
            },
            {
                'name': 'again',
                'type': 'calculated',
                'calculation': {'operation': 'formula', 'formula': '{doubled} + 1'},
            },
        ]
        row = evaluate_matrix_row(columns, {'income': 4})
        assert row['base'].value == 4
        assert row['doubled'].value == 8
        assert row['again'].value == 9

    def test_names_with_spaces(self):
        columns = [
            {'name': 'other income', 'type': 'number_whole'},
            {
                'name': 'total',
                'type': 'calculated',
                'calculation': {'operation': 'formula', 'formula': 'SUM({other income})'},
            },
        ]
        assert evaluate_matrix_row(columns, {'other income': '1,250'})['total'].value == 1250


class TestRowTotalFlag:
    def test_defaults(self):
        assert column_counts_toward_row_total({'name': 'a', 'type': 'number_whole'}) is True
        assert column_counts_toward_row_total({'name': 'a', 'type': 'number_whole', 'include_in_row_total': False}) is False
        assert column_counts_toward_row_total({'name': 'a', 'type': 'calculated'}) is False
        assert column_counts_toward_row_total({'name': 'a', 'type': 'calculated', 'include_in_row_total': True}) is True
        assert column_counts_toward_row_total('legacy') is True

    def test_normalize_keeps_formula(self):
        calc = normalize_calculation({
            'operation': 'formula',
            'formula': 'ABS({income} - {expenditure})',
            'decimals': 9,
            'blank_as_zero': False,
        })
        assert calc['decimals'] == 6
        assert calc['blank_as_zero'] is False
        assert calc['formula'].startswith('ABS(')


class TestApiFormulaCells:
    def test_formula_cells_are_flagged_and_left_out_of_the_row_total(self):
        config = {
            'columns': [
                {'name': 'income', 'type': 'number_whole'},
                {'name': 'note', 'type': 'number_whole', 'include_in_row_total': False},
                {
                    'name': 'doubled',
                    'type': 'calculated',
                    'calculation': {'operation': 'formula', 'formula': '{income} * 2'},
                },
            ],
            'show_row_totals': True,
            'show_column_totals': True,
        }
        rows = _build_matrix_long_rows_from_values({'10_income': 4, '10_note': 9}, config)
        formula = next(row for row in rows if row.get('is_formula'))
        assert formula['column_key'] == 'doubled'
        assert formula['value'] == 8
        assert formula.get('is_calculated_total') is not True
        row_total = next(row for row in rows if row.get('total_kind') == 'row')
        assert row_total['value'] == 4
        doubled_total = next(
            row for row in rows
            if row.get('total_kind') == 'column' and row.get('column_key') == 'doubled'
        )
        assert doubled_total['value'] == 8
        grand = next(row for row in rows if row.get('total_kind') == 'grand')
        assert grand['value'] == 4

    def test_saved_calculated_value_wins_over_the_formula(self):
        column = {
            'name': 'doubled',
            'type': 'calculated',
            'calculation_save_value': True,
            'calculation': {'operation': 'formula', 'formula': '{income} * 2', 'decimals': 0},
        }
        columns = [{'name': 'income', 'type': 'number_whole'}, column]
        data = {'10_income': 4, '10_doubled': 99}
        assert calculation_saves_value(column) is True
        assert calculation_is_readonly(column) is True
        assert calculation_is_readonly({**column, 'calculation_readonly': False}) is False
        assert matrix_formula_number(columns, data, '10', 'doubled') == 99
        assert matrix_formula_display(columns, data, '10', column) == '99'
        wide = [
            {'name': 'income', 'type': 'number_whole'},
            {'name': 'shown', 'type': 'calculated', 'calculation': {'operation': 'formula', 'formula': '{income}', 'decimals': 2}},
        ]
        assert matrix_formula_display(wide, {'1_income': 1234567.5}, '1', wide[1]) == '1,234,567.50'
        rows = _build_matrix_long_rows_from_values(data, {'columns': columns, 'show_row_totals': True, 'show_column_totals': True})
        stored = next(row for row in rows if row.get('column_key') == 'doubled' and not row.get('is_calculated_total'))
        assert stored['value'] == 99
        assert stored.get('is_formula') is not True
        unsaved = {**column}
        unsaved.pop('calculation_save_value')
        recomputed = _build_matrix_long_rows_from_values(
            {'10_income': 4, '10_doubled': 99},
            {'columns': [{'name': 'income', 'type': 'number_whole'}, unsaved], 'show_row_totals': False, 'show_column_totals': False},
        )
        formula = next(row for row in recomputed if row.get('column_key') == 'doubled')
        assert formula['is_formula'] is True
        assert formula['value'] == 8
