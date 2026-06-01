from datetime import datetime
from app.extensions import db
from app.utils.datetime_helpers import utcnow


class APIUsage(db.Model):
    """
    Canonical log of all /api/* request traffic.

    When a DB-managed API key is used, ``api_key_id`` links to ``api_keys`` and
    a companion row is also written to ``api_key_usage`` for per-key audit.
    Aggregate endpoint stats should use this table only (not both) to avoid
    double-counting.
    """
    __tablename__ = 'api_usage'

    id = db.Column(db.Integer, primary_key=True)
    api_endpoint = db.Column(db.String(255), nullable=False)
    ip_address = db.Column(db.String(45), nullable=False)  # IPv6 addresses can be up to 45 chars
    method = db.Column(db.String(10), nullable=False)  # GET, POST, etc.
    status_code = db.Column(db.Integer, nullable=False)
    response_time = db.Column(db.Float, nullable=False)  # in milliseconds
    timestamp = db.Column(db.DateTime, default=utcnow)
    user_agent = db.Column(db.String(255))
    request_data = db.Column(db.JSON)
    api_key_id = db.Column(db.Integer, db.ForeignKey('api_keys.id'), nullable=True, index=True)

    api_key = db.relationship('APIKey', foreign_keys=[api_key_id])

    def __repr__(self):
        return f'<APIUsage {self.api_endpoint} - {self.ip_address}>'
