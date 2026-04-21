"""add_fdrs_kpi_code_to_indicator_bank

Revision ID: 1680ccc4c512
Revises: add_form_data_prefilled_imputed_disagg_data
Create Date: 2026-02-12 22:27:18.375568

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1680ccc4c512'
down_revision = 'add_form_data_prefilled_imputed_disagg_data'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('indicator_bank', schema=None) as batch_op:
        batch_op.add_column(sa.Column('fdrs_kpi_code', sa.String(length=50), nullable=True))

    with op.batch_alter_table('indicator_bank_history', schema=None) as batch_op:
        batch_op.add_column(sa.Column('fdrs_kpi_code', sa.String(length=50), nullable=True))


def downgrade():
    with op.batch_alter_table('indicator_bank_history', schema=None) as batch_op:
        batch_op.drop_column('fdrs_kpi_code')

    with op.batch_alter_table('indicator_bank', schema=None) as batch_op:
        batch_op.drop_column('fdrs_kpi_code')
