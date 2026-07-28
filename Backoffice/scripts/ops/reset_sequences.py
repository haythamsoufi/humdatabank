#!/usr/bin/env python3
"""
Reset database sequences and IDs for form_item, form_template, and form_data tables.

This script provides two modes:
1. Reset sequences only (safer) - Resets auto-increment sequences but keeps existing IDs
2. Reorder IDs starting from 1 (more complex) - Actually reorders all IDs to start from 1

WARNING: Reordering IDs will update foreign key references. Make sure you have a database backup!
"""

import argparse
import logging
import os
import sys

logger = logging.getLogger(__name__)
import re
from sqlalchemy import text

# Add the parent directory to the path so we can import app
script_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(script_dir)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Set up environment
if 'FLASK_CONFIG' not in os.environ:
    os.environ['FLASK_CONFIG'] = 'production'

IDENTIFIER_PATTERN = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def ensure_safe_identifier(value: str, label: str) -> str:
    """Validate that identifiers only contain safe characters for interpolation."""
    if not IDENTIFIER_PATTERN.match(value or ''):
        raise ValueError(f"Invalid {label}: {value}")
    return value

def find_sequence(connection, table_name, id_column):
    """Find the sequence name for a given table and column using pg_get_serial_sequence."""
    table_name = ensure_safe_identifier(table_name, "table name")
    id_column = ensure_safe_identifier(id_column, "column name")
    try:
        seq_result = connection.execute(
            text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
            {"table_name": table_name, "column_name": id_column}
        )
        seq_name = seq_result.scalar()
        if seq_name:
            # pg_get_serial_sequence returns schema.sequence_name, extract just the name
            return seq_name.split('.')[-1] if '.' in seq_name else seq_name
    except Exception as e:
        logger.debug("pg_get_serial_sequence fallback: %s", e)

    # Fallback: try standard naming convention
    sequence_name = f"{table_name}_{id_column}_seq"
    check = connection.execute(
        text("""
            SELECT EXISTS (
                SELECT 1 FROM pg_class
                WHERE relname = :seq_name
            )
        """),
        {"seq_name": sequence_name}
    )
    if check.scalar():
        return sequence_name

    return None

def create_sequence_if_needed(connection, table_name, id_column):
    """Create a sequence for a table column if it doesn't exist, and link it to the column."""
    table_name = ensure_safe_identifier(table_name, "table name")
    id_column = ensure_safe_identifier(id_column, "column name")
    sequence_name = f"{table_name}_{id_column}_seq"

    # Check if sequence already exists
    check = connection.execute(
        text("""
            SELECT EXISTS (
                SELECT 1 FROM pg_class
                WHERE relname = :seq_name
            )
        """),
        {"seq_name": sequence_name}
    )
    if check.scalar():
        return sequence_name

    # Get current max ID to set sequence start value
    max_id_result = connection.execute(
        text(f'SELECT COALESCE(MAX("{id_column}"), 0) FROM "{table_name}"')
    )
    max_id = max_id_result.scalar()
    start_value = max_id + 1 if max_id > 0 else 1

    # Create the sequence
    connection.execute(
        text(f"CREATE SEQUENCE {sequence_name} START {start_value}")
    )

    # Link the sequence to the column as the default value
    connection.execute(
        text(f'ALTER TABLE "{table_name}" ALTER COLUMN "{id_column}" SET DEFAULT nextval(\'{sequence_name}\')')
    )

    # Set the sequence owner to the table column
    connection.execute(
        text(f'ALTER SEQUENCE {sequence_name} OWNED BY "{table_name}"."{id_column}"')
    )

    return sequence_name

