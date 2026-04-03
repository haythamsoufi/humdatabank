"""
Document-related models for file uploads and resource management.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, ForeignKey, String, Text, DateTime, Boolean, Date, Table
from sqlalchemy.orm import relationship, backref
from ..extensions import db
from app.utils.datetime_helpers import utcnow
from app.models.enums import DocumentStatus


submitted_document_countries = Table(
    'submitted_document_countries',
    db.metadata,
    db.Column('submitted_document_id', db.Integer,
              db.ForeignKey('submitted_document.id', ondelete='CASCADE'),
              primary_key=True),
    db.Column('country_id', db.Integer,
              db.ForeignKey('country.id', ondelete='CASCADE'),
              primary_key=True),
)


class SubmittedDocument(db.Model):
    __tablename__ = 'submitted_document'
    id = db.Column(db.Integer, primary_key=True)
    assignment_entity_status_id = db.Column(db.Integer, db.ForeignKey('assignment_entity_status.id'), nullable=True)
    public_submission_id = db.Column(db.Integer, db.ForeignKey('public_submission.id'), nullable=True)
    country_id = db.Column(db.Integer, db.ForeignKey('country.id'), nullable=True)
    # Standalone library documents: organizational entity (country, ns_branch, division, …)
    linked_entity_type = db.Column(db.String(50), nullable=True)
    linked_entity_id = db.Column(db.Integer, nullable=True)
    form_item_id = db.Column(db.Integer, db.ForeignKey('form_item.id'), nullable=True)
    filename = db.Column(db.String(255), nullable=False)
    storage_path = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    uploaded_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    document_type = db.Column(db.String(255), nullable=True)
    language = db.Column(db.String(10), nullable=True)
    is_public = db.Column(db.Boolean, default=False, nullable=False)
    period = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(50), nullable=False, default=DocumentStatus.PENDING)

    # Thumbnail fields
    thumbnail_filename = db.Column(db.String(255), nullable=True)
    thumbnail_relative_path = db.Column(db.String(512), nullable=True)

    # Soft-archive: JSON list of replaced file versions (see storage_service.archive)
    archived_versions = db.Column(db.JSON, nullable=True)

    # -- Relationships --
    form_item = relationship('FormItem', foreign_keys=[form_item_id], overlaps="document_field,submitted_documents")
    country = relationship('Country', foreign_keys=[country_id])
    countries = relationship('Country', secondary=submitted_document_countries, lazy='select',
                             backref=db.backref('submitted_documents_m2m', lazy='dynamic'))
    assignment_entity_status = relationship('AssignmentEntityStatus', foreign_keys=[assignment_entity_status_id], overlaps="submitted_documents")
    public_submission = relationship('PublicSubmission', overlaps="submitted_documents")
    uploaded_by_user = relationship('User', backref='focal_submitted_documents')

    __table_args__ = (
        db.Index('ix_submitted_doc_aes', 'assignment_entity_status_id'),
        db.Index('ix_submitted_doc_public', 'public_submission_id'),
        db.Index('ix_submitted_doc_country', 'country_id'),
        db.Index('ix_submitted_doc_linked_entity', 'linked_entity_type', 'linked_entity_id'),
        db.Index('ix_submitted_doc_item', 'form_item_id'),
        db.Index('ix_submitted_doc_uploaded_by', 'uploaded_by_user_id'),
        db.Index('ix_submitted_doc_uploaded_at', 'uploaded_at'),
        db.Index('ix_submitted_doc_status', 'status'),
        db.Index('ix_submitted_doc_period', 'period'),
        db.Index('ix_submitted_doc_is_public', 'is_public'),
        db.Index('ix_submitted_doc_language', 'language'),
    )

    @property
    def document_country(self):
        """Get the country associated with this document.

        Priority:
        1. From assignment_entity_status (if linked to an assignment)
        2. From public_submission (if linked to a public submission)
        3. From country_id (for standalone documents only)
        4. From linked_entity (e.g. NS branch → parent country) for standalone docs
        """
        if self.assignment_entity_status and self.assignment_entity_status.country:
            return self.assignment_entity_status.country
        if self.public_submission and self.public_submission.country:
            return self.public_submission.country
        if self.country:
            return self.country
        if self.linked_entity_type and self.linked_entity_id:
            from app.services.entity_service import EntityService
            return EntityService.get_country_for_entity(
                self.linked_entity_type, self.linked_entity_id
            )
        return None

    @property
    def standalone_linked_display(self):
        """Display name for standalone docs (grid/modal); None for assignment/public rows."""
        if self.assignment_entity_status_id or self.public_submission_id:
            return None
        if self.linked_entity_type and self.linked_entity_id:
            from app.services.entity_service import EntityService
            return EntityService.get_entity_display_name(
                self.linked_entity_type, self.linked_entity_id
            )
        if self.country:
            return self.country.name
        return None

    @property
    def document_label(self):
        """Get the label for this document (either from form_item or document_type)"""
        if self.form_item:
            return self.form_item.label
        return self.document_type or 'Document'

    def __repr__(self):
        field_label = self.document_label
        country_name = self.document_country.name if self.document_country else 'N/A'
        return f'<SubmittedDocument "{self.filename}" for "{field_label}" ({country_name})>'


class Resource(db.Model):
    __tablename__ = 'resource'
    id = Column(Integer, primary_key=True)
    resource_type = Column(String(50), nullable=False, default='publication')
    default_title = Column(String(255), nullable=False)
    default_description = Column(Text, nullable=True)
    publication_date = Column(Date, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    # Relationship to translations
    translations = db.relationship('ResourceTranslation', backref='resource', lazy='dynamic', cascade='all, delete-orphan')

    __table_args__ = (
        db.Index('ix_resource_type', 'resource_type'),
        db.Index('ix_resource_pub_date', 'publication_date'),
        db.Index('ix_resource_created_at', 'created_at'),
    )

    def __repr__(self):
        return f'<Resource {self.default_title}>'

    def get_translation(self, language_code):
        """Get translation for specific language, fallback to default if not found"""
        translation = self.translations.filter_by(language_code=language_code).first()
        return translation

    def get_title(self, language_code='en'):
        """Get title in specific language, fallback to default"""
        translation = self.get_translation(language_code)
        return translation.title if translation else self.default_title

    def get_description(self, language_code='en'):
        """Get description in specific language, fallback to default"""
        translation = self.get_translation(language_code)
        return translation.description if translation else self.default_description

    def get_available_languages(self):
        """Get list of language codes that have translations"""
        return [t.language_code for t in self.translations]


class ResourceTranslation(db.Model):
    __tablename__ = 'resource_translation'
    id = Column(Integer, primary_key=True)
    resource_id = Column(Integer, ForeignKey('resource.id'), nullable=False)
    language_code = Column(String(10), nullable=False)  # e.g., 'en', 'fr', 'es'

    # Translated content
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Language-specific file information
    filename = Column(String(255), nullable=True)  # Original secure filename of the document
    file_relative_path = Column(String(512), nullable=True)  # e.g., <uuid_folder>/<language>/<filename>

    # Language-specific thumbnail
    thumbnail_filename = Column(String(255), nullable=True)  # Original secure filename of the thumbnail
    thumbnail_relative_path = Column(String(512), nullable=True)  # e.g., <uuid_folder>/<language>/thumbnails/<thumb_filename>

    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    # Unique constraint to prevent duplicate translations for same language
    __table_args__ = (
        db.UniqueConstraint('resource_id', 'language_code', name='_resource_language_uc'),
        db.Index('ix_resource_tr_lang', 'language_code'),
    )

    def __repr__(self):
        return f'<ResourceTranslation {self.title} ({self.language_code})>'
