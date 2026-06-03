"""Add disagg_type discriminator to submission data tables

Revision ID: add_disagg_type_column
Revises: add_form_data_numeric_value
Create Date: 2026-06-03

Adds a nullable discriminator for the JSON payload shape stored in disagg_data.
"""

from alembic import op
import sqlalchemy as sa


revision = 'add_disagg_type_column'
down_revision = 'add_form_data_numeric_value'
branch_labels = None
depends_on = None

_DATA_TABLES = ('form_data', 'dynamic_indicator_data', 'repeat_group_data')


def upgrade():
    for table_name in _DATA_TABLES:
        with op.batch_alter_table(table_name, schema=None) as batch_op:
            batch_op.add_column(sa.Column('disagg_type', sa.String(length=20), nullable=True))

    for table_name in _DATA_TABLES:
        op.execute(
            f"""
            UPDATE {table_name}
            SET disagg_type = 'standard_disagg'
            WHERE disagg_data IS NOT NULL
              AND (disagg_data::jsonb ? 'mode')
            """
        )

        op.execute(
            f"""
            UPDATE {table_name}
            SET disagg_type = 'simple'
            WHERE value IS NOT NULL
              AND disagg_data IS NULL
              AND disagg_type IS NULL
            """
        )

    op.execute(
        """
        UPDATE form_data
        SET disagg_type = 'matrix'
        FROM form_item
        WHERE form_data.form_item_id = form_item.id
          AND form_item.item_type = 'matrix'
          AND form_data.disagg_data IS NOT NULL
          AND NOT (form_data.disagg_data::jsonb ? 'mode')
        """
    )

    op.execute(
        """
        UPDATE repeat_group_data
        SET disagg_type = 'matrix'
        FROM form_item
        WHERE repeat_group_data.form_item_id = form_item.id
          AND form_item.item_type = 'matrix'
          AND repeat_group_data.disagg_data IS NOT NULL
          AND NOT (repeat_group_data.disagg_data::jsonb ? 'mode')
        """
    )

    op.execute(
        """
        UPDATE form_data
        SET disagg_type = 'plugin'
        FROM form_item
        WHERE form_data.form_item_id = form_item.id
          AND form_item.item_type LIKE 'plugin_%'
          AND form_data.disagg_data IS NOT NULL
          AND form_data.disagg_type IS NULL
        """
    )

    # Dynamic indicator rows have no FormItem reference. Any non-standard JSON
    # currently represents matrix-style ad hoc payloads from the dynamic flow.
    op.execute(
        """
        UPDATE dynamic_indicator_data
        SET disagg_type = 'matrix'
        WHERE disagg_data IS NOT NULL
          AND NOT (disagg_data::jsonb ? 'mode')
          AND disagg_type IS NULL
        """
    )


def downgrade():
    for table_name in reversed(_DATA_TABLES):
        with op.batch_alter_table(table_name, schema=None) as batch_op:
            batch_op.drop_column('disagg_type')
