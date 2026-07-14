"""Per-plugin JSON config/data storage (one row per plugin_id)."""

from __future__ import annotations

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

from app.extensions import db
from app.utils.datetime_helpers import utcnow


class PluginData(db.Model):
    """One JSON document per installed plugin (config, state, versioned settings)."""

    __tablename__ = "plugin_data"

    id = db.Column(db.Integer, primary_key=True)
    plugin_id = db.Column(db.String(100), nullable=False, unique=True, index=True)
    data = db.Column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=dict,
    )
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    def __repr__(self) -> str:
        return f"<PluginData {self.plugin_id!r}>"
