"""Add activated_by_user_id and deactivated_by_user_id to assigned_form

Revision ID: add_activation_audit_af
Revises: add_accountability_aes
Create Date: 2026-02-23

"""
from alembic import op
import sqlalchemy as sa


revision = "add_activation_audit_af"
down_revision = "add_accountability_aes"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("assigned_form", schema=None) as batch_op:
        batch_op.add_column(sa.Column("activated_by_user_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("deactivated_by_user_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_af_activated_by_user",
            "user",
            ["activated_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_af_deactivated_by_user",
            "user",
            ["deactivated_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_assigned_form_activated_by", ["activated_by_user_id"])
        batch_op.create_index("ix_assigned_form_deactivated_by", ["deactivated_by_user_id"])


def downgrade():
    with op.batch_alter_table("assigned_form", schema=None) as batch_op:
        batch_op.drop_index("ix_assigned_form_deactivated_by")
        batch_op.drop_index("ix_assigned_form_activated_by")
        batch_op.drop_constraint("fk_af_deactivated_by_user", type_="foreignkey")
        batch_op.drop_constraint("fk_af_activated_by_user", type_="foreignkey")
        batch_op.drop_column("deactivated_by_user_id")
        batch_op.drop_column("activated_by_user_id")
