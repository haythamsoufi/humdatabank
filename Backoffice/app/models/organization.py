"""
Organization hierarchy models for National Society structure.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, ForeignKey, String, Text, DateTime, Boolean, Date
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, backref, validates
from ..extensions import db
from app.utils.datetime_helpers import utcnow


class NationalSociety(db.Model):
    """Represents a National Society entity associated to a Country.

    One Country can have one or more National Societies.
    """
    __tablename__ = 'national_societies'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    code = db.Column(db.String(50), nullable=True, unique=True)
    description = db.Column(db.Text, nullable=True)
    # Multilingual NS Name fields
    name_translations = db.Column(JSONB, nullable=True)

    # Projects/Emergencies/Programs this NS is part of
    part_of = db.Column(JSONB, nullable=True)

    # Status and metadata
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    display_order = db.Column(db.Integer, default=0, nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    # Foreign key relationships
    country_id = db.Column(db.Integer, db.ForeignKey('country.id'), nullable=False, index=True)

    # Relationships
    country = db.relationship('Country', backref='national_societies')

    def __repr__(self):
        country_name = self.country.name if self.country else 'N/A'
        return f'<NationalSociety {self.name} ({country_name})>'

    @validates('code')
    def _normalize_code(self, key, value):
        # Convert blank or whitespace-only codes to NULL to avoid unique conflicts on empty strings
        if value is None:
            return None
        stripped = value.strip()
        return stripped if stripped else None

    # Translation helpers
    def get_name_translation(self, language: str):
        if self.name_translations and language in self.name_translations:
            return self.name_translations[language]
        return self.name

    def set_name_translation(self, language: str, text: str):
        if not self.name_translations:
            self.name_translations = {}
        if text and text.strip():
            self.name_translations[language] = text.strip()
        elif language in self.name_translations:
            del self.name_translations[language]


class NSBranch(db.Model):
    """Represents a National Society branch within a country."""
    __tablename__ = 'ns_branches'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    code = db.Column(db.String(50), nullable=True, unique=True)  # Optional unique code
    description = db.Column(db.Text, nullable=True)
    name_translations = db.Column(JSONB, nullable=True)

    # Geographic information
    address = db.Column(db.Text, nullable=True)
    city = db.Column(db.String(100), nullable=True)
    postal_code = db.Column(db.String(20), nullable=True)
    coordinates = db.Column(db.String(100), nullable=True)  # Latitude,Longitude format

    # Contact information
    phone = db.Column(db.String(50), nullable=True)
    email = db.Column(db.String(255), nullable=True)
    website = db.Column(db.String(255), nullable=True)

    # Status and metadata
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    established_date = db.Column(db.Date, nullable=True)
    display_order = db.Column(db.Integer, default=0, nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    # Foreign key relationships
    country_id = db.Column(db.Integer, db.ForeignKey('country.id'), nullable=False, index=True)

    # Relationships
    country = db.relationship('Country', backref='ns_branches')
    subbranches = db.relationship('NSSubBranch', backref='branch', lazy='dynamic', cascade="all, delete-orphan")
    local_units = db.relationship('NSLocalUnit', backref='branch', lazy='dynamic', cascade="all, delete-orphan")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.created_at is None:
            self.created_at = utcnow()
        if self.updated_at is None:
            self.updated_at = utcnow()

    def __repr__(self):
        country_name = self.country.name if self.country else 'N/A'
        return f'<NSBranch {self.name} ({country_name})>'

    @validates('code')
    def _normalize_code(self, key, value):
        # Convert blank or whitespace-only codes to NULL to avoid unique conflicts on empty strings
        if value is None:
            return None
        stripped = value.strip()
        return stripped if stripped else None


class NSSubBranch(db.Model):
    """Represents a National Society sub-branch within a branch."""
    __tablename__ = 'ns_subbranches'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    code = db.Column(db.String(50), nullable=True)  # Optional code (not unique across all subbranches)
    description = db.Column(db.Text, nullable=True)
    name_translations = db.Column(JSONB, nullable=True)

    # Geographic information
    address = db.Column(db.Text, nullable=True)
    city = db.Column(db.String(100), nullable=True)
    postal_code = db.Column(db.String(20), nullable=True)
    coordinates = db.Column(db.String(100), nullable=True)  # Latitude,Longitude format

    # Contact information
    phone = db.Column(db.String(50), nullable=True)
    email = db.Column(db.String(255), nullable=True)

    # Status and metadata
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    established_date = db.Column(db.Date, nullable=True)
    display_order = db.Column(db.Integer, default=0, nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    # Foreign key relationships
    branch_id = db.Column(db.Integer, db.ForeignKey('ns_branches.id'), nullable=False)

    # Relationships
    local_units = db.relationship('NSLocalUnit', backref='subbranch', lazy='dynamic', cascade="all, delete-orphan")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.created_at is None:
            self.created_at = utcnow()
        if self.updated_at is None:
            self.updated_at = utcnow()

    def __repr__(self):
        branch_name = self.branch.name if self.branch else 'N/A'
        return f'<NSSubBranch {self.name} (Branch: {branch_name})>'


class NSLocalUnit(db.Model):
    """Represents a National Society local unit within a branch or sub-branch."""
    __tablename__ = 'ns_localunits'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    code = db.Column(db.String(50), nullable=True)  # Optional code (not unique across all local units)
    description = db.Column(db.Text, nullable=True)
    name_translations = db.Column(JSONB, nullable=True)

    # Geographic information
    address = db.Column(db.Text, nullable=True)
    city = db.Column(db.String(100), nullable=True)
    postal_code = db.Column(db.String(20), nullable=True)
    coordinates = db.Column(db.String(100), nullable=True)  # Latitude,Longitude format

    # Contact information
    phone = db.Column(db.String(50), nullable=True)
    email = db.Column(db.String(255), nullable=True)

    # Status and metadata
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    established_date = db.Column(db.Date, nullable=True)
    display_order = db.Column(db.Integer, default=0, nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    # Foreign key relationships - local units can belong to either a branch directly or a sub-branch
    branch_id = db.Column(db.Integer, db.ForeignKey('ns_branches.id'), nullable=False)
    subbranch_id = db.Column(db.Integer, db.ForeignKey('ns_subbranches.id'), nullable=True)  # Optional - can be null if directly under branch

    # Relationships
    # Note: branch relationship is defined above with backref
    # Note: subbranch relationship is defined above with backref

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.created_at is None:
            self.created_at = utcnow()
        if self.updated_at is None:
            self.updated_at = utcnow()

    @property
    def parent_entity(self):
        """Returns the immediate parent entity (either subbranch or branch)."""
        if self.subbranch_id:
            return self.subbranch
        return self.branch

    @property
    def hierarchy_path(self):
        """Returns a string representation of the full hierarchy path."""
        path_parts = []

        if self.country:
            path_parts.append(self.country.name)

        if self.branch:
            path_parts.append(self.branch.name)

        if self.subbranch:
            path_parts.append(self.subbranch.name)

        path_parts.append(self.name)

        return " > ".join(path_parts)

    @property
    def country(self):
        """Returns the country this local unit belongs to."""
        return self.branch.country if self.branch else None

    def __repr__(self):
        parent_info = f"SubBranch: {self.subbranch.name}" if self.subbranch else f"Branch: {self.branch.name}"
        return f'<NSLocalUnit {self.name} ({parent_info})>'


class SecretariatDivision(db.Model):
    """Represents a division in the IFRC Secretariat."""
    __tablename__ = 'secretariat_divisions'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    code = db.Column(db.String(50), nullable=True, unique=True)
    description = db.Column(db.Text, nullable=True)
    name_translations = db.Column(JSONB, nullable=True)

    # Status and metadata
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    display_order = db.Column(db.Integer, default=0, nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    # Relationships
    departments = db.relationship('SecretariatDepartment', backref='division', lazy='dynamic', cascade="all, delete-orphan")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.created_at is None:
            self.created_at = utcnow()
        if self.updated_at is None:
            self.updated_at = utcnow()

    def __repr__(self):
        return f'<SecretariatDivision {self.name}>'

    @validates('code')
    def _normalize_code(self, key, value):
        # Convert blank or whitespace-only codes to NULL to avoid unique conflicts on empty strings
        if value is None:
            return None
        stripped = value.strip()
        return stripped if stripped else None


class SecretariatRegionalOffice(db.Model):
    """Represents a Secretariat Regional Office (parent of Cluster Offices)."""
    __tablename__ = 'secretariat_regional_offices'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    code = db.Column(db.String(50), nullable=True, unique=True)
    description = db.Column(db.Text, nullable=True)
    name_translations = db.Column(JSONB, nullable=True)

    # Status and metadata
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    display_order = db.Column(db.Integer, default=0, nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    # Relationships
    cluster_offices = db.relationship('SecretariatClusterOffice', backref='regional_office', lazy='dynamic', cascade="all, delete-orphan")

    def __repr__(self):
        return f'<SecretariatRegionalOffice {self.name}>'

    @validates('code')
    def _normalize_code(self, key, value):
        # Convert blank or whitespace-only codes to NULL to avoid unique conflicts on empty strings
        if value is None:
            return None
        stripped = value.strip()
        return stripped if stripped else None


class SecretariatClusterOffice(db.Model):
    """Represents a Secretariat Cluster Office under a Regional Office."""
    __tablename__ = 'secretariat_cluster_offices'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    code = db.Column(db.String(50), nullable=True, unique=True)
    description = db.Column(db.Text, nullable=True)
    name_translations = db.Column(JSONB, nullable=True)

    # Foreign Key
    regional_office_id = db.Column(db.Integer, db.ForeignKey('secretariat_regional_offices.id'), nullable=False)

    # Status and metadata
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    display_order = db.Column(db.Integer, default=0, nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    def __repr__(self):
        return f'<SecretariatClusterOffice {self.name} (Region ID: {self.regional_office_id})>'

    @validates('code')
    def _normalize_code(self, key, value):
        # Convert blank or whitespace-only codes to NULL to avoid unique conflicts on empty strings
        if value is None:
            return None
        stripped = value.strip()
        return stripped if stripped else None


class SecretariatDepartment(db.Model):
    """Represents a department within a Secretariat division."""
    __tablename__ = 'secretariat_departments'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    code = db.Column(db.String(50), nullable=True)
    description = db.Column(db.Text, nullable=True)
    name_translations = db.Column(JSONB, nullable=True)

    # Status and metadata
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    display_order = db.Column(db.Integer, default=0, nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    # Foreign key
    division_id = db.Column(db.Integer, db.ForeignKey('secretariat_divisions.id'), nullable=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.created_at is None:
            self.created_at = utcnow()
        if self.updated_at is None:
            self.updated_at = utcnow()

    def __repr__(self):
        division_name = self.division.name if self.division else 'N/A'
        return f'<SecretariatDepartment {self.name} (Division: {division_name})>'
