"""Add symmetric prefill, imputation, and audit columns to data tables

Revision ID: add_symmetric_data_table_columns
Revises: add_reporting_period_catalog
Create Date: 2026-06-03
"""

from alembic import op
import sqlalchemy as sa


revision = 'add_symmetric_data_table_columns'
down_revision = 'add_reporting_period_catalog'
branch_labels = None
depends_on = None

_TABLES = ('dynamic_indicator_data', 'repeat_group_data')


def upgrade():
    for table_name in _TABLES:
        with op.batch_alter_table(table_name, schema=None) as batch_op:
            batch_op.add_column(sa.Column('prefilled_value', sa.JSON(none_as_null=True), nullable=True))
            batch_op.add_column(sa.Column('prefilled_disagg_data', sa.JSON(none_as_null=True), nullable=True))
            batch_op.add_column(sa.Column('imputed_value', sa.JSON(none_as_null=True), nullable=True))
            batch_op.add_column(sa.Column('imputed_disagg_data', sa.JSON(none_as_null=True), nullable=True))
            batch_op.add_column(sa.Column('imputed_numeric_value', sa.Float(), nullable=True))
            batch_op.add_column(sa.Column('created_at', sa.DateTime(), nullable=True))
            batch_op.add_column(sa.Column('created_by_user_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                f'fk_{table_name}_created_by_user',
                'user',
                ['created_by_user_id'],
                ['id'],
                ondelete='SET NULL',
            )
            batch_op.create_index(f'ix_{table_name}_created_by', ['created_by_user_id'])

    op.execute(
        """
        UPDATE dynamic_indicator_data
        SET created_at = added_at
        WHERE created_at IS NULL
        """
    )
    op.execute(
        """
        UPDATE repeat_group_data
        SET created_at = submitted_at
        WHERE created_at IS NULL
        """
    )


def downgrade():
    for table_name in reversed(_TABLES):
        with op.batch_alter_table(table_name, schema=None) as batch_op:
            batch_op.drop_index(f'ix_{table_name}_created_by')
            batch_op.drop_constraint(f'fk_{table_name}_created_by_user', type_='foreignkey')
            batch_op.drop_column('created_by_user_id')
            batch_op.drop_column('created_at')
            batch_op.drop_column('imputed_numeric_value')
            batch_op.drop_column('imputed_disagg_data')
            batch_op.drop_column('imputed_value')
            batch_op.drop_column('prefilled_disagg_data')
            batch_op.drop_column('prefilled_value')
