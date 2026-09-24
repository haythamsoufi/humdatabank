"""Add transactionally maintained UPR API cache revision

Revision ID: add_upr_api_cache_revision
Revises: add_guidance_document
Create Date: 2026-09-24

Every statement that can change either UPR endpoint advances one shared
revision in the same transaction. API cache keys include this revision, which
lets workers reuse expensive extracts without serving a pre-commit payload
after the commit becomes visible.
"""

from alembic import op
import sqlalchemy as sa


revision = "add_upr_api_cache_revision"
down_revision = "add_guidance_document"
branch_labels = None
depends_on = None


_SOURCE_TABLES = (
    "form_data",
    "dynamic_indicator_data",
    "dynamic_section_context",
    "assignment_entity_status",
    "assigned_form",
    "form_item",
    "form_section",
    "indicator_bank",
    "country",
    "national_societies",
)


def upgrade():
    op.create_table(
        "upr_api_cache_version",
        sa.Column("id", sa.SmallInteger(), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint("id = 1", name="ck_upr_api_cache_version_singleton"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        "INSERT INTO upr_api_cache_version (id, version) VALUES (1, 1)"
    )
    op.execute(
        """
        CREATE FUNCTION bump_upr_api_cache_version()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            UPDATE upr_api_cache_version
            SET version = version + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = 1;
            RETURN NULL;
        END;
        $$
        """
    )
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
    op.execute("DROP FUNCTION IF EXISTS bump_upr_api_cache_version()")
    op.drop_table("upr_api_cache_version")
