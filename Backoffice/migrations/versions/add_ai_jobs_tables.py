"""Add generic AI queued job tables

Revision ID: add_ai_jobs_tables
Revises: add_ai_doc_import_jobs
Create Date: 2026-02-20

Adds:
- ai_jobs: generic job header (type/status/meta)
- ai_job_items: per-item status + payload, optionally linked to an entity
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "add_ai_jobs_tables"
down_revision = "add_ai_doc_import_jobs"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("job_type", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("total_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_jobs_job_type", "ai_jobs", ["job_type"], unique=False)
    op.create_index("ix_ai_jobs_user_id", "ai_jobs", ["user_id"], unique=False)
    op.create_index("ix_ai_jobs_status", "ai_jobs", ["status"], unique=False)

    op.create_table(
        "ai_job_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("item_index", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=True),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["ai_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_job_items_job_id", "ai_job_items", ["job_id"], unique=False)
    op.create_index("ix_ai_job_items_status", "ai_job_items", ["status"], unique=False)
    op.create_index("ix_ai_job_items_entity_type", "ai_job_items", ["entity_type"], unique=False)
    op.create_index("ix_ai_job_items_entity_id", "ai_job_items", ["entity_id"], unique=False)
    op.create_index("ix_ai_job_items_entity_type_id", "ai_job_items", ["entity_type", "entity_id"], unique=False)
    op.create_index("ix_ai_job_items_job_index", "ai_job_items", ["job_id", "item_index"], unique=True)

    # ------------------------------------------------------------------
    # Migrate existing IFRC bulk import jobs/items into generic tables,
    # then drop the old import-job tables.
    #
    # NOTE: We keep the original migration that *created* those tables
    # because many DBs are already at that head.
    # ------------------------------------------------------------------
    conn = op.get_bind()

    # Copy jobs as-is (preserve IDs so existing URLs/job_ids keep working).
    conn.execute(
        sa.text(
            """
            INSERT INTO ai_jobs (id, job_type, user_id, status, total_items, created_at, started_at, finished_at, error, meta)
            SELECT id, job_type, user_id, status, total_items, created_at, started_at, finished_at, error, meta
            FROM ai_document_import_jobs
            """
        )
    )

    # Copy items. We keep import_status/import_error mapping to status/error and
    # store the original request fields in payload for compatibility/debugging.
    conn.execute(
        sa.text(
            """
            INSERT INTO ai_job_items (job_id, item_index, entity_type, entity_id, status, error, payload, created_at, updated_at)
            SELECT
                job_id,
                item_index,
                CASE WHEN ai_document_id IS NOT NULL THEN 'ai_document' ELSE NULL END AS entity_type,
                ai_document_id AS entity_id,
                import_status AS status,
                import_error AS error,
                jsonb_build_object(
                    'url', source_url,
                    'title', title,
                    'is_public', is_public,
                    'country_id', country_id,
                    'country_name', country_name,
                    'ai_document_id', ai_document_id
                ) AS payload,
                created_at,
                updated_at
            FROM ai_document_import_job_items
            """
        )
    )

    # Drop old tables (items first due to FK).
    op.drop_table("ai_document_import_job_items")
    op.drop_table("ai_document_import_jobs")


def downgrade():
    # Re-create legacy import job tables (best-effort; does not backfill from ai_jobs).
    op.create_table(
        "ai_document_import_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("job_type", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("total_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_document_import_jobs_job_type", "ai_document_import_jobs", ["job_type"], unique=False)
    op.create_index("ix_ai_document_import_jobs_user_id", "ai_document_import_jobs", ["user_id"], unique=False)
    op.create_index("ix_ai_document_import_jobs_status", "ai_document_import_jobs", ["status"], unique=False)

    op.create_table(
        "ai_document_import_job_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("item_index", sa.Integer(), nullable=False),
        sa.Column("source_url", sa.String(length=2000), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("country_id", sa.Integer(), nullable=True),
        sa.Column("country_name", sa.String(length=200), nullable=True),
        sa.Column("ai_document_id", sa.Integer(), nullable=True),
        sa.Column("import_status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("import_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["ai_document_import_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["country_id"], ["country.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["ai_document_id"], ["ai_documents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_document_import_job_items_job_id", "ai_document_import_job_items", ["job_id"], unique=False)
    op.create_index("ix_ai_document_import_job_items_ai_document_id", "ai_document_import_job_items", ["ai_document_id"], unique=False)
    op.create_index("ix_ai_document_import_job_items_import_status", "ai_document_import_job_items", ["import_status"], unique=False)
    op.create_index("ix_ai_doc_import_items_job_index", "ai_document_import_job_items", ["job_id", "item_index"], unique=True)

    op.drop_index("ix_ai_job_items_job_index", table_name="ai_job_items")
    op.drop_index("ix_ai_job_items_entity_type_id", table_name="ai_job_items")
    op.drop_index("ix_ai_job_items_entity_id", table_name="ai_job_items")
    op.drop_index("ix_ai_job_items_entity_type", table_name="ai_job_items")
    op.drop_index("ix_ai_job_items_status", table_name="ai_job_items")
    op.drop_index("ix_ai_job_items_job_id", table_name="ai_job_items")
    op.drop_table("ai_job_items")

    op.drop_index("ix_ai_jobs_status", table_name="ai_jobs")
    op.drop_index("ix_ai_jobs_user_id", table_name="ai_jobs")
    op.drop_index("ix_ai_jobs_job_type", table_name="ai_jobs")
    op.drop_table("ai_jobs")

