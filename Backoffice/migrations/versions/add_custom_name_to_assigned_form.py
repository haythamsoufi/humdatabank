"""Add custom_name to assigned_form

Revision ID: add_custom_name_af
Revises: add_dynamic_section_context
Create Date: 2026-06-19

"""
from alembic import op
import sqlalchemy as sa


revision = "add_custom_name_af"
down_revision = "add_dynamic_section_context"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("assigned_form", schema=None) as batch_op:
        batch_op.add_column(sa.Column("custom_name", sa.String(200), nullable=True))
        batch_op.create_index("ix_assigned_form_custom_name", ["custom_name"])


def downgrade():
    with op.batch_alter_table("assigned_form", schema=None) as batch_op:
        batch_op.drop_index("ix_assigned_form_custom_name")
        batch_op.drop_column("custom_name")
