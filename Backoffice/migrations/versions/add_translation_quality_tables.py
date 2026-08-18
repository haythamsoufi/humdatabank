"""Translation catalog, glossary, cache, and optional TM tables.

Revision ID: add_translation_quality
Revises: add_assignment_pdf_af
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "add_translation_quality"
down_revision = "add_assignment_pdf_af"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "translation_string",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("locale", sa.String(length=10), nullable=False),
        sa.Column("msgid", sa.Text(), nullable=False),
        sa.Column("msgid_hash", sa.String(length=16), nullable=False),
        sa.Column("msgstr", sa.Text(), nullable=False, server_default=""),
        sa.Column("msgctxt", sa.Text(), nullable=True),
        sa.Column("is_plural", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("msgstr_plural", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("provenance", sa.String(length=40), nullable=False, server_default="unknown_presumed_machine"),
        sa.Column("engine", sa.String(length=40), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="unreviewed"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("locale", "msgid", name="uq_translation_string_locale_msgid"),
    )
    op.create_index("ix_translation_string_locale", "translation_string", ["locale"])
    op.create_index("ix_translation_string_msgid_hash", "translation_string", ["msgid_hash"])
    op.create_index("ix_translation_string_provenance", "translation_string", ["provenance"])
    op.create_index("ix_translation_string_status", "translation_string", ["status"])
    op.create_index("ix_translation_string_locale_hash", "translation_string", ["locale", "msgid_hash"])
    op.create_index("ix_translation_string_locale_status", "translation_string", ["locale", "status"])

    op.create_table(
        "translation_entity_provenance",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("field_name", sa.String(length=80), nullable=False),
        sa.Column("locale", sa.String(length=10), nullable=False),
        sa.Column("provenance", sa.String(length=40), nullable=False, server_default="unknown_presumed_machine"),
        sa.Column("engine", sa.String(length=40), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "entity_type", "entity_id", "field_name", "locale",
            name="uq_translation_entity_prov",
        ),
    )
    op.create_index("ix_translation_entity_prov_type", "translation_entity_provenance", ["entity_type"])
    op.create_index("ix_translation_entity_prov_entity", "translation_entity_provenance", ["entity_id"])

    op.create_table(
        "translation_result_cache",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("source_lang", sa.String(length=10), nullable=False),
        sa.Column("target_lang", sa.String(length=10), nullable=False),
        sa.Column("engine", sa.String(length=40), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("translated_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "source_hash", "source_lang", "target_lang", "engine",
            name="uq_translation_result_cache",
        ),
    )
    op.create_index(
        "ix_translation_result_cache_lookup",
        "translation_result_cache",
        ["source_hash", "target_lang", "engine"],
    )

    op.create_table(
        "translation_glossary_term",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_term", sa.String(length=500), nullable=False),
        sa.Column("source_lang", sa.String(length=10), nullable=False, server_default="en"),
        sa.Column("target_term", sa.String(length=500), nullable=False),
        sa.Column("target_lang", sa.String(length=10), nullable=False),
        sa.Column("tier", sa.String(length=20), nullable=False, server_default="must"),
        sa.Column("origin", sa.String(length=50), nullable=False, server_default="manual"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("source_term", "source_lang", "target_lang", name="uq_translation_glossary_term"),
    )
    op.create_index(
        "ix_translation_glossary_active_lang",
        "translation_glossary_term",
        ["is_active", "target_lang", "tier"],
    )

    op.create_table(
        "translation_glossary_candidate",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_term", sa.String(length=500), nullable=False),
        sa.Column("target_term", sa.String(length=500), nullable=False),
        sa.Column("source_lang", sa.String(length=10), nullable=False, server_default="en"),
        sa.Column("target_lang", sa.String(length=10), nullable=False),
        sa.Column("extractor", sa.String(length=40), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("proposed_tier", sa.String(length=20), nullable=False, server_default="preferred"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("example_sentences", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("reviewer_user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index(
        "ix_translation_glossary_cand_status_lang",
        "translation_glossary_candidate",
        ["status", "target_lang"],
    )

    op.create_table(
        "translation_memory_entry",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("target_text", sa.Text(), nullable=False),
        sa.Column("source_lang", sa.String(length=10), nullable=False),
        sa.Column("target_lang", sa.String(length=10), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("provenance", sa.String(length=40), nullable=False, server_default="human"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1"),
        sa.Column("origin", sa.String(length=50), nullable=False, server_default="manual"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_translation_memory_entry_source_hash", "translation_memory_entry", ["source_hash"])
    op.create_index(
        "ix_translation_memory_lookup",
        "translation_memory_entry",
        ["source_lang", "target_lang", "source_hash"],
    )

    op.create_table(
        "translation_document_pair",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_document_id", sa.Integer(), sa.ForeignKey("ai_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_document_id", sa.Integer(), sa.ForeignKey("ai_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_lang", sa.String(length=10), nullable=False),
        sa.Column("target_lang", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="deferred"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("source_document_id", "target_document_id", name="uq_translation_document_pair"),
    )
    op.create_index("ix_translation_document_pair_status", "translation_document_pair", ["status"])


def downgrade():
    op.drop_table("translation_document_pair")
    op.drop_table("translation_memory_entry")
    op.drop_table("translation_glossary_candidate")
    op.drop_table("translation_glossary_term")
    op.drop_table("translation_result_cache")
    op.drop_table("translation_entity_provenance")
    op.drop_table("translation_string")
