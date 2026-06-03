"""Add created_at and created_by_user_id audit columns to form_data (F6)

Revision ID: add_form_data_created_audit
Revises: add_disagg_data_structure_checks
Create Date: 2026-06-02
"""

from alembic import op
import sqlalchemy as sa


revision = 'add_form_data_created_audit'
down_revision = 'add_disagg_data_structure_checks'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('form_data', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('created_by_user_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_form_data_created_by_user_id',
            'user',
            ['created_by_user_id'],
            ['id'],
            ondelete='SET NULL',
        )
        batch_op.create_index('ix_form_data_created_by', ['created_by_user_id'], unique=False)


def downgrade():
    with op.batch_alter_table('form_data', schema=None) as batch_op:
        batch_op.drop_index('ix_form_data_created_by')
        batch_op.drop_constraint('fk_form_data_created_by_user_id', type_='foreignkey')
        batch_op.drop_column('created_by_user_id')
        batch_op.drop_column('created_at')
