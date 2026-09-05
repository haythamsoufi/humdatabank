"""Helpers that keep a dead test-DB from failing a green pytest teardown."""

from tests.conftest import _is_lost_db_connection


def test_lost_connection_message_is_recognized():
    assert _is_lost_db_connection(
        RuntimeError("server closed the connection unexpectedly")
    )
    assert _is_lost_db_connection(RuntimeError("connection already closed"))
    assert _is_lost_db_connection(
        RuntimeError("SSL connection has been closed unexpectedly")
    )


def test_unrelated_errors_are_not_swallowed():
    assert _is_lost_db_connection(RuntimeError("division by zero")) is False
    assert _is_lost_db_connection(ValueError("bad fixture")) is False
