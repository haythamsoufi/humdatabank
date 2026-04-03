"""Add AI document import job tables

Revision ID: add_ai_doc_import_jobs
Revises: add_user_rating_trace
Create Date: 2026-02-20

Adds:
- ai_document_import_jobs: tracks batch imports so UI can resume/poll
- ai_document_import_job_items: per-item state + link to created ai_documents
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "add_ai_doc_import_jobs"
down_revision = "add_user_rating_trace"
branch_labels = None
depends_on = None


def upgrade():
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


def downgrade():
    op.drop_index("ix_ai_doc_import_items_job_index", table_name="ai_document_import_job_items")
    op.drop_index("ix_ai_document_import_job_items_import_status", table_name="ai_document_import_job_items")
    op.drop_index("ix_ai_document_import_job_items_ai_document_id", table_name="ai_document_import_job_items")
    op.drop_index("ix_ai_document_import_job_items_job_id", table_name="ai_document_import_job_items")
    op.drop_table("ai_document_import_job_items")

    op.drop_index("ix_ai_document_import_jobs_status", table_name="ai_document_import_jobs")
    op.drop_index("ix_ai_document_import_jobs_user_id", table_name="ai_document_import_jobs")
    op.drop_index("ix_ai_document_import_jobs_job_type", table_name="ai_document_import_jobs")
    op.drop_table("ai_document_import_jobs")
