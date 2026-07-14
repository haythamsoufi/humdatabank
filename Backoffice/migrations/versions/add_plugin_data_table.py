"""Add plugin_data table for per-plugin JSON config/state

Revision ID: add_plugin_data_table
Revises: drop_ib_related_programs_text
Create Date: 2026-07-11
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "add_plugin_data_table"
down_revision = "drop_ib_related_programs_text"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "plugin_data",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plugin_id", sa.String(length=100), nullable=False),
        sa.Column(
            "data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_plugin_data_plugin_id", "plugin_data", ["plugin_id"], unique=True)


def downgrade():
    op.drop_index("ix_plugin_data_plugin_id", table_name="plugin_data")
    op.drop_table("plugin_data")
