"""Add API key management tables

Revision ID: add_api_key_management
Revises: template_version_details
Create Date: 2025-01-28 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_api_key_management'
down_revision = 'template_version_details'
branch_labels = None
depends_on = None


def upgrade():
    # Create api_keys table
    op.create_table('api_keys',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('key_id', sa.String(length=32), nullable=False),
    sa.Column('key_hash', sa.String(length=128), nullable=False),
    sa.Column('key_prefix', sa.String(length=8), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('client_name', sa.String(length=255), nullable=False),
    sa.Column('client_description', sa.Text(), nullable=True),
    sa.Column('permissions', postgresql.JSON(astext_type=sa.Text()), nullable=True),
    sa.Column('rate_limit_per_minute', sa.Integer(), nullable=False, server_default='60'),
    sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
    sa.Column('is_revoked', sa.Boolean(), nullable=False, server_default='false'),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=True),
    sa.Column('last_used_at', sa.DateTime(), nullable=True),
    sa.Column('revoked_at', sa.DateTime(), nullable=True),
    sa.Column('created_by_user_id', sa.Integer(), nullable=True),
    sa.Column('revocation_reason', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('key_id'),
    sa.UniqueConstraint('key_hash')
    )

    # Create indexes for api_keys
    op.create_index('ix_api_key_user_active', 'api_keys', ['user_id', 'is_active'], unique=False)
    op.create_index('ix_api_key_prefix_active', 'api_keys', ['key_prefix', 'is_active'], unique=False)
    op.create_index('ix_api_key_expires', 'api_keys', ['expires_at'], unique=False)
    op.create_index(op.f('ix_api_keys_created_at'), 'api_keys', ['created_at'], unique=False)
    op.create_index(op.f('ix_api_keys_is_active'), 'api_keys', ['is_active'], unique=False)
    op.create_index(op.f('ix_api_keys_is_revoked'), 'api_keys', ['is_revoked'], unique=False)
    op.create_index(op.f('ix_api_keys_key_id'), 'api_keys', ['key_id'], unique=True)
    op.create_index(op.f('ix_api_keys_key_prefix'), 'api_keys', ['key_prefix'], unique=False)
    op.create_index(op.f('ix_api_keys_last_used_at'), 'api_keys', ['last_used_at'], unique=False)

    # Create api_key_usage table
    op.create_table('api_key_usage',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('api_key_id', sa.Integer(), nullable=False),
    sa.Column('endpoint', sa.String(length=255), nullable=False),
    sa.Column('method', sa.String(length=10), nullable=False),
    sa.Column('ip_address', sa.String(length=45), nullable=False),
    sa.Column('user_agent', sa.String(length=500), nullable=True),
    sa.Column('status_code', sa.Integer(), nullable=False),
    sa.Column('response_time_ms', sa.Float(), nullable=False),
    sa.Column('timestamp', sa.DateTime(), nullable=False),
    sa.Column('request_data', postgresql.JSON(astext_type=sa.Text()), nullable=True),
    sa.ForeignKeyConstraint(['api_key_id'], ['api_keys.id'], ),
    sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for api_key_usage
    op.create_index('ix_api_key_usage_timestamp', 'api_key_usage', ['timestamp'], unique=False)
    op.create_index('ix_api_key_usage_key_timestamp', 'api_key_usage', ['api_key_id', 'timestamp'], unique=False)
    op.create_index(op.f('ix_api_key_usage_api_key_id'), 'api_key_usage', ['api_key_id'], unique=False)
    op.create_index(op.f('ix_api_key_usage_endpoint'), 'api_key_usage', ['endpoint'], unique=False)
    op.create_index(op.f('ix_api_key_usage_ip_address'), 'api_key_usage', ['ip_address'], unique=False)


def downgrade():
    # Drop indexes for api_key_usage
    op.drop_index(op.f('ix_api_key_usage_ip_address'), table_name='api_key_usage')
    op.drop_index(op.f('ix_api_key_usage_endpoint'), table_name='api_key_usage')
    op.drop_index(op.f('ix_api_key_usage_api_key_id'), table_name='api_key_usage')
    op.drop_index('ix_api_key_usage_key_timestamp', table_name='api_key_usage')
    op.drop_index('ix_api_key_usage_timestamp', table_name='api_key_usage')

    # Drop api_key_usage table
    op.drop_table('api_key_usage')

    # Drop indexes for api_keys
    op.drop_index(op.f('ix_api_keys_last_used_at'), table_name='api_keys')
    op.drop_index(op.f('ix_api_keys_key_prefix'), table_name='api_keys')
    op.drop_index(op.f('ix_api_keys_key_id'), table_name='api_keys')
    op.drop_index(op.f('ix_api_keys_is_revoked'), table_name='api_keys')
    op.drop_index(op.f('ix_api_keys_is_active'), table_name='api_keys')
    op.drop_index(op.f('ix_api_keys_created_at'), table_name='api_keys')
    op.drop_index('ix_api_key_expires', table_name='api_keys')
    op.drop_index('ix_api_key_prefix_active', table_name='api_keys')
    op.drop_index('ix_api_key_user_active', table_name='api_keys')

    # Drop api_keys table
    op.drop_table('api_keys')