def reset_sequences_only(connection, tables_to_reset):
    """Reset sequences only, without reordering IDs."""
    logger.info("=" * 80)
    logger.info("MODE: Reset Sequences Only (IDs will remain unchanged)")
    logger.info("=" * 80)

    for table_name, id_column in tables_to_reset.items():
        table_name = ensure_safe_identifier(table_name, "table name")
        id_column = ensure_safe_identifier(id_column, "column name")
        logger.info("Processing table: %s (column: %s)", table_name, id_column)

        # Get current max ID (quote identifiers to handle reserved keywords)
        max_id_result = connection.execute(
            text(f'SELECT COALESCE(MAX("{id_column}"), 0) FROM "{table_name}"')
        )
        max_id = max_id_result.scalar()
        logger.info("  Current max ID: %s", max_id)

        # Find or create sequence
        sequence_name = find_sequence(connection, table_name, id_column)
        if not sequence_name:
            logger.warning("  Sequence not found for %s.%s", table_name, id_column)
            logger.info("  Creating sequence...")
            sequence_name = create_sequence_if_needed(connection, table_name, id_column)
            logger.info("  Created sequence: %s", sequence_name)
        else:
            logger.info("  Found sequence: %s", sequence_name)

        # Reset sequence
        if max_id > 0:
            new_start = max_id + 1
            logger.info("  Setting sequence to start from %s (next value after max ID)", new_start)
        else:
            new_start = 1
            logger.info("  Setting sequence to start from 1 (no existing records)")

        connection.execute(
            text("SELECT setval(:seq_name, :start_val, false)"),
            {"seq_name": sequence_name, "start_val": new_start}
        )
        logger.info("  Sequence reset successfully")

