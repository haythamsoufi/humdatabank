"""Add numeric_value columns for typed aggregation (F4)

Revision ID: add_form_data_numeric_value
Revises: add_form_data_created_audit
Create Date: 2026-06-02

Adds numeric_value to form_data, dynamic_indicator_data, repeat_group_data.
Adds imputed_numeric_value to form_data only.
Backfills numeric_value from existing string value where parseable.
"""

from alembic import op
import sqlalchemy as sa


revision = 'add_form_data_numeric_value'
down_revision = 'add_form_data_created_audit'
branch_labels = None
depends_on = None

_NUMERIC_BACKFILL = """
UPDATE {table}
SET numeric_value = CAST(value AS DOUBLE PRECISION)
WHERE value IS NOT NULL
  AND value ~ '^-?[0-9]+(\\.[0-9]+)?$'
"""

_IMPUTED_BACKFILL = """
UPDATE form_data
SET imputed_numeric_value = (imputed_value::text)::double precision
WHERE imputed_numeric_value IS NULL
  AND imputed_value IS NOT NULL
  AND jsonb_typeof(imputed_value::jsonb) = 'number'
"""

_IMPUTED_STRING_BACKFILL = """
UPDATE form_data
SET imputed_numeric_value = CAST(imputed_value #>> '{}' AS DOUBLE PRECISION)
WHERE imputed_numeric_value IS NULL
  AND imputed_value IS NOT NULL
  AND jsonb_typeof(imputed_value::jsonb) = 'string'
  AND (imputed_value #>> '{}') ~ '^-?[0-9]+(\\.[0-9]+)?$'
"""


def upgrade():
    for table_name in ('form_data', 'dynamic_indicator_data', 'repeat_group_data'):
        with op.batch_alter_table(table_name, schema=None) as batch_op:
            batch_op.add_column(sa.Column('numeric_value', sa.Float(), nullable=True))
        op.execute(_NUMERIC_BACKFILL.format(table=table_name))

    with op.batch_alter_table('form_data', schema=None) as batch_op:
        batch_op.add_column(sa.Column('imputed_numeric_value', sa.Float(), nullable=True))

    # Backfill imputed_numeric_value when imputed_value is a JSON number or numeric string
    op.execute(_IMPUTED_BACKFILL)
    op.execute(_IMPUTED_STRING_BACKFILL)


def downgrade():
    with op.batch_alter_table('form_data', schema=None) as batch_op:
        batch_op.drop_column('imputed_numeric_value')

    for table_name in reversed(('form_data', 'dynamic_indicator_data', 'repeat_group_data')):
        with op.batch_alter_table(table_name, schema=None) as batch_op:
            batch_op.drop_column('numeric_value')
