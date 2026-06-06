"""Add follow-up question linkage on validation_question.

Revision ID: add_vq_follow_up
Revises: add_vq_lifecycle_ts
Create Date: 2026-06-06
"""
from alembic import op
import sqlalchemy as sa


revision = "add_vq_follow_up"
down_revision = "add_vq_lifecycle_ts"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "validation_question",
        sa.Column("parent_question_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "validation_question",
        sa.Column("follow_up_round", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_foreign_key(
        "fk_validation_question_parent",
        "validation_question",
        "validation_question",
        ["parent_question_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_validation_question_parent_question_id",
        "validation_question",
        ["parent_question_id"],
    )


def downgrade():
    op.drop_index("ix_validation_question_parent_question_id", table_name="validation_question")
    op.drop_constraint("fk_validation_question_parent", "validation_question", type_="foreignkey")
    op.drop_column("validation_question", "follow_up_round")
    op.drop_column("validation_question", "parent_question_id")
