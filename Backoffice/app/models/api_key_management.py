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
from typing import Optional
from app.utils.datetime_helpers import utcnow, ensure_utc


class APIKey(db.Model):
    """
    Per-client API key management.

    Supports:
    - Multiple keys per client/user
    - Key rotation
    - Usage tracking
    - Revocation
    - Expiration
    """
    __tablename__ = 'api_keys'

    id = db.Column(db.Integer, primary_key=True)

    # Key identifier (public, shown to user)
    key_id = db.Column(db.String(32), unique=True, nullable=False, index=True)

    # Key hash (stored securely, never returned)
    key_hash = db.Column(db.String(128), nullable=False, unique=True, index=True)

    # Key prefix (first 8 chars for identification)
    key_prefix = db.Column(db.String(8), nullable=False, index=True)

    # Owner information
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # Optional: user-specific keys
    client_name = db.Column(db.String(255), nullable=False)  # Human-readable client name
    client_description = db.Column(db.Text, nullable=True)

    # Permissions and scope
    permissions = db.Column(db.JSON, nullable=True)  # Optional: fine-grained permissions
    rate_limit_per_minute = db.Column(db.Integer, default=60, nullable=False)

    # Status
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    is_revoked = db.Column(db.Boolean, default=False, nullable=False, index=True)

    # Dates
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    expires_at = db.Column(db.DateTime, nullable=True, index=True)
    last_used_at = db.Column(db.DateTime, nullable=True, index=True)
    revoked_at = db.Column(db.DateTime, nullable=True)

    # Metadata
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    revocation_reason = db.Column(db.Text, nullable=True)

    # Relationships
    user = db.relationship('User', foreign_keys=[user_id], backref='api_keys')
    created_by = db.relationship('User', foreign_keys=[created_by_user_id])
    usage_logs = db.relationship('APIKeyUsage', backref='api_key', lazy='dynamic', cascade='all, delete-orphan')

    __table_args__ = (
        Index('ix_api_key_user_active', 'user_id', 'is_active'),
        Index('ix_api_key_prefix_active', 'key_prefix', 'is_active'),
        Index('ix_api_key_expires', 'expires_at'),
    )

    @staticmethod
    def generate_key() -> tuple[str, str, str]:
        """
        Generate a new API key.

        Returns:
            tuple: (full_key, key_hash, key_prefix)
        """
        # Generate cryptographically secure key
        full_key = secrets.token_urlsafe(48)  # 64 chars base64-encoded

        # Create key ID (first 32 chars)
        key_id = full_key[:32]

        # Create prefix for identification (first 8 chars)
        key_prefix = full_key[:8]

        # Hash the full key for storage
        key_hash = hashlib.sha256(full_key.encode()).hexdigest()

        return full_key, key_hash, key_prefix

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

    def is_valid(self) -> bool:
        """Check if key is valid (active, not revoked, not expired)."""
        if not self.is_active or self.is_revoked:
            return False
        # Some DB drivers return naive datetimes for DateTime columns (no tz).
        # Treat naive values as UTC to avoid TypeError in comparisons.
        expires_at = ensure_utc(self.expires_at) if self.expires_at else None
        if expires_at and expires_at < utcnow():
            return False
        return True

    def revoke(self, reason: Optional[str] = None, revoked_by_user_id: Optional[int] = None):
        """Revoke this API key."""
        self.is_revoked = True
        self.is_active = False
        self.revoked_at = utcnow()
        self.revocation_reason = reason

    def update_last_used(self):
        """Update last used timestamp."""
        self.last_used_at = utcnow()
        db.session.commit()

    def __repr__(self):
        return f'<APIKey {self.key_id[:8]}... ({self.client_name})>'


class APIKeyUsage(db.Model):
    """
    Track API key usage for monitoring and analytics.
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
