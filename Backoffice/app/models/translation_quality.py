"""Translation catalog, glossary, cache, and optional prose-memory models."""

from __future__ import annotations

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

from app.extensions import db
from app.utils.datetime_helpers import utcnow


_JSON = JSON().with_variant(JSONB, "postgresql")


class TranslationString(db.Model):
    """Source of truth for gettext catalog values plus provenance."""

    __tablename__ = "translation_string"

    id = db.Column(db.Integer, primary_key=True)
    locale = db.Column(db.String(10), nullable=False, index=True)
    msgid = db.Column(db.Text, nullable=False)
    msgid_hash = db.Column(db.String(16), nullable=False, index=True)
    msgstr = db.Column(db.Text, nullable=False, default="")
    msgctxt = db.Column(db.Text, nullable=True)
    is_plural = db.Column(db.Boolean, nullable=False, default=False)
    msgstr_plural = db.Column(_JSON, nullable=True)
    provenance = db.Column(db.String(40), nullable=False, default="unknown_presumed_machine", index=True)
    engine = db.Column(db.String(40), nullable=True, index=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="unreviewed", index=True)
    version = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        db.UniqueConstraint("locale", "msgid", name="uq_translation_string_locale_msgid"),
        db.Index("ix_translation_string_locale_hash", "locale", "msgid_hash"),
        db.Index("ix_translation_string_locale_status", "locale", "status"),
    )


class TranslationEntityProvenance(db.Model):
    """Provenance for JSONB *_translations fields (indicators, forms, org)."""

    __tablename__ = "translation_entity_provenance"

    id = db.Column(db.Integer, primary_key=True)
    entity_type = db.Column(db.String(80), nullable=False, index=True)
    entity_id = db.Column(db.Integer, nullable=False, index=True)
    field_name = db.Column(db.String(80), nullable=False)
    locale = db.Column(db.String(10), nullable=False)
    provenance = db.Column(db.String(40), nullable=False, default="unknown_presumed_machine")
    engine = db.Column(db.String(40), nullable=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        db.UniqueConstraint(
            "entity_type", "entity_id", "field_name", "locale",
            name="uq_translation_entity_prov",
        ),
    )


class TranslationResultCache(db.Model):
    """MT result cache keyed on source hash + language pair + engine."""

    __tablename__ = "translation_result_cache"

    id = db.Column(db.Integer, primary_key=True)
    source_hash = db.Column(db.String(64), nullable=False)
    source_lang = db.Column(db.String(10), nullable=False)
    target_lang = db.Column(db.String(10), nullable=False)
    engine = db.Column(db.String(40), nullable=False)
    source_text = db.Column(db.Text, nullable=False)
    translated_text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    __table_args__ = (
        db.UniqueConstraint(
            "source_hash", "source_lang", "target_lang", "engine",
            name="uq_translation_result_cache",
        ),
        db.Index("ix_translation_result_cache_lookup", "source_hash", "target_lang", "engine"),
    )


class TranslationGlossaryTerm(db.Model):
    """Approved bilingual must/preferred terms forced during MT."""

    __tablename__ = "translation_glossary_term"

    id = db.Column(db.Integer, primary_key=True)
    source_term = db.Column(db.String(500), nullable=False)
    source_lang = db.Column(db.String(10), nullable=False, default="en")
    target_term = db.Column(db.String(500), nullable=False)
    target_lang = db.Column(db.String(10), nullable=False)
    tier = db.Column(db.String(20), nullable=False, default="must", index=True)
    origin = db.Column(db.String(50), nullable=False, default="manual")
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        db.UniqueConstraint(
            "source_term", "source_lang", "target_lang",
            name="uq_translation_glossary_term",
        ),
        db.Index("ix_translation_glossary_active_lang", "is_active", "target_lang", "tier"),
    )


class TranslationGlossaryCandidate(db.Model):
    """Proposed glossary terms awaiting human accept/reject."""

    __tablename__ = "translation_glossary_candidate"

    id = db.Column(db.Integer, primary_key=True)
    source_term = db.Column(db.String(500), nullable=False)
    target_term = db.Column(db.String(500), nullable=False)
    source_lang = db.Column(db.String(10), nullable=False, default="en")
    target_lang = db.Column(db.String(10), nullable=False)
    extractor = db.Column(db.String(40), nullable=False)
    confidence = db.Column(db.Float, nullable=False, default=0.0)
    proposed_tier = db.Column(db.String(20), nullable=False, default="preferred")
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    evidence = db.Column(_JSON, nullable=True)
    occurrence_count = db.Column(db.Integer, nullable=False, default=1)
    example_sentences = db.Column(_JSON, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    reviewer_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)

    __table_args__ = (
        db.Index("ix_translation_glossary_cand_status_lang", "status", "target_lang"),
        db.Index(
            "ix_translation_glossary_cand_dedupe",
            "source_term", "target_term", "target_lang", "extractor",
        ),
    )


class TranslationMemoryEntry(db.Model):
    """Optional prose TM. Disabled until TRANSLATION_MEMORY_PROSE_ENABLED is set."""

    __tablename__ = "translation_memory_entry"

    id = db.Column(db.Integer, primary_key=True)
    source_text = db.Column(db.Text, nullable=False)
    target_text = db.Column(db.Text, nullable=False)
    source_lang = db.Column(db.String(10), nullable=False)
    target_lang = db.Column(db.String(10), nullable=False)
    source_hash = db.Column(db.String(64), nullable=False, index=True)
    provenance = db.Column(db.String(40), nullable=False, default="human")
    confidence = db.Column(db.Float, nullable=False, default=1.0)
    origin = db.Column(db.String(50), nullable=False, default="manual")
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    __table_args__ = (
        db.Index("ix_translation_memory_lookup", "source_lang", "target_lang", "source_hash"),
    )


class TranslationDocumentPair(db.Model):
    """Opt-in Knowledge Base language pair for deferred sentence-level TM."""

    __tablename__ = "translation_document_pair"

    id = db.Column(db.Integer, primary_key=True)
    source_document_id = db.Column(
        db.Integer, db.ForeignKey("ai_documents.id", ondelete="CASCADE"), nullable=False
    )
    target_document_id = db.Column(
        db.Integer, db.ForeignKey("ai_documents.id", ondelete="CASCADE"), nullable=False
    )
    source_lang = db.Column(db.String(10), nullable=False)
    target_lang = db.Column(db.String(10), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="deferred", index=True)
    note = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)

    __table_args__ = (
        db.UniqueConstraint(
            "source_document_id", "target_document_id",
            name="uq_translation_document_pair",
        ),
    )
