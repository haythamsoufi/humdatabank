"""Add custom_name_translations to assigned_form

Revision ID: add_custom_name_trans_af
Revises: add_custom_name_af
Create Date: 2026-06-19

"""
from alembic import op
import sqlalchemy as sa


revision = "add_custom_name_trans_af"
down_revision = "add_custom_name_af"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("assigned_form", schema=None) as batch_op:
        batch_op.add_column(sa.Column("custom_name_translations", sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table("assigned_form", schema=None) as batch_op:
        batch_op.drop_column("custom_name_translations")
