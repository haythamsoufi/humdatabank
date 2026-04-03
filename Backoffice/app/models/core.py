"""
Core models for user management, countries, and activity tracking.
"""
import logging
from datetime import datetime

logger = logging.getLogger(__name__)
from werkzeug.security import generate_password_hash, check_password_hash
import base64
import hashlib
import hmac
from flask_login import UserMixin
from sqlalchemy import Table, Column, Integer, ForeignKey, String, Text, DateTime, Boolean, JSON, Enum, LargeBinary, Date, Float, event, and_
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, backref, foreign
from config import Config
import enum
import uuid
import json
from ..extensions import db, login
from sqlalchemy.sql import text
from sqlalchemy import inspect
from .assignments import AssignmentEntityStatus
from contextlib import suppress
from app.utils.datetime_helpers import utcnow

# Legacy user_countries association removed; countries are now derived via user_entity_permissions


class UserEntityPermission(db.Model):
    """Polymorphic table for user permissions across different organizational entities."""
    __tablename__ = 'user_entity_permissions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    # Polymorphic fields
    entity_type = db.Column(db.String(50), nullable=False)  # 'country', 'ns_branch', 'ns_subbranch', 'ns_localunit', 'division', 'department'
    entity_id = db.Column(db.Integer, nullable=False)

    created_at = db.Column(db.DateTime, default=utcnow)

    # Relationship to User
    user = db.relationship('User', backref=db.backref('entity_permissions', lazy='dynamic', cascade="all, delete-orphan"))

    __table_args__ = (
        db.UniqueConstraint('user_id', 'entity_type', 'entity_id', name='_user_entity_uc'),
        db.Index('ix_user_entity_user', 'user_id'),
        db.Index('ix_user_entity_type_id', 'entity_type', 'entity_id'),
    )

    def __repr__(self):
        return f'<UserEntityPermission user_id={self.user_id} type={self.entity_type} entity_id={self.entity_id}>'


def int_or_none(value):
    """Coerces value to int, returns None on ValueError or TypeError."""
    try:
        if value is not None and str(value).strip() != '':
            return int(value)
        return None
    except (ValueError, TypeError):
        return None


