"""Unit tests for PostgreSQL advisory lock helpers."""

from unittest.mock import MagicMock, patch

import pytest

from app.utils.pg_advisory_lock import (
    release_session_advisory_lock,
    session_holds_advisory_lock,
    try_session_advisory_lock,
    wait_for_session_advisory_lock,
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


class TestWaitForSessionAdvisoryLock:
    """Tests for the blocking-with-timeout retry helper used by
    RbacSeedLockMode.WAIT (operator/deploy-triggered RBAC seeding)."""

    def test_returns_true_immediately_when_free(self):
        session = MagicMock()
        with patch(
            "app.utils.pg_advisory_lock.try_session_advisory_lock", return_value=True
        ) as mock_try, patch("app.utils.pg_advisory_lock.time.sleep") as mock_sleep:
            acquired = wait_for_session_advisory_lock(session, 702346, timeout_seconds=5.0)

        assert acquired is True
        mock_try.assert_called_once_with(session, 702346)
        mock_sleep.assert_not_called()

    def test_retries_until_acquired(self):
        session = MagicMock()
        with patch(
            "app.utils.pg_advisory_lock.try_session_advisory_lock",
            side_effect=[False, False, True],
        ) as mock_try, patch("app.utils.pg_advisory_lock.time.sleep") as mock_sleep:
            acquired = wait_for_session_advisory_lock(
                session, 702346, timeout_seconds=5.0, poll_interval_seconds=0.25
            )

        assert acquired is True
        assert mock_try.call_count == 3
        # Slept between attempts, not after the final successful one.
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(0.25)

    def test_gives_up_after_timeout(self):
        """Never acquires; must return False rather than block forever."""
        session = MagicMock()
        with patch(
            "app.utils.pg_advisory_lock.try_session_advisory_lock", return_value=False
        ):
            acquired = wait_for_session_advisory_lock(
                session, 702346, timeout_seconds=0.05, poll_interval_seconds=0.01
            )

        assert acquired is False

    def test_zero_timeout_tries_once_and_gives_up(self):
        session = MagicMock()
        with patch(
            "app.utils.pg_advisory_lock.try_session_advisory_lock", return_value=False
        ) as mock_try, patch("app.utils.pg_advisory_lock.time.sleep") as mock_sleep:
            acquired = wait_for_session_advisory_lock(session, 702346, timeout_seconds=0.0)

        assert acquired is False
        mock_try.assert_called_once()
        mock_sleep.assert_not_called()
