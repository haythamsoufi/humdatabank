"""add is_closed to assigned_form

Revision ID: add_is_closed_af
Revises: add_is_active_af
Create Date: 2026-02-02

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_is_closed_af'
down_revision = 'add_is_active_af'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('assigned_form', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_closed', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    with op.batch_alter_table('assigned_form', schema=None) as batch_op:
        batch_op.drop_column('is_closed')
