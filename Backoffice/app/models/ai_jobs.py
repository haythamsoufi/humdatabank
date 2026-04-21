"""
Generic queued/batch job models for the AI system.

Purpose:
- Avoid creating a new pair of tables for each new queued/batch workflow.
- Support polling/resume/cancel semantics from the UI.

This is intentionally generic. Use `job_type` and JSON `meta`/`payload` to store
workflow-specific details.
"""

from __future__ import annotations

from sqlalchemy import Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.extensions import db
from app.utils.datetime_helpers import utcnow


class AIJob(db.Model):
    __tablename__ = "ai_jobs"

    id = db.Column(db.String(36), primary_key=True)  # uuid4 string
    job_type = db.Column(db.String(64), nullable=False, index=True)  # e.g. "docs.bulk_reprocess"

    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    user = relationship("User", foreign_keys=[user_id])

    status = db.Column(db.String(32), nullable=False, default="queued", index=True)
    # statuses: queued, running, completed, failed, cancel_requested, cancelled

    total_items = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)

    error = db.Column(db.Text, nullable=True)
    meta = db.Column(JSONB, nullable=True)  # job-level settings (concurrency, etc.)

    items = relationship(
        "AIJobItem",
        back_populates="job",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="AIJobItem.item_index.asc()",
    )


class AIJobItem(db.Model):
    __tablename__ = "ai_job_items"

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.String(36), db.ForeignKey("ai_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    job = relationship("AIJob", back_populates="items", foreign_keys=[job_id])

    item_index = db.Column(db.Integer, nullable=False)  # 0-based stable order within a job

    entity_type = db.Column(db.String(64), nullable=True, index=True)  # e.g. "ai_document"
    entity_id = db.Column(db.Integer, nullable=True, index=True)

    status = db.Column(db.String(32), nullable=False, default="queued", index=True)
    # statuses: queued, downloading, processing, completed, failed, cancelled
    error = db.Column(db.Text, nullable=True)

    payload = db.Column(JSONB, nullable=True)  # workflow-specific input for this item

    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        Index("ix_ai_job_items_job_index", "job_id", "item_index", unique=True),
    )

