"""
API Key Management Models

Enhanced API key management system supporting per-client keys,
rotation, usage tracking, and revocation.
"""

from datetime import datetime, timedelta
from app import db
import secrets
import hashlib
from sqlalchemy import Index, UniqueConstraint
from typing import Any, Dict, List, Optional, Tuple
from app.utils.datetime_helpers import utcnow, ensure_utc

# Permissions vocabulary for APIKey.permissions JSON column.
#   {"data": "read_all"}  — full data access (default when permissions is null)
#   {"data": "read_scoped", "template_ids": [1], "country_ids": [5]} — scoped read
#   {"data": "none"}      — explicitly no data access
API_KEY_DATA_READ_ALL = 'read_all'
API_KEY_DATA_READ_SCOPED = 'read_scoped'
API_KEY_DATA_NONE = 'none'


def resolve_api_key_data_access(permissions: Any) -> Tuple[str, Optional[Dict[str, List[int]]]]:
    """
    Interpret ``APIKey.permissions`` for data endpoints.

    Returns:
        (access_mode, scope) where access_mode is one of
        ``read_all``, ``read_scoped``, or ``none``; scope is set only for
        ``read_scoped`` and contains normalized ``template_ids`` / ``country_ids``.
    """
    if permissions is None:
        return API_KEY_DATA_READ_ALL, None
    if not isinstance(permissions, dict):
        return API_KEY_DATA_READ_ALL, None

    data_perm = permissions.get('data')
    if data_perm in (None, API_KEY_DATA_READ_ALL):
        return API_KEY_DATA_READ_ALL, None
    if data_perm == API_KEY_DATA_READ_SCOPED:
        template_ids = [
            int(x) for x in (permissions.get('template_ids') or [])
            if x is not None
        ]
        country_ids = [
            int(x) for x in (permissions.get('country_ids') or [])
            if x is not None
        ]
        return API_KEY_DATA_READ_SCOPED, {
            'template_ids': template_ids,
            'country_ids': country_ids,
        }
    if data_perm == API_KEY_DATA_NONE:
        return API_KEY_DATA_NONE, None
    return API_KEY_DATA_READ_ALL, None