def reorder_ids(connection, tables_to_reset):
    """Reorder IDs starting from 1, updating foreign key references.

    Args:
        connection: Database connection
        tables_to_reset: Dictionary of {table_name: id_column} or list of (table_name, id_column) tuples
    """
    logger.info("=" * 80)
    logger.info("MODE: Reorder IDs Starting from 1")
    logger.warning("WARNING: This will update all IDs and foreign key references!")
    logger.info("=" * 80)

    # Convert to list of tuples if it's a dict
    if isinstance(tables_to_reset, dict):
        ordered_tables = list(tables_to_reset.items())
    else:
        ordered_tables = tables_to_reset

    for table_name, id_column in ordered_tables:
        table_name = ensure_safe_identifier(table_name, "table name")
        id_column = ensure_safe_identifier(id_column, "column name")
        logger.info("=" * 80)
        logger.info("Processing table: %s (column: %s)", table_name, id_column)
        logger.info("=" * 80)

        # Get current count (quote table name to handle reserved keywords)
        count_result = connection.execute(
            text(f'SELECT COUNT(*) FROM "{table_name}"')
        )
        count = count_result.scalar()
        logger.info("  Total records: %d", count)

        if count == 0:
            logger.info("  No records to reorder, skipping.")
            continue

        # Get all current IDs ordered (quote identifiers to handle reserved keywords)
        ids_result = connection.execute(
            text(f'SELECT "{id_column}" FROM "{table_name}" ORDER BY "{id_column}"')
        )
        old_ids = [row[0] for row in ids_result]

        # Create mapping: old_id -> new_id (starting from 1)
        id_mapping = {old_id: new_id for new_id, old_id in enumerate(old_ids, start=1)}
        logger.info("  Will reorder %d IDs from %s-%s to 1-%d", len(id_mapping), min(old_ids), max(old_ids), len(id_mapping))

        # Disable foreign key constraints temporarily
        logger.info("  Temporarily disabling foreign key constraints...")

        # Get all foreign key constraints that reference this table
        fk_query = connection.execute(
            text("""
                SELECT
                    tc.table_name,
                    kcu.column_name,
                    tc.constraint_name
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                    ON tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage AS ccu
                    ON ccu.constraint_name = tc.constraint_name
                    AND ccu.table_schema = tc.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                    AND tc.table_schema = 'public'
                    AND ccu.table_name = :table_name
                    AND ccu.column_name = :column_name
            """),
            {"table_name": table_name, "column_name": id_column}
        )
        fk_constraints = fk_query.fetchall()

        # Drop foreign key constraints
        dropped_constraints = []
        for fk_table, fk_column, constraint_name in fk_constraints:
            try:
                connection.execute(
                    text(f'ALTER TABLE "{fk_table}" DROP CONSTRAINT IF EXISTS {constraint_name}')
                )
                dropped_constraints.append((fk_table, constraint_name, fk_column))
                logger.info("    Dropped FK constraint: %s.%s", fk_table, constraint_name)
            except Exception as e:
                logger.warning("    Could not drop constraint %s: %s", constraint_name, e)

        # Update IDs using a temporary column approach to avoid conflicts
        logger.info("  Reordering IDs...")

        # Use a safer approach: update IDs in batches using a temporary mapping table
        logger.info("  Creating temporary mapping table...")

        # Create temp table for ID mapping
        temp_table = f"temp_{table_name}_id_mapping"
        connection.execute(
            text(f"""
                CREATE TEMPORARY TABLE {temp_table} (
                    old_id INTEGER,
                    new_id INTEGER,
                    PRIMARY KEY (old_id)
                )
            """)
        )

        # Insert mappings
        for old_id, new_id in id_mapping.items():
            connection.execute(
                text(f"INSERT INTO {temp_table} (old_id, new_id) VALUES (:old_id, :new_id)"),
                {"old_id": old_id, "new_id": new_id}
            )

        # Step 1: Update foreign key references in other tables first
        logger.info("  Updating foreign key references in other tables...")
        for fk_table, fk_column, constraint_name in fk_constraints:
            result = connection.execute(
                text(f"""
                    UPDATE "{fk_table}" fk
                    SET "{fk_column}" = m.new_id
                    FROM {temp_table} m
                    WHERE fk."{fk_column}" = m.old_id
                """)
            )
            if result.rowcount > 0:
                logger.info("    Updated %d references in %s.%s", result.rowcount, fk_table, fk_column)

        # Step 2: Update IDs in the main table using a two-pass approach to avoid conflicts
        # This preserves column order by updating in place instead of dropping/recreating
        logger.info("  Reordering IDs in %s...", table_name)

        # First pass: Move all IDs to negative values to free up positive space
        # Use a large negative offset to avoid any conflicts
        offset = 10000000
        logger.info("    Step 1: Moving IDs to temporary negative values...")
        connection.execute(
            text(f"""
                UPDATE "{table_name}" t
                SET "{id_column}" = -(t."{id_column}" + :offset)
                FROM {temp_table} m
                WHERE t."{id_column}" = m.old_id
            """),
            {"offset": offset}
        )

        # Second pass: Update to final positive values
        # Match on the negative temporary value
        logger.info("    Step 2: Moving IDs to final values...")
        connection.execute(
            text(f"""
                UPDATE "{table_name}" t
                SET "{id_column}" = m.new_id
                FROM {temp_table} m
                WHERE t."{id_column}" = -(m.old_id + :offset)
            """),
            {"offset": offset}
        )

        # Drop temp table
        connection.execute(text(f"DROP TABLE IF EXISTS {temp_table}"))

        # Step 5: Move ID column to first position if it's not already (before recreating FKs)
        move_id_column_to_first(connection, table_name, id_column, dropped_constraints)

        # Step 6: Recreate foreign key constraints
        logger.info("  Recreating foreign key constraints...")
        for fk_table, constraint_name, fk_column in dropped_constraints:
            try:
                connection.execute(
                    text(f"""
                        ALTER TABLE "{fk_table}"
                        ADD CONSTRAINT {constraint_name}
                        FOREIGN KEY ("{fk_column}")
                        REFERENCES "{table_name}"("{id_column}")
                    """)
                )
                logger.info("    Recreated FK constraint: %s.%s", fk_table, constraint_name)
            except Exception as e:
                logger.warning("    Could not recreate constraint %s: %s", constraint_name, e)

        # Find or create and reset sequence
        sequence_name = find_sequence(connection, table_name, id_column)
        if not sequence_name:
            logger.info("  Sequence not found, creating...")
            sequence_name = create_sequence_if_needed(connection, table_name, id_column)

        new_start = len(id_mapping) + 1
        connection.execute(
            text("SELECT setval(:seq_name, :start_val, false)"),
            {"seq_name": sequence_name, "start_val": new_start}
        )
        logger.info("  Reset sequence %s to start from %s", sequence_name, new_start)

        logger.info("  Successfully reordered %d records", count)

