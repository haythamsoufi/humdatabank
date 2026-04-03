"""add indexes for hot columns

Revision ID: b9ad7d386c90
Revises: add_submitted_at_to_aes
Create Date: 2026-03-29 18:36:41.570388

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b9ad7d386c90'
down_revision = 'add_submitted_at_to_aes'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('national_societies', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_national_societies_country_id'), ['country_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_national_societies_is_active'), ['is_active'], unique=False)

    with op.batch_alter_table('ns_branches', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ns_branches_country_id'), ['country_id'], unique=False)

    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_user_active'), ['active'], unique=False)

    with op.batch_alter_table('user_activity_log', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_user_activity_log_activity_type'), ['activity_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_user_activity_log_timestamp'), ['timestamp'], unique=False)
        batch_op.create_index(batch_op.f('ix_user_activity_log_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('user_login_log', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_user_login_log_event_type'), ['event_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_user_login_log_timestamp'), ['timestamp'], unique=False)
        batch_op.create_index(batch_op.f('ix_user_login_log_user_id'), ['user_id'], unique=False)


def downgrade():
    with op.batch_alter_table('user_login_log', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_login_log_user_id'))
        batch_op.drop_index(batch_op.f('ix_user_login_log_timestamp'))
        batch_op.drop_index(batch_op.f('ix_user_login_log_event_type'))

    with op.batch_alter_table('user_activity_log', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_activity_log_user_id'))
        batch_op.drop_index(batch_op.f('ix_user_activity_log_timestamp'))
        batch_op.drop_index(batch_op.f('ix_user_activity_log_activity_type'))

    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_active'))

    with op.batch_alter_table('ns_branches', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ns_branches_country_id'))

    with op.batch_alter_table('national_societies', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_national_societies_is_active'))
        batch_op.drop_index(batch_op.f('ix_national_societies_country_id'))