class User(UserMixin, db.Model):
    __tablename__ = 'user'
    id = Column(Integer, primary_key=True)
    email = Column(String(120), index=True, unique=True, nullable=False)
    password_hash = Column(String(256))
    name = db.Column(db.String(100), nullable=True)
    title = db.Column(db.String(100), nullable=True)
    # Soft-archive/deactivation
    active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    deactivated_at = db.Column(db.DateTime, nullable=True)

    # User preferences
    chatbot_enabled = db.Column(db.Boolean, default=True, nullable=False)
    profile_color = db.Column(db.String(7), default='#3B82F6', nullable=False)  # Hex color code

    # Quiz game score
    quiz_score = db.Column(db.Integer, default=0, nullable=False)  # Total quiz points accumulated

    # Countries derived via UserEntityPermission (entity_type='country')
    countries = relationship(
        'Country',
        secondary='user_entity_permissions',
        primaryjoin=lambda: and_(User.id == foreign(UserEntityPermission.user_id), UserEntityPermission.entity_type == 'country'),
        secondaryjoin=lambda: foreign(UserEntityPermission.entity_id) == Country.id,
        lazy='dynamic',
        viewonly=True
    )

    api_key = db.Column(db.String(64), unique=True, nullable=True)

    @property
    def is_active(self):
        """Flask-Login uses this to determine if the user account is active."""
        try:
            return bool(self.active)
        except Exception as e:
            logger.debug("User.is_active check failed: %s", e)
            return True

    @property
    def all_countries(self):
        """Get all countries user has access to via entity permissions."""
        return list(self.countries.all())

    def set_password(self, password):
        # Ensure a cross-environment compatible default
        # Explicitly use PBKDF2-SHA256 so new hashes work on Fly and locally
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def check_password(self, password):
        if self.password_hash is None:
            return False
        # First, handle explicit scrypt hashes without invoking Werkzeug (to avoid UnsupportedDigestmodError)
        if isinstance(self.password_hash, str) and self.password_hash.startswith('scrypt:'):
            try:
                from flask import current_app
                current_app.logger.debug("Auth: scrypt hash detected; starting manual verification")
                # Format: 'scrypt:N:r:p$salt$hash'
                method_part, salt_str, hash_str = self.password_hash.split('$', 2)
                _, n_str, r_str, p_str = method_part.split(':', 3)
                n_cost = int(n_str)
                r_cost = int(r_str)
                p_cost = int(p_str)

                # Decode salt: try base64 (no padding), then hex, then raw ascii
                def _maybe_b64decode(s: str) -> bytes | None:
                    try:
                        # add padding to multiple of 4
                        pad = '=' * ((4 - (len(s) % 4)) % 4)
                        return base64.b64decode(s + pad)
                    except Exception as e:
                        logger.debug("_maybe_b64decode failed: %s", e)
                        return None

                def _maybe_hexdecode(s: str) -> bytes | None:
                    try:
                        return bytes.fromhex(s)
                    except Exception as e:
                        logger.debug("_maybe_hexdecode failed: %s", e)
                        return None

                # Prepare candidate salt interpretations: raw ascii, base64, hex
                candidates: list[tuple[str, bytes]] = []
                with suppress(Exception):
                    candidates.append(("raw", salt_str.encode('utf-8')))
                b64 = _maybe_b64decode(salt_str)
                if b64 is not None:
                    candidates.append(("base64", b64))
                hx = _maybe_hexdecode(salt_str)
                if hx is not None:
                    candidates.append(("hex", hx))

                # Infer dklen from stored hash
                dklen = None
                is_hex_hash = all(c in '0123456789abcdefABCDEF' for c in hash_str) and (len(hash_str) % 2 == 0)
                if is_hex_hash:
                    dklen = len(hash_str) // 2
                else:
                    # try base64 and urlsafe base64 to infer length
                    decoded = None
                    for use_urlsafe in (False, True):
                        try:
                            pad = '=' * ((4 - (len(hash_str) % 4)) % 4)
                            if use_urlsafe:
                                decoded = base64.urlsafe_b64decode(hash_str + pad)
                            else:
                                decoded = base64.b64decode(hash_str + pad)
                            dklen = len(decoded)
                            break
                        except Exception as e:
                            logger.debug("b64decode hash_str failed: %s", e)
                            decoded = None
                    if dklen is None:
                        dklen = 64  # safe default

                with suppress(Exception):
                    from flask import current_app as _cap
                    _cap.logger.debug(f"Auth: scrypt params n={n_cost}, r={r_cost}, p={p_cost}, inferred_dklen={dklen}, salt_candidates={[ (name, len(val)) for name, val in candidates ]}")

                # Try each salt candidate, password encoding, and dklen until a match is found
                password_encodings = ["utf-8", "latin1", "utf-16-le", "utf-16-be"]
                dklen_candidates = [dklen] if dklen is not None else []
                if 64 not in dklen_candidates:
                    dklen_candidates.append(64)
                if 32 not in dklen_candidates:
                    dklen_candidates.append(32)

                for salt_decode, salt_bytes in candidates:
                    for pwd_enc in password_encodings:
                        for dk in dklen_candidates:
                    # Compute a safe maxmem to avoid OpenSSL default limit errors
                            try:
                                mem_required = 128 * r_cost * n_cost
                                maxmem = max(mem_required + (1 << 20), 64 * 1024 * 1024)
                            except Exception as e:
                                logger.debug("mem_required calc failed: %s", e)
                                maxmem = 64 * 1024 * 1024

                            try:
                                derived = hashlib.scrypt(
                                    password=password.encode(pwd_enc),
                                    salt=salt_bytes,
                                    n=n_cost,
                                    r=r_cost,
                                    p=p_cost,
                                    dklen=dk,
                                    maxmem=maxmem,
                                )
                            except Exception as e:
                                with suppress(Exception):
                                    from flask import current_app as _cap
                                    _cap.logger.warning(f"Auth: scrypt derive failed for salt_decode={salt_decode}, enc={pwd_enc}, dklen={dk}: {e}")
                                continue

                            # Compare against either hex or base64 representations
                            derived_hex = derived.hex()
                            if hmac.compare_digest(derived_hex, hash_str):
                                with suppress(Exception):
                                    current_app.logger.debug(f"Auth: scrypt match (hex) salt={salt_decode}, enc={pwd_enc}, dklen={dk}")
                                return True
                            derived_b64 = base64.b64encode(derived).decode('utf-8').rstrip('=')
                            if hmac.compare_digest(derived_b64, hash_str):
                                with suppress(Exception):
                                    current_app.logger.debug(f"Auth: scrypt match (base64) salt={salt_decode}, enc={pwd_enc}, dklen={dk}")
                                return True
                            # Also try urlsafe base64 variant
                            derived_b64_url = base64.urlsafe_b64encode(derived).decode('utf-8').rstrip('=')
                            if hmac.compare_digest(derived_b64_url, hash_str):
                                with suppress(Exception):
                                    current_app.logger.debug(f"Auth: scrypt match (urlsafe) salt={salt_decode}, enc={pwd_enc}, dklen={dk}")
                                return True
                with suppress(Exception):
                    current_app.logger.warning("Auth: scrypt verification failed (no encoding matched)")
                return False
            except Exception as e:
                logger.debug("Auth: scrypt verification exception: %s", e)
                with suppress(Exception):
                    from flask import current_app as _cap
                    _cap.logger.exception("Auth: scrypt verification error")
                return False

        # Otherwise, rely on Werkzeug for pbkdf2 and other supported methods
        try:
            from flask import current_app
            result = check_password_hash(self.password_hash, password)
            with suppress(Exception):
                current_app.logger.debug(f"Auth: werkzeug verification result={result}")
            return result
        except Exception as e:
            logger.debug("Auth: check_password_hash exception: %s", e)
            return False

    def get_assigned_entities(self, entity_type=None):
        """Get all entities user has access to, optionally filtered by type.

        Args:
            entity_type (str, optional): Filter by entity type (e.g., 'country', 'ns_branch', etc.)

        Returns:
            list: List of entity objects
        """
        from .enums import EntityType

        query = self.entity_permissions
        if entity_type:
            query = query.filter_by(entity_type=entity_type)

        permissions = query.all()

        # Import entity service to fetch actual objects
        from app.services.entity_service import EntityService
        entities = []
        for perm in permissions:
            entity = EntityService.get_entity(perm.entity_type, perm.entity_id)
            if entity:
                entities.append(entity)

        return entities

    def has_entity_access(self, entity_type, entity_id):
        """Check if user has access to a specific entity.

        Args:
            entity_type (str): Entity type ('country', 'ns_branch', etc.)
            entity_id (int): Entity ID

        Returns:
            bool: True if user has access, False otherwise
        """
        # RBAC-only: system managers have access to everything.
        # Other users must have an explicit entity permission.
        try:
            from app.models.rbac import RbacUserRole, RbacRole
            is_system_manager = (
                db.session.query(RbacUserRole)
                .join(RbacRole, RbacUserRole.role_id == RbacRole.id)
                .filter(RbacUserRole.user_id == self.id, RbacRole.code == "system_manager")
                .first()
                is not None
            )
            if is_system_manager:
                return True
        except Exception as e:
            logger.debug("System manager check failed, falling back to entity permissions: %s", e)
            # Fall back to explicit entity permissions only
            pass

        return UserEntityPermission.query.filter_by(
            user_id=self.id,
            entity_type=entity_type,
            entity_id=entity_id
        ).first() is not None

    def add_entity_permission(self, entity_type, entity_id):
        """Grant user access to an entity.

        Args:
            entity_type (str): Entity type ('country', 'ns_branch', etc.)
            entity_id (int): Entity ID

        Returns:
            UserEntityPermission: The created permission object, or existing one if already exists
        """
        # Check if permission already exists
        existing = UserEntityPermission.query.filter_by(
            user_id=self.id,
            entity_type=entity_type,
            entity_id=entity_id
        ).first()

        if existing:
            return existing

        # Create new permission
        new_permission = UserEntityPermission(
            user_id=self.id,
            entity_type=entity_type,
            entity_id=entity_id
        )
        db.session.add(new_permission)
        return new_permission

    def remove_entity_permission(self, entity_type, entity_id):
        """Remove user access to an entity.

        Args:
            entity_type (str): Entity type ('country', 'ns_branch', etc.)
            entity_id (int): Entity ID

        Returns:
            bool: True if permission was removed, False if it didn't exist
        """
        permission = UserEntityPermission.query.filter_by(
            user_id=self.id,
            entity_type=entity_type,
            entity_id=entity_id
        ).first()

        if permission:
            db.session.delete(permission)
            return True

        return False

    def __repr__(self):
        return f"<User {self.email} - {self.name} ({self.title})>"

    def generate_profile_color(self):
        """Generate a profile color based on the user's email."""
        from app.utils.profile_utils import generate_color_from_email
        if not self.profile_color or self.profile_color == '#3B82F6':
            self.profile_color = generate_color_from_email(self.email)
        return self.profile_color


