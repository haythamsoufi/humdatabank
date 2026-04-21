"""Add progress_steps JSON column to ai_reasoning_traces.

Stores the ordered list of user-visible progress labels emitted by the agent
during a run (e.g. "Preparing query…", "Planning approach…", "Drafting answer…").
These are distinct from the ReAct-loop reasoning steps and are useful for
AI review of the full agent pipeline.

Revision ID: add_progress_steps_trace
Revises: 8e2a9c1f4b0d
Create Date: 2026-04-11
"""
from alembic import op
import sqlalchemy as sa


revision = "add_progress_steps_trace"
down_revision = "8e2a9c1f4b0d"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "ai_reasoning_traces",
        sa.Column("progress_steps", sa.JSON(), nullable=True),
    )


def downgrade():
    op.drop_column("ai_reasoning_traces", "progress_steps")
