"""Add opaque public_id (UUID) to submitted_document for unauthenticated URLs.

Revision ID: add_submitted_document_public_id
Revises: add_upr_api_cache_revision
Create Date: 2026-09-29

Public (no-login) document, thumbnail and download URLs previously exposed the
sequential integer primary key, so every stored file could be probed by counting.
Authorization (is_public + approved + public submission) is the primary control;
this column adds a non-guessable identifier as defense in depth. Existing rows are
backfilled in place; integer URLs keep working (they redirect / re-check the same
policy) until they are retired.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "add_submitted_document_public_id"
down_revision = "add_upr_api_cache_revision"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "submitted_document",
        sa.Column("public_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        sa.text("UPDATE submitted_document SET public_id = gen_random_uuid() WHERE public_id IS NULL")
    )
    op.alter_column("submitted_document", "public_id", nullable=False)
    op.create_index(
        "uq_submitted_doc_public_id",
        "submitted_document",
        ["public_id"],
        unique=True,
    )


def downgrade():
    op.drop_index("uq_submitted_doc_public_id", table_name="submitted_document")
    op.drop_column("submitted_document", "public_id")
