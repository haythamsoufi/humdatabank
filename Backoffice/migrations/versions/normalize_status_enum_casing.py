"""Normalize assignment/document status enum labels to lowercase snake_case.

Revision ID: normalize_status_enum_casing
Revises: add_status_enum_columns_batch
Create Date: 2026-06-03

Aligns PostgreSQL enum labels with the codebase convention:
lowercase snake_case in DB/Python; Title Case only in UI helpers.
"""

from alembic import op


revision = 'normalize_status_enum_casing'
down_revision = 'add_status_enum_columns_batch'
branch_labels = None
depends_on = None


def _rebuild_enum(table: str, column: str, old_type: str, new_type: str, new_values: tuple[str, ...], mapping_sql: str, default: str) -> None:
    op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} DROP DEFAULT")
    op.execute(
        f"""
        ALTER TABLE {table}
        ALTER COLUMN {column} TYPE TEXT
        USING {column}::text
        """
    )
    op.execute(mapping_sql)
    op.execute(f"DROP TYPE {old_type}")
    quoted = ", ".join(repr(v) for v in new_values)
    op.execute(f"CREATE TYPE {new_type} AS ENUM ({quoted})")
    op.execute(
        f"""
        ALTER TABLE {table}
        ALTER COLUMN {column} TYPE {new_type}
        USING {column}::{new_type}
        """
    )
    op.execute(
        f"ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT '{default}'::{new_type}"
    )
    op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} SET NOT NULL")


def upgrade():
    _rebuild_enum(
        'assignment_entity_status',
        'status',
        'assignmententitystatus',
        'assignmententitystatus',
        ('pending', 'in_progress', 'submitted', 'approved', 'requires_revision'),
        """
        UPDATE assignment_entity_status
        SET status = CASE LOWER(TRIM(status))
            WHEN 'pending' THEN 'pending'
            WHEN 'in progress' THEN 'in_progress'
            WHEN 'submitted' THEN 'submitted'
            WHEN 'approved' THEN 'approved'
            WHEN 'requires revision' THEN 'requires_revision'
            ELSE 'pending'
        END
        """,
        'pending',
    )

    _rebuild_enum(
        'submitted_document',
        'status',
        'documentstatus',
        'documentstatus',
        ('pending', 'approved', 'rejected'),
        """
        UPDATE submitted_document
        SET status = CASE LOWER(TRIM(status))
            WHEN 'pending' THEN 'pending'
            WHEN 'approved' THEN 'approved'
            WHEN 'rejected' THEN 'rejected'
            ELSE 'pending'
        END
        """,
        'pending',
    )


def downgrade():
    _rebuild_enum(
        'assignment_entity_status',
        'status',
        'assignmententitystatus',
        'assignmententitystatus',
        ('Pending', 'In Progress', 'Submitted', 'Approved', 'Requires Revision'),
        """
        UPDATE assignment_entity_status
        SET status = CASE status
            WHEN 'pending' THEN 'Pending'
            WHEN 'in_progress' THEN 'In Progress'
            WHEN 'submitted' THEN 'Submitted'
            WHEN 'approved' THEN 'Approved'
            WHEN 'requires_revision' THEN 'Requires Revision'
            ELSE 'Pending'
        END
        """,
        'Pending',
    )

    _rebuild_enum(
        'submitted_document',
        'status',
        'documentstatus',
        'documentstatus',
        ('Pending', 'Approved', 'Rejected'),
        """
        UPDATE submitted_document
        SET status = CASE status
            WHEN 'pending' THEN 'Pending'
            WHEN 'approved' THEN 'Approved'
            WHEN 'rejected' THEN 'Rejected'
            ELSE 'Pending'
        END
        """,
        'Pending',
    )
