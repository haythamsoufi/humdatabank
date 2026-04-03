"""Add LLM quality judge columns to ai_reasoning_traces

Stores results from the LLM-as-judge evaluation: overall quality score,
verdict, reasoning text, and a flag for human review.

Revision ID: add_llm_quality_judge
Revises: add_original_query_trace
Create Date: 2026-03-16

"""

from alembic import op
import sqlalchemy as sa


revision = "add_llm_quality_judge"
down_revision = "add_original_query_trace"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "ai_reasoning_traces",
        sa.Column("llm_quality_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "ai_reasoning_traces",
        sa.Column("llm_quality_verdict", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "ai_reasoning_traces",
        sa.Column("llm_quality_reasoning", sa.Text(), nullable=True),
    )
    op.add_column(
        "ai_reasoning_traces",
        sa.Column("llm_needs_review", sa.Boolean(), nullable=True),
    )


def downgrade():
    op.drop_column("ai_reasoning_traces", "llm_needs_review")
    op.drop_column("ai_reasoning_traces", "llm_quality_reasoning")
    op.drop_column("ai_reasoning_traces", "llm_quality_verdict")
    op.drop_column("ai_reasoning_traces", "llm_quality_score")
