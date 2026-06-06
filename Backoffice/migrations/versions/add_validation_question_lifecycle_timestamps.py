"""Add validation question lifecycle timestamp columns.

Revision ID: add_vq_lifecycle_ts
Revises: rename_non_zero_validation_rule
Create Date: 2026-06-06
"""
from alembic import op
import sqlalchemy as sa


revision = "add_vq_lifecycle_ts"
down_revision = "rename_non_zero_validation_rule"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("validation_question", sa.Column("drafted_at", sa.DateTime(), nullable=True))
    op.add_column("validation_question", sa.Column("answer_outcome", sa.String(length=32), nullable=True))
    op.add_column("validation_question", sa.Column("changes_made_approved_at", sa.DateTime(), nullable=True))
    op.add_column("validation_question", sa.Column("no_changes_approved_at", sa.DateTime(), nullable=True))

    op.execute(
        sa.text(
            """
            UPDATE validation_question
            SET drafted_at = asked_at
            WHERE drafted_at IS NULL
            """
        )
    )


def downgrade():
    op.drop_column("validation_question", "no_changes_approved_at")
    op.drop_column("validation_question", "changes_made_approved_at")
    op.drop_column("validation_question", "answer_outcome")
    op.drop_column("validation_question", "drafted_at")