def get_column_position(connection, table_name, column_name):
    """Get the ordinal position of a column in a table (1-based)."""
    table_name = ensure_safe_identifier(table_name, "table name")
    column_name = ensure_safe_identifier(column_name, "column name")
    result = connection.execute(
        text("""
            SELECT ordinal_position
            FROM information_schema.columns
            WHERE table_schema = 'public'
                AND table_name = :table_name
                AND column_name = :column_name
        """),
        {"table_name": table_name, "column_name": column_name}
    )
    pos = result.scalar()
    return pos if pos else None

def move_id_column_to_first(connection, table_name, id_column, dropped_constraints):
    """Move the ID column to the first position if it's not already there.

    Note: This recreates the table, so all constraints must be dropped first.
    Foreign key constraints are passed so we know they're already dropped.
    """
    table_name = ensure_safe_identifier(table_name, "table name")
    id_column = ensure_safe_identifier(id_column, "column name")
    current_pos = get_column_position(connection, table_name, id_column)

    if current_pos is None:
        logger.warning("    Could not determine position of %s column", id_column)
        return

    if current_pos == 1:
        logger.info("    ID column is already first (position %s)", current_pos)
        return

    logger.info("    Moving ID column from position %s to position 1...", current_pos)

    # Get all columns with full definitions
    columns_result = connection.execute(
        text("""
            SELECT
                c.column_name,
                c.ordinal_position,
                c.data_type,
                c.character_maximum_length,
                c.is_nullable,
                c.column_default,
                c.udt_name
            FROM information_schema.columns c
            WHERE c.table_schema = 'public'
                AND c.table_name = :table_name
            ORDER BY c.ordinal_position
        """),
        {"table_name": table_name}
    )
    all_columns = columns_result.fetchall()

    # Separate ID column from others
    id_col_info = None
    other_columns = []
    for col_name, pos, data_type, max_length, nullable, default, udt_name in all_columns:
        if col_name == id_column:
            id_col_info = (col_name, pos, data_type, max_length, nullable, default, udt_name)
        else:
            other_columns.append((col_name, pos, data_type, max_length, nullable, default, udt_name))

    if not id_col_info:
        logger.warning("    Could not find %s column information", id_column)
        return

    # Get all other table objects we need to preserve
    # Get indexes (excluding primary key)
    indexes_result = connection.execute(
        text("""
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE schemaname = 'public'
                AND tablename = :table_name
                AND indexname NOT LIKE '%_pkey'
        """),
        {"table_name": table_name}
    )
    indexes = indexes_result.fetchall()

    temp_table = f"{table_name}_reorder_temp_{int(__import__('time').time())}"

    try:
        # Build column definitions - ID first, then others
        column_defs = []
        for col_name, pos, data_type, max_length, nullable, default, udt_name in [id_col_info] + other_columns:
            # Use udt_name for more accurate type mapping
            if udt_name in ('int4', 'integer'):
                type_def = "INTEGER"
            elif udt_name == 'int8':
                type_def = "BIGINT"
            elif udt_name == 'int2':
                type_def = "SMALLINT"
            elif udt_name in ('varchar', 'bpchar'):
                type_def = f"VARCHAR({max_length})" if max_length else "VARCHAR"
            elif udt_name == 'text':
                type_def = "TEXT"
            elif udt_name == 'bool':
                type_def = "BOOLEAN"
            elif udt_name in ('timestamp', 'timestamptz'):
                type_def = "TIMESTAMP"
            elif udt_name == 'jsonb':
                type_def = "JSONB"
            elif udt_name == 'json':
                type_def = "JSON"
            else:
                # Fallback to data_type
                type_def = data_type.upper()

            null_def = "NULL" if nullable == 'YES' else "NOT NULL"
            # Preserve default if it exists (but clean it up)
            default_def = ""
            if default:
                # Remove function call parentheses for sequences
                if 'nextval' in str(default):
                    default_def = f" DEFAULT {default}"
                else:
                    default_def = f" DEFAULT {default}"

            column_defs.append(f'"{col_name}" {type_def} {null_def}{default_def}')

        # Create temp table with correct column order
        connection.execute(
            text(f'CREATE TABLE "{temp_table}" ({", ".join(column_defs)})')
        )

        # Copy data - specify column order explicitly
        all_col_names = [id_col_info[0]] + [col[0] for col in other_columns]
        col_list = ', '.join(f'"{col}"' for col in all_col_names)
        connection.execute(
            text(f'INSERT INTO "{temp_table}" ({col_list}) SELECT {col_list} FROM "{table_name}"')
        )

        # Drop old table (FKs are already dropped, so CASCADE is safe)
        connection.execute(text(f'DROP TABLE "{table_name}" CASCADE'))

        # Rename temp table
        connection.execute(text(f'ALTER TABLE "{temp_table}" RENAME TO "{table_name}"'))

        # Recreate primary key
        try:
            connection.execute(
                text(f'ALTER TABLE "{table_name}" ADD PRIMARY KEY ("{id_column}")')
            )
        except Exception as e:
            logger.warning("    Could not recreate primary key: %s", e)

        # Recreate indexes
        for index_name, index_def in indexes:
            try:
                # Replace table name in index definition
                new_index_def = index_def.replace(f' ON {table_name} ', f' ON "{table_name}" ')
                new_index_def = new_index_def.replace(f' ON {table_name}(', f' ON "{table_name}"(')
                connection.execute(text(new_index_def))
            except Exception as e:
                logger.warning("    Could not recreate index %s: %s", index_name, e)

        logger.info("    Moved ID column to first position")

    except Exception as e:
        # If something goes wrong, try to clean up
        try:
            connection.execute(text(f'DROP TABLE IF EXISTS "{temp_table}"'))
        except Exception as e2:
            logger.debug("DROP TABLE IF EXISTS temp cleanup: %s", e2)
        logger.warning("    Could not move ID column to first position: %s", e)
        logger.info("    Table structure remains unchanged")
        import traceback
        traceback.print_exc()

