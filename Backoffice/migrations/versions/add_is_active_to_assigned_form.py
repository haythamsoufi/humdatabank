"""add is_active to assigned_form

Revision ID: add_is_active_af
Revises: 2724a30cb756
Create Date: 2026-02-02

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_is_active_af'
down_revision = '2724a30cb756'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('assigned_form', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.create_index('ix_assigned_form_is_active', ['is_active'], unique=False)


def downgrade():
    with op.batch_alter_table('assigned_form', schema=None) as batch_op:
        batch_op.drop_index('ix_assigned_form_is_active', table_name='assigned_form')
        batch_op.drop_column('is_active')
