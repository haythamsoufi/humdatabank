"""Add submitted_by_user_id and approved_by_user_id to assignment_entity_status

Revision ID: add_accountability_aes
Revises: add_trace_exec_path_payloads
Create Date: 2026-02-23

"""
from alembic import op
import sqlalchemy as sa


revision = "add_accountability_aes"
down_revision = "add_trace_exec_path_payloads"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("assignment_entity_status", schema=None) as batch_op:
        batch_op.add_column(sa.Column("submitted_by_user_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("approved_by_user_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_aes_submitted_by_user",
            "user",
            ["submitted_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_aes_approved_by_user",
            "user",
            ["approved_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_aes_submitted_by", ["submitted_by_user_id"])
        batch_op.create_index("ix_aes_approved_by", ["approved_by_user_id"])


def downgrade():
    with op.batch_alter_table("assignment_entity_status", schema=None) as batch_op:
        batch_op.drop_index("ix_aes_approved_by")
        batch_op.drop_index("ix_aes_submitted_by")
        batch_op.drop_constraint("fk_aes_approved_by_user", type_="foreignkey")
        batch_op.drop_constraint("fk_aes_submitted_by_user", type_="foreignkey")
        batch_op.drop_column("approved_by_user_id")
        batch_op.drop_column("submitted_by_user_id")
