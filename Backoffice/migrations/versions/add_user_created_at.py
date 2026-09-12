"""Add user.created_at and backfill it from account-creation audit events

Revision ID: add_user_created_at
Revises: add_ns_logo_file
Create Date: 2026-09-11
"""
from alembic import op
import sqlalchemy as sa


revision = 'add_user_created_at'
down_revision = 'add_ns_logo_file'
branch_labels = None
depends_on = None


# Some environments bootstrap the schema via ``db.create_all()``, which already
# creates the model-declared column and index — so both may exist before this
# migration runs.
def _has_column(bind, table: str, column: str) -> bool:
    return any(col['name'] == column for col in sa.inspect(bind).get_columns(table))


def _has_index(bind, table: str, name: str) -> bool:
    return any(idx['name'] == name for idx in sa.inspect(bind).get_indexes(table))


def _has_table(bind, table: str) -> bool:
    return sa.inspect(bind).has_table(table)


def upgrade():
    bind = op.get_bind()

    if not _has_column(bind, 'user', 'created_at'):
        op.add_column('user', sa.Column('created_at', sa.DateTime(), nullable=True))
    if not _has_index(bind, 'user', 'ix_user_created_at'):
        op.create_index('ix_user_created_at', 'user', ['created_at'], unique=False)

    # Accounts that predate the column: recover the join date from the audit
    # trail. Admin-created users log admin_action_log.user_create; SSO and
    # self-service signups log user_activity_log.account_created. Where both
    # exist, keep the earliest.
    if _has_table(bind, 'admin_action_log'):
        bind.execute(sa.text(
            """
            UPDATE "user" AS u
            SET created_at = src.first_seen
            FROM (
                SELECT target_id AS user_id, MIN(timestamp) AS first_seen
                FROM admin_action_log
                WHERE action_type = 'user_create' AND target_id IS NOT NULL
                GROUP BY target_id
            ) AS src
            WHERE u.id = src.user_id
              AND (u.created_at IS NULL OR src.first_seen < u.created_at)
            """
        ))

    if _has_table(bind, 'user_activity_log'):
        bind.execute(sa.text(
            """
            UPDATE "user" AS u
            SET created_at = src.first_seen
            FROM (
                SELECT user_id, MIN(timestamp) AS first_seen
                FROM user_activity_log
                WHERE activity_type = 'account_created'
                GROUP BY user_id
            ) AS src
            WHERE u.id = src.user_id
              AND (u.created_at IS NULL OR src.first_seen < u.created_at)
            """
        ))


def downgrade():
    bind = op.get_bind()

    if _has_index(bind, 'user', 'ix_user_created_at'):
        op.drop_index('ix_user_created_at', table_name='user')
    if _has_column(bind, 'user', 'created_at'):
        op.drop_column('user', 'created_at')
