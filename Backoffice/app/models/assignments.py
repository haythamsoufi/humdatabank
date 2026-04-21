"""
Assignment-related models for form assignments and public submissions.
"""
import logging
from datetime import datetime

logger = logging.getLogger(__name__)
from sqlalchemy import Column, Integer, ForeignKey, String, DateTime, Date, Boolean, Enum
from sqlalchemy.orm import relationship, backref, foreign
from sqlalchemy import and_
from ..extensions import db
from .enums import PublicSubmissionStatus
from app.utils.datetime_helpers import utcnow


class AssignedForm(db.Model):
    __tablename__ = 'assigned_form'
    id = Column(Integer, primary_key=True)
    template_id = Column(Integer, ForeignKey('form_template.id'), nullable=False)
    period_name = Column(String(100), nullable=False)
    assigned_at = Column(DateTime, default=utcnow)

    # Assignment active state (inactive assignments are hidden from normal use)
    is_active = Column(Boolean, default=True, nullable=False)
    # Closed state: closed assignments (e.g. after one year) can be reopened by admins
    is_closed = Column(Boolean, default=False, nullable=False)
    # Expiry date: after this date the assignment is treated as Closed (optional)
    expiry_date = Column(Date, nullable=True)
    # Public URL fields for unified assignment system
    unique_token = Column(String(36), unique=True, nullable=True)  # UUID for public URL
    is_public_active = Column(Boolean, default=False, nullable=False)  # Public URL status

    # Data ownership governance
    data_owner_id = Column(Integer, ForeignKey('user.id', ondelete='SET NULL'), nullable=True)

    # Activation audit — who toggled is_active or closed/reopened this assignment
    activated_by_user_id = Column(Integer, ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
    deactivated_by_user_id = Column(Integer, ForeignKey('user.id', ondelete='SET NULL'), nullable=True)

    data_owner_user = relationship('User', foreign_keys=[data_owner_id])
    activated_by_user = relationship('User', foreign_keys=[activated_by_user_id])
    deactivated_by_user = relationship('User', foreign_keys=[deactivated_by_user_id])

    # Relationship to country-specific AssignmentEntityStatus entries (filtered view)
    country_statuses = relationship(
        'AssignmentEntityStatus',
        primaryjoin=lambda: and_(AssignedForm.id == foreign(AssignmentEntityStatus.assigned_form_id),
                                 AssignmentEntityStatus.entity_type == 'country'),
        lazy='dynamic',
        viewonly=True
    )

    # Relationship to public submissions (for unified assignment system)
    public_submissions = relationship('PublicSubmission', backref='assigned_form', lazy='dynamic', cascade="all, delete-orphan")

    __table_args__ = (
        db.Index('ix_assigned_form_template_period', 'template_id', 'period_name'),
        db.Index('ix_assigned_form_public_token', 'unique_token'),
        db.Index('ix_assigned_form_public_active', 'is_public_active'),
        db.Index('ix_assigned_form_assigned_at', 'assigned_at'),
        db.Index('ix_assigned_form_is_active', 'is_active'),
        db.Index('ix_assigned_form_data_owner', 'data_owner_id'),
        db.Index('ix_assigned_form_activated_by', 'activated_by_user_id'),
        db.Index('ix_assigned_form_deactivated_by', 'deactivated_by_user_id'),
    )

    @property
    def earliest_due_date(self):
        """Return the earliest non-null due_date across all entity statuses."""
        row = (
            AssignmentEntityStatus.query
            .filter_by(assigned_form_id=self.id)
            .filter(AssignmentEntityStatus.due_date.isnot(None))
            .order_by(AssignmentEntityStatus.due_date.asc())
            .with_entities(AssignmentEntityStatus.due_date)
            .first()
        )
        return row[0] if row else None

    @property
    def has_multiple_due_dates(self):
        """True when entities have more than one distinct due_date."""
        from sqlalchemy import func
        count = (
            AssignmentEntityStatus.query
            .filter_by(assigned_form_id=self.id)
            .filter(AssignmentEntityStatus.due_date.isnot(None))
            .with_entities(func.count(func.distinct(AssignmentEntityStatus.due_date)))
            .scalar()
        )
        return count > 1

    @property
    def countries(self):
        """Get countries for country-level entity statuses (AES)."""
        return [aes.country for aes in self.country_statuses.all() if aes.country]

    @property
    def public_countries(self):
        """Get countries that are available for public reporting (AES)."""
        return [aes.country for aes in self.country_statuses.filter_by(is_public_available=True).all() if aes.country]

    def add_country(self, country):
        """Add a country to this assignment by creating an AssignmentEntityStatus entry."""
        existing_aes = AssignmentEntityStatus.query.filter_by(
            assigned_form_id=self.id,
            entity_type='country',
            entity_id=country.id
        ).first()
        if not existing_aes:
            new_aes = AssignmentEntityStatus(
                assigned_form_id=self.id,
                entity_type='country',
                entity_id=country.id,
                status='Pending'
            )
            db.session.add(new_aes)
            return new_aes
        return existing_aes

    def remove_country(self, country):
        """Remove a country from this assignment by deleting the AES entry."""
        existing_aes = AssignmentEntityStatus.query.filter_by(
            assigned_form_id=self.id,
            entity_type='country',
            entity_id=country.id
        ).first()
        if existing_aes:
            db.session.delete(existing_aes)
            return True
        return False

    def generate_public_url(self):
        """Generate a unique token for public URL access."""
        import uuid
        if not self.unique_token:
            self.unique_token = str(uuid.uuid4())
        return self.unique_token

    def get_public_url(self, external=True):
        """Get the public URL for this assignment."""
        if not self.unique_token:
            return None
        from flask import url_for
        return url_for('forms.fill_public_form', public_token=self.unique_token, _external=external)

    def has_public_url(self):
        """Check if this assignment has a public URL generated."""
        return self.unique_token is not None

    def is_public_accessible(self):
        """Check if the public URL is active and accessible."""
        return self.has_public_url() and self.is_public_active

    @property
    def is_effectively_closed(self):
        """True if assignment is explicitly closed or past its expiry date."""
        if self.is_closed:
            return True
        if self.expiry_date is None:
            return False
        today = utcnow().date()
        return self.expiry_date < today

    def toggle_public_access(self):
        """Toggle the public access status."""
        if self.has_public_url():
            self.is_public_active = not self.is_public_active
        return self.is_public_active

    def __repr__(self):
        country_names = ", ".join([c.name for c in self.countries]) if self.countries else "N/A"
        template_name = self.template.name if self.template else "N/A"
        public_status = " (Public)" if self.is_public_accessible() else ""
        return f'<AssignedForm {template_name} for {country_names} ({self.period_name}){public_status}>'


class AssignmentEntityStatus(db.Model):
    """Track assignment status for any organizational entity (polymorphic).

    This model replaces AssignmentCountryStatus with support for multiple entity types.
    """
    __tablename__ = 'assignment_entity_status'

    id = db.Column(db.Integer, primary_key=True)
    assigned_form_id = db.Column(db.Integer, db.ForeignKey('assigned_form.id'), nullable=False)

    # Polymorphic entity reference
    entity_type = db.Column(db.String(50), nullable=False)  # 'country', 'ns_branch', 'ns_subbranch', etc.
    entity_id = db.Column(db.Integer, nullable=False)

    status = db.Column(db.String(50), default='Pending')
    status_timestamp = db.Column(db.DateTime, default=db.func.now())
    due_date = db.Column(db.DateTime, nullable=True)
    is_public_available = db.Column(db.Boolean, default=False, nullable=False)

    # Submission / approval accountability — who changed status to Submitted / Approved
    submitted_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
    approved_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
    # Separate timestamp for when the form was submitted (status_timestamp is overwritten on approval)
    submitted_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    assigned_form = relationship('AssignedForm', backref=db.backref('entity_statuses', lazy='dynamic', cascade="all, delete-orphan"))
    submitted_by_user = db.relationship('User', foreign_keys=[submitted_by_user_id])
    approved_by_user = db.relationship('User', foreign_keys=[approved_by_user_id])

    # Relationship to FormData
    data_entries = relationship('FormData', lazy='dynamic', cascade="all, delete-orphan", foreign_keys='FormData.assignment_entity_status_id')

    # Relationship to SubmittedDocuments
    submitted_documents = relationship('SubmittedDocument', lazy='dynamic', cascade="all, delete-orphan", foreign_keys='SubmittedDocument.assignment_entity_status_id')

    __table_args__ = (
        db.UniqueConstraint('assigned_form_id', 'entity_type', 'entity_id', name='_assigned_entity_uc'),
        db.Index('ix_aes_assigned_form', 'assigned_form_id'),
        db.Index('ix_aes_entity', 'entity_type', 'entity_id'),
        db.Index('ix_aes_status', 'status'),
        db.Index('ix_aes_is_public_available', 'is_public_available'),
        db.Index('ix_aes_due_date', 'due_date'),
        db.Index('ix_aes_status_timestamp', 'status_timestamp'),
        db.Index('ix_aes_submitted_by', 'submitted_by_user_id'),
        db.Index('ix_aes_approved_by', 'approved_by_user_id'),
        db.Index('ix_aes_submitted_at', 'submitted_at'),
    )

    @property
    def entity(self):
        """Get the actual entity object based on entity_type and entity_id."""
        from app.services.entity_service import EntityService
        return EntityService.get_entity(self.entity_type, self.entity_id)

    @property
    def country(self):
        """Get the related country for this entity.

        For backward compatibility and to get the country regardless of entity type.
        Returns the actual Country object if entity_type is 'country', or the parent
        country for NS branches/departments.
        """
        from app.services.entity_service import EntityService
        return EntityService.get_country_for_entity(self.entity_type, self.entity_id)

    @property
    def country_id(self):
        """Compatibility helper for legacy code that expects a country_id field."""
        # If entity_type is 'country', entity_id is the country_id
        if self.entity_type == 'country':
            return self.entity_id

        # For other entity types, try to get country through the country property
        try:
            c = self.country
            if c and hasattr(c, 'id'):
                return c.id
        except Exception as e:
            logger.debug("country property failed (detached instance?): %s", e)
        return None

    def __repr__(self):
        entity_info = f"{self.entity_type}:{self.entity_id}"
        return f'<AssignmentEntityStatus Assignment:{self.assigned_form_id}, Entity:{entity_info}, Status:{self.status}>'


class PublicSubmission(db.Model):
    __tablename__ = 'public_submission'
    id = db.Column(db.Integer, primary_key=True)
    assigned_form_id = db.Column(db.Integer, db.ForeignKey('assigned_form.id'), nullable=True)
    country_id = db.Column(db.Integer, db.ForeignKey('country.id'), nullable=False)
    submitted_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    status = db.Column(Enum(PublicSubmissionStatus), default=PublicSubmissionStatus.pending, nullable=False)
    submitter_name = db.Column(db.String(255), nullable=True)
    submitter_email = db.Column(db.String(255), nullable=True)

    # Relationships to the data and documents submitted as part of this submission
    data_entries = relationship('FormData', lazy='dynamic', cascade="all, delete-orphan")
    submitted_documents = relationship('SubmittedDocument', lazy='dynamic', cascade="all, delete-orphan")

    __table_args__ = (
        db.Index('ix_public_submission_assigned_country', 'assigned_form_id', 'country_id'),
        db.Index('ix_public_submission_submitted_at', 'submitted_at'),
        db.Index('ix_public_submission_status', 'status'),
        db.Index('ix_public_submission_submitter_email', 'submitter_email'),
    )

    def __repr__(self):
        assignment_info = f"AssignedForm:{self.assigned_form_id}" if self.assigned_form_id else "NoAssignment"
        country_name = self.country.name if self.country else 'N/A'
        return f'<PublicSubmission ID:{self.id} {assignment_info} Country:{country_name} Status:{self.status.value}>'
