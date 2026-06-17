"""
Form-related models including templates, sections, items, and data.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, ForeignKey, String, Text, DateTime, Boolean, JSON, Float
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, backref
from ..extensions import db
from .enums import SectionType, FormItemType, FormTemplateVersionStatusValue
from app.models.enum_columns import pg_str_enum_column
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

    @property
    def enable_data_quality(self):
        if self.published_version:
            return self.published_version.enable_data_quality
        first_version = self.versions.order_by('created_at').first()
        if first_version:
            return first_version.enable_data_quality
        return False

    @property
    def data_quality_methodology(self):
        if self.published_version:
            return self.published_version.data_quality_methodology
        first_version = self.versions.order_by('created_at').first()
        if first_version:
            return first_version.data_quality_methodology
        return None

    def __repr__(self):
        return f'<FormTemplate {self.name}>'


class FormTemplateVersion(db.Model):
    __tablename__ = 'form_template_version'

    id = Column(Integer, primary_key=True)
    template_id = Column(Integer, ForeignKey('form_template.id', ondelete='CASCADE'), nullable=False)
    version_number = Column(Integer, nullable=False)  # Template-scoped version number (1, 2, 3, ...)
    status = pg_str_enum_column(
        FormTemplateVersionStatusValue,
        'formtemplateversionstatus',
        default=FormTemplateVersionStatusValue.draft,
        nullable=False,
    )
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
    enable_data_quality = Column(Boolean, default=False, nullable=False)
    data_quality_methodology = Column(String(64), nullable=True)
    validation_rule_pack = Column(String(64), nullable=True)

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

    def get_effective_enable_data_quality(self):
        return self.enable_data_quality

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
    dynamic_section_contexts = relationship('DynamicSectionContext', backref='section', lazy='dynamic', cascade="all, delete-orphan")

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

    ENTRY_LABEL_ELIGIBLE_QUESTION_TYPES = frozenset({
        'text', 'textarea', 'number', 'percentage', 'yesno',
        'single_choice', 'date', 'datetime',
    })

    @classmethod
    def entry_label_item_eligible(cls, form_item):
        """Return True when a form item can drive repeat entry labels."""
        if not form_item or getattr(form_item, 'archived', False):
            return False
        if not getattr(form_item, 'is_question', False):
            return False
        question_type = (getattr(form_item, 'type', None) or '').lower()
        return question_type in cls.ENTRY_LABEL_ELIGIBLE_QUESTION_TYPES

    @property
    def entry_label_item_id(self):
        """Get form item id used to label repeat entries from config."""
        if self.config and isinstance(self.config, dict):
            return self.config.get('entry_label_item_id')
        return None

    def set_entry_label_item_id(self, item_id):
        """Set form item id used to label repeat entries in config."""
        if self.config is None:
            self.config = {}
        if not isinstance(self.config, dict):
            self.config = {}
        if item_id is not None:
            try:
                parsed = int(item_id)
            except (ValueError, TypeError):
                self.config.pop('entry_label_item_id', None)
                return
            if parsed > 0:
                self.config['entry_label_item_id'] = parsed
            else:
                self.config.pop('entry_label_item_id', None)
        else:
            self.config.pop('entry_label_item_id', None)

    @property
    def show_entries_in_navigation(self):
        """Whether repeat entry instances appear in the entry form side navigation."""
        if self.config and isinstance(self.config, dict):
            return bool(self.config.get('show_entries_in_navigation', False))
        return False

    def set_show_entries_in_navigation(self, enabled):
        if self.config is None:
            self.config = {}
        if not isinstance(self.config, dict):
            self.config = {}
        if enabled:
            self.config['show_entries_in_navigation'] = True
        else:
            self.config.pop('show_entries_in_navigation', None)

    @property
    def hide_section_header(self):
        """Whether the section title and divider are hidden on the entry form."""
        if self.config and isinstance(self.config, dict):
            return bool(self.config.get('hide_section_header', False))
        return False

    def set_hide_section_header(self, hidden):
        if self.config is None:
            self.config = {}
        if not isinstance(self.config, dict):
            self.config = {}
        if hidden:
            self.config['hide_section_header'] = True
        else:
            self.config.pop('hide_section_header', None)

    def __repr__(self):
        template_name = self.template.name if self.template else "N/A"
        parent_info = f" (Sub of: {self.parent_section.name})" if self.is_sub_section else ""
        return f'<FormSection {self.name}{parent_info} (Template: {template_name})>'


class DataEntryMixin:
    """Shared value/disaggregation columns and helpers for submission data tables.

    Invariant (F7):
    - ``value`` is a denormalized cache of the numeric total when ``disagg_data`` is set.
    - Always use ``total_value`` for reads; use ``set_simple_value`` / ``set_disaggregated_data``
      for writes — never mutate ``disagg_data`` in-place.
    """

    value = db.Column(db.String(255), nullable=True)
    # IMPORTANT: store Python None as SQL NULL (not JSON literal `null`)
    disagg_data = db.Column(db.JSON(none_as_null=True), nullable=True)
    disagg_type = db.Column(db.String(20), nullable=True)
    data_not_available = db.Column(db.Boolean, nullable=False, default=False)
    not_applicable = db.Column(db.Boolean, nullable=False, default=False)
    numeric_value = db.Column(db.Float, nullable=True)
    submitted_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    @staticmethod
    def _coerce_scalar_text_value(value):
        """Normalize auxiliary scalar values to the same storage shape as ``value``."""
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip()
            if not text or text.lower() in ('none', 'null', 'undefined'):
                return None
            if len(text) > 255:
                raise ValueError("Scalar form value exceeds 255 characters")
            return text
        if isinstance(value, bool):
            text = 'true' if value else 'false'
        elif isinstance(value, (int, float)):
            text = str(value)
        elif isinstance(value, list):
            text = json.dumps(value, ensure_ascii=False)
        elif isinstance(value, dict):
            raise ValueError("Structured form payloads must use a disaggregation data column")
        else:
            text = str(value)
        if len(text) > 255:
            raise ValueError("Scalar form value exceeds 255 characters")
        return text

    @staticmethod
    def _parse_numeric_string(value):
        """Return float when value is a numeric string, else None."""
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        try:
            return float(text)
        except (ValueError, TypeError):
            return None

    @classmethod
    def _calculate_disagg_total(cls, values):
        """Sum numeric leaf values from a disaggregation values dict."""
        total = 0
        if 'direct' in values:
            if isinstance(values['direct'], dict):
                for key, val in values['direct'].items():
                    if isinstance(val, (int, float)):
                        total += val
            elif isinstance(values['direct'], (int, float)):
                total += values['direct']
            if 'indirect' in values and isinstance(values['indirect'], (int, float)):
                total += values['indirect']
        else:
            for key, val in values.items():
                if key not in ('indirect', 'disability') and isinstance(val, (int, float)):
                    total += val
        return total

    def _sync_numeric_value_from_string(self):
        """Populate numeric_value from the string value column."""
        self.numeric_value = self._parse_numeric_string(self.value)

    @classmethod
    def sync_imputed_numeric_value(cls, entry, imputed_value):
        """Set imputed_numeric_value alongside imputed_value when imputed_value is numeric."""
        scalar_value = cls._coerce_scalar_text_value(imputed_value)
        entry.imputed_value = scalar_value
        if scalar_value is None:
            entry.imputed_numeric_value = None
            return
        entry.imputed_numeric_value = cls._parse_numeric_string(scalar_value)

    @property
    def has_disaggregation(self):
        """Check if this data entry has disaggregated data."""
        return self.disagg_data is not None

    @property
    def disaggregation_mode(self):
        """Get the disaggregation mode (total, sex, age, sex_age)."""
        if self.disagg_data:
            return self.disagg_data.get('mode')
        return None

    @property
    def total_value(self):
        """Get the total value, either from value field or calculated from disaggregation."""
        if self.value and not self.data_not_available and not self.not_applicable:
            return self.value
        if self.disagg_data:
            values = self.disagg_data.get('values', {})
            return sum(v for v in values.values() if isinstance(v, (int, float)))
        return None

    def get_disaggregated_value(self, category):
        """Get value for specific age/sex category."""
        if self.disagg_data:
            return self.disagg_data.get('values', {}).get(category)
        return None

    def get_effective_value(self):
        """Get the effective value considering data availability flags."""
        if self.data_not_available or self.not_applicable:
            return None
        return self.value

    @property
    def is_matrix(self):
        """Check if this entry stores matrix cell data."""
        return self.disagg_type == 'matrix'

    def set_simple_value(self, value):
        """Set a simple value (clears disaggregation data)."""
        if value is None:
            self.value = None
            self.numeric_value = None
            self.disagg_type = None
        else:
            self.value = str(value)
            self._sync_numeric_value_from_string()
            self.disagg_type = 'simple'
        self.disagg_data = db.null()
        self.data_not_available = False
        self.not_applicable = False

    def set_disaggregated_data(self, mode, values):
        """Set disaggregated data (clears simple value)."""
        total = self._calculate_disagg_total(values)
        self.value = str(total) if total > 0 else None
        self.numeric_value = float(total) if total > 0 else None
        self.disagg_data = {
            'mode': mode,
            'values': values,
        }
        self.disagg_type = 'standard_disagg'
        self.data_not_available = False
        self.not_applicable = False

    def set_data_availability(self, data_not_available=False, not_applicable=False):
        """Set data availability flags (clears actual values when flagged)."""
        if data_not_available or not_applicable:
            self.value = None
            self.numeric_value = None
            self.disagg_data = db.null()
            self.disagg_type = None
            self.data_not_available = bool(data_not_available)
            self.not_applicable = bool(not_applicable)
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


class FormData(DataEntryMixin, db.Model):
    __tablename__ = 'form_data'
    id = db.Column(db.Integer, primary_key=True)
    # Polymorphic foreign key for multi-entity support
    assignment_entity_status_id = db.Column(db.Integer, db.ForeignKey('assignment_entity_status.id'), nullable=True)
    public_submission_id = db.Column(db.Integer, db.ForeignKey('public_submission.id'), nullable=True)
    form_item_id = db.Column(db.Integer, db.ForeignKey('form_item.id'), nullable=False)
    prefilled_value = db.Column(db.String(255), nullable=True)
    # Prefilled values can also include a disaggregation/matrix JSON payload that corresponds to disagg_data
    prefilled_disagg_data = db.Column(db.JSON(none_as_null=True), nullable=True)
    imputed_value = db.Column(db.String(255), nullable=True)
    # Imputed values can also include a disaggregation/matrix JSON payload that corresponds to disagg_data
    imputed_disagg_data = db.Column(db.JSON(none_as_null=True), nullable=True)
    imputed_numeric_value = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
    form_item = relationship('FormItem', foreign_keys=[form_item_id], overlaps="data_entries")
    assignment_entity_status = relationship('AssignmentEntityStatus', foreign_keys=[assignment_entity_status_id], overlaps="data_entries")
    public_submission = relationship('PublicSubmission', overlaps="data_entries")
    created_by_user = relationship('User', foreign_keys=[created_by_user_id])

    __table_args__ = (
        db.Index('ix_form_data_aes_item', 'assignment_entity_status_id', 'form_item_id'),
        db.Index('ix_form_data_public_item', 'public_submission_id', 'form_item_id'),
        db.Index('ix_form_data_form_item', 'form_item_id'),
        db.Index('ix_form_data_submitted_at', 'submitted_at'),
        db.Index('ix_form_data_created_by', 'created_by_user_id'),
        db.CheckConstraint(
            '(assignment_entity_status_id IS NOT NULL) OR (public_submission_id IS NOT NULL)',
            name='ck_form_data_parent',
        ),
        db.CheckConstraint(
            "disagg_data IS NULL OR NOT (disagg_data::jsonb ? 'mode') OR "
            "(disagg_data::jsonb ? 'mode' AND disagg_data::jsonb ? 'values')",
            name='ck_form_data_disagg_shape',
        ),
    )

    @classmethod
    def sync_imputed_numeric_value(cls, entry, imputed_value):
        """Set imputed_numeric_value alongside imputed_value when imputed_value is numeric."""
        scalar_value = cls._coerce_scalar_text_value(imputed_value)
        entry.imputed_value = scalar_value
        if scalar_value is None:
            entry.imputed_numeric_value = None
            return
        entry.imputed_numeric_value = cls._parse_numeric_string(scalar_value)

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

    def __repr__(self):
        item_label = 'N/A'
        if self.form_item:
            item_type = self.form_item.item_type.title()
            item_label = f"{item_type}:{self.form_item.label}"
        else:
            item_label = "Item:N/A"

        # Access country and assignment info through the assignment_entity_status relationship
        status_info = self.assignment_entity_status
        country_name = 'N/A'
        if status_info:
            from app.utils.api_serialization import _country_for_aes
            _c = _country_for_aes(status_info)
            country_name = _c.name if _c else 'N/A'
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


class DynamicIndicatorData(DataEntryMixin, db.Model):
    """Tracks dynamically added indicators by focal points in dynamic sections and stores their data."""
    __tablename__ = 'dynamic_indicator_data'

    id = db.Column(db.Integer, primary_key=True)
    # Polymorphic foreign key for multi-entity support
    assignment_entity_status_id = db.Column(db.Integer, db.ForeignKey('assignment_entity_status.id'), nullable=True)
    public_submission_id = db.Column(db.Integer, db.ForeignKey('public_submission.id'), nullable=True)
    section_id = db.Column(db.Integer, db.ForeignKey('form_section.id'), nullable=False)  # The dynamic section
    indicator_bank_id = db.Column(db.Integer, db.ForeignKey('indicator_bank.id'), nullable=False)

    # When this indicator belongs to a specific repeat-group entry, store the instance number.
    # NULL means the indicator is section-level (no repeat parent).
    repeat_instance_number = db.Column(db.Integer, nullable=True)

    # Assignment metadata
    custom_label = db.Column(db.String(255), nullable=True)
    order = db.Column(db.Float, nullable=False, default=0)
    added_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    added_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    prefilled_value = db.Column(db.String(255), nullable=True)
    prefilled_disagg_data = db.Column(db.JSON(none_as_null=True), nullable=True)
    imputed_value = db.Column(db.String(255), nullable=True)
    imputed_disagg_data = db.Column(db.JSON(none_as_null=True), nullable=True)
    imputed_numeric_value = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, nullable=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)

    # Relationships
    assignment_entity_status = db.relationship('AssignmentEntityStatus', foreign_keys=[assignment_entity_status_id])
    public_submission = db.relationship('PublicSubmission')
    # Note: 'section' relationship is defined in FormSection with cascade delete
    indicator_bank = db.relationship('IndicatorBank', backref='dynamic_assignments')
    added_by_user = db.relationship('User', foreign_keys=[added_by_user_id], backref='added_dynamic_indicators')
    created_by_user = db.relationship('User', foreign_keys=[created_by_user_id])

    # Ensure unique assignment per country/section/indicator/repeat-instance combination.
    # repeat_instance_number=NULL means section-level (enforced by the API).
    __table_args__ = (
        db.UniqueConstraint('assignment_entity_status_id', 'section_id', 'indicator_bank_id', 'repeat_instance_number', name='_dynamic_indicator_entity_unique'),
        db.UniqueConstraint('public_submission_id', 'section_id', 'indicator_bank_id', 'repeat_instance_number', name='_dynamic_indicator_public_unique'),
        db.Index('ix_dynamic_indicator_aes', 'assignment_entity_status_id'),
        db.Index('ix_dynamic_indicator_public', 'public_submission_id'),
        db.Index('ix_dynamic_indicator_section', 'section_id'),
        db.Index('ix_dynamic_indicator_added_by', 'added_by_user_id'),
        db.Index('ix_dynamic_indicator_added_at', 'added_at'),
        db.Index('ix_dynamic_indicator_data_created_by', 'created_by_user_id'),
        db.CheckConstraint(
            '(assignment_entity_status_id IS NOT NULL) OR (public_submission_id IS NOT NULL)',
            name='ck_dynamic_indicator_data_parent',
        ),
        db.CheckConstraint(
            "disagg_data IS NULL OR NOT (disagg_data::jsonb ? 'mode') OR "
            "(disagg_data::jsonb ? 'mode' AND disagg_data::jsonb ? 'values')",
            name='ck_dynamic_indicator_data_disagg_shape',
        ),
    )

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
        if self.assignment_entity_status:
            from app.utils.api_serialization import _country_for_aes
            _c = _country_for_aes(self.assignment_entity_status)
            country_name = _c.name if _c else None
        return f'<DynamicIndicatorData {self.indicator_bank.name} for {country_name or "N/A"} Value:{display_value}>'


class DynamicSectionContext(db.Model):
    """Binds a dynamic section to a stable external context (e.g. an emergency operation) per assignment.

    Generic, provider-based binding so any list-type plugin can anchor a dynamic section to a stable
    key instead of a positional slot. For Emergency Operations: provider_id='emergency_operations',
    context_key=appeal code (e.g. 'MDRBD018'), slot=the EO position (1/2/3) the section references.

    The binding is captured server-side at save time and frozen, so saved dynamic-indicator data stays
    attributable to the same emergency even when the source API reorders results or filters change.
    """
    __tablename__ = 'dynamic_section_context'

    id = db.Column(db.Integer, primary_key=True)
    # Parent (mirrors DynamicIndicatorData's polymorphic parents)
    assignment_entity_status_id = db.Column(db.Integer, db.ForeignKey('assignment_entity_status.id'), nullable=True)
    public_submission_id = db.Column(db.Integer, db.ForeignKey('public_submission.id'), nullable=True)
    section_id = db.Column(db.Integer, db.ForeignKey('form_section.id'), nullable=False)

    # Generic provider/context identity
    provider_id = db.Column(db.String(64), nullable=False)  # e.g. 'emergency_operations'
    slot = db.Column(db.Integer, nullable=True)             # positional slot the section references (EO1/2/3 -> 1/2/3)
    context_key = db.Column(db.String(128), nullable=False)  # stable external key (appeal code)
    label_snapshot = db.Column(db.String(512), nullable=True)  # human label captured at bind time
    status = db.Column(db.String(32), nullable=False, default='active')  # 'active' | 'dropped'
    filters_hash = db.Column(db.String(64), nullable=True)   # snapshot of the filters used at resolution time

    resolved_at = db.Column(db.DateTime, default=utcnow, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)

    # Relationships
    assignment_entity_status = db.relationship('AssignmentEntityStatus', foreign_keys=[assignment_entity_status_id])
    public_submission = db.relationship('PublicSubmission', foreign_keys=[public_submission_id])
    created_by_user = db.relationship('User', foreign_keys=[created_by_user_id])

    __table_args__ = (
        db.UniqueConstraint('assignment_entity_status_id', 'section_id', 'provider_id', name='_dynamic_section_context_entity_unique'),
        db.UniqueConstraint('public_submission_id', 'section_id', 'provider_id', name='_dynamic_section_context_public_unique'),
        db.Index('ix_dynamic_section_context_aes', 'assignment_entity_status_id'),
        db.Index('ix_dynamic_section_context_public', 'public_submission_id'),
        db.Index('ix_dynamic_section_context_section', 'section_id'),
        db.CheckConstraint(
            '(assignment_entity_status_id IS NOT NULL) OR (public_submission_id IS NOT NULL)',
            name='ck_dynamic_section_context_parent',
        ),
    )

    def __repr__(self):
        return f'<DynamicSectionContext section={self.section_id} {self.provider_id}:{self.context_key} slot={self.slot} status={self.status}>'


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
        db.CheckConstraint(
            '(assignment_entity_status_id IS NOT NULL) OR (public_submission_id IS NOT NULL)',
            name='ck_repeat_group_instance_parent',
        ),
    )

    def __repr__(self):
        return f'<RepeatGroupInstance {self.instance_number} for Section {self.section_id}>'


class RepeatGroupData(DataEntryMixin, db.Model):
    """Stores data entries for fields within a repeat group instance."""
    __tablename__ = 'repeat_group_data'

    id = db.Column(db.Integer, primary_key=True)
    repeat_instance_id = db.Column(db.Integer, db.ForeignKey('repeat_group_instance.id'), nullable=False)

    # Unified approach - link to FormItem instead of separate indicator_id/question_id
    form_item_id = db.Column(db.Integer, db.ForeignKey('form_item.id'), nullable=False)

    # Unified relationship - primary approach
    form_item = db.relationship('FormItem', foreign_keys=[form_item_id], overlaps="repeat_data_entries")
    repeat_instance = relationship('RepeatGroupInstance', overlaps="data_entries")
    prefilled_value = db.Column(db.String(255), nullable=True)
    prefilled_disagg_data = db.Column(db.JSON(none_as_null=True), nullable=True)
    imputed_value = db.Column(db.String(255), nullable=True)
    imputed_disagg_data = db.Column(db.JSON(none_as_null=True), nullable=True)
    imputed_numeric_value = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, nullable=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
    created_by_user = db.relationship('User', foreign_keys=[created_by_user_id])

    __table_args__ = (
        db.Index('ix_repeat_data_instance', 'repeat_instance_id'),
        db.Index('ix_repeat_data_instance_item', 'repeat_instance_id', 'form_item_id'),
        db.Index('ix_repeat_data_form_item', 'form_item_id'),
        db.Index('ix_repeat_data_submitted_at', 'submitted_at'),
        db.Index('ix_repeat_group_data_created_by', 'created_by_user_id'),
        db.CheckConstraint(
            "disagg_data IS NULL OR NOT (disagg_data::jsonb ? 'mode') OR "
            "(disagg_data::jsonb ? 'mode' AND disagg_data::jsonb ? 'values')",
            name='ck_repeat_group_data_disagg_shape',
        ),
    )

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
