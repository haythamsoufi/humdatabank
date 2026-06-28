"""Add email_digest to notificationtype enum

Revision ID: add_email_digest_nt
Revises: add_account_welcome_nt
Create Date: 2026-06-28
"""

from alembic import op


revision = 'add_email_digest_nt'
down_revision = 'add_account_welcome_nt'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'email_digest'")


def downgrade():
    pass
