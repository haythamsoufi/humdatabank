"""Add last_digest_sent_at to notification_preferences for digest idempotency

Revision ID: add_digest_idempotency
Revises: drop_ib_steward_table
Create Date: 2026-02-27

Adds a timestamp column used as a "claim" marker so that concurrent scheduler
workers do not double-send digest emails to the same user within the same window.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_digest_idempotency'
down_revision = 'drop_ib_steward_table'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('notification_preferences', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('last_digest_sent_at', sa.DateTime(), nullable=True)
        )


def downgrade():
    with op.batch_alter_table('notification_preferences', schema=None) as batch_op:
        batch_op.drop_column('last_digest_sent_at')
