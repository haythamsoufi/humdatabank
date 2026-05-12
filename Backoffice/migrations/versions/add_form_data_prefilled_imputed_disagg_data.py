"""Add prefilled/imputed disaggregation fields to form_data

Revision ID: add_form_data_prefilled_imputed_disagg_data
Revises: add_indicator_bank_embeddings
Create Date: 2026-02-12

Adds:
- form_data.prefilled_disagg_data
- form_data.imputed_disagg_data

These correspond to form_data.disagg_data in the same way prefilled_value/imputed_value correspond to value.
"""

from alembic import op
import sqlalchemy as sa


revision = "add_form_data_prefilled_imputed_disagg_data"
down_revision = "add_indicator_bank_embeddings"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("form_data", sa.Column("prefilled_disagg_data", sa.JSON(), nullable=True))
    op.add_column("form_data", sa.Column("imputed_disagg_data", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("form_data", "imputed_disagg_data")
    op.drop_column("form_data", "prefilled_disagg_data")

