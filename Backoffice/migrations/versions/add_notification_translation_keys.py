"""Add translation keys to notifications

Revision ID: add_notif_i18n_keys
Revises: add_logged_out_at
Create Date: 2025-01-28 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_notif_i18n_keys'
down_revision = 'add_logged_out_at'
branch_labels = None
depends_on = None


def upgrade():
    # Add translation key columns to notification table
    # These are nullable to maintain backward compatibility with existing notifications
    op.add_column('notification', sa.Column('title_key', sa.String(length=255), nullable=True))
    op.add_column('notification', sa.Column('title_params', postgresql.JSON(astext_type=sa.Text()), nullable=True))
    op.add_column('notification', sa.Column('message_key', sa.String(length=255), nullable=True))
    op.add_column('notification', sa.Column('message_params', postgresql.JSON(astext_type=sa.Text()), nullable=True))


def downgrade():
    # Remove translation key columns
    op.drop_column('notification', 'message_params')
    op.drop_column('notification', 'message_key')
    op.drop_column('notification', 'title_params')
    op.drop_column('notification', 'title_key')
