"""Add profile_picture_url to user

Revision ID: add_profile_picture_url
Revises: add_quiz_score
Create Date: 2025-01-20 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_profile_picture_url'
down_revision = 'add_quiz_score'
branch_labels = None
depends_on = None


def upgrade():
    # Add profile_picture_url column to user table (nullable)
    op.add_column('user', sa.Column('profile_picture_url', sa.String(length=500), nullable=True))


def downgrade():
    # Remove profile_picture_url column
    op.drop_column('user', 'profile_picture_url')
