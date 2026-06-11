"""
Unit tests for app/utils/sequence_utils.py – 100% coverage target.

Database interactions are fully mocked via SQLAlchemy engine patches
so no live database is needed.
"""
import pytest
from unittest.mock import MagicMock, patch, call

from app.utils.sequence_utils import (
    _valid_identifier,
    get_tables_with_id_column,
    reset_table_sequence,
    check_sequence_status,
    scan_sequences_status,
    reset_user_sequence,
    scan_and_reset_all_sequences,
)


# ---------------------------------------------------------------------------
# _valid_identifier
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestValidIdentifier:
    def test_simple_name_valid(self):
        assert _valid_identifier('users') is True

    def test_name_with_underscore_valid(self):
        assert _valid_identifier('user_profile') is True

    def test_name_with_digits_valid(self):
        assert _valid_identifier('table123') is True

    def test_empty_string_invalid(self):
        assert _valid_identifier('') is False

    def test_none_invalid(self):
        assert _valid_identifier(None) is False

    def test_name_with_hyphen_invalid(self):
        assert _valid_identifier('my-table') is False

    def test_name_with_dot_invalid(self):
        assert _valid_identifier('schema.table') is False

    def test_name_with_space_invalid(self):
        assert _valid_identifier('my table') is False

    def test_name_with_semicolon_invalid(self):
        assert _valid_identifier('users; DROP TABLE') is False


# ---------------------------------------------------------------------------
# Helper: build a mock connection context manager
# ---------------------------------------------------------------------------
def _make_conn_ctx():
    """Return a (mock context manager, mock connection) pair."""
    conn = MagicMock()
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=conn)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx, conn


# ---------------------------------------------------------------------------
# get_tables_with_id_column
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestGetTablesWithIdColumn:
    def test_invalid_schema_returns_empty(self):
        result = get_tables_with_id_column(schema='bad-schema!')
        assert result == []

    def test_returns_valid_table_names(self, app):
        with app.app_context():
            ctx, conn = _make_conn_ctx()
            mock_result = MagicMock()
            mock_result.fetchall.return_value = [('users',), ('organizations',)]
            conn.execute.return_value = mock_result

            with patch('app.utils.sequence_utils.db') as mock_db:
                mock_db.engine.connect.return_value = ctx
                result = get_tables_with_id_column()
            assert 'users' in result
            assert 'organizations' in result

    def test_filters_out_invalid_table_names(self, app):
        with app.app_context():
            ctx, conn = _make_conn_ctx()
            mock_result = MagicMock()
            mock_result.fetchall.return_value = [('users',), ('bad-table',), (None,)]
            conn.execute.return_value = mock_result

            with patch('app.utils.sequence_utils.db') as mock_db:
                mock_db.engine.connect.return_value = ctx
                result = get_tables_with_id_column()
            assert 'users' in result
            assert 'bad-table' not in result

    def test_exception_returns_empty(self, app):
        with app.app_context():
            with patch('app.utils.sequence_utils.db') as mock_db:
                mock_db.engine.connect.side_effect = Exception('connection failed')
                result = get_tables_with_id_column()
            assert result == []


