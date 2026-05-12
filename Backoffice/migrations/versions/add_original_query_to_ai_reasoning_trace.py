"""Add original_query to ai_reasoning_traces for user message before rewriting

Revision ID: add_original_query_trace
Revises: migrate_ivfflat_to_hnsw
Create Date: 2026-03-06

Stores the user's raw message when the agent receives a rewritten query, so
trace detail UI can show both "Original query" and "Query (as sent to agent)".
"""
from alembic import op
import sqlalchemy as sa


revision = "add_original_query_trace"
down_revision = "migrate_ivfflat_to_hnsw"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "ai_reasoning_traces",
        sa.Column("original_query", sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_column("ai_reasoning_traces", "original_query")
