"""Add user_session_id to user_activity_log for audit drill-down

Revision ID: add_user_session_id_activity_log
Revises: add_page_view_path_counts
Create Date: 2026-04-16
"""

from alembic import op
import sqlalchemy as sa


revision = "add_user_session_id_activity_log"
down_revision = "add_page_view_path_counts"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "user_activity_log",
        sa.Column("user_session_id", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_user_activity_log_user_session_id",
        "user_activity_log",
        ["user_session_id"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_user_activity_log_user_session_id", table_name="user_activity_log")
    op.drop_column("user_activity_log", "user_session_id")