def get_all_tables_with_primary_keys(connection):
    """Get all tables with integer primary keys from the database."""
    result = connection.execute(
        text("""
            SELECT
                t.table_name,
                kcu.column_name
            FROM information_schema.tables t
            JOIN information_schema.table_constraints tc
                ON t.table_name = tc.table_name
                AND t.table_schema = tc.table_schema
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            JOIN information_schema.columns c
                ON kcu.table_name = c.table_name
                AND kcu.column_name = c.column_name
                AND kcu.table_schema = c.table_schema
            WHERE t.table_schema = 'public'
                AND tc.constraint_type = 'PRIMARY KEY'
                AND c.data_type IN ('integer', 'bigint', 'smallint')
                AND t.table_type = 'BASE TABLE'
            ORDER BY t.table_name
        """)
    )
    safe_tables = {}
    for row in result:
        table_name = ensure_safe_identifier(row[0], "table name")
        column_name = ensure_safe_identifier(row[1], "column name")
        safe_tables[table_name] = column_name
    return safe_tables

def get_table_dependencies(connection, table_name, id_column):
    """Get tables that have foreign keys referencing this table."""
    table_name = ensure_safe_identifier(table_name, "table name")
    id_column = ensure_safe_identifier(id_column, "column name")
    result = connection.execute(
        text("""
            SELECT DISTINCT
                tc.table_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
                AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
                AND tc.table_schema = 'public'
                AND ccu.table_name = :table_name
                AND ccu.column_name = :column_name
        """),
        {"table_name": table_name, "column_name": id_column}
    )
    return [ensure_safe_identifier(row[0], "table name") for row in result]

