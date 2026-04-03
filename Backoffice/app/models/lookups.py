"""
Lookup table models for dynamic data.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, ForeignKey, String, Text, DateTime, JSON
from sqlalchemy.orm import relationship, backref
from ..extensions import db
from app.utils.datetime_helpers import utcnow


class LookupList(db.Model):
    """Stores metadata and configuration for a dynamic lookup list (e.g. for calculated choice fields)."""
    __tablename__ = 'lookup_list'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)

    # Column definitions stored as a list of objects, e.g. [{"name": "Country", "type": "string"}, ...]
    columns_config = db.Column(db.JSON, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    # Relationship to rows (delete all rows if list is deleted)
    rows = db.relationship('LookupListRow', backref='lookup_list', lazy='dynamic', cascade='all, delete-orphan')

    __table_args__ = (
        db.Index('ix_lookup_list_updated_at', 'updated_at'),
    )

    def __repr__(self):
        return f'<LookupList {self.name} ({self.rows.count()} rows)>'


class LookupListRow(db.Model):
    """Stores individual rows for a lookup list as arbitrary JSON data."""
    __tablename__ = 'lookup_list_row'

    id = db.Column(db.Integer, primary_key=True)
    lookup_list_id = db.Column(db.Integer, db.ForeignKey('lookup_list.id'), nullable=False)

    # Arbitrary row data keyed by column names defined in LookupList.columns_config
    data = db.Column(db.JSON, nullable=False)

    # Preserve ordering within a list for deterministic display
    order = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (
        db.UniqueConstraint('lookup_list_id', 'order', name='_lookup_list_row_order_uc'),
        db.Index('ix_lookup_list_row_list_order', 'lookup_list_id', 'order'),
    )

    def __repr__(self):
        return f'<LookupListRow {self.id} of List {self.lookup_list_id}>'
