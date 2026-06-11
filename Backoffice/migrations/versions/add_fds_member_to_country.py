"""add fds_member to country

Revision ID: add_fds_member_to_country
Revises: add_vq_follow_up
Create Date: 2026-06-08 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_fds_member_to_country'
down_revision = 'add_vq_follow_up'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('country', schema=None) as batch_op:
        batch_op.add_column(sa.Column('fds_member', sa.Boolean(), nullable=True))


def downgrade():
    with op.batch_alter_table('country', schema=None) as batch_op:
        batch_op.drop_column('fds_member')
