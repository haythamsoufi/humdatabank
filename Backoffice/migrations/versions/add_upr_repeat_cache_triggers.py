"""Invalidate UPR API caches for repeat-group changes

Revision ID: add_upr_repeat_cache_triggers
Revises: add_upr_api_cache_revision
Create Date: 2026-09-24
"""

from alembic import op


revision = "add_upr_repeat_cache_triggers"
down_revision = "add_upr_api_cache_revision"
branch_labels = None
depends_on = None


_SOURCE_TABLES = (
    "repeat_group_instance",
    "repeat_group_data",
)


def upgrade():
    for table_name in _SOURCE_TABLES:
        op.execute(
            f"""
            CREATE TRIGGER trg_{table_name}_upr_api_cache_revision
            AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE ON {table_name}
            FOR EACH STATEMENT
            EXECUTE FUNCTION bump_upr_api_cache_version()
            """
        )


def downgrade():
    for table_name in reversed(_SOURCE_TABLES):
        op.execute(
            f"DROP TRIGGER IF EXISTS trg_{table_name}_upr_api_cache_revision ON {table_name}"
        )
