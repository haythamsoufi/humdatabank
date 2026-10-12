"""Matrix column code migration: pure key rewriting, config refs and the service loop."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.forms import matrix_column_migration_service as svc
from app.services.forms.matrix_column_migration_service import (
    MatrixColumnMigrationService,
    column_codes,
    rewrite_matrix_config_refs,
    rewrite_matrix_payload,
    validate_renames,
)
from app.utils.matrix_calculation import rename_formula_refs


class TestValidateRenames:
    def test_keeps_valid_rename(self):
        out = validate_renames([{'from': 'SP1', 'to': 'SP1_[assignment_year]'}], ['SP1', 'SP2'], ['SP1_[assignment_year]', 'SP2'])
        assert out == [('SP1', 'SP1_[assignment_year]')]

    def test_drops_unknown_source_or_target(self):
        requested = [{'from': 'GONE', 'to': 'X'}, {'from': 'SP2', 'to': 'NOT_IN_CONFIG'}]
        assert validate_renames(requested, ['SP1', 'SP2'], ['X', 'SP2']) == []

    def test_drops_noops_duplicates_and_garbage(self):
        requested = [
            {'from': 'A', 'to': 'A'},
            {'from': 'A', 'to': 'B'},
            {'from': 'A', 'to': 'C'},   # duplicate source
            {'from': 'D', 'to': 'B'},   # duplicate target
            'junk',
            {'from': 1, 'to': 'B'},
        ]
        assert validate_renames(requested, ['A', 'D'], ['B', 'C']) == [('A', 'B')]

    def test_non_list_is_empty(self):
        assert validate_renames(None, ['A'], ['B']) == []
        assert validate_renames({'from': 'A'}, ['A'], ['B']) == []


def test_column_codes_reads_dicts_and_strings():
    assert column_codes([{'name': ' A '}, 'B', {'name': ''}, {}, None]) == ['A', 'B']
    assert column_codes(None) == []


class TestRewriteMatrixPayload:
    def test_renames_cells_and_selectable_header(self):
        payload = {
            '_table': 'country',
            '61_SP1': 5,
            '62_SP1': {'original': 1, 'modified': 2, 'isModified': True},
            '61_SP2': 7,
            'col_header|SP1': 'Planned',
            'col_header_go_unmatched|SP1': 1,
            'row_go_unmatched|61': 1,
        }
        new, cells, conflicts = rewrite_matrix_payload(payload, {'SP1': 'SP1_2026'}, ['SP1', 'SP2'])
        assert conflicts == 0
        assert cells == 4
        assert new == {
            '_table': 'country',
            '61_SP1_2026': 5,
            '62_SP1_2026': {'original': 1, 'modified': 2, 'isModified': True},
            '61_SP2': 7,
            'col_header|SP1_2026': 'Planned',
            'col_header_go_unmatched|SP1_2026': 1,
            'row_go_unmatched|61': 1,
        }

    def test_nothing_to_do_returns_none(self):
        assert rewrite_matrix_payload({'61_SP2': 1}, {'SP1': 'X'}, ['SP1', 'SP2']) == (None, 0, 0)
        assert rewrite_matrix_payload(None, {'SP1': 'X'}, ['SP1']) == (None, 0, 0)
        assert rewrite_matrix_payload({'61_SP1': 1}, {}, ['SP1']) == (None, 0, 0)

    def test_longest_suffix_wins_so_other_columns_are_untouched(self):
        payload = {'61_SP1': 1, '61_NEW_SP1': 2}
        new, cells, _ = rewrite_matrix_payload(payload, {'SP1': 'X'}, ['SP1', 'NEW_SP1'])
        assert new == {'61_X': 1, '61_NEW_SP1': 2}
        assert cells == 1

    def test_row_id_may_contain_underscores_and_the_code_spaces(self):
        payload = {'Baseline_row 1_Total Funding': 9}
        new, _, _ = rewrite_matrix_payload(payload, {'Total Funding': 'ns_fun'}, ['Total Funding'])
        assert new == {'Baseline_row 1_ns_fun': 9}

    def test_swap_is_a_single_pass(self):
        payload = {'1_A': 'a', '1_B': 'b'}
        new, cells, conflicts = rewrite_matrix_payload(payload, {'A': 'B', 'B': 'A'}, ['A', 'B'])
        assert new == {'1_B': 'a', '1_A': 'b'}
        assert (cells, conflicts) == (2, 0)

    def test_chain_is_a_single_pass(self):
        payload = {'1_A': 'a', '1_B': 'b'}
        new, _, _ = rewrite_matrix_payload(payload, {'A': 'B', 'B': 'C'}, ['A', 'B'])
        assert new == {'1_B': 'a', '1_C': 'b'}

    def test_existing_value_under_new_code_is_a_conflict_and_is_kept(self):
        payload = {'1_SP1': 5, '1_X': 9}
        new, cells, conflicts = rewrite_matrix_payload(payload, {'SP1': 'X'}, ['SP1', 'X'])
        assert new is None
        assert (cells, conflicts) == (0, 1)

    def test_blank_value_under_new_code_is_overwritten(self):
        payload = {'1_SP1': 5, '1_X': '', '2_SP1': 6, '2_X': None}
        new, cells, conflicts = rewrite_matrix_payload(payload, {'SP1': 'X'}, ['SP1', 'X'])
        assert new == {'1_X': 5, '2_X': 6}
        assert (cells, conflicts) == (2, 0)

    def test_does_not_mutate_the_input(self):
        payload = {'1_SP1': 5}
        rewrite_matrix_payload(payload, {'SP1': 'X'}, ['SP1'])
        assert payload == {'1_SP1': 5}


class TestRenameFormulaRefs:
    def test_bare_and_braced_refs(self):
        assert rename_formula_refs('income - {Total Funding}', {'income': 'inc', 'Total Funding': 'tf'}) == 'inc - {tf}'

    def test_new_code_that_is_not_an_identifier_is_braced(self):
        assert rename_formula_refs('SP1 + 1', {'SP1': 'SP1_[assignment_year]'}) == '{SP1_[assignment_year]} + 1'

    def test_function_names_are_not_renamed(self):
        # The call keeps its name; the bare column that happens to share it is renamed.
        assert rename_formula_refs('SUM(SUM, a)', {'SUM': 'x', 'a': 'b'}) == 'SUM(x, b)'

    def test_swap_and_untouched_text(self):
        assert rename_formula_refs('a / b * 100', {'a': 'b', 'b': 'a'}) == 'b / a * 100'
        assert rename_formula_refs('IF(a = 0, BLANK(), 1)', {'z': 'y'}) == 'IF(a = 0, BLANK(), 1)'

    def test_empty_inputs(self):
        assert rename_formula_refs('', {'a': 'b'}) == ''
        assert rename_formula_refs('a', {}) == 'a'


class TestRewriteMatrixConfigRefs:
    def test_rewrites_custom_formula_and_source_lists(self):
        config = {'columns': [
            {'name': 'SP1_2026'},
            {'name': 'pct', 'calculation': {
                'operation': 'formula', 'formula': 'SP1 * 2', 'sources': ['SP1'],
            }},
        ]}
        assert rewrite_matrix_config_refs(config, {'SP1': 'SP1_2026'}) is True
        calc = config['columns'][1]['calculation']
        assert calc['formula'] == 'SP1_2026 * 2'
        assert calc['sources'] == ['SP1_2026']

    def test_no_change_returns_false(self):
        config = {'columns': [{'name': 'a', 'calculation': {'formula': 'b', 'sources': ['b']}}]}
        assert rewrite_matrix_config_refs(config, {'zz': 'yy'}) is False
        assert rewrite_matrix_config_refs(None, {'a': 'b'}) is False


class TestServiceRun:
    """Orchestration with the database stubbed out."""

    @staticmethod
    def _run(rows_by_model, *, renames, old_codes, dry_run, variables=None):
        executed = []

        def fake_iter(model, item_id, fields, chunk_size=200):
            return iter(rows_by_model.get(model.__name__, []))

        fake_session = MagicMock()
        fake_session.execute.side_effect = lambda stmt: executed.append(stmt)
        with patch.object(MatrixColumnMigrationService, '_iter_rows', side_effect=fake_iter), \
                patch.object(MatrixColumnMigrationService, '_migrate_variable_refs', return_value=variables or []), \
                patch.object(svc.db, 'session', fake_session):
            stats = MatrixColumnMigrationService._run(10, renames, old_codes, dry_run=dry_run)
        return stats, executed

    def test_migrates_static_rename_across_payload_fields(self):
        rows = {'FormData': [
            # id, aes, disagg, prefilled, imputed, published
            (1, 100, {'61_SP1': 5}, None, {'61_SP1': 1}, None),
            (2, 101, {'61_SP2': 5}, None, None, None),
        ]}
        stats, executed = self._run(rows, renames=[('SP1', 'SP1_X')], old_codes=['SP1', 'SP2'], dry_run=False)
        assert stats['rows_scanned'] == 2
        assert stats['rows_affected'] == 1
        assert stats['cells'] == 2
        assert stats['assignments'] == 1
        assert len(executed) == 1

    def test_dry_run_counts_but_writes_nothing(self):
        rows = {'FormData': [(1, 100, {'61_SP1': 5}, None, None, None)]}
        stats, executed = self._run(rows, renames=[('SP1', 'SP1_X')], old_codes=['SP1'], dry_run=True)
        assert stats['cells'] == 1
        assert executed == []

    def test_no_renames_is_a_noop(self):
        stats, executed = self._run({}, renames=[], old_codes=['SP1'], dry_run=False)
        assert stats['rows_scanned'] == 0
        assert executed == []

    def test_templated_target_resolves_per_assignment(self):
        rows = {'FormData': [
            (1, 100, {'61_SP1': 1}, None, None, None),
            (2, 101, {'61_SP1': 2}, None, None, None),
        ]}
        years = {100: '2026', 101: '2027'}

        def fake_get(_model, aes_id):
            return SimpleNamespace(id=aes_id)

        def fake_resolve(aes):
            return {'assignment_year': years[aes.id]}, {}

        def fake_replace(text, resolved, _configs):
            return text.replace('[assignment_year]', resolved['assignment_year'])

        written = []

        def capture(model, item_id, fields, chunk_size=200):
            return iter(rows.get(model.__name__, []))

        fake_session = MagicMock()
        fake_session.get.side_effect = fake_get
        fake_session.execute.side_effect = lambda stmt: written.append(stmt.compile().params)
        from app.services.forms.variable_resolution_service import VariableResolutionService
        with patch.object(MatrixColumnMigrationService, '_iter_rows', side_effect=capture), \
                patch.object(MatrixColumnMigrationService, '_migrate_variable_refs', return_value=[]), \
                patch.object(VariableResolutionService, 'resolve_for_assignment_display', side_effect=fake_resolve), \
                patch.object(VariableResolutionService, 'replace_variables_in_text', side_effect=fake_replace), \
                patch.object(svc.db, 'session', fake_session):
            stats = MatrixColumnMigrationService._run(
                10, [('SP1', 'SP1_[assignment_year]')], ['SP1'], dry_run=False
            )

        assert stats['rows_affected'] == 2
        assert stats['assignments'] == 2
        migrated = sorted(next(iter(p['disagg_data'])) for p in written)
        assert migrated == ['61_SP1_2026', '61_SP1_2027']

    def test_templated_rename_skips_rows_without_an_assignment(self):
        rows = {'FormData': [(1, None, {'61_SP1': 1}, None, None, None)]}
        stats, executed = self._run(
            rows, renames=[('SP1', 'SP1_[assignment_year]')], old_codes=['SP1'], dry_run=False
        )
        assert stats['skipped_unresolved'] == 1
        assert stats['rows_affected'] == 0
        assert executed == []
