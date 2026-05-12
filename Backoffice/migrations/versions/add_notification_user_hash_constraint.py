"""ensure notification hash uniqueness per user

Revision ID: add_notif_hash_constraint
Revises: add_org_translation_fields
Create Date: 2025-12-24 00:00:00.000000
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'add_notif_hash_constraint'
down_revision = 'add_org_translation_fields'
branch_labels = None
depends_on = None


def upgrade():
    # Remove duplicate notification rows keeping the newest (highest id) record.
    # First, delete related email_delivery_log records to avoid foreign key violations
    op.execute(
        """
        DELETE FROM email_delivery_log
        WHERE notification_id IN (
            SELECT id FROM (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY user_id, notification_hash
                        ORDER BY id DESC
                    ) AS rn
                FROM notification
                WHERE notification_hash IS NOT NULL
            ) dup
            WHERE dup.rn > 1
        )
        """
    )

    # Now delete the duplicate notifications
    op.execute(
        """
        DELETE FROM notification
        WHERE id IN (
            SELECT id FROM (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY user_id, notification_hash
                        ORDER BY id DESC
                    ) AS rn
                FROM notification
                WHERE notification_hash IS NOT NULL
            ) dup
            WHERE dup.rn > 1
        )
        """
    )

    op.create_unique_constraint(
        'uq_notification_user_hash',
        'notification',
        ['user_id', 'notification_hash']
    )


def downgrade():
    op.drop_constraint('uq_notification_user_hash', 'notification', type_='unique')
