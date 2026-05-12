"""
Password Reset Token Management

Tracks password reset tokens to enable single-use tokens and prevent reuse.
"""

from datetime import datetime, timedelta
from app import db
from sqlalchemy import Index
from typing import Optional
from app.utils.datetime_helpers import utcnow
from app.utils.datetime_helpers import ensure_utc


class PasswordResetToken(db.Model):
    """
    Track password reset tokens for security.

    Enables:
    - Single-use tokens
    - Token invalidation after use
    - Token expiration tracking
    - Security monitoring
    """
    __tablename__ = 'password_reset_tokens'

    id = db.Column(db.Integer, primary_key=True)

    # Token identifier (hash of the actual token)
    token_hash = db.Column(db.String(128), nullable=False, unique=True, index=True)

    # User who requested the reset
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    user_email = db.Column(db.String(120), nullable=False, index=True)

    # Status
    is_used = db.Column(db.Boolean, default=False, nullable=False, index=True)
    is_revoked = db.Column(db.Boolean, default=False, nullable=False, index=True)

    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    used_at = db.Column(db.DateTime, nullable=True)
    revoked_at = db.Column(db.DateTime, nullable=True)

    # Metadata
    ip_address = db.Column(db.String(45), nullable=True)  # IP that requested reset
    user_agent = db.Column(db.String(500), nullable=True)

    # Relationships
    user = db.relationship('User', backref='password_reset_tokens')

    __table_args__ = (
        Index('ix_reset_token_user_unused', 'user_id', 'is_used', 'is_revoked'),
        Index('ix_reset_token_expires', 'expires_at'),
    )

    @staticmethod
    def hash_token(token: str) -> str:
        """Hash a reset token for storage."""
        import hashlib
        return hashlib.sha256(token.encode()).hexdigest()

    def is_valid(self) -> bool:
        """Check if token is valid (not used, not revoked, not expired)."""
        if self.is_used or self.is_revoked:
            return False
        # DB column may be timezone-naive depending on DB settings; normalize to UTC-aware.
        if utcnow() > ensure_utc(self.expires_at):
            return False
        return True

    def mark_as_used(self):
        """Mark token as used."""
        self.is_used = True
        self.used_at = utcnow()
        db.session.commit()

    def revoke(self):
        """Revoke token (e.g., when new reset requested)."""
        self.is_revoked = True
        self.revoked_at = utcnow()
        db.session.commit()

    @staticmethod
    def revoke_all_user_tokens(user_id: int):
        """Revoke all unused tokens for a user (when new reset is requested)."""
        unused_tokens = PasswordResetToken.query.filter(
            PasswordResetToken.user_id == user_id,
            PasswordResetToken.is_used == False,
            PasswordResetToken.is_revoked == False
        ).all()

        for token in unused_tokens:
            token.revoke()

    def __repr__(self):
        return f'<PasswordResetToken {self.id} for user {self.user_id} (used={self.is_used})>'
