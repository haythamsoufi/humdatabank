"""add reopened_after_close to assignment_entity_status

Revision ID: add_aes_reopened_after_close
Revises: fdrs_submitted_doc_metadata
Create Date: 2026-06-06
"""
from alembic import op
import sqlalchemy as sa


revision = "add_aes_reopened_after_close"
down_revision = "fdrs_submitted_doc_metadata"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "assignment_entity_status",
        sa.Column("reopened_after_close", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade():
    op.drop_column("assignment_entity_status", "reopened_after_close")
