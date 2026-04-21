"""Add total_embeddings to ai_documents

Revision ID: add_total_embeddings_ai_docs
Revises: add_ai_chunks_fts_gin
Create Date: 2026-02-08

Tracks number of embeddings per document for consistent stats in document library.
Maintained by ai_vector_store.store_document_embeddings and document processing.
"""

from alembic import op
import sqlalchemy as sa


revision = "add_total_embeddings_ai_docs"
down_revision = "add_ai_chunks_fts_gin"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("ai_documents") as batch_op:
        batch_op.add_column(sa.Column("total_embeddings", sa.Integer(), nullable=True, server_default="0"))


def downgrade():
    with op.batch_alter_table("ai_documents") as batch_op:
        batch_op.drop_column("total_embeddings")
