"""
AI Embeddings and Document Models for RAG System

This module defines database models for storing document embeddings,
chunks, and metadata for the RAG (Retrieval Augmented Generation) system.
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)
import sqlalchemy as sa
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Float, JSON, ForeignKey, Index, Date
from sqlalchemy.orm import relationship, backref
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector
import uuid

from app.extensions import db
from app.utils.datetime_helpers import utcnow

# Many-to-many association table: AI documents ↔ countries
ai_document_countries = db.Table(
    'ai_document_countries',
    Column('ai_document_id', Integer, ForeignKey('ai_documents.id', ondelete='CASCADE'), primary_key=True),
    Column('country_id', Integer, ForeignKey('country.id', ondelete='CASCADE'), primary_key=True),
)


class AIDocument(db.Model):
    """
    Represents a document that has been processed for AI/RAG capabilities.

    Links to existing SubmittedDocument or can be standalone for system documents.
    """
    __tablename__ = 'ai_documents'

    id = Column(Integer, primary_key=True)

    # Link to existing document system (optional)
    submitted_document_id = Column(Integer, ForeignKey('submitted_document.id', ondelete='CASCADE'), nullable=True, index=True)
    submitted_document = relationship('SubmittedDocument', backref='ai_document', foreign_keys=[submitted_document_id])

    # Document metadata
    title = Column(String(500), nullable=False)
    filename = Column(String(500), nullable=False)
    file_type = Column(String(50), nullable=False)  # pdf, docx, xlsx, txt, md
    file_size_bytes = Column(Integer, nullable=True)
    storage_path = Column(String(1000), nullable=True)  # Path to original file
    # When set, document is reference-only: no local file; download/hyperlinks use this URL
    source_url = Column(String(2000), nullable=True, index=True)

    # Country linkage (optional)
    # Legacy single-country field kept for backward compatibility / quick queries.
    country_id = Column(Integer, ForeignKey('country.id', ondelete='SET NULL'), nullable=True, index=True)
    # Fallback textual country label when no DB match is found
    country_name = Column(String(200), nullable=True)

    # Geographic scope: NULL = country-specific (one or more), 'regional', 'cluster', 'global'
    geographic_scope = Column(String(50), nullable=True)

    # Content hash for deduplication
    content_hash = Column(String(64), nullable=True, index=True)  # SHA256 hash

    # Processing status
    processing_status = Column(String(50), default='pending', nullable=False, index=True)
    # Status values: pending, processing, completed, failed

    processing_error = Column(Text, nullable=True)  # Error message if failed
    processed_at = Column(DateTime, nullable=True)

    # Statistics
    total_chunks = Column(Integer, default=0)
    total_embeddings = Column(Integer, default=0)  # Number of embeddings stored for this document
    total_tokens = Column(Integer, default=0)
    total_pages = Column(Integer, nullable=True)  # For PDFs

    # Embedding configuration used
    embedding_model = Column(String(100), nullable=True)  # e.g., 'text-embedding-3-small'
    embedding_dimensions = Column(Integer, nullable=True)  # e.g., 1536

    # Access control
    user_id = Column(Integer, ForeignKey('user.id', ondelete='CASCADE'), nullable=True, index=True)
    user = relationship('User', backref='ai_documents', foreign_keys=[user_id])

    is_public = Column(Boolean, default=False, index=True)  # Public documents searchable by all
    allowed_roles = Column(JSON, nullable=True)  # ['admin', 'focal_point'] - null means all

    # AI search enabled
    searchable = Column(Boolean, default=True, index=True)

    # Structured provenance metadata (enriched during processing or editable by admin)
    document_date = Column(Date, nullable=True, index=True)               # Publication/report date
    document_language = Column(String(10), nullable=True, index=True)     # ISO 639-1 language code (e.g. 'en', 'fr')
    source_organization = Column(String(300), nullable=True)              # Originating organisation
    document_category = Column(String(100), nullable=True, index=True)    # policy|report|assessment|guideline|data_sheet|resolution|manual|other
    quality_score = Column(Float, nullable=True)                          # Automated extraction quality 0.0–1.0
    last_verified_at = Column(DateTime, nullable=True)                    # When content was last confirmed current

    # Extra metadata (named to avoid SQLAlchemy reserved 'metadata')
    extra_metadata = Column(JSON, nullable=True)  # Custom metadata (author, date, tags, etc.)

    # Timestamps
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    # Relationships
    chunks = relationship('AIDocumentChunk', back_populates='document', cascade='all, delete-orphan', lazy='dynamic')
    embeddings = relationship('AIEmbedding', back_populates='document', cascade='all, delete-orphan', lazy='dynamic')
    country = relationship('Country', foreign_keys=[country_id])
    # All countries this document covers (many-to-many)
    countries = relationship('Country', secondary=ai_document_countries, lazy='selectin',
                             backref=db.backref('ai_documents_multi', lazy='dynamic'))

    def __repr__(self):
        return f'<AIDocument {self.id}: {self.title}>'

    def to_dict(self):
        """Convert to dictionary for API responses."""
        # Build list of all linked countries from M2M relationship
        countries_list = []
        try:
            for c in (self.countries or []):
                countries_list.append({
                    'id': c.id,
                    'name': c.name,
                    'iso3': getattr(c, 'iso3', None),
                    'iso2': getattr(c, 'iso2', None),
                    'region': getattr(c, 'region', None),
                })
        except Exception as e:
            logger.debug("AIDocument.to_dict: failed to collect countries for doc %s: %s", self.id, e)

        return {
            'id': self.id,
            'title': self.title,
            'filename': self.filename,
            'file_type': self.file_type,
            'file_size_bytes': self.file_size_bytes,
            'processing_status': self.processing_status,
            'processing_error': self.processing_error or '',
            'total_chunks': self.total_chunks,
            'total_embeddings': getattr(self, 'total_embeddings', 0) or 0,
            'total_tokens': self.total_tokens,
            'total_pages': self.total_pages,
            'embedding_model': self.embedding_model,
            'is_public': self.is_public,
            'searchable': self.searchable,
            # Legacy single-country fields (backward compat)
            'country_id': self.country_id,
            'country_name': (self.country.name if self.country else self.country_name),
            'country_iso3': (self.country.iso3 if self.country else None),
            'country_iso2': (self.country.iso2 if self.country else None),
            'country_region': (getattr(self.country, 'region', None) if self.country else None),
            # Multi-country / scope fields
            'geographic_scope': self.geographic_scope,
            'countries': countries_list,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'processed_at': self.processed_at.isoformat() if self.processed_at else None,
            'metadata': self.extra_metadata,
            'source_url': self.source_url,
            # Enriched provenance metadata
            'document_date': self.document_date.isoformat() if self.document_date else None,
            'document_language': self.document_language,
            'source_organization': self.source_organization,
            'document_category': self.document_category,
            'quality_score': self.quality_score,
            'last_verified_at': self.last_verified_at.isoformat() if self.last_verified_at else None,
        }


class AIDocumentChunk(db.Model):
    """
    Represents a chunk of text from a processed document.

    Documents are split into chunks for more granular retrieval.
    Each chunk has its own embedding for semantic search.
    """
    __tablename__ = 'ai_document_chunks'

    id = Column(Integer, primary_key=True)

    # Parent document
    document_id = Column(Integer, ForeignKey('ai_documents.id', ondelete='CASCADE'), nullable=False, index=True)
    document = relationship('AIDocument', back_populates='chunks')

    # Chunk content
    content = Column(Text, nullable=False)
    content_length = Column(Integer, nullable=False)  # Character count
    token_count = Column(Integer, nullable=True)  # Token count for the chunk

    # Position in document
    chunk_index = Column(Integer, nullable=False)  # 0-based index in document
    page_number = Column(Integer, nullable=True)  # Page number if applicable (PDF)
    section_title = Column(String(500), nullable=True)  # Section/heading this chunk belongs to

    # Chunking strategy metadata
    chunk_type = Column(String(50), default='semantic', nullable=False)  # semantic, fixed, paragraph
    overlap_with_previous = Column(Integer, default=0)  # Overlap characters with previous chunk

    # Semantic richness metadata (enriched during processing)
    semantic_type = Column(String(50), default='paragraph', nullable=True)  # paragraph|table|list|header|figure_caption
    heading_hierarchy = Column(JSON, nullable=True)  # e.g. ["Chapter 3", "Section 3.1"] for contextual retrieval
    confidence_score = Column(Float, nullable=True)  # Extraction confidence 0.0–1.0 (OCR quality, parsing success)

    # Extra metadata (named to avoid SQLAlchemy reserved 'metadata')
    extra_metadata = Column(JSON, nullable=True)  # Additional chunk-specific metadata

    # Timestamps
    created_at = Column(DateTime, default=utcnow, nullable=False)

    # Relationships
    embedding = relationship('AIEmbedding', back_populates='chunk', uselist=False, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<AIDocumentChunk {self.id}: doc={self.document_id}, idx={self.chunk_index}>'

    def to_dict(self, include_content=True):
        """Convert to dictionary for API responses."""
        result = {
            'id': self.id,
            'document_id': self.document_id,
            'chunk_index': self.chunk_index,
            'page_number': self.page_number,
            'section_title': self.section_title,
            'content_length': self.content_length,
            'token_count': self.token_count,
            'chunk_type': self.chunk_type,
            'semantic_type': self.semantic_type,
            'heading_hierarchy': self.heading_hierarchy,
            'confidence_score': self.confidence_score,
            'metadata': self.extra_metadata,
        }
        if include_content:
            result['content'] = self.content
        return result


class AIEmbedding(db.Model):
    """
    Stores vector embeddings for document chunks.

    Uses pgvector extension for efficient similarity search.
    """
    __tablename__ = 'ai_embeddings'

    id = Column(Integer, primary_key=True)

    # Parent document and chunk
    document_id = Column(Integer, ForeignKey('ai_documents.id', ondelete='CASCADE'), nullable=False, index=True)
    document = relationship('AIDocument', back_populates='embeddings')

    chunk_id = Column(Integer, ForeignKey('ai_document_chunks.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)
    chunk = relationship('AIDocumentChunk', back_populates='embedding')

    # Embedding vector (pgvector)
    # Dimension depends on model: 1536 for text-embedding-3-small, 384 for all-MiniLM-L6-v2
    embedding = Column(Vector(1536), nullable=False)  # Default to OpenAI dimensions

    # Embedding metadata
    model = Column(String(100), nullable=False)  # Model used to generate embedding
    dimensions = Column(Integer, nullable=False)  # Actual dimensions

    # Versioning: allows gradual re-embedding when model changes
    embedding_version = Column(String(20), nullable=True)  # e.g. "v1", "v2" — incremented on model upgrades
    is_stale = Column(Boolean, default=False, nullable=False)  # True = needs regeneration after model change

    # Generation metadata
    generated_at = Column(DateTime, default=utcnow, nullable=False)
    generation_cost_usd = Column(Float, nullable=True)  # Track API costs

    # Timestamps
    created_at = Column(DateTime, default=utcnow, nullable=False)

    def __repr__(self):
        return f'<AIEmbedding {self.id}: chunk={self.chunk_id}, model={self.model}>'

    # Create indexes for vector similarity search
    __table_args__ = (
        Index('idx_ai_embeddings_vector_cosine', 'embedding', postgresql_using='ivfflat', postgresql_with={'lists': 100}, postgresql_ops={'embedding': 'vector_cosine_ops'}),
    )


class IndicatorBankEmbedding(db.Model):
    """
    Vector embedding for one Indicator Bank entry. Used for semantic indicator resolution:
    user phrase (e.g. "volunteers") is embedded and matched by cosine similarity to the
    best indicator(s). Dimensions must match AI_EMBEDDING_DIMENSIONS (e.g. 1536).
    """
    __tablename__ = 'indicator_bank_embeddings'

    id = Column(Integer, primary_key=True)
    indicator_bank_id = Column(Integer, ForeignKey('indicator_bank.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)
    indicator_bank = relationship('IndicatorBank', backref=backref('embedding', uselist=False, lazy='select'))

    embedding = Column(Vector(1536), nullable=False)
    text_embedded = Column(Text, nullable=True)  # name + definition + unit used to generate embedding
    model = Column(String(100), nullable=False)
    dimensions = Column(Integer, nullable=False)
    generation_cost_usd = Column(Float, nullable=True)
    generated_at = Column(DateTime, default=utcnow, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    def __repr__(self):
        return f'<IndicatorBankEmbedding {self.id}: indicator_bank_id={self.indicator_bank_id}>'

    __table_args__ = (
        Index('idx_indicator_bank_embeddings_vector_cosine', 'embedding', postgresql_using='ivfflat', postgresql_with={'lists': 50}, postgresql_ops={'embedding': 'vector_cosine_ops'}),
    )


class AIReasoningTrace(db.Model):
    """
    Logs agent reasoning steps for transparency and debugging.

    Stores the complete thought process and tool usage for each agent query.
    """
    __tablename__ = 'ai_reasoning_traces'

    id = Column(Integer, primary_key=True)

    # Link to conversation (optional). FK enforces referential integrity; SET NULL on conversation delete.
    conversation_id = Column(String(36), ForeignKey('ai_conversation.id', ondelete='SET NULL'), nullable=True, index=True)
    conversation = relationship('AIConversation', backref='reasoning_traces', foreign_keys=[conversation_id])

    # User context
    user_id = Column(Integer, ForeignKey('user.id', ondelete='CASCADE'), nullable=True, index=True)
    user = relationship('User', backref='reasoning_traces', foreign_keys=[user_id])

    # Query (as sent to agent; may be rewritten from user message)
    query = Column(Text, nullable=False)
    # Original user message before any query rewriting (when different from query)
    original_query = Column(Text, nullable=True)
    query_language = Column(String(10), default='en')

    # Agent execution
    agent_mode = Column(String(50), default='react', nullable=False)  # react, function_calling
    max_iterations = Column(Integer, default=10)
    actual_iterations = Column(Integer, default=0)

    # Execution status
    status = Column(String(50), default='completed', nullable=False, index=True)
    # Status values: completed, timeout, error, cost_limit_exceeded, max_iterations_exceeded

    error_message = Column(Text, nullable=True)

    # Reasoning steps (JSON array)
    steps = Column(JSON, nullable=False)
    # Format: [
    #   {
    #     "step": 1,  // monotonic index (1, 2, 3, ...) per step
    #     "thought": "I need to get Kenya volunteer data",
    #     "action": "get_indicator_value",
    #     "action_input": {"country": "Kenya", "indicator": "volunteers"},
    #     "observation": { ... },  // full tool result
    #     "timestamp": "2024-01-15T10:30:00Z",
    #     "execution_time_ms": 123.45,  // optional, from tool result
    #     "observation_summary": {"row_count": 192, "execution_time_ms": 1389}  // optional, for analytics
    #   },
    #   ...
    # ]

    # Tools used
    tools_used = Column(JSON, nullable=True)  # ['get_indicator_value', 'search_documents']
    tool_call_count = Column(Integer, default=0)

    # Cost tracking
    total_input_tokens = Column(Integer, default=0)
    total_output_tokens = Column(Integer, default=0)
    total_cost_usd = Column(Float, nullable=True)

    # Timing
    execution_time_ms = Column(Integer, nullable=True)

    # Final answer
    final_answer = Column(Text, nullable=True)

    # LLM provider
    llm_provider = Column(String(50), nullable=True)  # openai, gemini, etc.
    llm_model = Column(String(100), nullable=True)

    # Execution path: fast_path, openai_native, react, agent_disabled (for analytics)
    execution_path = Column(String(50), nullable=True, index=True)

    # Structured output payloads returned to client (map, chart, table, etc.)
    output_payloads = Column(JSON, nullable=True)  # map_payload, chart_payload, answer_content, output_hint, plan_kind

    # User feedback for quality improvement (recorded from chat UI)
    user_rating = Column(String(20), nullable=True, index=True)  # 'like' | 'dislike'

    # Quality metrics (computed post-answer)
    grounding_score = Column(Float, nullable=True)   # 0.0–1.0: fraction of answer claims supported by retrieved sources
    confidence_level = Column(String(20), nullable=True)  # 'high' | 'medium' | 'low'

    # LLM-as-judge evaluation (gated by AI_GROUNDING_LLM_ENABLED)
    llm_quality_score = Column(Float, nullable=True)        # 0.0–1.0: LLM-assessed overall response quality
    llm_quality_verdict = Column(String(30), nullable=True)  # 'excellent' | 'good' | 'acceptable' | 'poor' | 'incorrect'
    llm_quality_reasoning = Column(Text, nullable=True)      # LLM's explanation of its assessment
    llm_needs_review = Column(Boolean, nullable=True)        # True when LLM flags the response for human review

    # Timestamps
    created_at = Column(DateTime, default=utcnow, nullable=False, index=True)

    def __repr__(self):
        return f'<AIReasoningTrace {self.id}: {self.query[:50]}...>'

    @property
    def display_answer(self):
        """Answer text to show in UI: final_answer, or fallback from steps/output_payloads."""
        if self.final_answer and (self.final_answer or "").strip():
            return self.final_answer
        steps = self.steps if isinstance(self.steps, list) else []
        for s in reversed(steps):
            if not isinstance(s, dict):
                continue
            if (s.get("action") or "").strip().lower() != "finish":
                continue
            obs = s.get("observation")
            if isinstance(obs, dict) and (obs.get("answer") or "").strip():
                return obs.get("answer") or ""
            if isinstance(obs, str) and obs.strip():
                return obs
            break
        payloads = self.output_payloads if isinstance(self.output_payloads, dict) else {}
        ac = payloads.get("answer_content") if isinstance(payloads.get("answer_content"), dict) else None
        if ac:
            kind = (ac.get("kind") or "").strip().lower()
            if kind == "single_value":
                country = (ac.get("country_name") or "").strip() or "—"
                name = (ac.get("indicator_name") or "").strip() or "—"
                val = ac.get("value")
                period = (ac.get("period") or "").strip()
                pt = f" ({period})" if period else ""
                return f"**{country}{pt} — {name}:** {val}"
            if kind == "documents":
                total = ac.get("total", 0)
                return f"Found {total} document(s)."
            if kind == "country_list":
                countries = ac.get("countries") or []
                preview = ", ".join(str(c) for c in countries[:15])
                more = f" (+{len(countries) - 15} more)" if len(countries) > 15 else ""
                return f"Countries: {preview}{more}."
            if kind == "per_country_values":
                rows = ac.get("rows") or []
                metric = (ac.get("metric") or "Value").strip() or "Value"
                return f"Per-country values: {metric} ({len(rows)} countries)."
            if kind == "time_series":
                series = ac.get("series") or []
                metric = (ac.get("metric") or "value").strip() or "value"
                country = (ac.get("country") or "").strip()
                return f"Time series: {metric}" + (f" in {country}" if country else "") + f" ({len(series)} points)."
        return ""

    def to_dict(self, include_steps=True):
        """Convert to dictionary for API responses."""
        result = {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'query': self.query,
            'original_query': self.original_query,
            'query_language': self.query_language,
            'agent_mode': self.agent_mode,
            'status': self.status,
            'error_message': self.error_message,
            'actual_iterations': self.actual_iterations,
            'tools_used': self.tools_used,
            'tool_call_count': self.tool_call_count,
            'total_input_tokens': self.total_input_tokens,
            'total_output_tokens': self.total_output_tokens,
            'total_cost_usd': self.total_cost_usd,
            'execution_time_ms': self.execution_time_ms,
            'llm_provider': self.llm_provider,
            'llm_model': self.llm_model,
            'execution_path': self.execution_path,
            'output_payloads': self.output_payloads,
            'user_rating': self.user_rating,
            'grounding_score': self.grounding_score,
            'confidence_level': self.confidence_level,
            'llm_quality_score': self.llm_quality_score,
            'llm_quality_verdict': self.llm_quality_verdict,
            'llm_quality_reasoning': self.llm_quality_reasoning,
            'llm_needs_review': self.llm_needs_review,
            'max_iterations': self.max_iterations,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
        # Always include final_answer so it is available in list and detail views
        result['final_answer'] = self.final_answer
        if include_steps:
            result['steps'] = self.steps
        return result


class AIToolUsage(db.Model):
    """
    Tracks individual tool usage for analytics and monitoring.

    Helps identify popular tools, failure rates, and performance issues.
    """
    __tablename__ = 'ai_tool_usage'

    id = Column(Integer, primary_key=True)

    # Link to reasoning trace
    trace_id = Column(Integer, ForeignKey('ai_reasoning_traces.id', ondelete='CASCADE'), nullable=True, index=True)

    # Tool details
    tool_name = Column(String(100), nullable=False, index=True)
    tool_input = Column(JSON, nullable=True)  # Parameters passed to tool
    tool_output = Column(JSON, nullable=True)  # Result from tool (truncated if large)

    # Execution
    success = Column(Boolean, default=True, nullable=False, index=True)
    error_message = Column(Text, nullable=True)
    execution_time_ms = Column(Integer, nullable=True)

    # User context
    user_id = Column(Integer, ForeignKey('user.id', ondelete='SET NULL'), nullable=True, index=True)

    # Timestamps
    created_at = Column(DateTime, default=utcnow, nullable=False, index=True)

    def __repr__(self):
        return f'<AIToolUsage {self.id}: {self.tool_name}>'


class AITraceReview(db.Model):
    """
    Expert review record for an AI reasoning trace.

    Created automatically when grounding_score is below threshold (auto-queue),
    or manually by admins via the review queue UI.
    Stores reviewer verdict, notes, and an optional ground-truth answer for regression testing.
    """
    __tablename__ = 'ai_trace_reviews'

    id = Column(Integer, primary_key=True)

    # Link to trace being reviewed
    trace_id = Column(Integer, ForeignKey('ai_reasoning_traces.id', ondelete='CASCADE'), nullable=False, index=True)
    trace = relationship('AIReasoningTrace', backref='reviews', foreign_keys=[trace_id])

    # Reviewer assignment
    reviewer_id = Column(Integer, ForeignKey('user.id', ondelete='SET NULL'), nullable=True, index=True)
    reviewer = relationship('User', backref='ai_trace_reviews', foreign_keys=[reviewer_id])

    # Review workflow
    status = Column(String(30), default='pending', nullable=False, index=True)
    # Values: pending | in_review | completed | dismissed

    # Verdict recorded by reviewer
    verdict = Column(String(30), nullable=True)
    # Values: correct | partially_correct | incorrect | needs_improvement

    reviewer_notes = Column(Text, nullable=True)

    # Ground-truth answer: used as a golden pair for regression testing
    ground_truth_answer = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=utcnow, nullable=False, index=True)
    assigned_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f'<AITraceReview {self.id}: trace={self.trace_id} status={self.status}>'

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'trace_id': self.trace_id,
            'reviewer_id': self.reviewer_id,
            'status': self.status,
            'verdict': self.verdict,
            'reviewer_notes': self.reviewer_notes,
            'ground_truth_answer': self.ground_truth_answer,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'assigned_at': self.assigned_at.isoformat() if self.assigned_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }
