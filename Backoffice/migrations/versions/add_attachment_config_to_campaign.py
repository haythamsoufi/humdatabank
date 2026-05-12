"""Add attachment_config to notification_campaign

Revision ID: add_attachment_config
Revises: add_entity_based_campaigns
Create Date: 2025-02-03

Adds attachment_config JSON field for entity-based campaigns:
- static_attachments: list of {filename, content_base64, content_type}
- assignment_pdf_assigned_form_id: optional assigned form ID for per-entity PDF
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'add_attachment_config'
down_revision = 'add_expiry_af'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'notification_campaign',
        sa.Column('attachment_config', postgresql.JSON(astext_type=sa.Text()), nullable=True)
    )


def downgrade():
    op.drop_column('notification_campaign', 'attachment_config')
