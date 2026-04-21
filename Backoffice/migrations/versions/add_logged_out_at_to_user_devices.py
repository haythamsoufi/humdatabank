"""Add logged_out_at to user_devices

Revision ID: add_logged_out_at
Revises: add_access_request_received
Create Date: 2025-11-21 20:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_logged_out_at'
down_revision = 'add_access_request_received'
branch_labels = None
depends_on = None


def upgrade():
    # Add logged_out_at column to user_devices table
    op.add_column('user_devices', sa.Column('logged_out_at', sa.DateTime(), nullable=True))


def downgrade():
    # Remove logged_out_at column
    op.drop_column('user_devices', 'logged_out_at')
