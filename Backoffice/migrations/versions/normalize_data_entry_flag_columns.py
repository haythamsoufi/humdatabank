"""Normalize data_not_available and not_applicable to NOT NULL DEFAULT FALSE (F8)

Revision ID: normalize_data_entry_flags
Revises: add_data_submission_integrity
Create Date: 2026-06-02
"""

from alembic import op
import sqlalchemy as sa


revision = 'normalize_data_entry_flags'
down_revision = 'add_data_submission_integrity'
branch_labels = None
depends_on = None

_DATA_TABLES = ('form_data', 'dynamic_indicator_data', 'repeat_group_data')


def _normalize_flags(table_name: str) -> None:
    op.execute(
        f"UPDATE {table_name} SET data_not_available = FALSE WHERE data_not_available IS NULL"
    )
    op.execute(
        f"UPDATE {table_name} SET not_applicable = FALSE WHERE not_applicable IS NULL"
    )
    with op.batch_alter_table(table_name, schema=None) as batch_op:
        batch_op.alter_column(
            'data_not_available',
            existing_type=sa.Boolean(),
            nullable=False,
            server_default=sa.text('false'),
        )
        batch_op.alter_column(
            'not_applicable',
            existing_type=sa.Boolean(),
            nullable=False,
            server_default=sa.text('false'),
        )


def upgrade():
    for table_name in _DATA_TABLES:
        _normalize_flags(table_name)


def downgrade():
    for table_name in _DATA_TABLES:
        with op.batch_alter_table(table_name, schema=None) as batch_op:
            batch_op.alter_column(
                'not_applicable',
                existing_type=sa.Boolean(),
                nullable=True,
                server_default=None,
            )
            batch_op.alter_column(
                'data_not_available',
                existing_type=sa.Boolean(),
                nullable=True,
                server_default=None,
            )
