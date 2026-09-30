"""Add auth_state_entry: shared TTL state for refresh-token reuse detection and auth limits.

Revision ID: add_auth_state_entry
Revises: add_submitted_document_public_id
Create Date: 2026-09-29

Consumed mobile refresh-token JTIs, revoked token families/sessions, single-use mobile
OAuth authorization codes, login-failure counters and security-critical rate-limit
buckets were held in per-process memory, so every Gunicorn worker (and every restart)
saw a different view. This table is the shared fallback when Redis is not configured.
Rows are TTL-bound and purged opportunistically by the application.
"""

from alembic import op
import sqlalchemy as sa


revision = "add_auth_state_entry"
down_revision = "add_submitted_document_public_id"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "auth_state_entry",
        sa.Column("namespace", sa.String(length=32), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("counter", sa.Integer(), server_default="0", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("namespace", "key"),
    )
    op.create_index("ix_auth_state_entry_expires_at", "auth_state_entry", ["expires_at"])


def downgrade():
    op.drop_index("ix_auth_state_entry_expires_at", table_name="auth_state_entry")
    op.drop_table("auth_state_entry")
