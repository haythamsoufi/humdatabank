"""Add AI term glossary tables

Revision ID: add_ai_term_glossary
Revises: add_ai_doc_multi_country
Create Date: 2026-02-20

"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


revision = "add_ai_term_glossary"
down_revision = "add_ai_doc_multi_country"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_term_concepts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("concept_key", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("definition", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_ai_term_concepts_concept_key", "ai_term_concepts", ["concept_key"], unique=True)
    op.create_index("ix_ai_term_concepts_is_active", "ai_term_concepts", ["is_active"], unique=False)

    op.create_table(
        "ai_term_glossary",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("concept_id", sa.Integer(), sa.ForeignKey("ai_term_concepts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("term", sa.String(length=500), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=False, server_default="en"),
        sa.Column("term_type", sa.String(length=50), nullable=False, server_default="synonym"),
        sa.Column("weight", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("source", sa.String(length=50), nullable=False, server_default="manual"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("concept_id", "term", "language", name="uq_ai_term_glossary_concept_term_lang"),
    )
    op.create_index("ix_ai_term_glossary_concept_id", "ai_term_glossary", ["concept_id"], unique=False)
    op.create_index("ix_ai_term_glossary_term", "ai_term_glossary", ["term"], unique=False)
    op.create_index("ix_ai_term_glossary_language", "ai_term_glossary", ["language"], unique=False)
    op.create_index("ix_ai_term_glossary_term_type", "ai_term_glossary", ["term_type"], unique=False)
    op.create_index("ix_ai_term_glossary_source", "ai_term_glossary", ["source"], unique=False)
    op.create_index("ix_ai_term_glossary_is_active", "ai_term_glossary", ["is_active"], unique=False)
    op.create_index(
        "ix_ai_term_glossary_active_weight",
        "ai_term_glossary",
        ["is_active", "weight"],
        unique=False,
    )

    op.create_table(
        "ai_term_concept_embeddings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("concept_id", sa.Integer(), sa.ForeignKey("ai_term_concepts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column("text_embedded", sa.Text(), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("generation_cost_usd", sa.Float(), nullable=True),
        sa.Column("generated_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("concept_id", name="uq_ai_term_concept_embeddings_concept_id"),
    )
    op.create_index(
        "ix_ai_term_concept_embeddings_concept_id",
        "ai_term_concept_embeddings",
        ["concept_id"],
        unique=False,
    )
    op.create_index(
        "idx_ai_term_concept_embeddings_vector_cosine",
        "ai_term_concept_embeddings",
        ["embedding"],
        unique=False,
        postgresql_using="ivfflat",
        postgresql_with={"lists": 50},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    conn = op.get_bind()

    seed_concepts = [
        ("cea", "Community Engagement and Accountability", "IFRC CEA concept and related terms."),
        ("cash", "Cash and Voucher Assistance", "IFRC cash/CVA concept and related terms."),
        ("livelihoods", "Livelihoods", "Livelihoods and economic security related terms."),
        ("social_protection", "Social Protection", "Social protection and safety net related terms."),
        ("pgi", "Protection, Gender and Inclusion", "IFRC PGI concept and related terms."),
    ]
    for concept_key, display_name, definition in seed_concepts:
        conn.execute(
            sa.text(
                """
                INSERT INTO ai_term_concepts (concept_key, display_name, definition, is_active, created_at, updated_at)
                VALUES (:concept_key, :display_name, :definition, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            ),
            {
                "concept_key": concept_key,
                "display_name": display_name,
                "definition": definition,
            },
        )

    seed_terms = {
        "cea": [
            ("cea", "acronym", 200),
            ("community engagement and accountability", "canonical", 220),
            ("community engagement", "synonym", 140),
            ("accountability to affected populations", "synonym", 160),
            ("aap", "acronym", 150),
            ("feedback mechanism", "synonym", 130),
            ("community feedback", "synonym", 120),
        ],
        "cash": [
            ("cash", "canonical", 220),
            ("cash assistance", "synonym", 190),
            ("cash transfer", "synonym", 180),
            ("cash and voucher assistance", "canonical", 210),
            ("voucher assistance", "synonym", 150),
            ("cva", "acronym", 200),
        ],
        "livelihoods": [
            ("livelihoods", "canonical", 220),
            ("economic security", "synonym", 150),
            ("income generation", "synonym", 140),
        ],
        "social_protection": [
            ("social protection", "canonical", 220),
            ("social assistance", "synonym", 160),
            ("social safety net", "synonym", 150),
        ],
        "pgi": [
            ("pgi", "acronym", 200),
            ("protection, gender and inclusion", "canonical", 220),
            ("gender and inclusion", "synonym", 130),
        ],
    }
    for concept_key, terms in seed_terms.items():
        for term, term_type, weight in terms:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO ai_term_glossary (
                        concept_id, term, language, term_type, weight, source, is_active, created_at, updated_at
                    )
                    SELECT c.id, :term, 'en', :term_type, :weight, 'manual', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    FROM ai_term_concepts c
                    WHERE c.concept_key = :concept_key
                    """
                ),
                {
                    "concept_key": concept_key,
                    "term": term,
                    "term_type": term_type,
                    "weight": int(weight),
                },
            )


def downgrade():
    op.drop_index("idx_ai_term_concept_embeddings_vector_cosine", table_name="ai_term_concept_embeddings")
    op.drop_index("ix_ai_term_concept_embeddings_concept_id", table_name="ai_term_concept_embeddings")
    op.drop_table("ai_term_concept_embeddings")

    op.drop_index("ix_ai_term_glossary_active_weight", table_name="ai_term_glossary")
    op.drop_index("ix_ai_term_glossary_is_active", table_name="ai_term_glossary")
    op.drop_index("ix_ai_term_glossary_source", table_name="ai_term_glossary")
    op.drop_index("ix_ai_term_glossary_term_type", table_name="ai_term_glossary")
    op.drop_index("ix_ai_term_glossary_language", table_name="ai_term_glossary")
    op.drop_index("ix_ai_term_glossary_term", table_name="ai_term_glossary")
    op.drop_index("ix_ai_term_glossary_concept_id", table_name="ai_term_glossary")
    op.drop_table("ai_term_glossary")

    op.drop_index("ix_ai_term_concepts_is_active", table_name="ai_term_concepts")
    op.drop_index("ix_ai_term_concepts_concept_key", table_name="ai_term_concepts")
    op.drop_table("ai_term_concepts")

