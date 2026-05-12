"""
AI terminology models.

Stores glossary concepts/terms used by AI retrieval and classification.
"""

from app.extensions import db
from app.utils.datetime_helpers import utcnow
from pgvector.sqlalchemy import Vector


class AITermConcept(db.Model):
    __tablename__ = "ai_term_concepts"

    id = db.Column(db.Integer, primary_key=True)
    concept_key = db.Column(db.String(100), nullable=False, unique=True, index=True)  # e.g. "cea"
    display_name = db.Column(db.String(255), nullable=False)  # e.g. "Community Engagement and Accountability"
    definition = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    terms = db.relationship(
        "AITermGlossary",
        back_populates="concept",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )


class AITermGlossary(db.Model):
    __tablename__ = "ai_term_glossary"

    id = db.Column(db.Integer, primary_key=True)
    concept_id = db.Column(
        db.Integer,
        db.ForeignKey("ai_term_concepts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    term = db.Column(db.String(500), nullable=False, index=True)
    language = db.Column(db.String(10), nullable=False, default="en", index=True)
    term_type = db.Column(db.String(50), nullable=False, default="synonym", index=True)  # acronym/canonical/synonym/exclude
    weight = db.Column(db.Integer, nullable=False, default=100)
    source = db.Column(db.String(50), nullable=False, default="manual", index=True)  # manual/indicator_bank/imported
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    concept = db.relationship("AITermConcept", back_populates="terms")

    __table_args__ = (
        db.UniqueConstraint("concept_id", "term", "language", name="uq_ai_term_glossary_concept_term_lang"),
        db.Index("ix_ai_term_glossary_active_weight", "is_active", "weight"),
    )


class AITermConceptEmbedding(db.Model):
    __tablename__ = "ai_term_concept_embeddings"

    id = db.Column(db.Integer, primary_key=True)
    concept_id = db.Column(
        db.Integer,
        db.ForeignKey("ai_term_concepts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    embedding = db.Column(Vector(1536), nullable=False)
    text_embedded = db.Column(db.Text, nullable=True)
    model = db.Column(db.String(100), nullable=False)
    dimensions = db.Column(db.Integer, nullable=False)
    generation_cost_usd = db.Column(db.Float, nullable=True)
    generated_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    concept = db.relationship("AITermConcept", backref=db.backref("embedding", uselist=False, lazy="select"))

    __table_args__ = (
        db.Index(
            "idx_ai_term_concept_embeddings_vector_cosine",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_with={"lists": 50},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