@login.user_loader
def load_user(id):
    # Check if the user table exists before querying
    # This prevents errors during database initialization
    inspector = inspect(db.engine)
    if 'user' not in inspector.get_table_names():
        return None
    return User.query.get(int(id))


class Country(db.Model):
    __tablename__ = 'country'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    short_name = Column(String(50), nullable=True)
    iso3 = Column(String(3), unique=True, nullable=False)
    iso2 = Column(String(2), unique=True, nullable=True)
    region = Column(String(15), nullable=False)
    partof = Column(String(100), nullable=True)

    # Additional fields
    status = Column(String(50), nullable=True, default='Active')
    # Store ISO code (e.g. "en", "fr"). Keep backward-compat with legacy values like "English".
    preferred_language = Column(String(10), nullable=True, default='en')
    currency_code = Column(String(3), nullable=True)

    # Multilingual Country Name fields
    name_translations = Column(JSONB, nullable=True)

    # Relationship to AssignmentEntityStatus for country entities
    assignment_statuses = relationship(
        'AssignmentEntityStatus',
        primaryjoin=lambda: and_(Country.id == foreign(AssignmentEntityStatus.entity_id),
                                 AssignmentEntityStatus.entity_type == 'country'),
        lazy='dynamic',
        viewonly=True
    )

    # Relationship to PublicSubmission - a country can have multiple public submissions
    public_submissions = relationship('PublicSubmission', backref='country', lazy='dynamic', cascade="all, delete-orphan")

    @property
    def assigned_forms(self):
        """Get assigned forms for this country through AssignmentEntityStatus relationships."""
        class AssignedFormQuery:
            def __init__(self, country_id):
                self.country_id = country_id
            def all(self):
                return [aes.assigned_form for aes in AssignmentEntityStatus.query.filter_by(entity_type='country', entity_id=self.country_id).all() if aes.assigned_form]
            def first(self):
                aes = AssignmentEntityStatus.query.filter_by(entity_type='country', entity_id=self.country_id).first()
                return aes.assigned_form if aes and aes.assigned_form else None
            def count(self):
                return AssignmentEntityStatus.query.filter_by(entity_type='country', entity_id=self.country_id).count()
        return AssignedFormQuery(self.id)

    # Translation helper methods for JSONB fields
    def get_name_translation(self, language):
        """Get name translation for specific language.

        Uses short codes (e.g., 'fr', 'es', 'ar') for all translations.
        """
        if not self.name_translations:
            return self.name

        # Check for translation using short code
        if language in self.name_translations:
            trans_value = self.name_translations[language]
            if trans_value and isinstance(trans_value, str) and trans_value.strip():
                return trans_value

        return self.name

    def set_name_translation(self, language, text):
        """Set name translation for specific language."""
        if not self.name_translations:
            self.name_translations = {}
        if text and text.strip():
            self.name_translations[language] = text.strip()
        elif language in self.name_translations:
            del self.name_translations[language]

    @staticmethod
    def normalize_language_code(value: str | None) -> str:
        """Normalize a language value to an ISO code.

        Accepts:
        - ISO codes: "fr", "fr_FR", "fr-FR"
        - Legacy English labels: "English", "French", ...
        """
        if not value:
            return "en"
        raw = str(value).strip()
        if not raw:
            return "en"
        lowered = raw.lower()
        # ISO-ish: keep primary subtag only
        if "_" in lowered:
            lowered = lowered.split("_", 1)[0]
        if "-" in lowered:
            lowered = lowered.split("-", 1)[0]
        # Common legacy labels -> ISO codes
        legacy_map = {
            "english": "en",
            "french": "fr",
            "spanish": "es",
            "arabic": "ar",
            "russian": "ru",
            "chinese": "zh",
            "hindi": "hi",
        }
        return legacy_map.get(lowered, lowered)

    @property
    def preferred_language_code(self) -> str:
        """Preferred language as ISO code (normalized)."""
        return Country.normalize_language_code(getattr(self, "preferred_language", None))

    @property
    def primary_national_society(self):
        """
        Returns the primary National Society for this country.
        Prefers active NS ordered by display_order, then id.
        """
        try:
            nss = list(getattr(self, 'national_societies', []) or [])
        except Exception as e:
            logger.debug("Country.national_societies access failed: %s", e)
            nss = []
        if not nss:
            return None
        active = [ns for ns in nss if getattr(ns, 'is_active', True)]
        candidates = active if active else nss
        with suppress(Exception):
            candidates.sort(key=lambda ns: ((getattr(ns, 'display_order', 0) or 0), getattr(ns, 'id', 0) or 0))
        return candidates[0] if candidates else None

    def __repr__(self):
        try:
            name = self.name if hasattr(self, 'name') else 'Unknown'
            iso3 = self.iso3 if hasattr(self, 'iso3') else 'Unknown'
            return f'<Country {name} ({iso3})>'
        except Exception as e:
            logger.debug("Country.__repr__ failed: %s", e)
            return f'<Country id={getattr(self, "id", "Unknown")}>'


