"""FDRS tables that are not part of the shared form schema."""

from __future__ import annotations

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

from app.extensions import db
from app.utils.datetime_helpers import utcnow


class EveryoneCountsSnapshot(db.Model):
    """Saved Everyone Counts calculation for one form template.

    Opening the data-explorer tab reads this row. A refresh builds a new
    payload in the background and replaces it only when that build finishes.
    """

    __tablename__ = "fdrs_everyone_counts_snapshot"

    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, nullable=False, unique=True)
    status = db.Column(db.String(20), nullable=False, default="empty")
    payload = db.Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    error = db.Column(db.Text, nullable=True)
    build_token = db.Column(db.String(64), nullable=True)
    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)
    built_at = db.Column(db.DateTime, nullable=True)
    built_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    def __repr__(self) -> str:
        return f"<EveryoneCountsSnapshot template={self.template_id} status={self.status}>"
