"""Add notification system improvements

Revision ID: add_notification_improvements
Revises: add_logged_out_at_to_user_devices
Create Date: 2025-01-XX XX:XX:XX.XXXXXX

This migration adds:
1. consecutive_failures column to user_devices for push notification error recovery
2. timezone column to notification_preferences for timezone-aware email digests
3. Composite indexes on notification table for performance optimization
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_notification_improvements'
down_revision = 'add_notif_created_at_idx'
branch_labels = None
depends_on = None


def upgrade():
    # Add consecutive_failures to user_devices
    with op.batch_alter_table('user_devices', schema=None) as batch_op:
        batch_op.add_column(sa.Column('consecutive_failures', sa.Integer(), nullable=False, server_default='0'))

    # Add timezone to notification_preferences
    with op.batch_alter_table('notification_preferences', schema=None) as batch_op:
        batch_op.add_column(sa.Column('timezone', sa.String(length=50), nullable=True))

    # Add composite indexes on notification table
    with op.batch_alter_table('notification', schema=None) as batch_op:
        # Composite index for deduplication queries
        batch_op.create_index(
            'ix_notification_hash_user_time',
            ['notification_hash', 'user_id', 'created_at'],
            unique=False
        )
        # Composite index for common listing queries (user notifications with filters)
        batch_op.create_index(
            'ix_notification_user_read_archived_time',
            ['user_id', 'is_read', 'is_archived', 'created_at'],
            unique=False
        )


def downgrade():
    # Remove composite indexes
    with op.batch_alter_table('notification', schema=None) as batch_op:
        batch_op.drop_index('ix_notification_user_read_archived_time')
        batch_op.drop_index('ix_notification_hash_user_time')

    # Remove timezone column
    with op.batch_alter_table('notification_preferences', schema=None) as batch_op:
        batch_op.drop_column('timezone')

    # Remove consecutive_failures column
    with op.batch_alter_table('user_devices', schema=None) as batch_op:
        batch_op.drop_column('consecutive_failures')
