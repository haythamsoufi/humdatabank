"""Add cancelled to aireasoningtracestatus enum

User Stop used to finish the in-flight run and store it as completed, because
``cancelled`` was not a persisted trace status.

Revision ID: add_cancelled_aireasoningtracestatus
Revises: enable_fdrs_document_period_reuse
Create Date: 2026-11-10

"""
from alembic import op


revision = "add_cancelled_aireasoningtracestatus"
down_revision = "enable_fdrs_document_period_reuse"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TYPE aireasoningtracestatus ADD VALUE IF NOT EXISTS 'cancelled'"
    )


def downgrade():
    # PostgreSQL cannot drop individual enum values without recreating the type.
    pass
