"""Add notification UX enhancements

Revision ID: add_notif_ux_enhancements
Revises: add_notification_improvements
Create Date: 2025-01-XX XX:XX:XX.XXXXXX

This migration adds:
1. viewed_at column for read receipt/viewing tracking
2. category column for notification categorization
3. tags column (JSON) for flexible tagging
4. scheduled_for and sent_at columns for notification scheduling
5. Indexes for category and scheduling filtering
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'add_notif_ux_enhancements'
down_revision = 'add_notification_improvements'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('notification', schema=None) as batch_op:
        # Add viewing tracking
        batch_op.add_column(sa.Column('viewed_at', sa.DateTime(), nullable=True))

        # Add categorization
        batch_op.add_column(sa.Column('category', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('tags', postgresql.JSON(astext_type=sa.Text()), nullable=True))

        # Phase 5: Notification Scheduling
        batch_op.add_column(sa.Column('scheduled_for', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('sent_at', sa.DateTime(), nullable=True))

        # Add indexes
        batch_op.create_index('ix_notification_category', ['category'])
        batch_op.create_index('ix_notification_scheduled', ['scheduled_for'])


def downgrade():
    # Remove indexes
    with op.batch_alter_table('notification', schema=None) as batch_op:
        batch_op.drop_index('ix_notification_scheduled')
        batch_op.drop_index('ix_notification_category')

        # Remove columns
        batch_op.drop_column('sent_at')
        batch_op.drop_column('scheduled_for')
        batch_op.drop_column('tags')
        batch_op.drop_column('category')
        batch_op.drop_column('viewed_at')
