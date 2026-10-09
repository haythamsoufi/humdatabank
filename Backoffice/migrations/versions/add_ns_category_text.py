"""Add category_text to national_societies

Revision ID: add_ns_category_text
Revises: split_explore_analysis_tabs
Create Date: 2026-10-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "add_ns_category_text"
down_revision = "split_explore_analysis_tabs"
branch_labels = None
depends_on = None


def upgrade():
    jsonb_type = postgresql.JSONB(astext_type=sa.Text())
    op.add_column(
        "national_societies",
        sa.Column("category_text", jsonb_type, nullable=True),
    )


def downgrade():
    op.drop_column("national_societies", "category_text")
