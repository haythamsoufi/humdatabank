"""
System models for logging, notifications, and security.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, ForeignKey, String, Text, DateTime, Boolean, JSON
from sqlalchemy.orm import relationship, backref
from ..extensions import db
from .enums import NotificationType
from app.utils.datetime_helpers import utcnow


class CountryAccessRequestStatus:
    PENDING = 'pending'
    APPROVED = 'approved'
    REJECTED = 'rejected'


class CountryAccessRequest(db.Model):
    """User requests to obtain access to a single country. Processed by admins."""
    __tablename__ = 'country_access_request'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    country_id = db.Column(db.Integer, db.ForeignKey('country.id'), nullable=False)
    request_message = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default=CountryAccessRequestStatus.PENDING)  # pending/approved/rejected
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    processed_at = db.Column(db.DateTime, nullable=True)
    processed_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    admin_notes = db.Column(db.Text, nullable=True)

    # Relationships
    user = db.relationship('User', foreign_keys=[user_id], backref='country_access_requests')
    processed_by = db.relationship('User', foreign_keys=[processed_by_user_id])
    country = db.relationship('Country')

    __table_args__ = (
        db.Index('ix_car_status_time', 'status', 'created_at'),
        db.Index('ix_car_user', 'user_id'),
        db.UniqueConstraint('user_id', 'country_id', 'status', name='uq_user_country_status_active'),
    )

    def __repr__(self):
        return f'<CountryAccessRequest user_id={self.user_id} country_id={self.country_id} status={self.status}>'


class AdminActionLog(db.Model):
    """Tracks administrative actions performed by admin users."""
    __tablename__ = 'admin_action_log'

    id = db.Column(db.Integer, primary_key=True)
    admin_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    # Action details
    action_type = db.Column(db.String(50), nullable=False)  # 'user_create', 'user_edit', 'form_assign', etc.
    action_description = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=utcnow, nullable=False)

    # Target information
    target_type = db.Column(db.String(50), nullable=True)  # 'user', 'form', 'country', etc.
    target_id = db.Column(db.Integer, nullable=True)
    target_description = db.Column(db.String(255), nullable=True)

    # Request information
    ip_address = db.Column(db.String(45), nullable=False)
    user_agent = db.Column(db.Text, nullable=True)
    endpoint = db.Column(db.String(255), nullable=True)

    # Data changes (stored as JSON)
    old_values = db.Column(db.JSON, nullable=True)  # Previous values before change
    new_values = db.Column(db.JSON, nullable=True)  # New values after change

    # Risk assessment
    risk_level = db.Column(db.String(20), default='low', nullable=False)  # 'low', 'medium', 'high', 'critical'
    requires_review = db.Column(db.Boolean, default=False, nullable=False)

    # Relationship
    admin_user = db.relationship('User', backref='admin_actions')

    __table_args__ = (
        db.Index('ix_admin_action_user_time', 'admin_user_id', 'timestamp'),
        db.Index('ix_admin_action_type', 'action_type'),
        db.Index('ix_admin_action_target', 'target_type', 'target_id'),
        db.Index('ix_admin_action_risk', 'risk_level'),
    )

    def __repr__(self):
        return f'<AdminActionLog {self.admin_user.email} - {self.action_type} at {self.timestamp}>'


class SecurityEvent(db.Model):
    """Tracks security-related events and potential threats."""
    __tablename__ = 'security_event'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # Nullable for anonymous events

    # Event details
    event_type = db.Column(db.String(50), nullable=False)  # 'multiple_failed_logins', 'suspicious_activity', etc.
    severity = db.Column(db.String(20), nullable=False)  # 'low', 'medium', 'high', 'critical'
    description = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=utcnow, nullable=False)

    # Network information
    ip_address = db.Column(db.String(45), nullable=False)
    user_agent = db.Column(db.Text, nullable=True)

    # Event context
    context_data = db.Column(db.JSON, nullable=True)

    # Response tracking
    is_resolved = db.Column(db.Boolean, default=False, nullable=False)
    resolved_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)
    resolution_notes = db.Column(db.Text, nullable=True)

    # Relationships
    user = db.relationship('User', foreign_keys=[user_id], backref='security_events')
    resolved_by = db.relationship('User', foreign_keys=[resolved_by_user_id])

    __table_args__ = (
        db.Index('ix_security_event_user_time', 'user_id', 'timestamp'),
        db.Index('ix_security_event_type', 'event_type'),
        db.Index('ix_security_event_severity', 'severity'),
        db.Index('ix_security_event_resolved', 'is_resolved'),
        db.Index('ix_security_event_resolved_by', 'resolved_by_user_id'),
    )

    def __repr__(self):
        return f'<SecurityEvent {self.event_type} - {self.severity} at {self.timestamp}>'


class Notification(db.Model):
    __tablename__ = 'notification'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    # Entity scope for the notification (replaces country_id)
    entity_type = db.Column(db.String(50), nullable=True)  # e.g., 'country', 'ns_branch', 'department'
    entity_id = db.Column(db.Integer, nullable=True)
    notification_type = db.Column(db.Enum(NotificationType), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    related_object_type = db.Column(db.String(50), nullable=True)
    related_object_id = db.Column(db.Integer, nullable=True)
    related_url = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    read_at = db.Column(db.DateTime, nullable=True)
    priority = db.Column(db.String(20), nullable=False, default='normal')
    icon = db.Column(db.String(50), nullable=True)
    # New columns for archiving
    is_archived = db.Column(db.Boolean, nullable=False, default=False)
    archived_at = db.Column(db.DateTime, nullable=True)
    # Phase 1: Deduplication and expiration
    notification_hash = db.Column(db.String(64), nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    # Phase 2: Grouping
    group_id = db.Column(db.String(64), nullable=True)
    # Phase 3: Action buttons
    action_buttons = db.Column(db.JSON, nullable=True)  # [{"label": "Approve", "action": "approve", "endpoint": "/api/..."}]
    action_taken = db.Column(db.String(50), nullable=True)  # Which action was taken
    action_taken_at = db.Column(db.DateTime, nullable=True)
    # Phase 4: Internationalization - Translation keys for title and message
    title_key = db.Column(db.String(255), nullable=True)  # Translation key for title (e.g., 'notification.assignment_created.title')
    title_params = db.Column(db.JSON, nullable=True)  # Parameters for title translation
    message_key = db.Column(db.String(255), nullable=True)  # Translation key for message
    message_params = db.Column(db.JSON, nullable=True)  # Parameters for message translation
    # Phase 4: User Experience Enhancements
    viewed_at = db.Column(db.DateTime, nullable=True)  # When notification was first viewed (distinct from read)
    category = db.Column(db.String(50), nullable=True)  # Notification category for filtering (e.g., 'assignment', 'system', 'alert')
    tags = db.Column(db.JSON, nullable=True)  # Array of tags for flexible categorization
    # Phase 5: Notification Scheduling
    scheduled_for = db.Column(db.DateTime, nullable=True)  # When notification should be sent (for scheduled notifications)
    sent_at = db.Column(db.DateTime, nullable=True)  # When notification was actually sent (for scheduled notifications)

    # Relationships
    user = db.relationship('User', backref='notifications')

    __table_args__ = (
        db.Index('ix_notification_user_time', 'user_id', 'created_at'),
        db.Index('ix_notification_created_at', 'created_at'),  # Single-column index for expiration queries
        db.Index('ix_notification_entity', 'entity_type', 'entity_id'),
        db.Index('ix_notification_type', 'notification_type'),
        db.Index('ix_notification_is_read', 'is_read'),
        db.Index('ix_notification_priority', 'priority'),
        db.Index('ix_notification_archived', 'is_archived'),
        db.Index('ix_notification_hash', 'notification_hash'),
        db.Index('ix_notification_expires', 'expires_at'),
        db.Index('ix_notification_group', 'group_id'),
        # Composite indexes for optimized queries
        db.Index('ix_notification_hash_user_time', 'notification_hash', 'user_id', 'created_at'),  # For deduplication queries
        db.Index('ix_notification_user_read_archived_time', 'user_id', 'is_read', 'is_archived', 'created_at'),  # For common listing queries
        db.Index('ix_notification_category', 'category'),  # For category filtering
        db.Index('ix_notification_scheduled', 'scheduled_for'),  # For scheduled notification queries
        db.UniqueConstraint('user_id', 'notification_hash', name='uq_notification_user_hash'),
    )

    def __repr__(self):
        return f'<Notification {self.id}: {self.title} for User {self.user_id}>'


class NotificationPreferences(db.Model):
    __tablename__ = 'notification_preferences'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=False)
    email_notifications = db.Column(db.Boolean, default=True, nullable=False)
    notification_types_enabled = db.Column(db.JSON, default=list, nullable=False)
    notification_frequency = db.Column(db.String(20), default='instant', nullable=False)
    digest_day = db.Column(db.String(10), nullable=True)  # For weekly: 'monday', 'tuesday', etc.
    digest_time = db.Column(db.String(10), nullable=True)  # Time in HH:MM format (24-hour)
    sound_enabled = db.Column(db.Boolean, default=False, nullable=False)
    push_notifications = db.Column(db.Boolean, default=True, nullable=False)
    push_notification_types_enabled = db.Column(db.JSON, default=list, nullable=False)
    timezone = db.Column(db.String(50), nullable=True)  # User's timezone (e.g., 'America/New_York', 'UTC')
    last_digest_sent_at = db.Column(db.DateTime, nullable=True)  # Idempotency guard: when last digest was claimed/sent
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    # Relationship
    user = db.relationship('User', backref=db.backref('notification_preferences', uselist=False))

    def __repr__(self):
        return f'<NotificationPreferences for User {self.user_id}>'


class NotificationCampaign(db.Model):
    """Campaign model for creating and scheduling notification campaigns."""
    __tablename__ = 'notification_campaign'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)

    # Campaign content
    title = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    priority = db.Column(db.String(20), nullable=False, default='normal')
    category = db.Column(db.String(50), nullable=True)
    tags = db.Column(db.JSON, nullable=True)  # Array of tags

    # Delivery settings
    send_email = db.Column(db.Boolean, default=True, nullable=False)
    send_push = db.Column(db.Boolean, default=True, nullable=False)
    override_preferences = db.Column(db.Boolean, default=False, nullable=False)

    # Redirect URL for push notifications
    redirect_type = db.Column(db.String(20), nullable=True)  # 'app' or 'custom'
    redirect_url = db.Column(db.String(500), nullable=True)

    # Scheduling
    scheduled_for = db.Column(db.DateTime, nullable=True)  # When campaign should be sent
    status = db.Column(db.String(20), nullable=False, default='draft')  # 'draft', 'scheduled', 'sent', 'failed', 'cancelled'

    # User selection (stored as JSON array of user IDs or filter criteria)
    user_selection_type = db.Column(db.String(20), nullable=False, default='manual')  # 'manual', 'filter', or 'entity'
    user_ids = db.Column(db.JSON, nullable=True)  # Array of user IDs for manual selection
    user_filters = db.Column(db.JSON, nullable=True)  # Filter criteria for automatic selection

    # Entity-based campaign settings (for entity-based email campaigns)
    entity_selection = db.Column(db.JSON, nullable=True)  # Array of {'entity_type': str, 'entity_id': int} for entity-based campaigns
    email_distribution_rules = db.Column(db.JSON, nullable=True)  # {'organization_in': 'to'|'cc', 'non_organization_in': 'to'|'cc'} or {'to': ['organization'], 'cc': ['non_organization']} - where to place organization and non-organization contacts
    attachment_config = db.Column(db.JSON, nullable=True)  # {'static_attachments': [{'filename', 'content_base64', 'content_type'}], 'assignment_pdf_assigned_form_id': int or null}

    # Execution tracking
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    sent_at = db.Column(db.DateTime, nullable=True)  # When campaign was actually sent
    sent_count = db.Column(db.Integer, default=0, nullable=False)  # Number of notifications sent
    failed_count = db.Column(db.Integer, default=0, nullable=False)  # Number of failed sends
    error_message = db.Column(db.Text, nullable=True)  # Human-readable failure reason (e.g., email protection blocks)

    # Relationships
    creator = db.relationship('User', backref='notification_campaigns')

    __table_args__ = (
        db.Index('ix_campaign_status', 'status'),
        db.Index('ix_campaign_scheduled', 'scheduled_for'),
        db.Index('ix_campaign_created_by', 'created_by'),
        db.Index('ix_campaign_created_at', 'created_at'),
    )

    def __repr__(self):
        return f'<NotificationCampaign {self.id}: {self.name} ({self.status})>'


class EmailDeliveryLog(db.Model):
    """Track email delivery status for notifications."""
    __tablename__ = 'email_delivery_log'

    id = db.Column(db.Integer, primary_key=True)
    notification_id = db.Column(db.Integer, db.ForeignKey('notification.id'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    email_address = db.Column(db.String(255), nullable=False)
    subject = db.Column(db.String(500), nullable=True)
    status = db.Column(db.String(50), nullable=False, default='pending')  # pending, sent, failed, retrying
    error_message = db.Column(db.Text, nullable=True)
    retry_count = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    sent_at = db.Column(db.DateTime, nullable=True)
    failed_at = db.Column(db.DateTime, nullable=True)
    next_retry_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    notification = db.relationship('Notification', backref='email_delivery_logs')
    user = db.relationship('User', backref='email_delivery_logs')

    __table_args__ = (
        db.Index('ix_email_delivery_status', 'status'),
        db.Index('ix_email_delivery_user', 'user_id'),
        db.Index('ix_email_delivery_retry', 'next_retry_at'),
    )

    def __repr__(self):
        return f'<EmailDeliveryLog {self.id}: {self.email_address} - {self.status}>'


class UserDevice(db.Model):
    """Store mobile device tokens for push notifications."""
    __tablename__ = 'user_devices'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    device_token = db.Column(db.String(255), nullable=False, unique=True)
    platform = db.Column(db.String(20), nullable=False)  # 'ios' or 'android'
    app_version = db.Column(db.String(20), nullable=True)
    device_model = db.Column(db.String(100), nullable=True)  # e.g., "iPhone 14 Pro", "Samsung Galaxy S23"
    device_name = db.Column(db.String(100), nullable=True)  # User-assigned device name
    os_version = db.Column(db.String(50), nullable=True)  # e.g., "iOS 17.2", "Android 14"
    ip_address = db.Column(db.String(45), nullable=True)  # IPv4 or IPv6
    timezone = db.Column(db.String(50), nullable=True)  # e.g., "America/New_York", "UTC"
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    last_active_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    logged_out_at = db.Column(db.DateTime, nullable=True)  # When user logged out from this device (None = active)
    consecutive_failures = db.Column(db.Integer, nullable=False, default=0)  # Track consecutive push notification failures

    # Relationships
    user = db.relationship('User', backref='devices')

    __table_args__ = (
        db.Index('ix_user_device_user', 'user_id'),
        db.Index('ix_user_device_token', 'device_token'),
        db.Index('ix_user_device_platform', 'platform'),
        db.UniqueConstraint('device_token', name='uq_user_device_token'),
    )

    def __repr__(self):
        return f'<UserDevice {self.id}: {self.platform} for User {self.user_id}>'


class EntityActivityLog(db.Model):
    __tablename__ = 'entity_activity_log'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    # Polymorphic entity fields (primary)
    entity_type = db.Column(db.String(50), nullable=False)  # 'country', 'ns_branch', 'ns_subbranch', etc.
    entity_id = db.Column(db.Integer, nullable=False)
    # country_id field maintained for cross-linking; avoid legacy aliases
    country_id = db.Column(db.Integer, db.ForeignKey('country.id'), nullable=True)
    activity_type = db.Column(db.String(50), nullable=False)
    activity_description = db.Column(db.Text, nullable=False)
    # Internationalized activity summary
    summary_key = db.Column(db.String(255), nullable=False)
    summary_params = db.Column(db.JSON, nullable=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=utcnow)
    related_object_type = db.Column(db.String(50), nullable=True)
    related_object_id = db.Column(db.Integer, nullable=True)
    # Add assignment_id field to track which assignment was modified
    assignment_id = db.Column(db.Integer, nullable=True)
    related_url = db.Column(db.String(500), nullable=True)
    icon = db.Column(db.String(50), nullable=True)
    activity_category = db.Column(db.String(30), nullable=False, default='general')

    # Relationships
    user = db.relationship('User', backref='entity_activities')
    country = db.relationship('Country', backref='activity_logs')

    __table_args__ = (
        db.Index('ix_entity_activity_user_time', 'user_id', 'timestamp'),
        db.Index('ix_entity_activity_entity_time', 'entity_type', 'entity_id', 'timestamp'),
        db.Index('ix_entity_activity_type', 'activity_type'),
        db.Index('ix_entity_activity_category', 'activity_category'),
        db.Index('ix_entity_activity_assignment', 'assignment_id'),
        db.Index('ix_entity_activity_entity', 'entity_type', 'entity_id'),
        db.Index('ix_entity_activity_country_time', 'country_id', 'timestamp'),
    )

    @property
    def entity(self):
        """Get the actual entity object based on entity_type and entity_id."""
        from app.services.entity_service import EntityService
        return EntityService.get_entity(self.entity_type, self.entity_id)

    def __repr__(self):
        return f'<EntityActivityLog {self.id}: {self.activity_type} by {self.user_id} for {self.entity_type}:{self.entity_id}>'


class SystemSettings(db.Model):
    """System-wide configuration settings stored in the database."""
    __tablename__ = 'system_settings'

    id = db.Column(db.Integer, primary_key=True)
    setting_key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    setting_value = db.Column(db.JSON, nullable=False)  # Store as JSON for flexibility
    description = db.Column(db.Text, nullable=True)  # Optional description of what this setting does
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    updated_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    # Relationship
    updated_by = db.relationship('User', foreign_keys=[updated_by_user_id])

    __table_args__ = (
        db.Index('ix_system_settings_key', 'setting_key'),
    )

    @classmethod
    def get_value(cls, key: str, default=None):
        """Get a setting value by key."""
        setting = cls.query.filter_by(setting_key=key).first()
        if setting:
            return setting.setting_value
        return default

    @classmethod
    def set_value(cls, key: str, value, description: str = None, user_id: int = None):
        """Set or update a setting value."""
        setting = cls.query.filter_by(setting_key=key).first()
        if setting:
            setting.setting_value = value
            if description:
                setting.description = description
            if user_id:
                setting.updated_by_user_id = user_id
            setting.updated_at = utcnow()
        else:
            setting = cls(
                setting_key=key,
                setting_value=value,
                description=description,
                updated_by_user_id=user_id
            )
            db.session.add(setting)
        db.session.commit()
        return setting

    @classmethod
    def get_all_as_dict(cls) -> dict:
        """Get all settings as a dictionary."""
        settings = cls.query.all()
        return {s.setting_key: s.setting_value for s in settings}

    def __repr__(self):
        return f'<SystemSettings {self.setting_key}={self.setting_value}>'
