"""convert fds_member boolean to fds_member_user_id

Revision ID: convert_fds_member_to_user
Revises: add_fds_member_to_country
Create Date: 2026-06-08 21:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'convert_fds_member_to_user'
down_revision = 'add_fds_member_to_country'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('country', schema=None) as batch_op:
        batch_op.add_column(sa.Column('fds_member_user_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_country_fds_member_user_id',
            'user',
            ['fds_member_user_id'],
            ['id'],
        )
        batch_op.drop_column('fds_member')


def downgrade():
    with op.batch_alter_table('country', schema=None) as batch_op:
        batch_op.drop_constraint('fk_country_fds_member_user_id', type_='foreignkey')
        batch_op.drop_column('fds_member_user_id')
        batch_op.add_column(sa.Column('fds_member', sa.Boolean(), nullable=True))
