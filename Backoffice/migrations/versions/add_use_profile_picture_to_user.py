"""Add use_profile_picture to user

Revision ID: add_use_profile_picture
Revises: add_profile_picture_url
Create Date: 2025-01-25 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_use_profile_picture'
down_revision = 'rename_form_item_id'
branch_labels = None
depends_on = None


def upgrade():
    # Add use_profile_picture column to user table with default value of True
    op.add_column('user', sa.Column('use_profile_picture', sa.Boolean(), nullable=False, server_default='true'))


def downgrade():
    # Remove use_profile_picture column
    op.drop_column('user', 'use_profile_picture')
