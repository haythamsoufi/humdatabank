"""
AI validation models.

Stores AI-generated "opinions" for validating a reported FormData value
against documents available in the AI Knowledge Base (RAG).

Design:
- Latest-only per target:
  - persisted FormData rows (unique on form_data_id)
  - OR virtual "missing" rows addressed by (assignment_entity_status_id, form_item_id)
"""

from __future__ import annotations

from app.extensions import db
from app.utils.datetime_helpers import utcnow


class AIFormDataValidation(db.Model):
    __tablename__ = "ai_formdata_validation"

    id = db.Column(db.Integer, primary_key=True)

    # Latest-only opinion for a specific persisted FormData row (optional for virtual missing rows)
    form_data_id = db.Column(
        db.Integer,
        db.ForeignKey("form_data.id", ondelete="CASCADE"),
        nullable=True,
        unique=True,
        index=True,
    )

    # Virtual (non-reported) target for Explore Data: (assignment_entity_status_id, form_item_id)
    # NOTE: This does NOT create any FormData rows; it only stores the AI opinion/suggestion.
    assignment_entity_status_id = db.Column(
        db.Integer,
        db.ForeignKey("assignment_entity_status.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    form_item_id = db.Column(
        db.Integer,
        db.ForeignKey("form_item.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Execution status of the validation run (completed | failed | pending)
    status = db.Column(db.String(32), nullable=False, default="completed", index=True)

    # Verdict of the validation (good | discrepancy | uncertain)
    verdict = db.Column(db.String(32), nullable=True, index=True)

    confidence = db.Column(db.Float, nullable=True)
    opinion_text = db.Column(db.Text, nullable=True)

    # Evidence/citations for UI display and auditability.
    # Stored as JSON (chunks + doc ids/pages + scores + snippets).
    evidence = db.Column(db.JSON, nullable=True)

    provider = db.Column(db.String(32), nullable=True)
    model = db.Column(db.String(128), nullable=True)

    run_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False, index=True)

    __table_args__ = (
        # Either validate a persisted FormData row OR a virtual missing item identified by AES+FormItem.
        db.CheckConstraint(
            "(form_data_id IS NOT NULL) OR (assignment_entity_status_id IS NOT NULL AND form_item_id IS NOT NULL)",
            name="ck_ai_formdata_validation_target",
        ),
        db.UniqueConstraint(
            "assignment_entity_status_id",
            "form_item_id",
            name="uq_ai_formdata_validation_aes_item",
        ),
    )

    # Relationships
    form_data = db.relationship("FormData", backref=db.backref("ai_validation", uselist=False, lazy="select"))
    assignment_entity_status = db.relationship("AssignmentEntityStatus", foreign_keys=[assignment_entity_status_id])
    form_item = db.relationship("FormItem", foreign_keys=[form_item_id])
    run_by_user = db.relationship("User", foreign_keys=[run_by_user_id])

    def __repr__(self) -> str:
        if self.form_data_id:
            target = f"form_data_id={self.form_data_id}"
        else:
            target = f"aes_id={self.assignment_entity_status_id} form_item_id={self.form_item_id}"
        return f"<AIFormDataValidation {target} verdict={self.verdict} status={self.status}>"
