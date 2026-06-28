"""Add cancelled to emaildeliverystatus enum

Revision ID: add_email_delivery_cancelled
Revises: add_email_digest_nt
Create Date: 2026-06-28
"""

from alembic import op


revision = 'add_email_delivery_cancelled'
down_revision = 'add_email_digest_nt'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TYPE emaildeliverystatus ADD VALUE IF NOT EXISTS 'cancelled'")


def downgrade():
    pass
