"""
Email services package.

Consolidates all email infrastructure: sending, rendering, delivery tracking,
campaign management, and recipient protection.
"""

from .client import send_email
from .service import (
    send_welcome_email,
    send_security_alert,
    send_suggestion_confirmation_email,
    send_admin_notification_email,
)
from .rendering import render_admin_email_template
from .delivery import (
    log_email_attempt,
    mark_email_sent,
    mark_email_failed,
    get_pending_retries,
    admin_retry_email_delivery_log,
    admin_retry_failed_email_delivery_logs,
)
from .campaigns import send_multiple_entity_email_campaigns
from .protection import check_email_recipients_allowed

__all__ = [
    'send_email',
    'send_welcome_email',
    'send_security_alert',
    'send_suggestion_confirmation_email',
    'send_admin_notification_email',
    'render_admin_email_template',
    'log_email_attempt',
    'mark_email_sent',
    'mark_email_failed',
    'get_pending_retries',
    'admin_retry_email_delivery_log',
    'admin_retry_failed_email_delivery_logs',
    'send_multiple_entity_email_campaigns',
    'check_email_recipients_allowed',
]
