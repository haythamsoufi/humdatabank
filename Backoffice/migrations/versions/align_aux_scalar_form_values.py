"""Align auxiliary scalar form values with value columns

Revision ID: align_aux_scalar_form_values
Revises: convert_fds_member_to_user
Create Date: 2026-06-08 23:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "align_aux_scalar_form_values"
down_revision = "convert_fds_member_to_user"
branch_labels = None
depends_on = None


TABLES = ("form_data", "dynamic_indicator_data", "repeat_group_data")
COLUMNS = ("prefilled_value", "imputed_value")


def _upgrade_column(table_name: str, column_name: str) -> None:
    op.execute(
        f"""
        ALTER TABLE {table_name}
        ALTER COLUMN {column_name} TYPE VARCHAR(255)
        USING CASE
            WHEN {column_name} IS NULL THEN NULL
            WHEN json_typeof({column_name}) = 'null' THEN NULL
            WHEN json_typeof({column_name}) = 'string' THEN {column_name} #>> '{{}}'
            WHEN json_typeof({column_name}) IN ('number', 'boolean') THEN {column_name}::text
            ELSE {column_name}::text
        END
        """
    )


def _downgrade_column(table_name: str, column_name: str) -> None:
    op.execute(
        f"""
        ALTER TABLE {table_name}
        ALTER COLUMN {column_name} TYPE JSON
        USING CASE
            WHEN {column_name} IS NULL THEN NULL
            ELSE to_json({column_name})::json
        END
        """
    )


def upgrade():
    for table_name in TABLES:
        for column_name in COLUMNS:
            _upgrade_column(table_name, column_name)


def downgrade():
    for table_name in TABLES:
        for column_name in COLUMNS:
            _downgrade_column(table_name, column_name)
