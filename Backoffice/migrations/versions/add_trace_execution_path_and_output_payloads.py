"""Add execution_path and output_payloads to ai_reasoning_traces for improved analytics

Revision ID: add_trace_exec_path_payloads
Revises: add_ai_jobs_tables
Create Date: 2026-02-22

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "add_trace_exec_path_payloads"
down_revision = "add_ai_jobs_tables"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "ai_reasoning_traces",
        sa.Column("execution_path", sa.String(length=50), nullable=True),
    )
    op.create_index(
        "ix_ai_reasoning_traces_execution_path",
        "ai_reasoning_traces",
        ["execution_path"],
        unique=False,
    )
    # output_payloads: map_payload, chart_payload, answer_content, output_hint, plan_kind
    op.add_column(
        "ai_reasoning_traces",
        sa.Column("output_payloads", postgresql.JSON(astext_type=sa.Text()), nullable=True),
    )


def downgrade():
    op.drop_column("ai_reasoning_traces", "output_payloads")
    op.drop_index("ix_ai_reasoning_traces_execution_path", table_name="ai_reasoning_traces")
    op.drop_column("ai_reasoning_traces", "execution_path")
