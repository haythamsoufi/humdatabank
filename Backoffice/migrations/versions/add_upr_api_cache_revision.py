"""Add transactionally maintained UPR API cache revision

Revision ID: add_upr_api_cache_revision
Revises: add_guidance_document
Create Date: 2026-09-24

Every transaction that can change either UPR endpoint inserts one change-log
row in the same transaction. API cache keys include the committed row count,
which lets workers reuse expensive extracts without serving a pre-commit
payload after the commit becomes visible. The append-only design avoids a
singleton revision-row lock serializing concurrent form saves and imports.
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
        "upr_api_cache_change",
        sa.Column("transaction_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("transaction_id"),
    )
    op.execute(
        """
        CREATE FUNCTION bump_upr_api_cache_version()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            INSERT INTO upr_api_cache_change (transaction_id)
            VALUES (txid_current())
            ON CONFLICT (transaction_id) DO NOTHING;
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
    op.drop_table("upr_api_cache_change")
