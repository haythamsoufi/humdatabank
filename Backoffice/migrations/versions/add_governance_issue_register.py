"""Add the governance issue register.

Revision ID: add_governance_issue
Revises: api_key_permissions_v2
Create Date: 2026-10-01

"""
from alembic import op
import sqlalchemy as sa


revision = "add_governance_issue"
down_revision = "api_key_permissions_v2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "governance_issue",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("control_code", sa.String(length=32), nullable=False),
        sa.Column("fingerprint", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("failing_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("opened_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("reopened_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("resolution", sa.String(length=40), nullable=True),
        sa.Column("accepted_by_user_id", sa.Integer(), nullable=True),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.Column("acceptance_reason", sa.Text(), nullable=True),
        sa.Column("accepted_until", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(
            ["accepted_by_user_id"],
            ["user.id"],
            name="fk_governance_issue_accepted_by",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("fingerprint", name="uq_governance_issue_fingerprint"),
    )
    op.create_index("ix_governance_issue_status", "governance_issue", ["status"])
    op.create_index("ix_governance_issue_control", "governance_issue", ["control_code"])


def downgrade():
    op.drop_index("ix_governance_issue_control", table_name="governance_issue")
    op.drop_index("ix_governance_issue_status", table_name="governance_issue")
    op.drop_table("governance_issue")
