"""Add indicator_bank_embeddings table for semantic indicator resolution

Revision ID: add_indicator_bank_embeddings
Revises: add_total_embeddings_ai_docs
Create Date: 2026-02-09

Stores one embedding per Indicator Bank row (name + definition + unit) for
vector similarity search. Dimensions must match AI_EMBEDDING_DIMENSIONS (e.g. 1536).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "add_indicator_bank_embeddings"
down_revision = "add_total_embeddings_ai_docs"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "indicator_bank_embeddings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("indicator_bank_id", sa.Integer(), nullable=False),
        sa.Column("embedding", postgresql.ARRAY(sa.Float()), nullable=False),
        sa.Column("text_embedded", sa.Text(), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("generation_cost_usd", sa.Float(), nullable=True),
        sa.Column("generated_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["indicator_bank_id"], ["indicator_bank.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_indicator_bank_embeddings_indicator_bank_id", "indicator_bank_embeddings", ["indicator_bank_id"], unique=True)
    op.execute("ALTER TABLE indicator_bank_embeddings ALTER COLUMN embedding TYPE vector(1536) USING embedding::vector(1536)")
    op.execute("""
        CREATE INDEX idx_indicator_bank_embeddings_vector_cosine
        ON indicator_bank_embeddings
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 50)
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_indicator_bank_embeddings_vector_cosine")
    op.drop_table("indicator_bank_embeddings")
