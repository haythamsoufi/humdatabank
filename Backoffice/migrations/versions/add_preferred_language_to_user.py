"""Add preferred_language to user

Revision ID: add_user_preferred_language
Revises: rename_notif_rbac_comm
Create Date: 2026-07-01 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'add_user_preferred_language'
down_revision = 'rename_notif_rbac_comm'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'user',
        sa.Column('preferred_language', sa.String(length=10), nullable=True, server_default='en'),
    )


def downgrade():
    op.drop_column('user', 'preferred_language')
