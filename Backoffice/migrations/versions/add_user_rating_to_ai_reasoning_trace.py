"""Add user_rating to ai_reasoning_traces for like/dislike feedback

Revision ID: add_user_rating_trace
Revises: add_ai_term_glossary
Create Date: 2026-02-20

"""

from alembic import op
import sqlalchemy as sa


revision = "add_user_rating_trace"
down_revision = "add_ai_term_glossary"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "ai_reasoning_traces",
        sa.Column("user_rating", sa.String(length=20), nullable=True),
    )
    op.create_index(
        "ix_ai_reasoning_traces_user_rating",
        "ai_reasoning_traces",
        ["user_rating"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_ai_reasoning_traces_user_rating", table_name="ai_reasoning_traces")
    op.drop_column("ai_reasoning_traces", "user_rating")
