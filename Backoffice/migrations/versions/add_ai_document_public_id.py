"""Add opaque public_id (UUID) to AI Knowledge Base documents and chunks.

Revision ID: add_ai_document_public_id
Revises: fix_car_pending_unique
Create Date: 2026-10-27

Public MCP / Custom GPT document APIs previously exposed sequential integer
primary keys in paths and JSON (``document_id``, ``chunk_id``, download URLs),
so every public AI document could be probed by counting. Authorization
(``is_public`` + searchable + completed) remains the primary control; these
columns add non-guessable identifiers as defense in depth. Existing rows are
backfilled in place. Integer path segments no longer match the UUID routes
(404), so legacy int URLs do not leak existence via redirect.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "add_ai_document_public_id"
down_revision = "fix_car_pending_unique"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "ai_documents",
        sa.Column("public_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        sa.text("UPDATE ai_documents SET public_id = gen_random_uuid() WHERE public_id IS NULL")
    )
    op.alter_column("ai_documents", "public_id", nullable=False)
    op.create_index(
        "uq_ai_documents_public_id",
        "ai_documents",
        ["public_id"],
        unique=True,
    )

    op.add_column(
        "ai_document_chunks",
        sa.Column("public_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE ai_document_chunks SET public_id = gen_random_uuid() WHERE public_id IS NULL"
        )
    )
    op.alter_column("ai_document_chunks", "public_id", nullable=False)
    op.create_index(
        "uq_ai_document_chunks_public_id",
        "ai_document_chunks",
        ["public_id"],
        unique=True,
    )


def downgrade():
    op.drop_index("uq_ai_document_chunks_public_id", table_name="ai_document_chunks")
    op.drop_column("ai_document_chunks", "public_id")
    op.drop_index("uq_ai_documents_public_id", table_name="ai_documents")
    op.drop_column("ai_documents", "public_id")