class UserLoginLog(db.Model):
    """Tracks user login/logout activities and authentication attempts."""
    __tablename__ = 'user_login_log'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    email_attempted = db.Column(db.String(120), nullable=False)

    # Event details
    event_type = db.Column(db.String(20), nullable=False, index=True)
    timestamp = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)

    # Network and device information
    ip_address = db.Column(db.String(45), nullable=False)  # IPv6 compatible
    user_agent = db.Column(db.Text, nullable=True)
    browser = db.Column(db.String(100), nullable=True)
    operating_system = db.Column(db.String(100), nullable=True)
    device_type = db.Column(db.String(50), nullable=True)  # 'desktop', 'mobile', 'tablet'

    # Geographic information (if available)
    country = db.Column(db.String(100), nullable=True)
    city = db.Column(db.String(100), nullable=True)

    # Security tracking
    is_suspicious = db.Column(db.Boolean, default=False, nullable=False)
    failed_attempts_count = db.Column(db.Integer, default=0, nullable=False)
    failure_reason = db.Column(db.String(100), nullable=True)  # Reason for failed login
    is_bot_detected = db.Column(db.Boolean, default=False, nullable=False)  # Bot detection flag

    # Session tracking
    session_id = db.Column(db.String(255), nullable=True)
    session_duration_minutes = db.Column(db.Integer, nullable=True)  # For logout events

    # Additional tracking
    referrer_url = db.Column(db.String(500), nullable=True)  # Referrer URL

    # Relationship
    user = db.relationship('User', backref='login_logs')

    def __repr__(self):
        return f'<UserLoginLog {self.email_attempted} - {self.event_type} at {self.timestamp}>'

    @property
    def is_successful(self):
        """Returns True if the login event was successful."""
        return self.event_type == 'login_success'

    @property
    def is_logout(self):
        """Returns True if this is a logout event."""
        return self.event_type == 'logout'

    @property
    def browser_name(self):
        """Extract browser name from the browser field."""
        if not self.browser:
            return None
        # Split on first space to separate name from version
        parts = self.browser.split(' ', 1)
        return parts[0] if parts else None

    @property
    def browser_version(self):
        """Extract browser version from the browser field."""
        if not self.browser:
            return None
        # Split on first space to separate name from version
        parts = self.browser.split(' ', 1)
        return parts[1] if len(parts) > 1 else None

    @property
    def device_name(self):
        """Get device name (same as device_type for compatibility)."""
        return self.device_type

    @property
    def location(self):
        """Combine country and city for location display."""
        if self.city and self.country:
            return f"{self.city}, {self.country}"
        elif self.country:
            return self.country
        elif self.city:
            return self.city
        return None

    @property
    def failure_reason_display(self):
        """Get a human-readable failure reason."""
        if not self.failure_reason:
            return None

        reason_map = {
            'user_not_found': 'User not found',
            'wrong_password': 'Incorrect password',
            'account_locked': 'Account locked',
            'account_disabled': 'Account disabled',
            'too_many_attempts': 'Too many failed attempts'
        }

        return reason_map.get(self.failure_reason, self.failure_reason.replace('_', ' ').title())

    @property
    def risk_level_display(self):
        """Get risk level display information for failed login attempts."""
        if self.event_type != 'login_failed':
            return None

        # Determine risk level based on various factors
        risk_level = 'low'

        if self.is_suspicious:
            risk_level = 'high'
        elif self.is_bot_detected:
            risk_level = 'medium'
        elif self.failed_attempts_count >= 10:
            risk_level = 'high'
        elif self.failed_attempts_count >= 5:
            risk_level = 'medium'

        # Return styling information based on risk level
        risk_styles = {
            'low': {
                'class': 'bg-gray-100 text-gray-800',
                'icon': 'fas fa-info-circle',
                'text': 'Low Risk'
            },
            'medium': {
                'class': 'bg-yellow-100 text-yellow-800',
                'icon': 'fas fa-exclamation-triangle',
                'text': 'Medium Risk'
            },
            'high': {
                'class': 'bg-red-100 text-red-800',
                'icon': 'fas fa-exclamation-circle',
                'text': 'High Risk'
            }
        }

        return type('RiskLevel', (), risk_styles[risk_level])()


