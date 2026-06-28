"""Add account_welcome to notificationtype enum

Revision ID: add_account_welcome_nt
Revises: normalize_email_retrying
Create Date: 2026-06-28
"""

from alembic import op


revision = 'add_account_welcome_nt'
down_revision = 'normalize_email_retrying'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'account_welcome'")


def downgrade():
    pass
