"""Add opaque external_id (UUID) to user for client-visible references.

Revision ID: add_user_external_id
Revises: ai_trace_diagnostics_v1
Create Date: 2026-04-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "add_user_external_id"
down_revision = "ai_trace_diagnostics_v1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "user",
        sa.Column("external_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(sa.text('UPDATE "user" SET external_id = gen_random_uuid() WHERE external_id IS NULL'))
    op.alter_column("user", "external_id", nullable=False)
    op.create_index("uq_user_external_id", "user", ["external_id"], unique=True)


def downgrade():
    op.drop_index("uq_user_external_id", table_name="user")
    op.drop_column("user", "external_id")
