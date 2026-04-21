"""Add entity-based campaign support

Revision ID: add_entity_based_campaigns
Revises: add_campaign_error_message
Create Date: 2025-01-XX XX:XX:XX.XXXXXX

This migration adds:
1. entity_selection field to notification_campaign for entity-based campaigns
2. email_distribution_rules field to configure To/CC distribution for IFRC vs non-IFRC contacts
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'add_entity_based_campaigns'
down_revision = 'add_campaign_error_message'
branch_labels = None
depends_on = None


def upgrade():
    # Add entity-based campaign fields
    op.add_column('notification_campaign',
        sa.Column('entity_selection', postgresql.JSON(astext_type=sa.Text()), nullable=True)
    )
    op.add_column('notification_campaign',
        sa.Column('email_distribution_rules', postgresql.JSON(astext_type=sa.Text()), nullable=True)
    )

    # Update user_selection_type to allow 'entity' value
    # Note: This is just a data change, the column already exists with length 20 which is sufficient


def downgrade():
    # Remove entity-based campaign fields
    op.drop_column('notification_campaign', 'email_distribution_rules')
    op.drop_column('notification_campaign', 'entity_selection')
