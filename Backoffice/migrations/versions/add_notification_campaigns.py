"""Add notification campaigns

Revision ID: add_notification_campaigns
Revises: add_notif_ux_enhancements
Create Date: 2025-01-XX XX:XX:XX.XXXXXX

This migration adds:
1. notification_campaign table for creating and managing notification campaigns
2. Campaigns can be scheduled, saved as drafts, and reused
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'add_notification_campaigns'
down_revision = 'add_notif_ux_enhancements'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('notification_campaign',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('priority', sa.String(length=20), nullable=False, server_default='normal'),
        sa.Column('category', sa.String(length=50), nullable=True),
        sa.Column('tags', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('send_email', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('send_push', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('override_preferences', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('redirect_type', sa.String(length=20), nullable=True),
        sa.Column('redirect_url', sa.String(length=500), nullable=True),
        sa.Column('scheduled_for', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='draft'),
        sa.Column('user_selection_type', sa.String(length=20), nullable=False, server_default='manual'),
        sa.Column('user_ids', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('user_filters', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('sent_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_count', sa.Integer(), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['created_by'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes
    op.create_index('ix_campaign_status', 'notification_campaign', ['status'])
    op.create_index('ix_campaign_scheduled', 'notification_campaign', ['scheduled_for'])
    op.create_index('ix_campaign_created_by', 'notification_campaign', ['created_by'])
    op.create_index('ix_campaign_created_at', 'notification_campaign', ['created_at'])


def downgrade():
    # Drop indexes
    op.drop_index('ix_campaign_created_at', table_name='notification_campaign')
    op.drop_index('ix_campaign_created_by', table_name='notification_campaign')
    op.drop_index('ix_campaign_scheduled', table_name='notification_campaign')
    op.drop_index('ix_campaign_status', table_name='notification_campaign')

    # Drop table
    op.drop_table('notification_campaign')
