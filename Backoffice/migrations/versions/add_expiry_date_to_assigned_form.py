"""add expiry_date to assigned_form

Revision ID: add_expiry_af
Revises: add_is_closed_af
Create Date: 2026-02-02

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_expiry_af'
down_revision = 'add_is_closed_af'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('assigned_form', schema=None) as batch_op:
        batch_op.add_column(sa.Column('expiry_date', sa.Date(), nullable=True))


def downgrade():
    with op.batch_alter_table('assigned_form', schema=None) as batch_op:
        batch_op.drop_column('expiry_date')