# ---------------------------------------------------------------------------
# reset_table_sequence
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestResetTableSequence:
    def test_invalid_table_name_returns_false(self):
        ok, reason = reset_table_sequence('bad-table!')
        assert ok is False
        assert 'invalid' in reason

    def test_invalid_schema_returns_false(self):
        ok, reason = reset_table_sequence('users', schema='bad-schema!')
        assert ok is False
        assert 'invalid' in reason

    def test_table_not_found_returns_false(self, app):
        with app.app_context():
            ctx, conn = _make_conn_ctx()
            # to_regclass returns False (table not found)
            conn.execute.return_value.scalar.return_value = False

            with patch('app.utils.sequence_utils.db') as mock_db:
                mock_db.engine.connect.return_value = ctx
                ok, reason = reset_table_sequence('ghost_table')
            assert ok is False
            assert 'not found' in reason

    def test_id_column_not_found_returns_false(self, app):
        with app.app_context():
            ctx, conn = _make_conn_ctx()
            exec_results = [
                MagicMock(scalar=MagicMock(return_value=True)),   # to_regclass
                MagicMock(first=MagicMock(return_value=None)),     # id column check
            ]
            conn.execute.side_effect = exec_results

            with patch('app.utils.sequence_utils.db') as mock_db:
                mock_db.engine.connect.return_value = ctx
                ok, reason = reset_table_sequence('users')
            assert ok is False
            assert 'id column' in reason

    def test_no_sequence_returns_false(self, app):
        with app.app_context():
            ctx, conn = _make_conn_ctx()
            exec_results = [
                MagicMock(scalar=MagicMock(return_value=True)),    # to_regclass
                MagicMock(first=MagicMock(return_value=(1,))),     # id column
                MagicMock(scalar=MagicMock(return_value=None)),    # no sequence
            ]
            conn.execute.side_effect = exec_results

            with patch('app.utils.sequence_utils.db') as mock_db:
                mock_db.engine.connect.return_value = ctx
                ok, reason = reset_table_sequence('users')
            assert ok is False
            assert 'sequence' in reason

    def test_successful_reset_with_data(self, app):
        with app.app_context():
            ctx, conn = _make_conn_ctx()
            exec_results = [
                MagicMock(scalar=MagicMock(return_value=True)),                   # to_regclass
                MagicMock(first=MagicMock(return_value=(1,))),                    # id column
                MagicMock(scalar=MagicMock(return_value='public.users_id_seq')),  # seq name
                MagicMock(scalar=MagicMock(return_value=42)),                     # max(id)
                MagicMock(),                                                       # setval
            ]
            conn.execute.side_effect = exec_results

            with patch('app.utils.sequence_utils.db') as mock_db:
                mock_db.engine.connect.return_value = ctx
                ok, reason = reset_table_sequence('users')
            assert ok is True
            assert reason == 'reset'
            conn.commit.assert_called_once()

    def test_successful_reset_empty_table(self, app):
        with app.app_context():
            ctx, conn = _make_conn_ctx()
            exec_results = [
                MagicMock(scalar=MagicMock(return_value=True)),
                MagicMock(first=MagicMock(return_value=(1,))),
                MagicMock(scalar=MagicMock(return_value='public.users_id_seq')),
                MagicMock(scalar=MagicMock(return_value=None)),  # max(id) = None (empty)
                MagicMock(),
            ]
            conn.execute.side_effect = exec_results

            with patch('app.utils.sequence_utils.db') as mock_db:
                mock_db.engine.connect.return_value = ctx
                ok, reason = reset_table_sequence('users')
            assert ok is True

    def test_exception_returns_false_error(self, app):
        with app.app_context():
            with patch('app.utils.sequence_utils.db') as mock_db:
                mock_db.engine.connect.side_effect = Exception('boom')
                ok, reason = reset_table_sequence('users')
            assert ok is False
            assert reason == 'error'


