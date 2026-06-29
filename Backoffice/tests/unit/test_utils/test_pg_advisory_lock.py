"""Unit tests for PostgreSQL advisory lock helpers."""

from unittest.mock import MagicMock, patch

import pytest

from app.utils.pg_advisory_lock import (
    release_session_advisory_lock,
    session_holds_advisory_lock,
    try_session_advisory_lock,
)


class TestPgAdvisoryLockHelpers:
    def test_session_holds_advisory_lock_delegates_to_connection(self):
        conn = MagicMock()
        conn.execute.return_value.scalar.return_value = True

        assert session_holds_advisory_lock(conn, 702346) is True
        conn.execute.assert_called_once()

    def test_try_session_advisory_lock_uses_session_connection(self):
        session = MagicMock()
        session.connection.return_value.execute.return_value.scalar.return_value = True

        assert try_session_advisory_lock(session, 702346) is True
        session.connection.assert_called_once()

    def test_release_skips_when_not_acquired(self):
        session = MagicMock()
        release_session_advisory_lock(session, 702346, acquired=False)
        session.connection.assert_not_called()

    def test_release_skips_unlock_when_lock_not_held(self):
        session = MagicMock()
        conn = session.connection.return_value
        conn.execute.return_value.scalar.return_value = False

        release_session_advisory_lock(session, 702346, acquired=True)

        assert conn.execute.call_count == 1

    def test_release_unlocks_when_lock_held(self):
        session = MagicMock()
        conn = session.connection.return_value
        conn.execute.return_value.scalar.side_effect = [True, None]

        release_session_advisory_lock(session, 702346, acquired=True)

        assert conn.execute.call_count == 2
        unlock_sql = str(conn.execute.call_args_list[1].args[0])
        assert "pg_advisory_unlock" in unlock_sql
