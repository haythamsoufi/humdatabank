"""Widen form data value columns from VARCHAR(255) to TEXT

VARCHAR(255) causes psycopg2.errors.StringDataRightTruncation when a user types
more than 255 characters into a textarea question. All major data-collection
platforms (Kobo, ODK, SurveyCTO) use an unbounded TEXT column for free-text
answers. This migration widens `value`, `prefilled_value`, and `imputed_value`
on all three form-data tables.

Revision ID: widen_form_data_value_to_text
Revises: drop_country_partof
Create Date: 2026-07-22
"""

from alembic import op
import sqlalchemy as sa


revision = "widen_form_data_value_to_text"
down_revision = "drop_country_partof"
branch_labels = None
depends_on = None

# Tables and columns to widen
_TABLES = [
    "form_data",
    "dynamic_indicator_data",
    "repeat_group_data",
]

_SCALAR_VALUE_COLS = ["value", "prefilled_value", "imputed_value"]


def upgrade():
    for table in _TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            for col in _SCALAR_VALUE_COLS:
                # Only alter columns that actually exist on this table.
                # `value` is on all three; `prefilled_value`/`imputed_value`
                # are also on all three (DataEntryMixin). batch_alter_table
                # is safe on PostgreSQL: it issues ALTER COLUMN ... TYPE TEXT,
                # which is a metadata-only change on PG (no full table rewrite
                # needed when widening character types).
                batch_op.alter_column(
                    col,
                    existing_type=sa.String(length=255),
                    type_=sa.Text(),
                    existing_nullable=True,
                )


def downgrade():
    for table in _TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            for col in _SCALAR_VALUE_COLS:
                batch_op.alter_column(
                    col,
                    existing_type=sa.Text(),
                    type_=sa.String(length=255),
                    existing_nullable=True,
                )
