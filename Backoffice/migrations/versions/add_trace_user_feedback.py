"""Optional dislike comment on AI reasoning traces.

Revision ID: add_trace_user_feedback
Revises: add_aes_status_note
Create Date: 2026-11-25

Stored when a user explains what should be improved or corrected after a dislike.
"""
from alembic import op
import sqlalchemy as sa


revision = "add_trace_user_feedback"
down_revision = "add_aes_status_note"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "ai_reasoning_traces",
        sa.Column("user_feedback", sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_column("ai_reasoning_traces", "user_feedback")
