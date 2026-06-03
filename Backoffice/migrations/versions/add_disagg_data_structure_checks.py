"""Add CHECK constraints for disagg_data JSON shape (F9)

Revision ID: add_disagg_data_structure_checks
Revises: normalize_data_entry_flags
Create Date: 2026-06-02

Repairs malformed disagg_data rows (missing mode/values keys) before adding constraints.
Uses jsonb cast because columns are JSON type, not JSONB.
"""

from alembic import op


revision = 'add_disagg_data_structure_checks'
down_revision = 'normalize_data_entry_flags'
branch_labels = None
depends_on = None

_DISAGG_SHAPE_CHECK = (
    "disagg_data IS NULL OR "
    "NOT (disagg_data::jsonb ? 'mode') OR "
    "(disagg_data::jsonb ? 'mode' AND disagg_data::jsonb ? 'values')"
)

_DATA_TABLES = ('form_data', 'dynamic_indicator_data', 'repeat_group_data')


def upgrade():
    for table_name in _DATA_TABLES:
        op.execute(
            f"""
            UPDATE {table_name}
            SET disagg_data = NULL
            WHERE disagg_data IS NOT NULL
              AND (disagg_data::jsonb ? 'mode')
              AND NOT (disagg_data::jsonb ? 'values')
            """
        )
        op.create_check_constraint(
            f'ck_{table_name}_disagg_shape',
            table_name,
            _DISAGG_SHAPE_CHECK,
        )


def downgrade():
    for table_name in reversed(_DATA_TABLES):
        op.drop_constraint(f'ck_{table_name}_disagg_shape', table_name, type_='check')