def order_tables_by_dependencies(connection, tables_to_reset):
    """Order tables by their dependency relationships (topological sort)."""
    # Build dependency graph
    dependencies = {}
    for table_name, id_column in tables_to_reset.items():
        deps = get_table_dependencies(connection, table_name, id_column)
        # Only include dependencies that are in our list
        dependencies[table_name] = [d for d in deps if d in tables_to_reset]

    # Topological sort
    ordered = []
    remaining = set(tables_to_reset.keys())

    while remaining:
        # Find tables with no dependencies (or all dependencies already processed)
        ready = [
            t for t in remaining
            if all(dep in ordered for dep in dependencies[t])
        ]

        if not ready:
            # Circular dependency or error - just add remaining tables
            ready = list(remaining)

        # Sort for consistent ordering
        ready.sort()
        ordered.extend(ready)
        remaining -= set(ready)

    return [(t, tables_to_reset[t]) for t in ordered]

def main():
    parser = argparse.ArgumentParser(
        description='Reset database sequences and IDs for tables'
    )
    parser.add_argument(
        '--reorder',
        action='store_true',
        help='Reorder IDs starting from 1 (WARNING: updates foreign keys). Default: only reset sequences.'
    )
    parser.add_argument(
        '--tables',
        nargs='+',
        help='Specific tables to process (default: all tables with integer primary keys)'
    )
    parser.add_argument(
        '--exclude',
        nargs='+',
        help='Tables to exclude from processing'
    )

    args = parser.parse_args()

    try:
        from app import create_app
        from app.extensions import db
        from sqlalchemy import inspect

        app = create_app()
        with app.app_context():
            inspector = inspect(db.engine)

            # Get database connection for queries
            connection = db.engine.connect()

            try:
                # Get all tables with integer primary keys
                all_tables = get_all_tables_with_primary_keys(connection)

                if not all_tables:
                    logger.warning("No tables with integer primary keys found.")
                    sys.exit(0)

                # Filter by user selection
                if args.tables:
                    # User specified specific tables
                    tables_to_reset = {}
                    for table_name in args.tables:
                        if table_name not in all_tables:
                            logger.warning("Table %s not found or doesn't have an integer primary key, skipping.", table_name)
                            continue
                        tables_to_reset[table_name] = all_tables[table_name]

                    if not tables_to_reset:
                        logger.error("No valid tables to process.")
                        sys.exit(1)
                else:
                    # Process all tables
                    tables_to_reset = all_tables.copy()

                # Exclude specified tables
                if args.exclude:
                    for table_name in args.exclude:
                        if table_name in tables_to_reset:
                            del tables_to_reset[table_name]
                            logger.info("Excluding table: %s", table_name)

                if not tables_to_reset:
                    logger.warning("No tables to process after filtering.")
                    sys.exit(0)

                logger.info("Found %d table(s) to process:", len(tables_to_reset))
                for table_name, id_column in sorted(tables_to_reset.items()):
                    logger.info("  - %s (PK: %s)", table_name, id_column)

            finally:
                connection.close()

            # Get database connection for transaction
            connection = db.engine.connect()
            transaction = connection.begin()

            try:
                if args.reorder:
                    logger.warning("WARNING: You are about to reorder IDs starting from 1.")
                    logger.warning("This will update all IDs and foreign key references.")
                    logger.warning("Make sure you have a database backup!")
                    response = input("\nType 'yes' to continue: ")
                    if response.lower() != 'yes':
                        logger.info("Aborted.")
                        sys.exit(0)

                    # Order tables by dependencies
                    ordered_tables = order_tables_by_dependencies(connection, tables_to_reset)
                    logger.info("Processing %d table(s) in dependency order...", len(ordered_tables))
                    reorder_ids(connection, ordered_tables)
                else:
                    reset_sequences_only(connection, tables_to_reset)

                # Commit the changes
                transaction.commit()
                logger.info("=" * 80)
                logger.info("Operation completed successfully!")
                logger.info("=" * 80)

            except Exception as e:
                transaction.rollback()
                logger.error("Operation failed: %s", e)
                import traceback
                traceback.print_exc()
                sys.exit(1)
            finally:
                connection.close()

    except Exception as e:
        logger.error("Error: %s", e)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
