"""Persisted governance findings.

Controls themselves live in code (see governance_program). This table is the
register: one row per control, updated whenever the register is evaluated.
A gap stays open until the check passes, or until someone records a risk
acceptance with a reason and a review date.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Date, JSON, ForeignKey
from sqlalchemy.orm import relationship

from app.extensions import db
from app.utils.datetime_helpers import utcnow


class GovernanceIssue(db.Model):
    """One finding for one control.

    ``fingerprint`` is the control code. Aggregate controls produce one issue,
    not one row per country or user. The evidence list on the row is the work
    queue; the row is the decision record.
    """

    __tablename__ = "governance_issue"

    id = Column(Integer, primary_key=True)
    control_code = Column(String(32), nullable=False)
    fingerprint = Column(String(80), nullable=False)
    title = Column(String(255), nullable=False)
    severity = Column(String(20), nullable=False)  # critical, high, medium
    status = Column(String(20), nullable=False, default="open")  # open, accepted, resolved

    summary = Column(Text, nullable=True)
    failing_count = Column(Integer, nullable=False, default=0)
    evidence = Column(JSON, nullable=True)

    opened_at = Column(DateTime, nullable=False, default=utcnow)
    last_seen_at = Column(DateTime, nullable=False, default=utcnow)
    reopened_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    resolution = Column(String(40), nullable=True)  # control_passed, control_not_applicable, control_retired

    accepted_by_user_id = Column(Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    accepted_at = Column(DateTime, nullable=True)
    acceptance_reason = Column(Text, nullable=True)
    accepted_until = Column(Date, nullable=True)

    accepted_by = relationship("User", foreign_keys=[accepted_by_user_id])

    __table_args__ = (
        db.UniqueConstraint("fingerprint", name="uq_governance_issue_fingerprint"),
        db.Index("ix_governance_issue_status", "status"),
        db.Index("ix_governance_issue_control", "control_code"),
    )

    def __repr__(self):
        return f"<GovernanceIssue {self.control_code} {self.status}>"
