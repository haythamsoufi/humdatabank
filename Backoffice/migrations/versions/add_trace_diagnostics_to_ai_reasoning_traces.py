"""Add trace_diagnostics JSON on ai_reasoning_traces

Extensible JSON for optional debugging and persistence context (e.g.
``user_attribution`` when user_id is missing, plus room for future keys).

Revision ID: ai_trace_diagnostics_v1
Revises: add_ns_indicator_bank_unit
Create Date: 2026-04-28
"""

from alembic import op
import sqlalchemy as sa


revision = "ai_trace_diagnostics_v1"
down_revision = "add_ns_indicator_bank_unit"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "ai_reasoning_traces",
        sa.Column("trace_diagnostics", sa.JSON(), nullable=True),
    )


def downgrade():
    op.drop_column("ai_reasoning_traces", "trace_diagnostics")
