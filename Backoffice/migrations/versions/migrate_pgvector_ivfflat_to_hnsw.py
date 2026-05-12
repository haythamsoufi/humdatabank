"""Migrate pgvector indexes from IVFFlat to HNSW

Replaces all IVFFlat approximate-nearest-neighbour indexes with HNSW, which
offers better recall at the same or lower query latency, is incremental (no
VACUUM needed after bulk inserts), and does not require knowing ``lists`` in
advance.

Affected indexes:
  - idx_ai_embeddings_vector_cosine       (ai_embeddings)
  - idx_indicator_bank_embeddings_vector_cosine (indicator_bank_embeddings)
  - idx_ai_term_concept_embeddings_vector_cosine (ai_term_concept_embeddings)

HNSW parameters chosen:
  - m=16      (number of connections per layer; 16 is the pgvector default and
               a good trade-off between build time and recall)
  - ef_construction=64  (size of candidate list during construction; higher →
                         better recall but slower build; 64 is the default)

The migration is safe to run on a live database; CREATE INDEX CONCURRENTLY
avoids table locks. It falls back to a plain (blocking) CREATE INDEX when
CONCURRENTLY is not available (e.g. inside a transaction on older versions).

Revision ID: migrate_ivfflat_to_hnsw
Revises: add_ai_document_metadata_enrichment
Create Date: 2026-03-05 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
import logging

logger = logging.getLogger("alembic.migrate_pgvector_ivfflat_to_hnsw")

# revision identifiers, used by Alembic.
revision = 'migrate_ivfflat_to_hnsw'
down_revision = 'add_ai_doc_meta'
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _drop_index_if_exists(index_name: str) -> None:
    """Drop an index by name, ignoring errors if it does not exist."""
    try:
        op.execute(f'DROP INDEX IF EXISTS "{index_name}"')
        logger.info("Dropped index %s", index_name)
    except Exception as exc:
        logger.warning("Could not drop index %s: %s", index_name, exc)


def _create_hnsw_index(index_name: str, table: str, column: str,
                        ops: str = "vector_cosine_ops",
                        m: int = 16, ef_construction: int = 64) -> None:
    """
    Create an HNSW vector index.

    Tries CONCURRENTLY first (non-blocking).  If the database is in an
    explicit transaction (Alembic default), CONCURRENTLY is not allowed, so
    we fall back to a regular CREATE INDEX.
    """
    ddl_concurrent = f"""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS "{index_name}"
        ON "{table}"
        USING hnsw ("{column}" {ops})
        WITH (m = {m}, ef_construction = {ef_construction})
    """
    ddl_blocking = f"""
        CREATE INDEX IF NOT EXISTS "{index_name}"
        ON "{table}"
        USING hnsw ("{column}" {ops})
        WITH (m = {m}, ef_construction = {ef_construction})
    """
    try:
        # CONCURRENTLY cannot run inside a transaction block.
        op.execute(sa.text("COMMIT"))          # end Alembic's implicit transaction
        op.execute(ddl_concurrent)
        logger.info("Created HNSW index %s (CONCURRENTLY)", index_name)
        op.execute(sa.text("BEGIN"))           # restart transaction so Alembic can finish
    except Exception as exc_c:
        logger.warning(
            "CONCURRENT HNSW index creation failed (%s), falling back to blocking: %s",
            index_name, exc_c,
        )
        try:
            op.execute(ddl_blocking)
            logger.info("Created HNSW index %s (blocking)", index_name)
        except Exception as exc_b:
            logger.error(
                "Could not create HNSW index %s (blocking): %s", index_name, exc_b
            )
            raise


# ---------------------------------------------------------------------------
# Upgrade: IVFFlat → HNSW
# ---------------------------------------------------------------------------

def upgrade():
    # 1. ai_embeddings -------------------------------------------------------
    _drop_index_if_exists("idx_ai_embeddings_vector_cosine")
    _create_hnsw_index(
        index_name="idx_ai_embeddings_vector_cosine_hnsw",
        table="ai_embeddings",
        column="embedding",
        ops="vector_cosine_ops",
    )

    # 2. indicator_bank_embeddings -------------------------------------------
    _drop_index_if_exists("idx_indicator_bank_embeddings_vector_cosine")
    _create_hnsw_index(
        index_name="idx_indicator_bank_embeddings_vector_cosine_hnsw",
        table="indicator_bank_embeddings",
        column="embedding",
        ops="vector_cosine_ops",
    )

    # 3. ai_term_concept_embeddings ------------------------------------------
    # Table from add_ai_term_glossary_tables; index idx_ai_term_concept_embeddings_vector_cosine.
    _drop_index_if_exists("idx_ai_term_concept_embeddings_vector_cosine")
    _create_hnsw_index(
        index_name="idx_ai_term_concept_embeddings_vector_cosine_hnsw",
        table="ai_term_concept_embeddings",
        column="embedding",
        ops="vector_cosine_ops",
    )


# ---------------------------------------------------------------------------
# Downgrade: HNSW → IVFFlat
# ---------------------------------------------------------------------------

def downgrade():
    # Remove HNSW indexes
    _drop_index_if_exists("idx_ai_embeddings_vector_cosine_hnsw")
    _drop_index_if_exists("idx_indicator_bank_embeddings_vector_cosine_hnsw")
    _drop_index_if_exists("idx_ai_term_concept_embeddings_vector_cosine_hnsw")

    # Restore IVFFlat indexes
    try:
        op.execute(sa.text("COMMIT"))
        op.execute("""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ai_embeddings_vector_cosine
            ON ai_embeddings
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100)
        """)
        op.execute(sa.text("BEGIN"))
    except Exception as exc:
        logger.warning("IVFFlat restore (ai_embeddings) failed concurrently, trying blocking: %s", exc)
        op.execute("""
            CREATE INDEX IF NOT EXISTS idx_ai_embeddings_vector_cosine
            ON ai_embeddings
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100)
        """)

    try:
        op.execute(sa.text("COMMIT"))
        op.execute("""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_indicator_bank_embeddings_vector_cosine
            ON indicator_bank_embeddings
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100)
        """)
        op.execute(sa.text("BEGIN"))
    except Exception as exc:
        logger.warning("IVFFlat restore (indicator_bank_embeddings) failed concurrently, trying blocking: %s", exc)
        op.execute("""
            CREATE INDEX IF NOT EXISTS idx_indicator_bank_embeddings_vector_cosine
            ON indicator_bank_embeddings
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100)
        """)

    try:
        op.execute(sa.text("COMMIT"))
        op.execute("""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ai_term_concept_embeddings_vector_cosine
            ON ai_term_concept_embeddings
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100)
        """)
        op.execute(sa.text("BEGIN"))
    except Exception as exc:
        logger.warning("IVFFlat restore (ai_term_concept_embeddings) failed concurrently, trying blocking: %s", exc)
        op.execute("""
            CREATE INDEX IF NOT EXISTS idx_ai_term_concept_embeddings_vector_cosine
            ON ai_term_concept_embeddings
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100)
        """)
