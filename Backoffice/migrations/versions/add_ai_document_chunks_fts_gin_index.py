"""Add GIN index on ai_document_chunks for full-text search (PostgreSQL only)

Revision ID: add_ai_chunks_fts_gin
Revises: migrate_data_explorer_perms
Create Date: 2026-02-06

Improves keyword_search performance when using to_tsvector('simple', content).
SQLite does not support GIN; this migration is a no-op for SQLite.
"""

from alembic import op


revision = "add_ai_chunks_fts_gin"
down_revision = "migrate_data_explorer_perms"
branch_labels = None
depends_on = None


def _is_postgres(connection):
    return connection.dialect.name == "postgresql"


def upgrade():
    conn = op.get_bind()
    if not _is_postgres(conn):
        return
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_document_chunk_content_fts "
        "ON ai_document_chunks USING GIN (to_tsvector('simple', content))"
    )


def downgrade():
    conn = op.get_bind()
    if not _is_postgres(conn):
        return
    op.execute("DROP INDEX IF EXISTS idx_ai_document_chunk_content_fts")
