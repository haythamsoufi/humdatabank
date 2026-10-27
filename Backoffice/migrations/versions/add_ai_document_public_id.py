"""Add opaque public_id (UUID) to AI Knowledge Base documents and chunks.

Revision ID: add_ai_document_public_id
Revises: fix_car_pending_unique
Create Date: 2026-10-27

Public MCP / Custom GPT document APIs previously exposed sequential integer
primary keys in paths and JSON (``document_id``, ``chunk_id``, download URLs),
so every public AI document could be probed by counting. Authorization
(``is_public`` + searchable + completed) remains the primary control; these
columns add non-guessable identifiers as defense in depth.

Existing rows are backfilled in place. Integer path segments no longer match
the UUID routes (404), so legacy int URLs do not leak existence via redirect.

Implementation notes (prod boot safety):
- ``ai_document_chunks`` can be large; a single ``UPDATE … gen_random_uuid()``
  under the default statement timeout (or App Service start window) can kill
  the entrypoint and leave the container failing to start.
- This revision is idempotent (safe to retry after a partial failure), raises
  ``statement_timeout`` for the migration session, and backfills in batches.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text
from sqlalchemy.dialects import postgresql


revision = "add_ai_document_public_id"
down_revision = "fix_car_pending_unique"
branch_labels = None
depends_on = None

_BATCH_SIZE = 5000


def _column_names(table: str) -> set[str]:
    bind = op.get_bind()
    return {col["name"] for col in inspect(bind).get_columns(table)}


def _index_names(table: str) -> set[str]:
    bind = op.get_bind()
    return {idx["name"] for idx in inspect(bind).get_indexes(table)}


def _backfill_public_ids(table: str) -> None:
    """Fill NULL public_id values in batches so a large table cannot time out once."""
    bind = op.get_bind()
    # Table names are fixed literals from upgrade(); not user input.
    while True:
        result = bind.execute(
            text(
                f"""
                UPDATE {table} AS t
                SET public_id = gen_random_uuid()
                WHERE t.id IN (
                    SELECT id
                    FROM {table}
                    WHERE public_id IS NULL
                    ORDER BY id
                    LIMIT :limit
                )
                """
            ),
            {"limit": _BATCH_SIZE},
        )
        updated = result.rowcount or 0
        if updated <= 0:
            break


def upgrade():
    bind = op.get_bind()
    # App Service boots run migrations under the container start window; do not
    # inherit a short DB statement_timeout for this potentially large backfill.
    bind.execute(text("SET LOCAL statement_timeout = 0"))

    # --- ai_documents (usually small) ---
    doc_cols = _column_names("ai_documents")
    if "public_id" not in doc_cols:
        op.add_column(
            "ai_documents",
            sa.Column("public_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
    _backfill_public_ids("ai_documents")
    op.alter_column("ai_documents", "public_id", nullable=False)
    if "uq_ai_documents_public_id" not in _index_names("ai_documents"):
        op.create_index(
            "uq_ai_documents_public_id",
            "ai_documents",
            ["public_id"],
            unique=True,
        )

    # --- ai_document_chunks (can be very large) ---
    chunk_cols = _column_names("ai_document_chunks")
    if "public_id" not in chunk_cols:
        op.add_column(
            "ai_document_chunks",
            sa.Column("public_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
    _backfill_public_ids("ai_document_chunks")
    op.alter_column("ai_document_chunks", "public_id", nullable=False)
    if "uq_ai_document_chunks_public_id" not in _index_names("ai_document_chunks"):
        op.create_index(
            "uq_ai_document_chunks_public_id",
            "ai_document_chunks",
            ["public_id"],
            unique=True,
        )


def downgrade():
    bind = op.get_bind()
    chunk_indexes = _index_names("ai_document_chunks")
    if "uq_ai_document_chunks_public_id" in chunk_indexes:
        op.drop_index("uq_ai_document_chunks_public_id", table_name="ai_document_chunks")
    if "public_id" in _column_names("ai_document_chunks"):
        op.drop_column("ai_document_chunks", "public_id")

    doc_indexes = _index_names("ai_documents")
    if "uq_ai_documents_public_id" in doc_indexes:
        op.drop_index("uq_ai_documents_public_id", table_name="ai_documents")
    if "public_id" in _column_names("ai_documents"):
        op.drop_column("ai_documents", "public_id")
