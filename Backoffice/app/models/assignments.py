"""
Assignment-related models for form assignments and public submissions.
"""
import logging
from datetime import datetime

logger = logging.getLogger(__name__)
from sqlalchemy import Column, Integer, ForeignKey, String, DateTime, Date, Boolean, Enum, JSON, and_, or_
from sqlalchemy.orm import relationship, backref, foreign
from sqlalchemy import and_
from ..extensions import db
from .enums import AssignmentEntityStatusValue, PublicSubmissionStatus
from app.utils.datetime_helpers import utcnow


class ReportingPeriod(db.Model):
    """Typed reporting period catalog for assignment periods."""
    __tablename__ = 'reporting_period'

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    period_type = Column(String(20), nullable=False)  # annual, quarterly, custom
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    assigned_forms = relationship('AssignedForm', backref='reporting_period', lazy='dynamic')

    __table_args__ = (
        db.Index('ix_reporting_period_dates', 'period_start', 'period_end'),
        db.Index('ix_reporting_period_type', 'period_type'),
    )

    def __repr__(self):
        return f'<ReportingPeriod {self.name} ({self.period_start} - {self.period_end})>'


class AssignedForm(db.Model):
    __tablename__ = 'assigned_form'
    id = Column(Integer, primary_key=True)
    template_id = Column(Integer, ForeignKey('form_template.id'), nullable=False)
    period_name = Column(String(100), nullable=False)
    period_id = Column(Integer, ForeignKey('reporting_period.id', ondelete='SET NULL'), nullable=True)
    period_start = Column(Date, nullable=True)
    period_end = Column(Date, nullable=True)
    assigned_at = Column(DateTime, default=utcnow)

    # Admin pause toggle (independent of closed lifecycle state)
    is_active = Column(Boolean, default=True, nullable=False)
    # Reporting cycle ended (UI/workflow label); does not block viewing the form
    is_closed = Column(Boolean, default=False, nullable=False)
    # Expiry date: after this date the assignment is treated as Closed (optional)
    expiry_date = Column(Date, nullable=True)
    # Public URL fields for unified assignment system
    unique_token = Column(String(36), unique=True, nullable=True)  # UUID for public URL
    is_public_active = Column(Boolean, default=False, nullable=False)  # Public URL status

    # When true, non-org focal points must use sent_for_review before upstream submit
    requires_delegation_review = Column(Boolean, default=False, nullable=False)

    # Optional override for the assignment's display name.
    # When None the UI falls back to "<template name> – <period>".
    custom_name = Column(String(200), nullable=True)
    # Per-language translations for custom_name, keyed by ISO code {"ar": "...", "fr": "..."}.
    # English is always stored in custom_name; this dict holds non-English variants.
    custom_name_translations = Column(JSON, nullable=True)

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
        db.UniqueConstraint('template_id', 'period_name', name='uq_assigned_form_template_period'),
        db.Index('ix_assigned_form_template_period', 'template_id', 'period_name'),
        db.Index('ix_assigned_form_period', 'period_id'),
        db.Index('ix_assigned_form_period_dates', 'period_start', 'period_end'),
        db.Index('ix_assigned_form_public_token', 'unique_token'),
        db.Index('ix_assigned_form_public_active', 'is_public_active'),
        db.Index('ix_assigned_form_assigned_at', 'assigned_at'),
        db.Index('ix_assigned_form_is_active', 'is_active'),
        db.Index('ix_assigned_form_data_owner', 'data_owner_id'),
        db.Index('ix_assigned_form_activated_by', 'activated_by_user_id'),
        db.Index('ix_assigned_form_deactivated_by', 'deactivated_by_user_id'),
        db.Index('ix_assigned_form_custom_name', 'custom_name'),
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
        from app.utils.api_serialization import batch_countries_for_aes_list, _country_for_aes

        statuses = self.country_statuses.all()
        if not statuses:
            return []
        countries_map = batch_countries_for_aes_list(statuses)
        result = []
        for aes in statuses:
            country = _country_for_aes(aes, countries_map)
            if country:
                result.append(country)
        return result

    @property
    def public_countries(self):
        """Get countries that are available for public reporting (AES)."""
        from app.utils.api_serialization import batch_countries_for_aes_list, _country_for_aes

        statuses = self.country_statuses.filter_by(is_public_available=True).all()
        if not statuses:
            return []
        countries_map = batch_countries_for_aes_list(statuses)
        result = []
        for aes in statuses:
            country = _country_for_aes(aes, countries_map)
            if country:
                result.append(country)
        return result

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
                status=AssignmentEntityStatusValue.pending,
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

    @property
    def is_entry_allowed(self) -> bool:
        """Whether logged-in users may open the assignment form (deactivate blocks; close does not)."""
        return self.is_active

    def get_custom_name_translation(self, lang: str) -> str:
        """Return the translation for *lang*, falling back to English custom_name."""
        if self.custom_name_translations and isinstance(self.custom_name_translations, dict):
            val = self.custom_name_translations.get(lang)
            if val and str(val).strip():
                return str(val).strip()
        return self.custom_name or ''

    def set_custom_name_translation(self, lang: str, text: str) -> None:
        """Set (or clear) the translation for *lang*.  Replaces the whole dict so SQLAlchemy
        detects the mutation without needing flag_modified."""
        current = dict(self.custom_name_translations) if isinstance(self.custom_name_translations, dict) else {}
        text = (text or '').strip()
        if text:
            current[lang] = text
        else:
            current.pop(lang, None)
        self.custom_name_translations = current or None

    @property
    def display_name(self) -> str:
        """Human-readable name, locale-aware when inside a request context.

        Resolution order:
          1. custom_name_translations[current_locale]  (if set and non-English)
          2. custom_name                               (English / fallback)
          3. "<template> – <period>"                  (default)
        """
        if self.custom_name:
            from contextlib import suppress
            with suppress(Exception):
                from app.utils.form_localization import get_translation_key
                lang = get_translation_key()
                if lang and lang != 'en' and self.custom_name_translations:
                    val = self.custom_name_translations.get(lang)
                    if val and str(val).strip():
                        return str(val).strip()
            return self.custom_name
        template_name = self.template.name if self.template else 'Template Missing'
        return f"{template_name} \u2013 {self.period_name}" if self.period_name else template_name

    @property
    def is_public_submission_allowed(self) -> bool:
        """Whether the public URL may accept new submissions."""
        return self.is_active and not self.is_effectively_closed

    @classmethod
    def operational_clause(cls):
        """SQL filter for assignments with an open data-collection round (governance metrics)."""
        today = utcnow().date()
        return and_(
            cls.is_active.is_(True),
            cls.is_closed.is_(False),
            or_(cls.expiry_date.is_(None), cls.expiry_date >= today),
        )

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

    status = db.Column(
        Enum(
            AssignmentEntityStatusValue,
            name='assignmententitystatus',
            values_callable=lambda obj: [member.value for member in obj],
        ),
        default=AssignmentEntityStatusValue.pending,
        nullable=False,
    )
    status_timestamp = db.Column(db.DateTime, default=db.func.now())
    due_date = db.Column(db.DateTime, nullable=True)
    is_public_available = db.Column(db.Boolean, default=False, nullable=False)

    # Submission / approval accountability — who changed status to Submitted / Approved
    submitted_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
    approved_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
    # Separate timestamp for when the form was submitted (status_timestamp is overwritten on approval)
    submitted_at = db.Column(db.DateTime, nullable=True)

    # Delegation review workflow accountability
    sent_for_review_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
    sent_for_review_at = db.Column(db.DateTime, nullable=True)
    # When the parent assignment round is closed, admins can reopen data entry for this entity only
    reopened_after_close = db.Column(db.Boolean, default=False, nullable=False)

    # Denormalized cache of AssignmentCompletionService.compute_for_assignment() (refreshed on save).
    completion_rate = db.Column(db.Numeric(5, 1), nullable=True)

    # Relationships
    assigned_form = relationship('AssignedForm', backref=db.backref('entity_statuses', lazy='dynamic', cascade="all, delete-orphan"))
    submitted_by_user = db.relationship('User', foreign_keys=[submitted_by_user_id])
    approved_by_user = db.relationship('User', foreign_keys=[approved_by_user_id])
    sent_for_review_by_user = db.relationship('User', foreign_keys=[sent_for_review_by_user_id])

    # Relationship to FormData
    data_entries = relationship('FormData', lazy='dynamic', cascade="all, delete-orphan", foreign_keys='FormData.assignment_entity_status_id')

    # Relationship to SubmittedDocuments
    submitted_documents = relationship('SubmittedDocument', lazy='dynamic', cascade="all, delete-orphan", foreign_keys='SubmittedDocument.assignment_entity_status_id')

    def is_round_closed_for_entity(self) -> bool:
        """True when the parent assignment round is closed and this entity has not been reopened."""
        if self.reopened_after_close:
            return False
        assigned_form = self.assigned_form
        return bool(assigned_form and assigned_form.is_effectively_closed)

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
        db.Index('ix_aes_sent_for_review_by', 'sent_for_review_by_user_id'),
        db.Index('ix_aes_sent_for_review_at', 'sent_for_review_at'),
    )

    @property
    def entity(self):
        """Get the actual entity object based on entity_type and entity_id."""
        from app.services.organization.entity_service import EntityService
        return EntityService.get_entity(self.entity_type, self.entity_id)

    @property
    def country(self):
        """Get the related country for this entity.

        For backward compatibility and to get the country regardless of entity type.
        Returns the actual Country object if entity_type is 'country', or the parent
        country for NS branches/departments.
        """
        from app.services.organization.entity_service import EntityService
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
        return f'<AssignmentEntityStatus Assignment:{self.assigned_form_id}, Entity:{entity_info}, Status:{self.status.value}>'


class PublicSubmission(db.Model):
    __tablename__ = 'public_submission'
    id = db.Column(db.Integer, primary_key=True)
    assigned_form_id = db.Column(db.Integer, db.ForeignKey('assigned_form.id'), nullable=True)
    country_id = db.Column(db.Integer, db.ForeignKey('country.id'), nullable=False)
    submitted_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    status = db.Column(
        Enum(
            PublicSubmissionStatus,
            name='publicsubmissionstatus',
            values_callable=lambda obj: [member.value for member in obj],
        ),
        default=PublicSubmissionStatus.pending,
        nullable=False,
    )
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
