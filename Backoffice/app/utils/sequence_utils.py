"""Utilities for resetting PostgreSQL sequences (e.g. after loading a dump)."""
from __future__ import annotations

import logging

from sqlalchemy import text

from app.extensions import db

logger = logging.getLogger(__name__)


def _valid_identifier(name: str) -> bool:
    """True if name is safe for use as schema/table name (alphanumeric + underscore)."""
    return bool(name and all(c.isalnum() or c == "_" for c in name))


def get_tables_with_id_column(schema: str = "public") -> list[str]:
    """Return all base tables in the schema that have an 'id' column.

    Names are validated (alphanumeric + underscore only) before returning.
    Use with PostgreSQL; on other engines returns [].
    """
    if not _valid_identifier(schema):
        return []
    try:
        with db.engine.connect() as conn:
            rows = conn.execute(
                text("""
                SELECT c.table_name
                FROM information_schema.columns c
                JOIN information_schema.tables t
                  ON t.table_schema = c.table_schema AND t.table_name = c.table_name
                WHERE c.table_schema = :schema AND c.column_name = 'id'
                  AND t.table_type = 'BASE TABLE'
                ORDER BY c.table_name
                """),
                {"schema": schema},
            ).fetchall()
            names = [r[0] for r in rows if r and r[0] and _valid_identifier(str(r[0]))]
            return names
    except Exception as e:
        logger.debug("get_tables_with_id_column failed: %s", e)
        return []


def reset_table_sequence(
    table_name: str, schema: str = "public"
) -> tuple[bool, str]:
    """Reset the sequence for a table's id column to MAX(id).

    Use after loading a DB dump so the next INSERT gets a valid id.
    Returns (True, "reset") if the sequence was reset, otherwise (False, reason).
    Uses a raw connection and commits on that connection.

    SECURITY: Only call with validated table names (alphanumeric + underscore).
    """
    try:
        if not _valid_identifier(table_name):
            return (False, "invalid table name")
        if not _valid_identifier(schema):
            return (False, "invalid schema name")

        qual_quoted = f'"{schema}"."{table_name}"'

        with db.engine.connect() as conn:
            table_exists = conn.execute(
                text("SELECT to_regclass(:qual) IS NOT NULL"),
                {"qual": qual_quoted},
            ).scalar()
            if not table_exists:
                return (False, "table not found")

            id_column_exists = conn.execute(
                text(
                    """
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = :schema
                      AND table_name = :table
                      AND column_name = :column
                    LIMIT 1
                    """
                ),
                {"schema": schema, "table": table_name, "column": "id"},
            ).first()
            if not id_column_exists:
                return (False, "id column not found")

            seq_name = conn.execute(
                text("SELECT pg_get_serial_sequence(:qual, :column)"),
                {"qual": qual_quoted, "column": "id"},
            ).scalar()
            if not seq_name:
                return (False, "no serial/identity sequence for id")

            max_id = conn.execute(
                text(f"SELECT MAX(id) FROM {qual_quoted}")
            ).scalar()
            value = int(max_id) if max_id is not None else 1
            is_called = max_id is not None

            conn.execute(
                text("SELECT setval(to_regclass(:seq), :value, :is_called)"),
                {"seq": seq_name, "value": value, "is_called": is_called},
            )
            conn.commit()
        return (True, "reset")
    except Exception as e:
        logger.debug("reset_table_sequence failed: %s", e)
        return (False, "error")


def check_sequence_status(
    table_name: str, schema: str = "public"
) -> tuple[str, str]:
    """Check if a table's id sequence is ahead of MAX(id). Read-only, no setval.

    Returns (status, detail) where:
    - status is "ok" (sequence is fine), "needs_reset" (sequence behind max id), or "skip"
    - detail is a short reason (e.g. "behind max_id=100", "no serial sequence", "table not found").
    """
    try:
        if not _valid_identifier(table_name):
            return ("skip", "invalid table name")
        if not _valid_identifier(schema):
            return ("skip", "invalid schema name")

        qual_quoted = f'"{schema}"."{table_name}"'

        with db.engine.connect() as conn:
            table_exists = conn.execute(
                text("SELECT to_regclass(:qual) IS NOT NULL"),
                {"qual": qual_quoted},
            ).scalar()
            if not table_exists:
                return ("skip", "table not found")

            id_column_exists = conn.execute(
                text(
                    """
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = :schema
                      AND table_name = :table
                      AND column_name = :column
                    LIMIT 1
                    """
                ),
                {"schema": schema, "table": table_name, "column": "id"},
            ).first()
            if not id_column_exists:
                return ("skip", "id column not found")

            seq_name = conn.execute(
                text("SELECT pg_get_serial_sequence(:qual, :column)"),
                {"qual": qual_quoted, "column": "id"},
            ).scalar()
            if not seq_name:
                return ("skip", "no serial/identity sequence for id")

            max_id = conn.execute(
                text(f"SELECT MAX(id) FROM {qual_quoted}")
            ).scalar()

            # Get sequence state without consuming a value (pg_sequences.last_value, is_called)
            parts = seq_name.split(".", 1)
            seq_schema = parts[0] if len(parts) == 2 else schema
            seq_only_name = parts[1] if len(parts) == 2 else seq_name
            row = conn.execute(
                text(
                    """
                    SELECT last_value, is_called
                    FROM pg_sequences
                    WHERE schemaname = :seq_schema
                      AND sequencename = :seq_only_name
                    """
                ),
                {"seq_schema": seq_schema, "seq_only_name": seq_only_name},
            ).first()
            if not row:
                return ("skip", "sequence not found")

            last_value, is_called = row
            next_val = int(last_value) + (1 if is_called else 0)

            if max_id is None:
                # Empty table: next insert should get id 1
                if next_val < 1:
                    return ("needs_reset", "empty table, sequence not at 1")
                return ("ok", "ok")
            max_id_int = int(max_id)
            if next_val <= max_id_int:
                return ("needs_reset", f"behind max_id={max_id_int}")
            return ("ok", "ok")
    except Exception as e:
        logger.debug("check_sequence_status failed: %s", e)
        return ("skip", "error")


def scan_sequences_status(
    schema: str = "public",
) -> list[tuple[str, str, str]]:
    """Scan all tables with an id column and report sequence status only (no reset).

    Returns a list of (table_name, status, detail) where status is "ok", "needs_reset", or "skip".
    Use to report which tables need a sequence reset (e.g. after a DB dump) without changing anything.
    """
    tables = get_tables_with_id_column(schema=schema)
    results: list[tuple[str, str, str]] = []
    for name in tables:
        status, detail = check_sequence_status(name, schema=schema)
        results.append((name, status, detail))
    return results


def reset_user_sequence(schema: str = "public") -> bool:
    """Reset the user table's id sequence. Safe to call from request handlers."""
    ok, _ = reset_table_sequence("user", schema=schema)
    return ok


def scan_and_reset_all_sequences(
    schema: str = "public",
) -> list[tuple[str, bool, str]]:
    """Scan all tables with an id column and reset each sequence to MAX(id).

    Tables are discovered via information_schema; only those with a
    serial/identity sequence are actually reset; others are reported as skipped.
    Returns a list of (table_name, ok, reason) for each table.
    Use after migrations or loading a DB dump so all sequences are at max id.
    """
    tables = get_tables_with_id_column(schema=schema)
    results: list[tuple[str, bool, str]] = []
    for table_name in tables:
        ok, reason = reset_table_sequence(table_name, schema=schema)
        results.append((table_name, ok, reason))
    return results
