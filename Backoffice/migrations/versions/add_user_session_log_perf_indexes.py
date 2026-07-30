"""Add performance indexes for user_session_log list queries

Revision ID: add_usl_perf_indexes
Revises: add_aes_completion_rate
Create Date: 2026-07-30

Session logs grid orders by is_active DESC, session_start DESC and often filters
by user_id + session_start. Without covering indexes PostgreSQL/SQLite may scan
the full table on large deployments.
"""

from alembic import op

revision = 'add_usl_perf_indexes'
down_revision = 'add_aes_completion_rate'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user_session_log', schema=None) as batch_op:
        batch_op.create_index(
            'ix_usl_active_session_start',
            ['is_active', 'session_start'],
            unique=False,
        )
        batch_op.create_index(
            'ix_usl_user_session_start',
            ['user_id', 'session_start'],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table('user_session_log', schema=None) as batch_op:
        batch_op.drop_index('ix_usl_user_session_start')
        batch_op.drop_index('ix_usl_active_session_start')
