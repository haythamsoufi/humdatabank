"""Add FDRS document import metadata columns to submitted_document.

Revision ID: fdrs_submitted_doc_metadata
Revises: add_data_quality_validation
Create Date: 2026-06-05
"""
from alembic import op
import sqlalchemy as sa


revision = "fdrs_submitted_doc_metadata"
down_revision = "add_data_quality_validation"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("submitted_document", sa.Column("source_url", sa.String(length=2000), nullable=True))
    op.add_column(
        "submitted_document",
        sa.Column("thumbnail_source_url", sa.String(length=2000), nullable=True),
    )
    op.add_column(
        "submitted_document",
        sa.Column("fdrs_import_key", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "submitted_document",
        sa.Column(
            "file_pending",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.alter_column("submitted_document", "storage_path", existing_type=sa.String(length=255), nullable=True)
    op.create_index(
        "ix_submitted_doc_fdrs_import_key",
        "submitted_document",
        ["fdrs_import_key"],
        unique=True,
        postgresql_where=sa.text("fdrs_import_key IS NOT NULL"),
    )


def downgrade():
    op.drop_index("ix_submitted_doc_fdrs_import_key", table_name="submitted_document")
    op.alter_column("submitted_document", "storage_path", existing_type=sa.String(length=255), nullable=False)
    op.drop_column("submitted_document", "file_pending")
    op.drop_column("submitted_document", "fdrs_import_key")
    op.drop_column("submitted_document", "thumbnail_source_url")
    op.drop_column("submitted_document", "source_url")
