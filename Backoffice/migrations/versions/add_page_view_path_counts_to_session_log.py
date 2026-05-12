"""Add page_view_path_counts JSON to user_session_log

Revision ID: add_page_view_path_counts
Revises: add_embed_content_table
Create Date: 2026-04-15
"""

from alembic import op
import sqlalchemy as sa


revision = "add_page_view_path_counts"
down_revision = "add_embed_content_table"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "user_session_log",
        sa.Column("page_view_path_counts", sa.JSON(), nullable=True),
    )


def downgrade():
    op.drop_column("user_session_log", "page_view_path_counts")
