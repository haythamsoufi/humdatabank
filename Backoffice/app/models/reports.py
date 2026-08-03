"""Report builder models — persisted report definitions and publish runs."""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import JSONB

from app.extensions import db
from app.utils.datetime_helpers import utcnow


class ReportDefinition(db.Model):
    """User-defined report composed of sections and widgets."""

    __tablename__ = "report_definition"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(120), nullable=False, unique=True, index=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)

    definition_json = db.Column(
        db.JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=dict,
    )
    schema_version = db.Column(db.Integer, nullable=False, default=1)
    status = db.Column(db.String(32), nullable=False, default="draft", index=True)
    # draft | published | archived

    owner_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    scope_json = db.Column(
        db.JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=dict,
    )

    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    published_at = db.Column(db.DateTime, nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    updated_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    owner = db.relationship("User", foreign_keys=[owner_user_id])
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    updated_by = db.relationship("User", foreign_keys=[updated_by_id])

    runs = db.relationship(
        "ReportRun",
        back_populates="report",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    __table_args__ = (
        db.Index("ix_report_definition_owner_status", "owner_user_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<ReportDefinition {self.slug!r} ({self.status})>"


class ReportRun(db.Model):
    """Background publish run producing static report artifacts."""

    __tablename__ = "report_run"

    id = db.Column(db.String(36), primary_key=True)  # uuid4
    report_id = db.Column(
        db.Integer,
        db.ForeignKey("report_definition.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status = db.Column(db.String(32), nullable=False, default="queued", index=True)
    # queued | running | completed | failed | cancelled
    build_stage = db.Column(db.String(64), nullable=True)
    error = db.Column(db.Text, nullable=True)
    output_paths = db.Column(
        db.JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )
    triggered_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)

    report = db.relationship("ReportDefinition", back_populates="runs")
    triggered_by = db.relationship("User", foreign_keys=[triggered_by_id])

    def __repr__(self) -> str:
        return f"<ReportRun {self.id!r} report={self.report_id} status={self.status!r}>"
