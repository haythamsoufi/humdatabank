"""Add access_request_received to notificationtype enum

Revision ID: add_access_request_received
Revises: 90aafe7711e0
Create Date: 2025-11-21 18:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_access_request_received'
down_revision = '90aafe7711e0'
branch_labels = None
depends_on = None


def upgrade():
    # Add the new enum value to the notificationtype enum
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'access_request_received'")


def downgrade():
    # Note: PostgreSQL doesn't support removing enum values directly
    # This would require recreating the enum type, which is complex
    # For now, we'll leave the enum value in place
    # If you need to remove it, you would need to:
    # 1. Create a new enum without the value
    # 2. Update all rows using the old value
    # 3. Drop the old enum and rename the new one
    pass
