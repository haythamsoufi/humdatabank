"""Link API usage to keys; record who revoked a key

Revision ID: add_api_key_audit_usage_link
Revises: add_perf_indexes_dashboard
Create Date: 2026-05-31

"""
from alembic import op
import sqlalchemy as sa


revision = 'add_api_key_audit_usage_link'
down_revision = 'add_perf_indexes_dashboard'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('api_keys', schema=None) as batch_op:
        batch_op.add_column(sa.Column('revoked_by_user_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_api_keys_revoked_by_user_id',
            'user',
            ['revoked_by_user_id'],
            ['id'],
        )

    with op.batch_alter_table('api_usage', schema=None) as batch_op:
        batch_op.add_column(sa.Column('api_key_id', sa.Integer(), nullable=True))
        batch_op.create_index('ix_api_usage_api_key_id', ['api_key_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_api_usage_api_key_id',
            'api_keys',
            ['api_key_id'],
            ['id'],
        )


def downgrade():
    with op.batch_alter_table('api_usage', schema=None) as batch_op:
        batch_op.drop_constraint('fk_api_usage_api_key_id', type_='foreignkey')
        batch_op.drop_index('ix_api_usage_api_key_id')
        batch_op.drop_column('api_key_id')

    with op.batch_alter_table('api_keys', schema=None) as batch_op:
        batch_op.drop_constraint('fk_api_keys_revoked_by_user_id', type_='foreignkey')
        batch_op.drop_column('revoked_by_user_id')