# ---------------------------------------------------------------------------
# check_sequence_status
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestCheckSequenceStatus:
    def test_invalid_table_name_returns_skip(self):
        status, detail = check_sequence_status('bad-table!')
        assert status == 'skip'

    def test_invalid_schema_returns_skip(self):
        status, detail = check_sequence_status('users', schema='bad!')
        assert status == 'skip'

    def test_table_not_found_returns_skip(self, app):
        with app.app_context():
            ctx, conn = _make_conn_ctx()
            conn.execute.return_value.scalar.return_value = False

            with patch('app.utils.sequence_utils.db') as mock_db:
                mock_db.engine.connect.return_value = ctx
                status, detail = check_sequence_status('ghost')
            assert status == 'skip'

    def test_no_id_column_returns_skip(self, app):
        with app.app_context():
            ctx, conn = _make_conn_ctx()
            exec_results = [
                MagicMock(scalar=MagicMock(return_value=True)),
                MagicMock(first=MagicMock(return_value=None)),
            ]
            conn.execute.side_effect = exec_results

            with patch('app.utils.sequence_utils.db') as mock_db:
                mock_db.engine.connect.return_value = ctx
                status, detail = check_sequence_status('users')
            assert status == 'skip'

    def test_no_sequence_returns_skip(self, app):
        with app.app_context():
            ctx, conn = _make_conn_ctx()
            exec_results = [
                MagicMock(scalar=MagicMock(return_value=True)),
                MagicMock(first=MagicMock(return_value=(1,))),
                MagicMock(scalar=MagicMock(return_value=None)),
            ]
            conn.execute.side_effect = exec_results

            with patch('app.utils.sequence_utils.db') as mock_db:
                mock_db.engine.connect.return_value = ctx
                status, detail = check_sequence_status('users')
            assert status == 'skip'

    def test_sequence_not_found_in_pg_sequences_returns_skip(self, app):
        with app.app_context():
            ctx, conn = _make_conn_ctx()
            exec_results = [
                MagicMock(scalar=MagicMock(return_value=True)),
                MagicMock(first=MagicMock(return_value=(1,))),
                MagicMock(scalar=MagicMock(return_value='public.users_id_seq')),
                MagicMock(scalar=MagicMock(return_value=10)),  # max(id)
                MagicMock(first=MagicMock(return_value=None)),  # pg_sequences row = None
            ]
            conn.execute.side_effect = exec_results

            with patch('app.utils.sequence_utils.db') as mock_db:
                mock_db.engine.connect.return_value = ctx
                status, detail = check_sequence_status('users')
            assert status == 'skip'

    def test_ok_when_next_val_above_max_id(self, app):
        with app.app_context():
            ctx, conn = _make_conn_ctx()
            exec_results = [
                MagicMock(scalar=MagicMock(return_value=True)),
                MagicMock(first=MagicMock(return_value=(1,))),
                MagicMock(scalar=MagicMock(return_value='public.users_id_seq')),
                MagicMock(scalar=MagicMock(return_value=10)),
                MagicMock(first=MagicMock(return_value=(10, True))),   # last_value=10, is_called=True → next=11
            ]
            conn.execute.side_effect = exec_results

            with patch('app.utils.sequence_utils.db') as mock_db:
                mock_db.engine.connect.return_value = ctx
                status, detail = check_sequence_status('users')
            assert status == 'ok'

    def test_needs_reset_when_next_val_behind_max_id(self, app):
        with app.app_context():
            ctx, conn = _make_conn_ctx()
            exec_results = [
                MagicMock(scalar=MagicMock(return_value=True)),
                MagicMock(first=MagicMock(return_value=(1,))),
                MagicMock(scalar=MagicMock(return_value='public.users_id_seq')),
                MagicMock(scalar=MagicMock(return_value=100)),            # max(id) = 100
                MagicMock(first=MagicMock(return_value=(5, True))),       # next = 6, behind 100
            ]
            conn.execute.side_effect = exec_results

            with patch('app.utils.sequence_utils.db') as mock_db:
                mock_db.engine.connect.return_value = ctx
                status, detail = check_sequence_status('users')
            assert status == 'needs_reset'
            assert '100' in detail

    def test_empty_table_ok_when_next_val_is_1(self, app):
        with app.app_context():
            ctx, conn = _make_conn_ctx()
            exec_results = [
                MagicMock(scalar=MagicMock(return_value=True)),
                MagicMock(first=MagicMock(return_value=(1,))),
                MagicMock(scalar=MagicMock(return_value='public.users_id_seq')),
                MagicMock(scalar=MagicMock(return_value=None)),           # empty table
                MagicMock(first=MagicMock(return_value=(1, False))),      # next=1 (is_called=False)
            ]
            conn.execute.side_effect = exec_results

            with patch('app.utils.sequence_utils.db') as mock_db:
                mock_db.engine.connect.return_value = ctx
                status, detail = check_sequence_status('users')
            assert status == 'ok'

    def test_empty_table_needs_reset_when_next_below_1(self, app):
        with app.app_context():
            ctx, conn = _make_conn_ctx()
            exec_results = [
                MagicMock(scalar=MagicMock(return_value=True)),
                MagicMock(first=MagicMock(return_value=(1,))),
                MagicMock(scalar=MagicMock(return_value='public.users_id_seq')),
                MagicMock(scalar=MagicMock(return_value=None)),
                MagicMock(first=MagicMock(return_value=(0, False))),  # next=0 < 1
            ]
            conn.execute.side_effect = exec_results

            with patch('app.utils.sequence_utils.db') as mock_db:
                mock_db.engine.connect.return_value = ctx
                status, detail = check_sequence_status('users')
            assert status == 'needs_reset'

    def test_seq_name_without_dot_uses_schema(self, app):
        """seq_name without dot prefix should use the schema param."""
        with app.app_context():
            ctx, conn = _make_conn_ctx()
            exec_results = [
                MagicMock(scalar=MagicMock(return_value=True)),
                MagicMock(first=MagicMock(return_value=(1,))),
                MagicMock(scalar=MagicMock(return_value='users_id_seq')),  # no dot
                MagicMock(scalar=MagicMock(return_value=5)),
                MagicMock(first=MagicMock(return_value=(10, True))),   # next=11 > 5
            ]
            conn.execute.side_effect = exec_results

            with patch('app.utils.sequence_utils.db') as mock_db:
                mock_db.engine.connect.return_value = ctx
                status, _ = check_sequence_status('users')
            assert status == 'ok'

    def test_exception_returns_skip(self, app):
        with app.app_context():
            with patch('app.utils.sequence_utils.db') as mock_db:
                mock_db.engine.connect.side_effect = Exception('crash')
                status, detail = check_sequence_status('users')
            assert status == 'skip'
            assert detail == 'error'


