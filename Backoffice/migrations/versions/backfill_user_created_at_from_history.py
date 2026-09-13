"""Backfill user.created_at from the earliest available historical record

Revision ID: backfill_user_created_at_history
Revises: add_user_created_at
Create Date: 2026-09-12
"""
from alembic import op
import sqlalchemy as sa


revision = 'backfill_user_created_at_history'
down_revision = 'add_user_created_at'
branch_labels = None
depends_on = None


def _has_columns(inspector, table: str, *columns: str) -> bool:
    if not inspector.has_table(table):
        return False
    available = {column['name'] for column in inspector.get_columns(table)}
    return all(column in available for column in columns)


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # The preceding migration used explicit account-creation audit events. Those
    # events were not recorded for older production accounts, so recover the
    # earliest timestamp at which each still-empty account appears anywhere in
    # the retained history. This is the best available upper bound on its join
    # date; it is preferable to inventing the deployment date.
    sources = []

    def add(table: str, user_column: str, timestamp_column: str, where: str = ''):
        if _has_columns(inspector, table, user_column, timestamp_column):
            predicate = f'WHERE "{user_column}" IS NOT NULL'
            if where:
                predicate += f' AND ({where})'
            sources.append(
                f'SELECT "{user_column}" AS user_id, '
                f'"{timestamp_column}" AS observed_at '
                f'FROM "{table}" {predicate}'
            )

    add('user_activity_log', 'user_id', 'timestamp')
    add('user_login_log', 'user_id', 'timestamp')
    add('user_session_log', 'user_id', 'session_start')
    add('user_entity_permissions', 'user_id', 'created_at')
    add('rbac_user_role', 'user_id', 'created_at')
    add('country_access_request', 'user_id', 'created_at')
    add('notification', 'user_id', 'created_at')
    add('user_devices', 'user_id', 'created_at')
    add('password_reset_tokens', 'user_id', 'created_at')
    add('admin_action_log', 'admin_user_id', 'timestamp')
    add(
        'admin_action_log',
        'target_id',
        'timestamp',
        "\"target_type\" = 'user'",
    )

    if not sources:
        return

    bind.execute(sa.text(
        f"""
        WITH observed AS (
            {' UNION ALL '.join(sources)}
        ),
        first_observed AS (
            SELECT user_id, MIN(observed_at) AS first_seen
            FROM observed
            WHERE observed_at IS NOT NULL
            GROUP BY user_id
        )
        UPDATE "user" AS u
        SET created_at = first_observed.first_seen
        FROM first_observed
        WHERE u.id = first_observed.user_id
          AND u.created_at IS NULL
        """
    ))


def downgrade():
    # This is a data-recovery migration. Do not erase recovered dates on
    # downgrade because they cannot be distinguished from exact creation dates.
    pass
