"""Add data_owner_id to assigned_form for assignment-level data ownership governance

Revision ID: add_data_owner_af
Revises: add_activation_audit_af
Create Date: 2026-02-23

"""
from alembic import op
import sqlalchemy as sa


revision = "add_data_owner_af"
down_revision = "add_activation_audit_af"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("assigned_form", schema=None) as batch_op:
        batch_op.add_column(sa.Column("data_owner_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_af_data_owner_user",
            "user",
            ["data_owner_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_assigned_form_data_owner", ["data_owner_id"])


def downgrade():
    with op.batch_alter_table("assigned_form", schema=None) as batch_op:
        batch_op.drop_index("ix_assigned_form_data_owner")
        batch_op.drop_constraint("fk_af_data_owner_user", type_="foreignkey")
        batch_op.drop_column("data_owner_id")
