"""
Indicator Bank models including indicators, sectors, subsectors, and common words.
"""
from sqlalchemy import Column, Integer, ForeignKey, String, Text, Boolean, JSON, Date, Float
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, backref
from ..extensions import db
from app.utils.datetime_helpers import utcnow

# Import FormItem for the template_instances property
from .form_items import FormItem


class IndicatorBank(db.Model):
    __tablename__ = 'indicator_bank'
    id = db.Column(db.Integer, primary_key=True)
    # Changed to Text to remove 255-char limit for long indicator names
    name = db.Column(db.Text, nullable=False, unique=True)
    type = db.Column(db.String(50), nullable=False) # e.g., 'number', 'percentage'
    unit = db.Column(db.String(50), nullable=True) # e.g., 'people', '%'
    fdrs_kpi_code = db.Column(db.String(50), nullable=True)  # FDRS KPI Code
    definition = db.Column(db.Text, nullable=True)  # Changed from 'description' to 'definition'

    # Multilingual indicator name fields - now using JSONB for better performance and flexibility
    name_translations = db.Column(JSONB, nullable=True)  # Format: {"en": "name", "fr": "nom", "es": "nombre", "ar": "اسم", "zh": "名称", "ru": "название", "hi": "नाम"}

    # Multilingual indicator definition fields - now using JSONB for better performance and flexibility
    definition_translations = db.Column(JSONB, nullable=True)  # Format: {"en": "definition", "fr": "définition", "es": "definición", "ar": "تعريف", "zh": "定义", "ru": "определение", "hi": "परिभाषा"}

    # New fields for management
    archived = db.Column(db.Boolean, default=False, nullable=False)
    comments = db.Column(db.Text, nullable=True)
    emergency = db.Column(db.Boolean, default=False, nullable=False)
    related_programs = db.Column(db.Text, nullable=True)  # Comma separated list

    # JSON fields for Sector and Sub-Sector with Primary/Secondary/Tertiary levels
    # Format: {"primary": sector_id, "secondary": sector_id, "tertiary": sector_id}
    sector = db.Column(JSONB, nullable=True)
    sub_sector = db.Column(JSONB, nullable=True)

    # Timestamps for tracking changes
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    # Legacy template_instances relationship removed - now handled via FormItem
    history = db.relationship('IndicatorBankHistory', backref='indicator', lazy='dynamic', order_by='desc(IndicatorBankHistory.created_at)')

    __table_args__ = (
        db.Index('ix_indicator_bank_type_unit', 'type', 'unit'),
        db.Index('ix_indicator_bank_archived', 'archived'),
        db.Index('ix_indicator_bank_emergency', 'emergency'),
        db.Index('ix_indicator_bank_created_at', 'created_at'),
        db.Index('ix_indicator_bank_updated_at', 'updated_at'),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.created_at is None:
            self.created_at = utcnow()
        if self.updated_at is None:
            self.updated_at = utcnow()

    @property
    def sector_display(self):
        """Returns a formatted display string for sector levels."""
        if not self.sector:
            return ""
        parts = []
        if self.sector.get('primary'):
            sector = Sector.query.get(self.sector['primary'])
            if sector:
                parts.append(f"Primary: {sector.name}")
        if self.sector.get('secondary'):
            sector = Sector.query.get(self.sector['secondary'])
            if sector:
                parts.append(f"Secondary: {sector.name}")
        if self.sector.get('tertiary'):
            sector = Sector.query.get(self.sector['tertiary'])
            if sector:
                parts.append(f"Tertiary: {sector.name}")
        return " | ".join(parts)

    @property
    def sub_sector_display(self):
        """Returns a formatted display string for sub-sector levels."""
        if not self.sub_sector:
            return ""
        parts = []
        if self.sub_sector.get('primary'):
            subsector = SubSector.query.get(self.sub_sector['primary'])
            if subsector:
                parts.append(f"Primary: {subsector.name}")
        if self.sub_sector.get('secondary'):
            subsector = SubSector.query.get(self.sub_sector['secondary'])
            if subsector:
                parts.append(f"Secondary: {subsector.name}")
        if self.sub_sector.get('tertiary'):
            subsector = SubSector.query.get(self.sub_sector['tertiary'])
            if subsector:
                parts.append(f"Tertiary: {subsector.name}")
        return " | ".join(parts)

    @property
    def related_programs_list(self):
        """Returns related programs as a list."""
        if not self.related_programs:
            return []

        # Cache the parsed list to avoid repeated string splitting
        if not hasattr(self, '_cached_programs_list'):
            self._cached_programs_list = [program.strip() for program in self.related_programs.split(',') if program.strip()]

        return self._cached_programs_list

    # Helper methods for sector and sub-sector access
    def get_sector_by_level(self, level):
        """Get sector object by level (primary, secondary, tertiary)."""
        if not self.sector or level not in self.sector:
            return None

        # Use cached sector data if available (from prefetching)
        if hasattr(self, '_cached_sectors') and level in self._cached_sectors:
            return self._cached_sectors[level]

        # Fallback to database query if not cached
        from ..extensions import db
        return db.session.get(Sector, self.sector[level])

    def get_sector_name_by_level(self, level):
        """Get sector name by level (primary, secondary, tertiary)."""
        sector = self.get_sector_by_level(level)
        return sector.name if sector else None

    def get_subsector_by_level(self, level):
        """Get sub-sector object by level (primary, secondary, tertiary)."""
        if not self.sub_sector or level not in self.sub_sector:
            return None

        # Use cached subsector data if available (from prefetching)
        if hasattr(self, '_cached_subsectors') and level in self._cached_subsectors:
            return self._cached_subsectors[level]

        # Fallback to database query if not cached
        from ..extensions import db
        return db.session.get(SubSector, self.sub_sector[level])

    def get_subsector_name_by_level(self, level):
        """Get sub-sector name by level (primary, secondary, tertiary)."""
        subsector = self.get_subsector_by_level(level)
        return subsector.name if subsector else None

    def get_all_sector_names(self):
        """Get all sector names as a list."""
        names = []
        for level in ['primary', 'secondary', 'tertiary']:
            name = self.get_sector_name_by_level(level)
            if name:
                names.append(name)
        return names

    def get_all_subsector_names(self):
        """Get all sub-sector names as a list."""
        names = []
        for level in ['primary', 'secondary', 'tertiary']:
            name = self.get_subsector_name_by_level(level)
            if name:
                names.append(name)
        return names

    def clear_cache(self):
        """Clear cached data when sector/subsector relationships change."""
        if hasattr(self, '_cached_sectors'):
            delattr(self, '_cached_sectors')
        if hasattr(self, '_cached_subsectors'):
            delattr(self, '_cached_subsectors')
        if hasattr(self, '_cached_programs_list'):
            delattr(self, '_cached_programs_list')

    @property
    def template_instances(self):
        """Return a SQLAlchemy *query* of ``FormItem`` objects that reference this
        indicator. This preserves compatibility with legacy templates that expect a
        ``template_instances`` dynamic relationship supporting ``.count()`` and
        iteration.

        The ``FormItem`` class is defined in this module, so we can reference it
        directly. Because the query is created lazily at call-time, there are no
        circular import issues.
        """
        return FormItem.query.filter_by(indicator_bank_id=self.id)

    @property
    def usage_count(self):
        """Calculate the number of times this indicator is used in templates.
        This is calculated dynamically at runtime by counting FormItem references.
        Uses cached value if available (from prefetching) to avoid N+1 queries.
        """
        # Use cached value if available (set during bulk prefetching)
        if hasattr(self, '_cached_usage_count'):
            return self._cached_usage_count
        return self.template_instances.count()

    # Translation helper methods for JSONB fields
    def get_name_translation(self, language):
        """Get name translation for specific language."""
        if self.name_translations and language in self.name_translations:
            return self.name_translations[language]
        return self.name

    def set_name_translation(self, language, text):
        """Set name translation for specific language."""
        if not self.name_translations:
            self.name_translations = {}
        if text and text.strip():
            self.name_translations[language] = text.strip()
        elif language in self.name_translations:
            del self.name_translations[language]

    def get_definition_translation(self, language):
        """Get definition translation for specific language."""
        if self.definition_translations and language in self.definition_translations:
            return self.definition_translations[language]
        return self.definition

    def set_definition_translation(self, language, text):
        """Set definition translation for specific language."""
        if not self.definition_translations:
            self.definition_translations = {}
        if text and text.strip():
            self.definition_translations[language] = text.strip()
        elif language in self.definition_translations:
            del self.definition_translations[language]

    def __repr__(self):
        return f'<IndicatorBank {self.name} (Type: {self.type})>'


class IndicatorBankHistory(db.Model):
    """Model to track changes to indicators in the indicator bank."""
    __tablename__ = 'indicator_bank_history'

    id = db.Column(db.Integer, primary_key=True)
    indicator_bank_id = db.Column(db.Integer, db.ForeignKey('indicator_bank.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    # Store the complete state at the time of change
    name = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(50), nullable=False)
    unit = db.Column(db.String(50), nullable=True)
    fdrs_kpi_code = db.Column(db.String(50), nullable=True)
    definition = db.Column(db.Text, nullable=True)

    # Multilingual indicator name fields - now using JSONB for better performance and flexibility
    name_translations = db.Column(JSONB, nullable=True)  # Format: {"en": "name", "fr": "nom", "es": "nombre", "ar": "اسم", "zh": "名称", "ru": "название", "hi": "नाम"}

    # Multilingual indicator definition fields - now using JSONB for better performance and flexibility
    definition_translations = db.Column(JSONB, nullable=True)  # Format: {"en": "definition", "fr": "définition", "es": "definición", "ar": "تعريف", "zh": "定义", "ru": "определение", "hi": "परिभाषा"}

    archived = db.Column(db.Boolean, default=False, nullable=False)
    comments = db.Column(db.Text, nullable=True)
    emergency = db.Column(db.Boolean, default=False, nullable=False)
    related_programs = db.Column(db.Text, nullable=True)
    sector = db.Column(JSONB, nullable=True)  # Now stores IDs instead of names
    sub_sector = db.Column(JSONB, nullable=True)  # Now stores IDs instead of names

    # Change metadata
    change_type = db.Column(db.String(20), nullable=False)  # 'create', 'update', 'delete'
    change_description = db.Column(db.Text, nullable=False)  # Human-readable description of changes
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    # Relationships
    user = db.relationship('User', backref='indicator_changes')

    __table_args__ = (
        db.Index('ix_indicator_history_indicator_time', 'indicator_bank_id', 'created_at'),
        db.Index('ix_indicator_history_user', 'user_id'),
        db.Index('ix_indicator_history_change_type', 'change_type'),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.created_at is None:
            self.created_at = utcnow()

    # Translation helper methods for JSONB fields
    def get_name_translation(self, language):
        """Get name translation for specific language."""
        if self.name_translations and language in self.name_translations:
            return self.name_translations[language]
        return self.name

    def set_name_translation(self, language, text):
        """Set name translation for specific language."""
        if not self.name_translations:
            self.name_translations = {}
        if text and text.strip():
            self.name_translations[language] = text.strip()
        elif language in self.name_translations:
            del self.name_translations[language]

    def get_definition_translation(self, language):
        """Get definition translation for specific language."""
        if self.definition_translations and language in self.definition_translations:
            return self.definition_translations[language]
        return self.definition

    def set_definition_translation(self, language, text):
        """Set definition translation for specific language."""
        if not self.definition_translations:
            self.definition_translations = {}
        if text and text.strip():
            self.definition_translations[language] = text.strip()
        elif language in self.definition_translations:
            del self.definition_translations[language]

    def __repr__(self):
        return f'<IndicatorBankHistory {self.indicator_bank_id} - {self.change_type} by {self.user_id} at {self.created_at}>'


class IndicatorSuggestion(db.Model):
    __tablename__ = 'indicator_suggestion'

    id = db.Column(db.Integer, primary_key=True)

    # Contact information
    submitter_name = db.Column(db.String(255), nullable=False)
    submitter_email = db.Column(db.String(255), nullable=False)

    # Suggestion metadata
    suggestion_type = db.Column(db.String(50), nullable=False)  # 'correction', 'improvement', 'new_indicator', 'other'
    status = db.Column(db.String(20), default='Pending', nullable=False)  # 'Pending', 'reviewed', 'approved', 'rejected'
    submitted_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    reviewed_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    # Related indicator (nullable for new indicator suggestions)
    indicator_id = db.Column(db.Integer, db.ForeignKey('indicator_bank.id'), nullable=True)

    # Suggested indicator data
    indicator_name = db.Column(db.String(255), nullable=False)
    definition = db.Column(db.Text, nullable=True)
    type = db.Column(db.String(50), nullable=True)
    unit = db.Column(db.String(50), nullable=True)
    sector = db.Column(JSONB, nullable=True)  # Use JSONB for Postgres operations
    sub_sector = db.Column(JSONB, nullable=True)  # Use JSONB for Postgres operations
    emergency = db.Column(db.Boolean, default=False, nullable=False)
    related_programs = db.Column(db.Text, nullable=True)

    # Additional information
    reason = db.Column(db.Text, nullable=False)
    additional_notes = db.Column(db.Text, nullable=True)

    # Admin notes
    admin_notes = db.Column(db.Text, nullable=True)

    # Relationships
    indicator = db.relationship('IndicatorBank', backref='suggestions')
    reviewed_by = db.relationship('User', backref='reviewed_suggestions')

    __table_args__ = (
        db.Index('ix_indicator_suggestion_indicator', 'indicator_id'),
        db.Index('ix_indicator_suggestion_status', 'status'),
        db.Index('ix_indicator_suggestion_submitted_at', 'submitted_at'),
        db.Index('ix_indicator_suggestion_reviewer', 'reviewed_by_user_id'),
        db.Index('ix_indicator_suggestion_submitter_email', 'submitter_email'),
    )

    def __repr__(self):
        return f'<IndicatorSuggestion {self.id}: {self.indicator_name} by {self.submitter_name}>'

    @property
    def is_new_indicator(self):
        return self.suggestion_type == 'new_indicator'

    @property
    def status_display(self):
        status_map = {
            'pending': 'Pending Review',
            'reviewed': 'Under Review',
            'approved': 'Approved',
            'rejected': 'Rejected'
        }
        return status_map.get(self.status, self.status.title())

    @property
    def suggestion_type_display(self):
        type_map = {
            'correction': 'Correction to existing indicator',
            'improvement': 'Improvement to existing indicator',
            'new_indicator': 'Propose new indicator',
            'other': 'Other'
        }
        return type_map.get(self.suggestion_type, self.suggestion_type.title())

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


class Sector(db.Model):
    """Model for managing sectors with logos and display information."""
    __tablename__ = 'sector'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=True)
    logo_filename = db.Column(db.String(255), nullable=True)  # Original filename
    logo_path = db.Column(db.String(512), nullable=True)  # Relative path to logo file
    display_order = db.Column(db.Integer, default=0, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    # Icon fallback for backwards compatibility
    icon_class = db.Column(db.String(50), nullable=True)  # FontAwesome class

    # Multilingual sector name translations (future-proof; supports any ISO code)
    # Format: {"en": "...", "fr": "...", ...}
    name_translations = db.Column(JSONB, nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    # Note: Relationships to indicators handled via direct queries when needed
    # due to JSON field complexity across different database types

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.created_at is None:
            self.created_at = utcnow()
        if self.updated_at is None:
            self.updated_at = utcnow()

    @property
    def logo_url(self):
        """Returns the URL path for the logo if it exists."""
        if self.logo_path:
            return f"/uploads/sectors/{self.logo_path}"
        return None

    __table_args__ = (
        db.Index('ix_sector_active_order', 'is_active', 'display_order'),
    )

    def __repr__(self):
        return f'<Sector {self.name}>'

    # Translation helpers using JSONB
    def get_name_translation(self, language: str):
        lang = (language or '').strip().lower().split('_', 1)[0].split('-', 1)[0]
        if self.name_translations and isinstance(self.name_translations, dict):
            val = self.name_translations.get(lang)
            if isinstance(val, str) and val.strip():
                return val.strip()
        return self.name

    def set_name_translation(self, language: str, text: str):
        lang = (language or '').strip().lower().split('_', 1)[0].split('-', 1)[0]
        if not lang or lang == 'en':
            return
        if not self.name_translations or not isinstance(self.name_translations, dict):
            self.name_translations = {}
        value = (text or '').strip()
        if value:
            self.name_translations[lang] = value
        else:
            self.name_translations.pop(lang, None)


class SubSector(db.Model):
    """Model for managing sub-sectors with logos and display information."""
    __tablename__ = 'sub_sector'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=True)
    logo_filename = db.Column(db.String(255), nullable=True)  # Original filename
    logo_path = db.Column(db.String(512), nullable=True)  # Relative path to logo file
    display_order = db.Column(db.Integer, default=0, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    # Icon fallback for backwards compatibility
    icon_class = db.Column(db.String(50), nullable=True)  # FontAwesome class

    # Multilingual sub-sector name translations (future-proof; supports any ISO code)
    name_translations = db.Column(JSONB, nullable=True)

    # Optional: Link to parent sector
    sector_id = db.Column(db.Integer, db.ForeignKey('sector.id'), nullable=True)
    sector = db.relationship('Sector', backref='sub_sectors')

    __table_args__ = (
        db.Index('ix_subsector_active_order', 'is_active', 'display_order'),
        db.Index('ix_subsector_sector', 'sector_id'),
    )

    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    # Note: Relationships to indicators handled via direct queries when needed
    # due to JSON field complexity across different database types

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.created_at is None:
            self.created_at = utcnow()
        if self.updated_at is None:
            self.updated_at = utcnow()

    @property
    def logo_url(self):
        """Returns the URL path for the logo if it exists."""
        if self.logo_path:
            return f"/uploads/subsectors/{self.logo_path}"
        return None

    def __repr__(self):
        return f'<SubSector {self.name}>'

    def get_name_translation(self, language: str):
        lang = (language or '').strip().lower().split('_', 1)[0].split('-', 1)[0]
        if self.name_translations and isinstance(self.name_translations, dict):
            val = self.name_translations.get(lang)
            if isinstance(val, str) and val.strip():
                return val.strip()
        return self.name

    def set_name_translation(self, language: str, text: str):
        lang = (language or '').strip().lower().split('_', 1)[0].split('-', 1)[0]
        if not lang or lang == 'en':
            return
        if not self.name_translations or not isinstance(self.name_translations, dict):
            self.name_translations = {}
        value = (text or '').strip()
        if value:
            self.name_translations[lang] = value
        else:
            self.name_translations.pop(lang, None)


class CommonWord(db.Model):
    """Model to store common words/terms used in indicators with their meanings for tooltips."""
    __tablename__ = 'common_word'

    id = db.Column(db.Integer, primary_key=True)
    term = db.Column(db.String(255), nullable=False, unique=True, index=True)
    meaning = db.Column(db.Text, nullable=False)

    # Multilingual meanings for different languages
    meaning_translations = db.Column(JSONB, nullable=True)  # Format: {"fr": "meaning", "es": "meaning", "ar": "meaning", "zh": "meaning", "ru": "meaning", "hi": "meaning"}

    # Metadata
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    # Relationships
    created_by_user = db.relationship('User', backref='created_common_words')

    __table_args__ = (
        db.Index('ix_common_word_active', 'is_active'),
        db.Index('ix_common_word_created_at', 'created_at'),
        db.Index('ix_common_word_created_by', 'created_by_user_id'),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.created_at is None:
            self.created_at = utcnow()
        if self.updated_at is None:
            self.updated_at = utcnow()

    def get_meaning_translation(self, language):
        """Get meaning translation for specific language."""
        if self.meaning_translations and language in self.meaning_translations:
            return self.meaning_translations[language]
        return self.meaning

    def set_meaning_translation(self, language, text):
        """Set meaning translation for specific language."""
        if not self.meaning_translations:
            self.meaning_translations = {}
        if text and text.strip():
            self.meaning_translations[language] = text.strip()
        elif language in self.meaning_translations:
            del self.meaning_translations[language]

    def __repr__(self):
        return f'<CommonWord {self.term}>'
