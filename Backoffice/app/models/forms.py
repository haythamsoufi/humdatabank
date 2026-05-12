"""
Form-related models including templates, sections, items, and data.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, ForeignKey, String, Text, DateTime, Boolean, JSON, Float
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, backref
from ..extensions import db
from .enums import SectionType, FormItemType
from config import Config
import json
from app.utils.datetime_helpers import utcnow


class FormTemplate(db.Model):
    __tablename__ = 'form_template'
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=utcnow)
    # Add created_by field to track template creator
    created_by = Column(Integer, ForeignKey('user.id'), nullable=True)
    # Add owned_by field to track template owner
    owned_by = Column(Integer, ForeignKey('user.id'), nullable=True)

    # Versioning: pointer to currently published version (nullable for legacy until backfilled)
    # The foreign key is declared via __table_args__ with use_alter=True to avoid circular DDL issues.
    published_version_id = Column(Integer, nullable=True)

    # Relationship to FormSection - sections can be indicator or document sections
    sections = relationship(
        'FormSection',
        backref='template',
        lazy='dynamic',
        order_by='FormSection.order',
        cascade="all, delete-orphan",
        passive_deletes=True
    )
    assigned_forms = relationship('AssignedForm', backref='template', lazy='dynamic')
    # Relationship to the user who created the template
    created_by_user = relationship('User', foreign_keys=[created_by])
    # Relationship to the user who owns the template
    owned_by_user = relationship('User', foreign_keys=[owned_by])

    # Relationship to pages (defined below)
    pages = relationship(
        'FormPage',
        backref='template',
        lazy='dynamic',
        order_by='FormPage.order',
        cascade="all, delete-orphan",
        passive_deletes=True
    )

    # Relationship to versions (disambiguate foreign keys)
    versions = relationship(
        'FormTemplateVersion',
        lazy='dynamic',
        cascade="all, delete-orphan",
        foreign_keys='FormTemplateVersion.template_id',
        back_populates='template',
        passive_deletes=True
    )
    published_version = relationship('FormTemplateVersion', foreign_keys=[published_version_id], post_update=True, uselist=False)

    __table_args__ = (
        db.Index('ix_form_template_created_by', 'created_by'),
        db.Index('ix_form_template_owned_by', 'owned_by'),
        db.ForeignKeyConstraint(
            ['published_version_id'],
            ['form_template_version.id'],
            name='fk_form_template_published_version',
            ondelete='SET NULL',
            use_alter=True,
            deferrable=True,
            initially='DEFERRED',
        ),
    )

    @property
    def name(self):
        """Get the name from the published version, or fallback to first version."""
        if self.published_version and self.published_version.name:
            return self.published_version.name
        # Fallback to first version if no published version
        first_version = self.versions.order_by('created_at').first()
        if first_version and first_version.name:
            return first_version.name
        return "Unnamed Template"

    @property
    def name_translations(self):
        """Get name translations from the published version, or fallback to first version."""
        if self.published_version and self.published_version.name_translations:
            return self.published_version.name_translations
        # Fallback to first version if no published version
        first_version = self.versions.order_by('created_at').first()
        if first_version and first_version.name_translations:
            return first_version.name_translations
        return None

    def get_name_translation(self, language):
        """Get the translated name for a specific language from the published version."""
        if self.published_version:
            return self.published_version.get_name_translation(language)
        # Fallback to first version
        first_version = self.versions.order_by('created_at').first()
        if first_version:
            return first_version.get_name_translation(language)
        return self.name

    @property
    def is_paginated(self):
        """Get is_paginated from the published version, or fallback to first version."""
        if self.published_version:
            return self.published_version.is_paginated
        # Fallback to first version
        first_version = self.versions.order_by('created_at').first()
        if first_version:
            return first_version.is_paginated
        return False

    @property
    def display_order_visible(self):
        """Get display_order_visible from the published version, or fallback to first version."""
        if self.published_version:
            return self.published_version.display_order_visible
        # Fallback to first version
        first_version = self.versions.order_by('created_at').first()
        if first_version:
            return first_version.display_order_visible
        return False

    @property
    def enable_export_pdf(self):
        """Get enable_export_pdf from the published version, or fallback to first version."""
        if self.published_version:
            return self.published_version.enable_export_pdf
        # Fallback to first version
        first_version = self.versions.order_by('created_at').first()
        if first_version:
            return first_version.enable_export_pdf
        return False

    @property
    def enable_export_excel(self):
        """Get enable_export_excel from the published version, or fallback to first version."""
        if self.published_version:
            return self.published_version.enable_export_excel
        # Fallback to first version
        first_version = self.versions.order_by('created_at').first()
        if first_version:
            return first_version.enable_export_excel
        return False

    @property
    def enable_import_excel(self):
        """Get enable_import_excel from the published version, or fallback to first version."""
        if self.published_version:
            return self.published_version.enable_import_excel
        # Fallback to first version
        first_version = self.versions.order_by('created_at').first()
        if first_version:
            return first_version.enable_import_excel
        return False

    @property
    def enable_ai_validation(self):
        """Get enable_ai_validation from the published version, or fallback to first version."""
        if self.published_version:
            return self.published_version.enable_ai_validation
        # Fallback to first version
        first_version = self.versions.order_by('created_at').first()
        if first_version:
            return first_version.enable_ai_validation
        return False

    def __repr__(self):
        return f'<FormTemplate {self.name}>'


class FormTemplateVersion(db.Model):
    __tablename__ = 'form_template_version'

    id = Column(Integer, primary_key=True)
    template_id = Column(Integer, ForeignKey('form_template.id', ondelete='CASCADE'), nullable=False)
    version_number = Column(Integer, nullable=False)  # Template-scoped version number (1, 2, 3, ...)
    status = Column(String(20), nullable=False, default='draft')  # draft, published, archived
    comment = Column(Text, nullable=True)
    based_on_version_id = Column(Integer, ForeignKey('form_template_version.id', ondelete='SET NULL'), nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    created_by = Column(Integer, ForeignKey('user.id'), nullable=True)
    updated_by = Column(Integer, ForeignKey('user.id'), nullable=True)  # User who last edited this version

    # Version-specific name (nullable - falls back to template.name if not set)
    name = Column(String(100), nullable=True)
    # Multilingual support for version-specific names
    name_translations = Column(JSON, nullable=True)

    # Template configuration fields (moved from FormTemplate - all properties are now version-specific)
    description = Column(Text, nullable=True)
    # Multilingual support for version-specific descriptions
    description_translations = Column(JSON, nullable=True)
    add_to_self_report = Column(Boolean, default=False, nullable=False)
    display_order_visible = Column(Boolean, default=False, nullable=False)
    is_paginated = Column(Boolean, default=False, nullable=False)
    enable_export_pdf = Column(Boolean, default=False, nullable=False)
    enable_export_excel = Column(Boolean, default=False, nullable=False)
    enable_import_excel = Column(Boolean, default=False, nullable=False)
    enable_ai_validation = Column(Boolean, default=False, nullable=False)

    # Template variables for referencing values from other form submissions
    # Structure: {"variable_name": {"source_template_id": int, "source_assignment_period": str,
    #                                "source_form_item_id": int, "entity_scope": str, ...}}
    variables = Column(JSON, nullable=True)

    # Relationships
    # Link back to FormTemplate (disambiguated)
    template = relationship('FormTemplate', back_populates='versions', foreign_keys=[template_id])
    # Self-referential relationship for ancestry
    based_on_version = relationship('FormTemplateVersion', remote_side=[id], uselist=False)
    # Audit relationships
    created_by_user = relationship('User', foreign_keys=[created_by])
    updated_by_user = relationship('User', foreign_keys=[updated_by])

    __table_args__ = (
        db.Index('ix_form_template_version_template_status', 'template_id', 'status'),
        db.UniqueConstraint('template_id', 'version_number', name='uq_template_version_number'),
    )

    def get_effective_name(self):
        """Get the effective name for this version: version name if set, otherwise None."""
        return self.name if self.name else None

    def get_effective_description(self):
        """Get the effective description for this version."""
        return self.description

    def get_effective_add_to_self_report(self):
        """Get the effective add_to_self_report for this version."""
        return self.add_to_self_report

    def get_effective_display_order_visible(self):
        """Get the effective display_order_visible for this version."""
        return self.display_order_visible

    def get_effective_is_paginated(self):
        """Get the effective is_paginated for this version."""
        return self.is_paginated

    def get_effective_enable_export_pdf(self):
        """Get the effective enable_export_pdf for this version."""
        return self.enable_export_pdf

    def get_effective_enable_export_excel(self):
        """Get the effective enable_export_excel for this version."""
        return self.enable_export_excel

    def get_effective_enable_import_excel(self):
        """Get the effective enable_import_excel for this version."""
        return self.enable_import_excel

    def get_effective_enable_ai_validation(self):
        """Get the effective enable_ai_validation for this version."""
        return self.enable_ai_validation

    def get_name_translation(self, language):
        """Get the translated name for a specific language."""
        # Try version-specific translations
        if self.name_translations and language in self.name_translations:
            return self.name_translations[language]
        # Fall back to effective name
        return self.get_effective_name()

    def __repr__(self):
        return f"<FormTemplateVersion {self.id} template={self.template_id} status={self.status}>"


class FormPage(db.Model):
    __tablename__ = 'form_page'

    id = Column(Integer, primary_key=True)
    # Version that this page belongs to (primary reference)
    version_id = Column(Integer, ForeignKey('form_template_version.id', ondelete='CASCADE'), nullable=False)
    # Template reference (denormalized for performance, can be derived from version)
    template_id = Column(Integer, ForeignKey('form_template.id', ondelete='CASCADE'), nullable=True)
    name = Column(String(100), nullable=False)
    order = Column(Integer, nullable=False, default=1)

    # Multilingual support for page names
    name_translations = Column(JSON, nullable=True)

    # Relationship back to sections handled through FormSection.page_id FK
    sections = relationship(
        'FormSection',
        backref='page',
        lazy='dynamic',
        cascade="all, delete-orphan",
        passive_deletes=True
    )

    __table_args__ = (
        db.Index('ix_form_page_version_order', 'version_id', 'order'),
        db.Index('ix_form_page_template', 'template_id'),
    )

    def get_name_translation(self, language):
        """Get the translated name for a specific language."""
        if self.name_translations and language in self.name_translations:
            return self.name_translations[language]
        return self.name

    def set_name_translation(self, language, text):
        """Set the translated name for a specific language."""
        if not self.name_translations:
            self.name_translations = {}
        if text and text.strip():
            self.name_translations[language] = text.strip()
        elif language in self.name_translations:
            del self.name_translations[language]

    def __repr__(self):
        return f"<FormPage {self.id}: {self.name}>"


class TemplateShare(db.Model):
    """Model for managing template sharing between admin users."""
    __tablename__ = 'template_share'

    id = Column(Integer, primary_key=True)
    template_id = Column(Integer, ForeignKey('form_template.id', ondelete='CASCADE'), nullable=False)
    shared_with_user_id = Column(Integer, ForeignKey('user.id'), nullable=False)
    shared_at = Column(DateTime, default=utcnow)
    shared_by_user_id = Column(Integer, ForeignKey('user.id'), nullable=False)

    # Relationships
    template = relationship('FormTemplate', backref='shared_with')
    shared_with_user = relationship('User', foreign_keys=[shared_with_user_id])
    shared_by_user = relationship('User', foreign_keys=[shared_by_user_id])

    __table_args__ = (
        db.Index('ix_template_share_template_user', 'template_id', 'shared_with_user_id'),
        db.Index('ix_template_share_user', 'shared_with_user_id'),
        db.UniqueConstraint('template_id', 'shared_with_user_id', name='uq_template_share_template_user'),
    )

    def __repr__(self):
        return f'<TemplateShare template_id={self.template_id} shared_with_user_id={self.shared_with_user_id}>'


class FormSection(db.Model):
    __tablename__ = 'form_section'
    id = Column(Integer, primary_key=True)
    # Version that this section belongs to (primary reference)
    version_id = Column(Integer, ForeignKey('form_template_version.id', ondelete='CASCADE'), nullable=False)
    # Template reference (denormalized for performance, can be derived from version)
    template_id = Column(Integer, ForeignKey('form_template.id'), nullable=True)
    name = Column(String(100), nullable=False)
    order = Column(Float, nullable=False, default=0)  # Changed to Float for hierarchical ordering

    # Support for sub-sections
    parent_section_id = Column(Integer, ForeignKey('form_section.id'), nullable=True)

    # Reference to FormPage for pagination support (nullable when template is not paginated)
    page_id = Column(Integer, ForeignKey('form_page.id', ondelete='CASCADE'), nullable=True)

    # Self-referential relationship for sub-sections
    sub_sections = relationship(
        'FormSection',
        backref=backref('parent_section', remote_side=[id]),
        lazy='dynamic',
        order_by='FormSection.order',
        passive_deletes=True
    )

    # Relationship to FormTemplateVersion
    version = relationship('FormTemplateVersion', foreign_keys=[version_id], lazy='select')

    # Relationship to RepeatGroupInstance - ensure cascade delete when section is deleted
    repeat_instances = relationship('RepeatGroupInstance', backref='section', lazy='dynamic', cascade="all, delete-orphan")

    # Relationship to DynamicIndicatorData - ensure cascade delete when section is deleted
    dynamic_indicator_assignments = relationship('DynamicIndicatorData', backref='section', lazy='dynamic', cascade="all, delete-orphan")

    # Section configuration
    section_type = Column(String(50), default='standard', nullable=False)  # Use String for SQLite compatibility
    max_dynamic_indicators = Column(db.Integer, nullable=True)  # Optional limit
    allowed_sectors = Column(JSON, nullable=True)  # Store sectors as JSON array
    # Store multiple filters as JSON - format: [{"field": "type", "values": ["number", "percentage"]}, {"field": "emergency", "values": [true]}]
    indicator_filters = Column(JSON, nullable=True)  # Store filters as JSON array

    # Dynamic section configuration options
    allow_data_not_available = db.Column(db.Boolean, default=False, nullable=False)
    allow_not_applicable = db.Column(db.Boolean, default=False, nullable=False)
    allowed_disaggregation_options = Column(JSON, nullable=True)  # Store options as JSON array

    # Store which filter fields should be displayed in data entry form
    data_entry_display_filters = Column(JSON, nullable=True)  # Store filter fields as JSON array

    # Optional note text for "Add indicator" button in dynamic sections
    add_indicator_note = db.Column(db.Text, nullable=True)  # Note text to display beside "Add indicator" button

    # Multilingual support for section names
    name_translations = Column(JSON, nullable=True)

    # Skip logic support for sections
    relevance_condition = Column(Text, nullable=True)

    # Archive flag for soft deletion when keeping data
    archived = Column(Boolean, nullable=False, default=False)

    # Consolidated configuration field (similar to FormItem)
    config = Column(JSON, nullable=True, default=lambda: {})

    __table_args__ = (
        db.Index('ix_form_section_version_order', 'version_id', 'order'),
        db.Index('ix_form_section_page', 'page_id'),
        db.Index('ix_form_section_parent', 'parent_section_id'),
        db.Index('ix_form_section_type', 'section_type'),
        db.Index('ix_form_section_template', 'template_id'),
    )

    @property
    def is_sub_section(self):
        """Returns True if this is a sub-section (has a parent)."""
        return self.parent_section_id is not None

    @property
    def section_type_enum(self):
        """Get the section type as enum for compatibility."""
        st = (self.section_type or 'standard').lower()
        if st == 'dynamic_indicators':
            return SectionType.dynamic_indicators
        elif st == 'repeat':
            return SectionType.repeat
        return SectionType.standard

    @property
    def allowed_sectors_list(self):
        """Get allowed sectors as a list."""
        if self.allowed_sectors:
            return self.allowed_sectors if isinstance(self.allowed_sectors, list) else []
        return []

    def set_allowed_sectors(self, sectors_list):
        """Set allowed sectors from a list."""
        self.allowed_sectors = sectors_list if sectors_list else None

    @property
    def indicator_filters_list(self):
        """Returns indicator filters as a list of dictionaries."""
        if self.indicator_filters:
            return self.indicator_filters if isinstance(self.indicator_filters, list) else []
        return []

    def set_indicator_filters(self, filters_list):
        """Set indicator filters as JSON array."""
        self.indicator_filters = filters_list if filters_list else None

    @property
    def allowed_disaggregation_options_list(self):
        """Get allowed disaggregation options as a list."""
        if self.allowed_disaggregation_options:
            return self.allowed_disaggregation_options if isinstance(self.allowed_disaggregation_options, list) else []
        return []

    def set_allowed_disaggregation_options(self, options_list):
        """Set allowed disaggregation options from a list."""
        self.allowed_disaggregation_options = options_list if options_list is not None else []

    @property
    def data_entry_display_filters_list(self):
        """Get data entry display filters as a list."""
        if self.data_entry_display_filters:
            return self.data_entry_display_filters if isinstance(self.data_entry_display_filters, list) else ['sector']
        return ['sector']  # Default to sector only

    def set_data_entry_display_filters(self, filters_list):
        """Set data entry display filters from a list."""
        self.data_entry_display_filters = filters_list if filters_list else []

    @property
    def depth_level(self):
        """Returns the depth level of this section (0 for main sections, 1 for sub-sections)."""
        return 1 if self.is_sub_section else 0

    @property
    def display_order(self):
        """Returns an integer order for display (e.g., '1', '2', '3').

        Note: Sub-section numbering is handled by the parent/child relationship in the UI.
        """
        try:
            return str(int(float(self.order)))
        except (ValueError, TypeError):
            return "0"

    def get_name_translation(self, language):
        """Get name translation for a specific language."""
        if not self.name_translations:
            return None
        return self.name_translations.get(language)

    def set_name_translation(self, language, text):
        """Set name translation for a specific language."""
        if self.name_translations is None:
            self.name_translations = {}
        self.name_translations[language] = text

    @property
    def max_entries(self):
        """Get max entries for repeat group sections from config."""
        if self.config and isinstance(self.config, dict):
            return self.config.get('max_entries')
        return None

    def set_max_entries(self, max_entries):
        """Set max entries for repeat group sections in config."""
        if self.config is None:
            self.config = {}
        if not isinstance(self.config, dict):
            self.config = {}
        if max_entries is not None:
            try:
                self.config['max_entries'] = int(max_entries)
            except (ValueError, TypeError):
                self.config['max_entries'] = None
        else:
            self.config.pop('max_entries', None)

    def __repr__(self):
        template_name = self.template.name if self.template else "N/A"
        parent_info = f" (Sub of: {self.parent_section.name})" if self.is_sub_section else ""
        return f'<FormSection {self.name}{parent_info} (Template: {template_name})>'


class FormData(db.Model):
    __tablename__ = 'form_data'
    id = db.Column(db.Integer, primary_key=True)
    # Polymorphic foreign key for multi-entity support
    assignment_entity_status_id = db.Column(db.Integer, db.ForeignKey('assignment_entity_status.id'), nullable=True)
    public_submission_id = db.Column(db.Integer, db.ForeignKey('public_submission.id'), nullable=True)
    form_item_id = db.Column(db.Integer, db.ForeignKey('form_item.id'), nullable=False)
    value = db.Column(db.String(255), nullable=True)
    # IMPORTANT: store Python None as SQL NULL (not JSON literal `null`)
    disagg_data = db.Column(db.JSON(none_as_null=True), nullable=True)
    data_not_available = db.Column(db.Boolean, nullable=True)
    not_applicable = db.Column(db.Boolean, nullable=True)
    prefilled_value = db.Column(db.JSON(none_as_null=True), nullable=True)
    # Prefilled values can also include a disaggregation/matrix JSON payload that corresponds to disagg_data
    prefilled_disagg_data = db.Column(db.JSON(none_as_null=True), nullable=True)
    imputed_value = db.Column(db.JSON(none_as_null=True), nullable=True)
    # Imputed values can also include a disaggregation/matrix JSON payload that corresponds to disagg_data
    imputed_disagg_data = db.Column(db.JSON(none_as_null=True), nullable=True)
    submitted_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)
    form_item = relationship('FormItem', foreign_keys=[form_item_id], overlaps="data_entries")
    assignment_entity_status = relationship('AssignmentEntityStatus', foreign_keys=[assignment_entity_status_id], overlaps="data_entries")
    public_submission = relationship('PublicSubmission', overlaps="data_entries")

    __table_args__ = (
        db.Index('ix_form_data_aes_item', 'assignment_entity_status_id', 'form_item_id'),
        db.Index('ix_form_data_public_item', 'public_submission_id', 'form_item_id'),
        db.Index('ix_form_data_form_item', 'form_item_id'),
        db.Index('ix_form_data_submitted_at', 'submitted_at'),
    )

    # Helper methods for prefilled values
    def get_display_value(self):
        """
        Get a scalar value to display in forms.

        Priority: reported value -> prefilled value -> imputed value.
        (Disaggregated/matrix payloads are exposed via get_display_disagg_data()).
        """
        if self.data_not_available or self.not_applicable:
            return None
        if self.value is not None and str(self.value).strip() != "":
            return self.value
        if self.prefilled_value is not None:
            return self.prefilled_value
        if self.imputed_value is not None:
            return self.imputed_value
        return None

    def get_display_disagg_data(self):
        """
        Get the disaggregation/matrix payload to display in forms.

        Priority: reported disagg_data -> prefilled_disagg_data -> imputed_disagg_data.
        """
        if self.data_not_available or self.not_applicable:
            return None
        if self.disagg_data is not None:
            return self.disagg_data
        if self.prefilled_disagg_data is not None:
            return self.prefilled_disagg_data
        if self.imputed_disagg_data is not None:
            return self.imputed_disagg_data
        return None

    def is_prefilled(self):
        """Check if this entry is using a prefilled payload (no reported value/disagg, but has prefilled data)."""
        has_reported = (self.value is not None and str(self.value).strip() != "") or (self.disagg_data is not None)
        has_prefilled = (self.prefilled_value is not None) or (self.prefilled_disagg_data is not None)
        return (not has_reported) and has_prefilled

    @property
    def has_disaggregation(self):
        """Check if this data entry has disaggregated data"""
        return self.disagg_data is not None

    @property
    def disaggregation_mode(self):
        """Get the disaggregation mode (total, sex, age, sex_age)"""
        if self.disagg_data:
            return self.disagg_data.get('mode')
        return None

    @property
    def total_value(self):
        """Get the total value, either from value field or calculated from disaggregation"""
        if self.value and not self.data_not_available and not self.not_applicable:
            return self.value
        elif self.disagg_data:
            values = self.disagg_data.get('values', {})
            return sum(v for v in values.values() if v is not None)
        return None

    def get_disaggregated_value(self, category):
        """Get value for specific age/sex category"""
        if self.disagg_data:
            return self.disagg_data.get('values', {}).get(category)
        return None

    def get_effective_value(self):
        """Get the effective value considering data availability flags"""
        if self.data_not_available:
            return None
        if self.not_applicable:
            return None
        return self.value

    def set_simple_value(self, value):
        """Set a simple value (clears disaggregation data)"""
        if value is None:
            self.value = None
        else:
            # Store all values as strings
            self.value = str(value)
        self.disagg_data = db.null()
        self.data_not_available = False
        self.not_applicable = False

    def set_disaggregated_data(self, mode, values):
        """Set disaggregated data (clears simple value)"""
        # Calculate the total from all values (excluding 'indirect' if present)
        total = 0

        # Handle nested structure for indirect reach items
        if 'direct' in values:
            if isinstance(values['direct'], dict):
                # For disaggregated modes (sex, age, sex_age), values are nested under 'direct'
                direct_values = values['direct']
                for key, value in direct_values.items():
                    if isinstance(value, (int, float)):
                        total += value
            elif isinstance(values['direct'], (int, float)):
                # For total mode, 'direct' contains a single value
                total += values['direct']

            # Add indirect value if present
            if 'indirect' in values and isinstance(values['indirect'], (int, float)):
                total += values['indirect']
        else:
            # For items without indirect reach, values are at the top level
            for key, value in values.items():
                if key != 'indirect' and isinstance(value, (int, float)):
                    total += value

        # Save the calculated total to the main value field
        self.value = str(total) if total > 0 else None

        # Save the disaggregated data structure
        self.disagg_data = {
            'mode': mode,
            'values': values
        }
        self.data_not_available = False
        self.not_applicable = False

    def set_data_availability(self, data_not_available=False, not_applicable=False):
        """Set data availability flags (clears actual values)"""
        if data_not_available or not_applicable:
            self.value = None
            self.disagg_data = db.null()
            self.data_not_available = data_not_available
            self.not_applicable = not_applicable
        else:
            self.data_not_available = False
            self.not_applicable = False

    @property
    def has_data_availability_flags(self):
        """Check if this entry has data availability flags set."""
        return bool(self.data_not_available or self.not_applicable)

    @property
    def is_data_not_available(self):
        """Check if data is marked as not available."""
        return bool(self.data_not_available)

    @property
    def is_not_applicable(self):
        """Check if data is marked as not applicable."""
        return bool(self.not_applicable)

    def __repr__(self):
        item_label = 'N/A'
        if self.form_item:
            item_type = self.form_item.item_type.title()
            item_label = f"{item_type}:{self.form_item.label}"
        else:
            item_label = "Item:N/A"

        # Access country and assignment info through the assignment_entity_status relationship
        status_info = self.assignment_entity_status
        country_name = status_info.country.name if status_info and status_info.country else 'N/A'
        assignment_id = status_info.assigned_form_id if status_info else 'N/A'

        # Show appropriate value based on data type
        display_value = 'N/A'
        if self.data_not_available:
            display_value = 'Data Not Available'
        elif self.not_applicable:
            display_value = 'Not Applicable'
        elif self.value:
            display_value = self.value[:30]
        elif self.disagg_data:
            display_value = f"Disaggregated ({self.disaggregation_mode})"

        return f'<FormData Assignment:{assignment_id} Country:{country_name} {item_label} Value:{display_value}>'


class DynamicIndicatorData(db.Model):
    """Tracks dynamically added indicators by focal points in repeat group sections and stores their data."""
    __tablename__ = 'dynamic_indicator_data'

    id = db.Column(db.Integer, primary_key=True)
    # Polymorphic foreign key for multi-entity support
    assignment_entity_status_id = db.Column(db.Integer, db.ForeignKey('assignment_entity_status.id'), nullable=True)
    public_submission_id = db.Column(db.Integer, db.ForeignKey('public_submission.id'), nullable=True)
    section_id = db.Column(db.Integer, db.ForeignKey('form_section.id'), nullable=False)  # The dynamic section
    indicator_bank_id = db.Column(db.Integer, db.ForeignKey('indicator_bank.id'), nullable=False)

    # Assignment metadata
    custom_label = db.Column(db.String(255), nullable=True)
    order = db.Column(db.Float, nullable=False, default=0)
    added_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    added_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    # Data fields (merged from DynamicIndicatorData)
    value = db.Column(db.String(255), nullable=True)
    # IMPORTANT: store Python None as SQL NULL (not JSON literal `null`)
    disagg_data = db.Column(db.JSON(none_as_null=True), nullable=True)
    data_not_available = db.Column(db.Boolean, nullable=True)
    not_applicable = db.Column(db.Boolean, nullable=True)
    submitted_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    # Relationships
    assignment_entity_status = db.relationship('AssignmentEntityStatus', foreign_keys=[assignment_entity_status_id])
    public_submission = db.relationship('PublicSubmission')
    # Note: 'section' relationship is defined in FormSection with cascade delete
    indicator_bank = db.relationship('IndicatorBank', backref='dynamic_assignments')
    added_by_user = db.relationship('User', backref='added_dynamic_indicators')

    # Ensure unique assignment per country/section/indicator combination
    __table_args__ = (
        db.UniqueConstraint('assignment_entity_status_id', 'section_id', 'indicator_bank_id', name='_dynamic_indicator_entity_unique'),
        db.UniqueConstraint('public_submission_id', 'section_id', 'indicator_bank_id', name='_dynamic_indicator_public_unique'),
        db.Index('ix_dynamic_indicator_aes', 'assignment_entity_status_id'),
        db.Index('ix_dynamic_indicator_public', 'public_submission_id'),
        db.Index('ix_dynamic_indicator_section', 'section_id'),
        db.Index('ix_dynamic_indicator_added_by', 'added_by_user_id'),
        db.Index('ix_dynamic_indicator_added_at', 'added_at'),
    )

    # Data properties (moved from DynamicIndicatorData)
    @property
    def has_disaggregation(self):
        """Check if this data entry has disaggregated data"""
        return self.disagg_data is not None

    @property
    def disaggregation_mode(self):
        """Get the disaggregation mode (total, sex, age, sex_age)"""
        if self.disagg_data:
            return self.disagg_data.get('mode')
        return None

    @property
    def total_value(self):
        """Get the total value, either from value field or calculated from disaggregation"""
        if self.value and not self.data_not_available and not self.not_applicable:
            return self.value
        elif self.disagg_data:
            values = self.disagg_data.get('values', {})
            return sum(v for v in values.values() if v is not None)
        return None

    def get_disaggregated_value(self, category):
        """Get value for specific age/sex category"""
        if self.disagg_data:
            return self.disagg_data.get('values', {}).get(category)
        return None

    def get_effective_value(self):
        """Get the effective value considering data availability flags"""
        if self.data_not_available:
            return None
        if self.not_applicable:
            return None
        return self.value

    def set_simple_value(self, value):
        """Set a simple value (clears disaggregation data)"""
        self.value = str(value) if value is not None else None
        self.disagg_data = db.null()
        self.data_not_available = False
        self.not_applicable = False

    def set_disaggregated_data(self, mode, values):
        """Set disaggregated data (clears simple value)"""
        # Calculate the total from all values (excluding 'indirect' if present)
        total = 0

        # Handle nested structure for indirect reach items
        if 'direct' in values:
            if isinstance(values['direct'], dict):
                # For disaggregated modes (sex, age, sex_age), values are nested under 'direct'
                direct_values = values['direct']
                for key, value in direct_values.items():
                    if isinstance(value, (int, float)):
                        total += value
            elif isinstance(values['direct'], (int, float)):
                # For total mode, 'direct' contains a single value
                total += values['direct']

            # Add indirect value if present
            if 'indirect' in values and isinstance(values['indirect'], (int, float)):
                total += values['indirect']
        else:
            # For items without indirect reach, values are at the top level
            for key, value in values.items():
                if key != 'indirect' and isinstance(value, (int, float)):
                    total += value

        # Save the calculated total to the main value field
        self.value = str(total) if total > 0 else None

        # Save the disaggregated data structure
        self.disagg_data = {
            'mode': mode,
            'values': values
        }
        self.data_not_available = False
        self.not_applicable = False

    def set_data_availability(self, data_not_available=False, not_applicable=False):
        """Set data availability flags."""
        self.data_not_available = data_not_available if data_not_available else None
        self.not_applicable = not_applicable if not_applicable else None

    def __repr__(self):
        # Show appropriate value based on data type
        display_value = 'N/A'
        if self.data_not_available:
            display_value = 'Data Not Available'
        elif self.not_applicable:
            display_value = 'Not Applicable'
        elif self.value:
            display_value = self.value[:30]
        elif self.disagg_data:
            display_value = f"Disaggregated ({self.disaggregation_mode})"

        country_name = None
        if self.assignment_entity_status and self.assignment_entity_status.country:
            country_name = self.assignment_entity_status.country.name
        return f'<DynamicIndicatorData {self.indicator_bank.name} for {country_name or "N/A"} Value:{display_value}>'




class RepeatGroupInstance(db.Model):
    """Represents an instance of a repeated section in a form."""
    __tablename__ = 'repeat_group_instance'

    id = db.Column(db.Integer, primary_key=True)
    # Polymorphic foreign key for multi-entity support
    assignment_entity_status_id = db.Column(db.Integer, db.ForeignKey('assignment_entity_status.id'), nullable=True)
    public_submission_id = db.Column(db.Integer, db.ForeignKey('public_submission.id'), nullable=True)
    section_id = db.Column(db.Integer, db.ForeignKey('form_section.id'), nullable=False)
    instance_number = db.Column(db.Integer, nullable=False)
    instance_label = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    is_hidden = db.Column(db.Boolean, nullable=False, default=False)

    # Relationships
    assignment_entity_status = db.relationship('AssignmentEntityStatus', foreign_keys=[assignment_entity_status_id])
    public_submission = db.relationship('PublicSubmission')
    # Note: 'section' relationship is defined in FormSection with cascade delete
    created_by_user = db.relationship('User', backref='created_repeat_instances')
    data_entries = db.relationship('RepeatGroupData', lazy='dynamic', cascade="all, delete-orphan")

    # Ensure unique instance numbers per section and assignment/submission
    __table_args__ = (
        db.UniqueConstraint('assignment_entity_status_id', 'section_id', 'instance_number', name='_repeat_instance_entity_unique'),
        db.UniqueConstraint('public_submission_id', 'section_id', 'instance_number', name='_repeat_instance_public_unique'),
        db.Index('ix_repeat_instance_aes', 'assignment_entity_status_id'),
        db.Index('ix_repeat_instance_public', 'public_submission_id'),
        db.Index('ix_repeat_instance_section', 'section_id'),
        db.Index('ix_repeat_instance_created_by', 'created_by_user_id'),
        db.Index('ix_repeat_instance_label', 'instance_label'),
    )

    def __repr__(self):
        return f'<RepeatGroupInstance {self.instance_number} for Section {self.section_id}>'


class RepeatGroupData(db.Model):
    """Stores data entries for fields within a repeat group instance."""
    __tablename__ = 'repeat_group_data'

    id = db.Column(db.Integer, primary_key=True)
    repeat_instance_id = db.Column(db.Integer, db.ForeignKey('repeat_group_instance.id'), nullable=False)

    # Unified approach - link to FormItem instead of separate indicator_id/question_id
    form_item_id = db.Column(db.Integer, db.ForeignKey('form_item.id'), nullable=False)

    # 1. Main value field - for totals, yes/no, text, etc.
    value = db.Column(db.String(255), nullable=True)

    # 2. Age disaggregation data - structured JSON for age/sex breakdowns
    # IMPORTANT: store Python None as SQL NULL (not JSON literal `null`)
    disagg_data = db.Column(db.JSON(none_as_null=True), nullable=True)

    # 3. Data availability flags - separate boolean fields for clarity (nullable for migration)
    data_not_available = db.Column(db.Boolean, nullable=True)
    not_applicable = db.Column(db.Boolean, nullable=True)

    submitted_at = db.Column(db.DateTime, nullable=True, default=utcnow, onupdate=utcnow)

    # Unified relationship - primary approach
    form_item = db.relationship('FormItem', foreign_keys=[form_item_id], overlaps="repeat_data_entries")
    repeat_instance = relationship('RepeatGroupInstance', overlaps="data_entries")

    __table_args__ = (
        db.Index('ix_repeat_data_instance', 'repeat_instance_id'),
        db.Index('ix_repeat_data_instance_item', 'repeat_instance_id', 'form_item_id'),
        db.Index('ix_repeat_data_form_item', 'form_item_id'),
        db.Index('ix_repeat_data_submitted_at', 'submitted_at'),
    )

    @property
    def has_disaggregation(self):
        """Check if this data entry has disaggregated data"""
        return self.disagg_data is not None

    @property
    def disaggregation_mode(self):
        """Get the disaggregation mode (total, sex, age, sex_age)"""
        if self.disagg_data:
            return self.disagg_data.get('mode')
        return None

    @property
    def total_value(self):
        """Get the total value, either from value field or calculated from disaggregation"""
        if self.value and not self.data_not_available and not self.not_applicable:
            return self.value
        elif self.disagg_data:
            values = self.disagg_data.get('values', {})
            return sum(v for v in values.values() if v is not None)
        return None

    def get_disaggregated_value(self, category):
        """Get value for specific age/sex category"""
        if self.disagg_data:
            return self.disagg_data.get('values', {}).get(category)
        return None

    def get_effective_value(self):
        """Get the effective value considering data availability flags"""
        if self.data_not_available:
            return None
        if self.not_applicable:
            return None
        return self.value

    def set_simple_value(self, value):
        """Set a simple value (clears disaggregation data)"""
        self.value = str(value) if value is not None else None
        # Store SQL NULL (not JSON literal `null`)
        self.disagg_data = db.null()
        self.data_not_available = False
        self.not_applicable = False

    def set_disaggregated_data(self, mode, values):
        """Set disaggregated data (clears simple value)"""
        # Calculate the total from all values (excluding 'indirect' if present)
        total = 0

        # Handle nested structure for indirect reach items
        if 'direct' in values:
            if isinstance(values['direct'], dict):
                # For disaggregated modes (sex, age, sex_age), values are nested under 'direct'
                direct_values = values['direct']
                for key, value in direct_values.items():
                    if isinstance(value, (int, float)):
                        total += value
            elif isinstance(values['direct'], (int, float)):
                # For total mode, 'direct' contains a single value
                total += values['direct']

            # Add indirect value if present
            if 'indirect' in values and isinstance(values['indirect'], (int, float)):
                total += values['indirect']
        else:
            # For items without indirect reach, values are at the top level
            for key, value in values.items():
                if key != 'indirect' and isinstance(value, (int, float)):
                    total += value

        # Save the calculated total to the main value field
        self.value = str(total) if total > 0 else None

        # Save the disaggregated data structure
        self.disagg_data = {
            'mode': mode,
            'values': values
        }
        self.data_not_available = False
        self.not_applicable = False

    def set_data_availability(self, data_not_available=False, not_applicable=False):
        """Set data availability flags."""
        self.data_not_available = data_not_available if data_not_available else None
        self.not_applicable = not_applicable if not_applicable else None

    def __repr__(self):
        item_label = 'N/A'
        if self.form_item:
            item_type = self.form_item.item_type.title()
            item_label = f"{item_type}:{self.form_item.label}"
        else:
            item_label = "Item:N/A"

        # Show appropriate value based on data type
        display_value = 'N/A'
        if self.data_not_available:
            display_value = 'Data Not Available'
        elif self.not_applicable:
            display_value = 'Not Applicable'
        elif self.value:
            display_value = self.value[:30]
        elif self.disagg_data:
            display_value = f"Disaggregated ({self.disaggregation_mode})"

        return f'<RepeatGroupData Instance:{self.repeat_instance_id} {item_label} Value:{display_value}>'
