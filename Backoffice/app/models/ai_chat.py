"""
AI chat persistence models (logged-in users only).

Notes:
- We store conversations and messages for authenticated users only.
- RBAC is enforced at query time by user_id ownership.
"""

from __future__ import annotations

from app.extensions import db
from app.utils.datetime_helpers import utcnow
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import UniqueConstraint, JSON


class AIConversation(db.Model):
    __tablename__ = "ai_conversation"

    id = db.Column(db.String(36), primary_key=True)  # UUID string
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)

    title = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    last_message_at = db.Column(db.DateTime, nullable=True)

    # Retention/archiving fields (optional; populated by maintenance jobs)
    is_archived = db.Column(db.Boolean, default=False, nullable=False, index=True)
    archived_at = db.Column(db.DateTime, nullable=True, index=True)
    archive_provider = db.Column(db.String(32), nullable=True)  # filesystem | azure_blob | ...
    archive_path = db.Column(db.Text, nullable=True)  # relative path (filesystem) or blob name (azure)
    archive_size_bytes = db.Column(db.BigInteger, nullable=True)
    archive_sha256 = db.Column(db.String(64), nullable=True)

    # Optional metadata for future use (client, model, etc.)
    # NOTE: Use a cross-database JSON type.
    # - In production (PostgreSQL): JSONB
    # - In development (SQLite): generic JSON (stored as TEXT)
    meta = db.Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)

    user = db.relationship("User", backref=db.backref("ai_conversations", lazy="dynamic"))


class AIMessage(db.Model):
    __tablename__ = "ai_message"
    __table_args__ = (
        UniqueConstraint("conversation_id", "user_id", "client_message_id", name="uq_ai_message_client_message_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.String(36), db.ForeignKey("ai_conversation.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)

    # "user" | "assistant" | "system"
    role = db.Column(db.String(16), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)
    # Optional idempotency key from clients (mobile offline import, etc.)
    client_message_id = db.Column(db.String(64), nullable=True, index=True)

    meta = db.Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)

    conversation = db.relationship(
        "AIConversation",
        backref=db.backref("messages", lazy="dynamic", cascade="all, delete-orphan"),
    )