# ---------------------------------------------------------------------------
# scan_sequences_status
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestScanSequencesStatus:
    def test_returns_list_of_tuples(self, app):
        with app.app_context():
            with patch('app.utils.sequence_utils.get_tables_with_id_column', return_value=['users', 'orgs']), \
                 patch('app.utils.sequence_utils.check_sequence_status', return_value=('ok', 'ok')):
                result = scan_sequences_status()
            assert isinstance(result, list)
            assert len(result) == 2
            for table, status, detail in result:
                assert status == 'ok'

    def test_empty_tables_returns_empty_list(self, app):
        with app.app_context():
            with patch('app.utils.sequence_utils.get_tables_with_id_column', return_value=[]):
                result = scan_sequences_status()
            assert result == []


# ---------------------------------------------------------------------------
# reset_user_sequence
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestResetUserSequence:
    def test_delegates_to_reset_table_sequence(self, app):
        with app.app_context():
            with patch('app.utils.sequence_utils.reset_table_sequence', return_value=(True, 'reset')) as mock_reset:
                result = reset_user_sequence()
            mock_reset.assert_called_once_with('user', schema='public')
            assert result is True

    def test_returns_false_on_failure(self, app):
        with app.app_context():
            with patch('app.utils.sequence_utils.reset_table_sequence', return_value=(False, 'error')):
                result = reset_user_sequence()
            assert result is False


# ---------------------------------------------------------------------------
# scan_and_reset_all_sequences
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestScanAndResetAllSequences:
    def test_returns_list_of_tuples(self, app):
        with app.app_context():
            with patch('app.utils.sequence_utils.get_tables_with_id_column', return_value=['users']), \
                 patch('app.utils.sequence_utils.reset_table_sequence', return_value=(True, 'reset')):
                result = scan_and_reset_all_sequences()
            assert result == [('users', True, 'reset')]

    def test_empty_tables_returns_empty(self, app):
        with app.app_context():
            with patch('app.utils.sequence_utils.get_tables_with_id_column', return_value=[]):
                result = scan_and_reset_all_sequences()
            assert result == []

    def test_mixed_results(self, app):
        with app.app_context():
            tables = ['users', 'orgs', 'assignments']
            side_effects = [(True, 'reset'), (False, 'error'), (True, 'reset')]
            with patch('app.utils.sequence_utils.get_tables_with_id_column', return_value=tables), \
                 patch('app.utils.sequence_utils.reset_table_sequence', side_effect=side_effects):
                result = scan_and_reset_all_sequences()
            assert len(result) == 3
            assert result[0] == ('users', True, 'reset')
            assert result[1] == ('orgs', False, 'error')
