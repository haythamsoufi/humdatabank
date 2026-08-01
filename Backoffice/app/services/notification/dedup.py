"""Notification deduplication, hashing, and grouping helpers."""
import hashlib
from datetime import timedelta

from flask import current_app
from sqlalchemy import and_

from app import db
from app.models import Notification
from app.utils.datetime_helpers import utcnow

def generate_notification_hash(user_id, notification_type, related_object_id, title, message=None):
    """
    Generate a hash for notification deduplication.

    Args:
        user_id (int): User ID
        notification_type (NotificationType): Notification type
        related_object_id (int): Related object ID (can be None)
        title (str): Notification title
        message (str, optional): Notification message content.
                                 For admin_message type, message is included in hash
                                 to allow same title with different messages.

    Returns:
        str: SHA256 hash as hex string

    Security Note: All inputs are sanitized by converting to string and encoding to UTF-8.
    This prevents injection attacks through hash manipulation.
    """
    # Sanitize and convert all inputs to strings to prevent injection
    user_id_str = str(int(user_id)) if user_id is not None else 'none'

    # Get notification type as string
    if hasattr(notification_type, 'value'):
        notif_type_str = str(notification_type.value)
    else:
        notif_type_str = str(notification_type)

    # Sanitize related_object_id
    related_obj_str = str(int(related_object_id)) if related_object_id is not None else 'none'

    # Sanitize title (ensure it's a string, strip whitespace)
    title_str = str(title).strip() if title else ''

    # Include message discriminator if provided (useful to avoid dedup across entities for same assignment)
    # Keep behavior compatible: if no message provided, fall back to title-only hashing
    if message:
        # Sanitize message (ensure it's a string)
        message_str = str(message).strip()
        hash_string = f"{user_id_str}:{notif_type_str}:{related_obj_str}:{title_str}:{message_str}"
    else:
        hash_string = f"{user_id_str}:{notif_type_str}:{related_obj_str}:{title_str}"

    # Generate hash using UTF-8 encoding (safe for all valid strings)
    return hashlib.sha256(hash_string.encode('utf-8', errors='replace')).hexdigest()


def check_duplicate_notification(user_id, notification_hash, notification_type=None, window_minutes=None):
    """
    Check if a duplicate notification exists within the time window.

    Args:
        user_id (int): User ID
        notification_hash (str): Notification hash
        notification_type (NotificationType, optional): Notification type.
                                                       Used to determine deduplication window.
        window_minutes (int): Time window in minutes (defaults to config value or type-specific value)

    Returns:
        bool: True if duplicate exists, False otherwise
    """
    if window_minutes is None:
        # Use shorter window for admin messages (1 minute) since they're explicitly sent
        # For other types, use the default 5-minute window
        if notification_type and hasattr(notification_type, 'value') and notification_type.value == 'admin_message':
            window_minutes = current_app.config.get('NOTIFICATION_DEDUP_WINDOW_MINUTES_ADMIN', 1)
        else:
            window_minutes = current_app.config.get('NOTIFICATION_DEDUP_WINDOW_MINUTES', 5)

    try:
        cutoff_time = utcnow() - timedelta(minutes=window_minutes)

        # Check for existing notification with same hash within time window
        existing = Notification.query.filter(
            and_(
                Notification.user_id == user_id,
                Notification.notification_hash == notification_hash,
                Notification.created_at >= cutoff_time
            )
        ).first()

        return existing is not None
    except Exception as e:
        current_app.logger.error(f"Error checking duplicate notification: {str(e)}")
        # On error, allow notification to proceed (fail open)
        return False


def calculate_notification_expiration(notification_type):
    """
    Calculate expiration date for a notification based on its type.

    Args:
        notification_type (NotificationType): Notification type

    Returns:
        datetime: Expiration datetime, or None if no expiration
    """
    try:
        # Get notification type as string
        if hasattr(notification_type, 'value'):
            notif_type_str = notification_type.value
        else:
            notif_type_str = str(notification_type)

        # Get TTL configuration (per-type override, else NOTIFICATION_EXPIRATION_DAYS)
        try:
            default_ttl = int(current_app.config.get('NOTIFICATION_EXPIRATION_DAYS', 90))
        except (TypeError, ValueError):
            default_ttl = 90
        ttl_days = current_app.config.get('NOTIFICATION_TTL_DAYS', {}).get(
            notif_type_str,
            default_ttl,
        )

        if ttl_days > 0:
            return utcnow() + timedelta(days=ttl_days)
        else:
            return None  # No expiration
    except Exception as e:
        current_app.logger.error(f"Error calculating notification expiration: {str(e)}")
        return None


def generate_group_id(user_id, notification_type, related_object_id, entity_type, entity_id, window_minutes=None):
    """
    Generate a group ID for notification grouping.
    Groups notifications that share the same type, related object, and entity within a time window.

    Args:
        user_id (int): User ID
        notification_type (NotificationType): Notification type
        related_object_id (int): Related object ID (can be None)
        entity_type (str): Entity type (can be None)
        entity_id (int): Entity ID (can be None)
        window_minutes (int): Time window in minutes (defaults to config value)

    Returns:
        str: Group ID hash, or None if grouping is not applicable
    """
    try:
        if window_minutes is None:
            window_minutes = current_app.config.get('NOTIFICATION_GROUPING_WINDOW_MINUTES', 60)

        # Get notification type as string
        if hasattr(notification_type, 'value'):
            notif_type_str = notification_type.value
        else:
            notif_type_str = str(notification_type)

        # Create group identifier from key components
        group_string = f"{user_id}:{notif_type_str}:{related_object_id or 'none'}:{entity_type or 'none'}:{entity_id or 'none'}"
        group_hash = hashlib.sha256(group_string.encode('utf-8')).hexdigest()[:16]  # Use first 16 chars

        # Always return a deterministic group hash so first notifications can start a group.
        # The consumer can still use time windows in queries/logic if needed.
        return group_hash

    except Exception as e:
        current_app.logger.error(f"Error generating group ID: {str(e)}")
        return None
