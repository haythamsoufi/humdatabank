"""Normalize legacy retrying email delivery logs to failed

Automatic email retries were removed; stale ``retrying`` rows are failed.

Revision ID: normalize_email_retrying
Revises: add_email_delivery_log_fk_idx
Create Date: 2026-06-28
"""

from alembic import op


revision = 'normalize_email_retrying'
down_revision = 'add_email_delivery_log_fk_idx'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        UPDATE email_delivery_log
        SET status = 'failed',
            next_retry_at = NULL
        WHERE status = 'retrying'
        """
    )


def downgrade():
    pass
