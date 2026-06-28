"""Add email_delivery_log.notification_id index and ON DELETE CASCADE

Revision ID: add_email_delivery_log_fk_idx
Revises: add_stable_key_form_structure
Create Date: 2026-06-28
"""

from alembic import op


revision = 'add_email_delivery_log_fk_idx'
down_revision = 'add_stable_key_form_structure'
branch_labels = None
depends_on = None

_FK_NAME = 'email_delivery_log_notification_id_fkey'


def upgrade():
    op.create_index(
        'ix_email_delivery_notification',
        'email_delivery_log',
        ['notification_id'],
        unique=False,
    )
    op.drop_constraint(_FK_NAME, 'email_delivery_log', type_='foreignkey')
    op.create_foreign_key(
        _FK_NAME,
        'email_delivery_log',
        'notification',
        ['notification_id'],
        ['id'],
        ondelete='CASCADE',
    )


def downgrade():
    op.drop_constraint(_FK_NAME, 'email_delivery_log', type_='foreignkey')
    op.create_foreign_key(
        _FK_NAME,
        'email_delivery_log',
        'notification',
        ['notification_id'],
        ['id'],
    )
    op.drop_index('ix_email_delivery_notification', table_name='email_delivery_log')
