"""PostgreSQL session advisory lock helpers.

Session-level advisory locks must be acquired and released on the same DB
connection. Unlocking after the connection was reset (pool recycle, idle
timeout, or a separate checkout) makes PostgreSQL emit:

    WARNING: you don't own a lock of type ExclusiveLock

SQLAlchemy logs that server notice at INFO under sqlalchemy.dialects.postgresql.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection


def _lock_key_parts(lock_id: int) -> tuple[int, int]:
    lock_id = int(lock_id)
    return (lock_id >> 32) & 0xFFFFFFFF, lock_id & 0xFFFFFFFF


def session_holds_advisory_lock(conn: Connection, lock_id: int) -> bool:
    """Return True if this backend connection currently holds the advisory lock."""
    classid, objid = _lock_key_parts(lock_id)
    return bool(
        conn.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM pg_locks
                    WHERE locktype = 'advisory'
                      AND pid = pg_backend_pid()
                      AND classid = :classid
                      AND objid = :objid
                )
                """
            ),
            {"classid": classid, "objid": objid},
        ).scalar()
    )


def try_session_advisory_lock(session, lock_id: int) -> bool:
    """Try to acquire a session advisory lock on the session's connection."""
    conn = session.connection()
    return bool(
        conn.execute(
            text("SELECT pg_try_advisory_lock(:lock_id)"),
            {"lock_id": int(lock_id)},
        ).scalar()
    )


def acquire_transaction_advisory_lock(session, lock_id: int) -> None:
    """Acquire a transaction-scoped advisory lock (PostgreSQL only).

    The lock is released automatically when the surrounding transaction commits
    or rolls back. No-op on non-PostgreSQL dialects (e.g. SQLite tests).
    """
    if session.get_bind().dialect.name != "postgresql":
        return
    session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_id)"),
        {"lock_id": int(lock_id)},
    )


def release_session_advisory_lock(session, lock_id: int, *, acquired: bool) -> None:
    """Release a session advisory lock if this connection still holds it."""
    if not acquired:
        return
    conn = session.connection()
    if session_holds_advisory_lock(conn, lock_id):
        conn.execute(
            text("SELECT pg_advisory_unlock(:lock_id)"),
            {"lock_id": int(lock_id)},
        )
