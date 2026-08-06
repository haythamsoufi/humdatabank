"""Add separate in-app notification type preferences.

Revision ID: add_in_app_notif_types
Revises: multi_submission_review_recipients
Create Date: 2026-08-06

"""
from alembic import op
import sqlalchemy as sa


revision = 'add_in_app_notif_types'
down_revision = 'multi_submission_review_recipients'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('notification_preferences', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'in_app_notification_types_enabled',
                sa.JSON(),
                nullable=False,
                server_default='[]',
            )
        )

    # Preserve legacy behaviour: explicit email lists previously gated in-app too.
    op.execute(
        """
        UPDATE notification_preferences
        SET in_app_notification_types_enabled = notification_types_enabled
        WHERE notification_types_enabled IS NOT NULL
          AND jsonb_array_length(notification_types_enabled::jsonb) > 0
        """
    )


def downgrade():
    with op.batch_alter_table('notification_preferences', schema=None) as batch_op:
        batch_op.drop_column('in_app_notification_types_enabled')
