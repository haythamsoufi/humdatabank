"""Remove usage_count from indicator_bank

Revision ID: remove_usage_count
Revises: add_profile_picture_url
Create Date: 2025-01-27 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'remove_usage_count'
down_revision = 'add_profile_picture_url'
branch_labels = None
depends_on = None


def upgrade():
    # Drop the index first
    with op.batch_alter_table('indicator_bank', schema=None) as batch_op:
        batch_op.drop_index('ix_indicator_bank_usage_count')

    # Drop the usage_count column
    op.drop_column('indicator_bank', 'usage_count')


def downgrade():
    # Re-add the usage_count column
    op.add_column('indicator_bank', sa.Column('usage_count', sa.Integer(), nullable=False, server_default='0'))

    # Re-create the index
    with op.batch_alter_table('indicator_bank', schema=None) as batch_op:
        batch_op.create_index('ix_indicator_bank_usage_count', ['usage_count'], unique=False)