class UserActivityLog(db.Model):
    """Tracks user activities within the application."""
    __tablename__ = 'user_activity_log'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)

    # Activity details
    activity_type = db.Column(db.String(50), nullable=False, index=True)
    activity_description = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)

    # Request information
    endpoint = db.Column(db.String(255), nullable=True)  # Flask endpoint
    http_method = db.Column(db.String(10), nullable=True)  # GET, POST, etc.
    url_path = db.Column(db.String(500), nullable=True)
    referrer = db.Column(db.String(500), nullable=True)

    # Network information
    ip_address = db.Column(db.String(45), nullable=False)
    user_agent = db.Column(db.Text, nullable=True)

    # Context data (stored as JSON)
    context_data = db.Column(db.JSON, nullable=True)  # Additional data like form IDs, country IDs, etc.

    # Performance tracking
    response_time_ms = db.Column(db.Integer, nullable=True)
    response_status_code = db.Column(db.Integer, nullable=True)

    # Relationship
    user = db.relationship('User', backref='activity_logs')

    def __repr__(self):
        return f'<UserActivityLog {self.user.email} - {self.activity_type} at {self.timestamp}>'


class UserSessionLog(db.Model):
    """Tracks user session information and analytics."""
    __tablename__ = 'user_session_log'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    # Session identifiers
    session_id = db.Column(db.String(255), nullable=False, unique=True)

    # Session timing
    session_start = db.Column(db.DateTime, default=utcnow, nullable=False)
    session_end = db.Column(db.DateTime, nullable=True)
    last_activity = db.Column(db.DateTime, default=utcnow, nullable=False)
    duration_minutes = db.Column(db.Integer, nullable=True)

    # Session statistics
    page_views = db.Column(db.Integer, default=0, nullable=False)
    actions_performed = db.Column(db.Integer, default=0, nullable=False)
    forms_submitted = db.Column(db.Integer, default=0, nullable=False)
    files_uploaded = db.Column(db.Integer, default=0, nullable=False)

    # Network and device information
    ip_address = db.Column(db.String(45), nullable=False)
    user_agent = db.Column(db.Text, nullable=True)
    browser = db.Column(db.String(100), nullable=True)
    operating_system = db.Column(db.String(100), nullable=True)
    device_type = db.Column(db.String(50), nullable=True)

    # Session quality metrics
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    # Increased length to accommodate composite reasons like 'timeout_and_max_duration'
    ended_by = db.Column(db.String(50), nullable=True)  # 'logout', 'timeout', 'system', etc.

    # Relationship
    user = db.relationship('User', backref='session_logs')

    def __repr__(self):
        return f'<UserSessionLog {self.user.email} - Session {self.session_id[:8]}...>'
