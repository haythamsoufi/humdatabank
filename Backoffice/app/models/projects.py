"""Core project registry for project-based periodic reporting.

Assignments can target ``entity_type='project'`` (see ``EntityType.project``).
Plugins (e.g. NSD funds) upsert rows and attach schedule-driven submissions;
admins can also manage projects and add them to assignments in the UI.
"""

from __future__ import annotations

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

from app.extensions import db
from app.models.enums import EntityType
from app.utils.datetime_helpers import utcnow


class Project(db.Model):
    """A reportable project / funded initiative (country is geography, not the reporter)."""

    __tablename__ = "project"

    id = db.Column(db.Integer, primary_key=True)
    reference = db.Column(db.String(80), nullable=False, unique=True)
    # Owning team / portfolio (e.g. NSD). Distinct from fund (CBF, NSIA, …).
    portfolio = db.Column(db.String(40), nullable=True)
    # Optional programme tag (e.g. CBF, NSIA) — free text for filtering
    fund = db.Column(db.String(40), nullable=True)
    title = db.Column(db.String(500), nullable=True)
    country_id = db.Column(db.Integer, db.ForeignKey("country.id", ondelete="RESTRICT"), nullable=False)
    # Display name of the implementing NS when useful (not a FK — NS matching varies by fund)
    organization_name = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(40), nullable=False, default="Open")
    funding_modality = db.Column(db.String(120), nullable=True)
    categories = db.Column(db.Text, nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    amount_granted = db.Column(db.Numeric(14, 2), nullable=True)
    expected_spending = db.Column(db.Numeric(14, 2), nullable=True)
    planned_overview = db.Column(db.Text, nullable=True)
    focal_name = db.Column(db.String(255), nullable=True)
    focal_email = db.Column(db.String(255), nullable=True)
    manager_name = db.Column(db.String(255), nullable=True)
    manager_email = db.Column(db.String(255), nullable=True)
    # Optional structured plan (e.g. logframe JSON); plugins interpret shape
    plan_data = db.Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    country = db.relationship("Country", foreign_keys=[country_id])

    __table_args__ = (
        db.Index("ix_project_country", "country_id"),
        db.Index("ix_project_status", "status"),
        db.Index("ix_project_portfolio", "portfolio"),
        db.Index("ix_project_fund", "fund"),
        db.Index("ix_project_manager_email", "manager_email"),
        db.Index("ix_project_focal_email", "focal_email"),
    )

    # --- compatibility aliases used by the NSD plugin (same semantics) ---
    @property
    def national_society_name(self):
        return self.organization_name

    @national_society_name.setter
    def national_society_name(self, value):
        self.organization_name = value

    @property
    def amount_granted_chf(self):
        return self.amount_granted

    @amount_granted_chf.setter
    def amount_granted_chf(self, value):
        self.amount_granted = value

    @property
    def expected_spending_chf(self):
        return self.expected_spending

    @expected_spending_chf.setter
    def expected_spending_chf(self, value):
        self.expected_spending = value

    @property
    def ns_focal_name(self):
        return self.focal_name

    @ns_focal_name.setter
    def ns_focal_name(self, value):
        self.focal_name = value

    @property
    def ns_focal_email(self):
        return self.focal_email

    @ns_focal_email.setter
    def ns_focal_email(self, value):
        self.focal_email = value

    @property
    def ifrc_pm_name(self):
        return self.manager_name

    @ifrc_pm_name.setter
    def ifrc_pm_name(self, value):
        self.manager_name = value

    @property
    def ifrc_pm_email(self):
        return self.manager_email

    @ifrc_pm_email.setter
    def ifrc_pm_email(self, value):
        self.manager_email = value

    @property
    def logframe(self):
        return self.plan_data

    @logframe.setter
    def logframe(self, value):
        self.plan_data = value

    @property
    def name(self) -> str:
        title = (self.title or "").strip()
        if title:
            return f"{self.reference} — {title}"
        return self.reference

    @property
    def is_open(self) -> bool:
        return (self.status or "") in ("Open", "Active")

    @property
    def entity_type(self) -> str:
        return EntityType.project.value

    def __repr__(self) -> str:
        return f"<Project {self.reference} country={self.country_id}>"