class APIKey(db.Model):
    """
    Per-client API key management.

    Status lifecycle (derived via ``status`` property):
      active   — is_active and not revoked/expired
      disabled — is_active=False, is_revoked=False (admin pause; re-enable possible)
      revoked  — is_revoked=True (permanent; is_active also False)
      expired  — expires_at in the past
    """
    __tablename__ = 'api_keys'

    id = db.Column(db.Integer, primary_key=True)

    # Public identifier (shown to admins; independent of the secret key material)
    key_id = db.Column(db.String(32), unique=True, nullable=False, index=True)

    # Key hash (stored securely, never returned)
    key_hash = db.Column(db.String(128), nullable=False, unique=True, index=True)

    # Key prefix (first 8 chars of secret — for human identification in lists)
    key_prefix = db.Column(db.String(8), nullable=False, index=True)

    # Owner information
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # Optional: user-specific keys
    client_name = db.Column(db.String(255), nullable=False)  # Human-readable client name
    client_description = db.Column(db.Text, nullable=True)

    # Permissions and scope
    permissions = db.Column(db.JSON, nullable=True)  # Optional: fine-grained permissions
    rate_limit_per_minute = db.Column(db.Integer, default=60, nullable=False)

    # Status flags (see ``status`` property for the canonical label)
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    is_revoked = db.Column(db.Boolean, default=False, nullable=False, index=True)

    # Dates
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    expires_at = db.Column(db.DateTime, nullable=True, index=True)
    last_used_at = db.Column(db.DateTime, nullable=True, index=True)
    revoked_at = db.Column(db.DateTime, nullable=True)

    # Metadata
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    revoked_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    revocation_reason = db.Column(db.Text, nullable=True)

    # Relationships
    user = db.relationship('User', foreign_keys=[user_id], backref='api_keys')
    created_by = db.relationship('User', foreign_keys=[created_by_user_id])
    revoked_by = db.relationship('User', foreign_keys=[revoked_by_user_id])
    usage_logs = db.relationship('APIKeyUsage', backref='api_key', lazy='dynamic', cascade='all, delete-orphan')

    __table_args__ = (
        Index('ix_api_key_user_active', 'user_id', 'is_active'),
        Index('ix_api_key_prefix_active', 'key_prefix', 'is_active'),
        Index('ix_api_key_expires', 'expires_at'),
    )

    @staticmethod
    def generate_key() -> tuple[str, str, str, str]:
        """
        Generate a new API key.

        Returns:
            tuple: (full_key, key_id, key_hash, key_prefix)
        """
        full_key = secrets.token_urlsafe(48)
        key_id = secrets.token_hex(16)
        key_prefix = full_key[:8]
        key_hash = hashlib.sha256(full_key.encode()).hexdigest()
        return full_key, key_id, key_hash, key_prefix

    @staticmethod
    def hash_key(key: str) -> str:
        """Hash an API key for storage/comparison."""
        return hashlib.sha256(key.encode()).hexdigest()

    def verify_key(self, provided_key: str) -> bool:
        """
        Verify if the provided key matches this API key.

        Uses constant-time comparison to prevent timing attacks.
        """
        import hmac
        provided_hash = self.hash_key(provided_key)
        return hmac.compare_digest(self.key_hash, provided_hash)

    @property
    def status(self) -> str:
        """Canonical lifecycle label: active, disabled, revoked, or expired."""
        if self.is_revoked:
            return 'revoked'
        expires_at = ensure_utc(self.expires_at) if self.expires_at else None
        if expires_at and expires_at < utcnow():
            return 'expired'
        if not self.is_active:
            return 'disabled'
        return 'active'

    def is_valid(self) -> bool:
        """Check if key is valid (active, not revoked, not expired)."""
        return self.status == 'active'

    def disable(self, reason: Optional[str] = None):
        """Pause the key without revoking it (can be re-enabled)."""
        self.is_active = False
        self.is_revoked = False
        if reason:
            self.revocation_reason = reason

    def enable(self):
        """Re-enable a disabled (non-revoked) key."""
        if self.is_revoked:
            raise ValueError('Cannot enable a revoked API key')
        self.is_active = True

    def revoke(self, reason: Optional[str] = None, revoked_by_user_id: Optional[int] = None):
        """Revoke this API key."""
        self.is_revoked = True
        self.is_active = False
        self.revoked_at = utcnow()
        self.revocation_reason = reason
        if revoked_by_user_id is not None:
            self.revoked_by_user_id = revoked_by_user_id

    def update_last_used(self):
        """Update last used timestamp (flush only; caller owns the transaction)."""
        self.last_used_at = utcnow()
        db.session.flush()

    def __repr__(self):
        return f'<APIKey {self.key_id[:8]}... ({self.client_name})>'


class APIKeyUsage(db.Model):
    """
    Per-key audit trail for DB-managed API keys.

    Written alongside rows in ``api_usage`` when a request authenticates with
    a database key. Use ``APIUsage`` for aggregate endpoint analytics;
    use ``APIKeyUsage`` for per-client drill-down in API Key Management.
    """
    __tablename__ = 'api_key_usage'

    id = db.Column(db.Integer, primary_key=True)
    api_key_id = db.Column(db.Integer, db.ForeignKey('api_keys.id'), nullable=False, index=True)

    # Request details
    endpoint = db.Column(db.String(255), nullable=False, index=True)
    method = db.Column(db.String(10), nullable=False)
    ip_address = db.Column(db.String(45), nullable=False, index=True)
    user_agent = db.Column(db.String(500), nullable=True)

    # Response details
    status_code = db.Column(db.Integer, nullable=False)
    response_time_ms = db.Column(db.Float, nullable=False)

    # Timestamp
    # NOTE: Do not set index=True here; we define the named index explicitly in
    # __table_args__ to avoid duplicate CREATE INDEX attempts.
    timestamp = db.Column(db.DateTime, nullable=False, default=utcnow)

    # Optional request metadata
    request_data = db.Column(db.JSON, nullable=True)

    __table_args__ = (
        Index('ix_api_key_usage_timestamp', 'timestamp'),
        Index('ix_api_key_usage_key_timestamp', 'api_key_id', 'timestamp'),
    )

    def __repr__(self):
        return f'<APIKeyUsage {self.api_key_id} - {self.endpoint} at {self.timestamp}>'
