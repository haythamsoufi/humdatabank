"""Shared, TTL-bound authentication state (used when Redis is not configured)."""
from sqlalchemy import Column, DateTime, Index, Integer, String, Text, func

from ..extensions import db


class AuthStateEntry(db.Model):
    """Short-lived key/value + counter row shared by every worker.

    Holds consumed refresh-token JTIs, revoked token families/sessions, single-use
    mobile OAuth codes, login-failure counters and DB-backed rate-limit buckets.
    Rows are meaningless after ``expires_at`` and are purged opportunistically
    (``app.utils.auth_state``).
    """

    __tablename__ = 'auth_state_entry'

    namespace = Column(String(32), primary_key=True)
    key = Column(String(128), primary_key=True)
    value = Column(Text, nullable=True)
    counter = Column(Integer, nullable=False, default=0, server_default='0')
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index('ix_auth_state_entry_expires_at', 'expires_at'),
    )

    def __repr__(self):
        return f'<AuthStateEntry {self.namespace}:{self.key}>'
