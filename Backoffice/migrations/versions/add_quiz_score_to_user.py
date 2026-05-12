"""Add quiz_score to user

Revision ID: add_quiz_score
Revises: add_logged_out_at
Create Date: 2025-01-15 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_quiz_score'
down_revision = 'notif_entity_scope'
branch_labels = None
depends_on = None


def upgrade():
    # Add quiz_score column to user table with default value of 0
    op.add_column('user', sa.Column('quiz_score', sa.Integer(), nullable=False, server_default='0'))


def downgrade():
    # Remove quiz_score column
    op.drop_column('user', 'quiz_score')
