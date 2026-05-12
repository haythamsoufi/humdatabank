"""Add error_message to notification_campaign

Revision ID: add_campaign_error_message
Revises: add_notification_campaigns
Create Date: 2025-12-12
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_campaign_error_message'
down_revision = 'add_notification_campaigns'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('notification_campaign', sa.Column('error_message', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('notification_campaign', 'error_message')
