"""
Notifications and Entity Activity Tracking Utilities

This module provides functions for creating notifications and logging entity-specific
activities that are visible to focal points within the same entity (country, NS branch, etc.).
"""

from datetime import datetime, timedelta
from flask import url_for, current_app
from flask_login import current_user
from flask_babel import gettext as _, get_locale
from sqlalchemy import and_, or_, desc, cast, String, select
from sqlalchemy.exc import IntegrityError
from app import db
from app.utils.constants import MAX_NOTIFICATION_MESSAGE_LENGTH
from app.utils.datetime_helpers import utcnow
from app.utils.form_localization import get_translation_key
from app.models import (
    Notification, EntityActivityLog, NotificationType, NotificationPreferences,
    User, Country, UserActivityLog, AdminActionLog, EmailDeliveryLog
)
from contextlib import suppress
from app.models.assignments import AssignmentEntityStatus
import json
import hashlib
from typing import Optional, Dict, Any, Tuple, List, Union
from urllib.parse import urlparse


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def validate_notification_url(url: str) -> bool:
    """
    Validate notification URLs to prevent open redirects and XSS attacks.

    By default, only relative paths are allowed. External URLs require
    explicit whitelist configuration via NOTIFICATION_ALLOWED_DOMAINS.

    Args:
        url: URL to validate

    Returns:
        True if URL is safe, False otherwise
    """
    if not url:
        return True  # Empty URL is OK

    url = url.strip()

    # Reject dangerous schemes
    dangerous_schemes = ['javascript:', 'data:', 'vbscript:', 'file:', 'about:']
    url_lower = url.lower()
    for scheme in dangerous_schemes:
        if url_lower.startswith(scheme):
            return False

    # Allow relative paths (must start with /)
    if url.startswith('/'):
        # Reject protocol-relative URLs (//evil.com)
        if url.startswith('//'):
            return False
        # Reject characters that break out of HTML attributes or enable injection if ever
        # rendered without escaping (defence in depth alongside Jinja escaping).
        if any(ch in url for ch in ('"', "'", '<', '>', '\n', '\r', '\0')):
            return False
        # Allow relative paths by default (safest option)
        return True

    # For absolute URLs, require explicit whitelist configuration
    retry_context = None
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ['http', 'https']:
            return False

        # SECURITY: By default, only allow relative paths
        # External URLs require explicit whitelist configuration
        allowed_domains = current_app.config.get('NOTIFICATION_ALLOWED_DOMAINS', [])
        if not allowed_domains:
            current_app.logger.warning(
                f"External URL rejected (no whitelist configured): {url[:100]}. "
                f"Only relative paths are allowed by default. "
                f"Configure NOTIFICATION_ALLOWED_DOMAINS to allow external URLs."
            )
            return False

        if parsed.netloc not in allowed_domains:
            current_app.logger.warning(
                f"External URL rejected (domain not in whitelist): {parsed.netloc}. "
                f"Allowed domains: {allowed_domains}"
            )
            return False

        return True
    except Exception as e:
        # Invalid URL format
        current_app.logger.debug(f"URL validation failed for '{url[:100]}': {e}")
        return False


def validate_action_button_endpoint(endpoint: Optional[str]) -> bool:
    """
    Validate action button endpoint to ensure it's safe.

    Args:
        endpoint: Endpoint URL to validate

    Returns:
        True if endpoint is safe, False otherwise
    """
    if not endpoint:
        return True  # Empty endpoint is OK

    endpoint = endpoint.strip()

    # Must be a relative path
    if not endpoint.startswith('/'):
        return False

    # Reject dangerous patterns
    dangerous_patterns = ['//', 'javascript:', 'data:', '../', '..\\']
    endpoint_lower = endpoint.lower()
    for pattern in dangerous_patterns:
        if pattern in endpoint_lower:
            return False

    # Optionally: Check against whitelist of allowed endpoint patterns
    allowed_patterns = current_app.config.get('NOTIFICATION_ALLOWED_ENDPOINTS', [])
    if allowed_patterns:
        # Check if endpoint matches any allowed pattern
        for pattern in allowed_patterns:
            # Simple pattern matching (could use regex for more complex)
            if pattern.replace('{id}', '').replace('{*}', '') in endpoint:
                return True
        return False

    # If no whitelist configured, allow any relative path (but still check for dangerous patterns above)
    return True


def validate_and_sanitize_action_buttons(action_buttons: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
    """
    Validate and sanitize action buttons when deserializing from database.
    This provides defense-in-depth validation when action buttons are retrieved.

    Args:
        action_buttons: List of action button dictionaries from database

    Returns:
        Validated and sanitized list of action buttons, or None if invalid/empty
    """
    if not action_buttons:
        return None

    if not isinstance(action_buttons, list):
        current_app.logger.warning(f"Invalid action_buttons type: {type(action_buttons)}, expected list")
        return None

    validated_buttons = []
    for i, btn in enumerate(action_buttons):
        if not isinstance(btn, dict):
            current_app.logger.warning(f"Action button at index {i} is not a dictionary, skipping")
            continue

        # Validate required fields
        if 'action' not in btn or 'label' not in btn:
            current_app.logger.warning(f"Action button at index {i} missing required fields (action, label), skipping")
            continue

        # Validate and sanitize label
        label = btn.get('label', '')
        if not isinstance(label, str):
            current_app.logger.warning(f"Action button at index {i} label is not a string, skipping")
            continue

        max_label_length = current_app.config.get('MAX_ACTION_BUTTON_LABEL_LENGTH', 100)
        if len(label) > max_label_length:
            current_app.logger.warning(f"Action button at index {i} label too long ({len(label)} chars), truncating")
            label = label[:max_label_length]

        # Validate action identifier
        action = btn.get('action', '')
        if not isinstance(action, str):
            current_app.logger.warning(f"Action button at index {i} action is not a string, skipping")
            continue

        max_action_length = current_app.config.get('MAX_ACTION_BUTTON_ACTION_LENGTH', 50)
        if len(action) > max_action_length:
            current_app.logger.warning(f"Action button at index {i} action too long ({len(action)} chars), skipping")
            continue

        # Validate endpoint if provided
        endpoint = btn.get('endpoint')
        if endpoint:
            if not isinstance(endpoint, str):
                current_app.logger.warning(f"Action button at index {i} endpoint is not a string, removing endpoint")
                endpoint = None
            elif not validate_action_button_endpoint(endpoint):
                current_app.logger.warning(
                    f"Action button at index {i} has unsafe endpoint '{endpoint}', removing endpoint"
                )
                endpoint = None

        # Validate style if provided
        style = btn.get('style')
        valid_styles = ['primary', 'danger', 'secondary', 'success', 'warning', 'info']
        if style and style not in valid_styles:
            current_app.logger.warning(f"Action button at index {i} has invalid style '{style}', using default")
            style = 'primary'

        # Create validated button
        validated_btn = {
            'action': action,
            'label': label,
        }

        if endpoint:
            validated_btn['endpoint'] = endpoint

        if style:
            validated_btn['style'] = style

        validated_buttons.append(validated_btn)

    return validated_buttons if validated_buttons else None


def _notification_msgid(msgid: str) -> str:
    """
    Mark English gettext msgids for pybabel extract.

    Plain string literals in dicts are not scanned by Babel; wrapping each msgid in this
    no-op ensures the same strings appear in messages.pot / manage_translations as runtime
    gettext(source_string) lookups.
    """
    return msgid


def translate_notification_message(translation_key: str, params: Optional[Dict[str, Any]] = None, locale: Optional[str] = None) -> str:
    """
    Translate a notification message using Flask-Babel.

    Args:
        translation_key: Translation key (e.g., 'notification.assignment_created.title')
        params: Parameters for translation interpolation
        locale: Optional locale to use (defaults to current locale from request context)

    Returns:
        Translated message string

    This function maps translation keys to Flask-Babel translatable strings.
    Translations are performed at runtime to respect the user's current locale.
    """
    if not translation_key:
        return ""

    params = params or {}

    # Notification translation source strings (English msgids for gettext).
    # Each value MUST be wrapped in _notification_msgid("...") so pybabel extract lists them
    # in messages.pot; otherwise manage_translations shows unrelated/old entries only.
    translation_sources = {
        # Assignment notifications (title = headline; message = detail — avoid repeating the same sentence in both)
        'notification.assignment_created.title': _notification_msgid('New Assignment Created'),
        'notification.assignment_created.message': _notification_msgid(
            "Template '%(template)s', period '%(period)s'. Due date: %(due_date)s."
        ),

        'notification.assignment_submitted.title': _notification_msgid('Team update: %(template)s submitted'),
        'notification.assignment_submitted.message': _notification_msgid(
            'Period %(period)s: another focal point in your entity submitted this form. No action needed from you.'
        ),

        'notification.assignment_submitted.admin.title': _notification_msgid(
            '{submitter_name} has submitted this assignment for period {period}.'
        ),
        'notification.assignment_submitted.admin.message': _notification_msgid(
            'Please review and validate this submission in the Backoffice.'
        ),

        'notification.assignment_approved.title': _notification_msgid('Assignment approved'),
        'notification.assignment_approved.message': _notification_msgid(
            "Your assignment '%(template)s' has been approved."
        ),

        'notification.assignment_reopened.title': _notification_msgid('Assignment reopened'),
        'notification.assignment_reopened.message': _notification_msgid(
            "Assignment '%(template)s' has been reopened."
        ),

        # Document notifications
        'notification.document_uploaded.title': _notification_msgid('Document uploaded'),
        'notification.document_uploaded.message': _notification_msgid(
            "'%(document)s' (%(document_type)s) was uploaded."
        ),

        'notification.document_uploaded.pending.title': _notification_msgid('Document pending review'),
        'notification.document_uploaded.pending.message': _notification_msgid(
            "'%(document)s' (%(document_type)s) has been uploaded and requires approval."
        ),

        # Access request notifications
        'notification.access_request_received.title': _notification_msgid('Country access request'),
        'notification.access_request_received.message': _notification_msgid(
            '%(user_name)s requested access to %(country_name)s.'
        ),

        # User notifications
        'notification.user_added_to_country.title': _notification_msgid('Added to country team'),
        'notification.user_added_to_country.message': _notification_msgid(
            'You are now a focal point for %(country)s.'
        ),

        # Template notifications
        'notification.template_updated.title': _notification_msgid('Template updated'),
        'notification.template_updated.message': _notification_msgid("'%(template)s' has been updated."),

        # Form notifications
        'notification.form_updated.title': _notification_msgid('Form updated'),
        'notification.form_updated.message': _notification_msgid('Form data has been updated.'),

        # Deadline notifications
        'notification.deadline_reminder.title': _notification_msgid('Deadline reminder'),
        'notification.deadline_reminder.message': _notification_msgid(
            "Assignment '%(template)s' is due on %(due_date)s."
        ),

        # Self-report notifications
        'notification.self_report_created.title': _notification_msgid('Self report created'),
        'notification.self_report_created.message': _notification_msgid('A new self-report has been created.'),

        # Public submission notifications
        'notification.public_submission_received.title': _notification_msgid('Public submission received'),
        'notification.public_submission_received.message': _notification_msgid(
            "From %(submitter)s (%(country)s) for '%(template)s'."
        ),

        # Admin message notifications (these use custom messages, so we handle them specially)
        'notification.admin_message.title': _notification_msgid('Admin Message'),
        'notification.admin_message.message': _notification_msgid('You have received an admin message'),
    }

    # Try to get translation source from map
    if translation_key in translation_sources:
        try:
            source_string = translation_sources[translation_key]

            # Handle special cases for admin messages (user-generated content)
            # Sanitize before returning to prevent XSS if rendered in an HTML context downstream.
            if params:
                # For admin message title, use custom title if provided
                if translation_key == 'notification.admin_message.title' and 'custom_title' in params:
                    return str(params['custom_title'])[:255]
                # For admin message body, use custom message if provided
                if translation_key == 'notification.admin_message.message' and 'message' in params:
                    return str(params['message'])[:MAX_NOTIFICATION_MESSAGE_LENGTH]

            # Translate at runtime using the current locale
            # Use force_locale if a specific locale is provided, otherwise use canonical session/request language
            from flask_babel import force_locale
            from app.utils.form_localization import get_translation_key

            locale_to_use = locale or get_translation_key()

            # Normalize and validate locale
            if locale_to_use:
                supported_langs = current_app.config.get('LANGUAGES', [])
                # First, check if the locale is already in the supported languages
                if locale_to_use not in supported_langs:
                    # Try to find a matching language (e.g., 'fr' matches 'fr_FR' or vice versa)
                    # Extract base language code (e.g., 'fr' from 'fr_FR')
                    base_lang = locale_to_use.split('_')[0] if '_' in locale_to_use else locale_to_use
                    # Try exact match first
                    matching_lang = next((lang for lang in supported_langs if lang == locale_to_use), None)
                    if not matching_lang:
                        # Try base language match (e.g., 'fr' matches 'fr_FR')
                        matching_lang = next((lang for lang in supported_langs if lang.startswith(base_lang) or base_lang.startswith(lang.split('_')[0])), None)
                    if matching_lang:
                        locale_to_use = matching_lang
                    elif base_lang in supported_langs:
                        # Use base language if it's in the list
                        locale_to_use = base_lang
                    else:
                        current_app.logger.warning(f"[NOTIFICATION_TRANSLATE] Locale '{locale_to_use}' not in supported languages: {supported_langs}")
                        locale_to_use = None

            if locale_to_use:
                try:
                    # Import gettext within the function to ensure it uses the forced locale
                    from flask_babel import gettext, refresh
                    # Refresh translations to ensure they're loaded
                    try:
                        refresh()
                    except Exception:
                        pass

                    with force_locale(locale_to_use):
                        # Use gettext directly to ensure it respects force_locale
                        translated = gettext(source_string)
                        # Check if translation actually changed (Flask-Babel returns msgid if translation missing)
                        if str(translated) == source_string and locale_to_use != 'en':
                            current_app.logger.warning(
                                f"[NOTIFICATION_TRANSLATE] Missing translation: key='{translation_key}', locale='{locale_to_use}'"
                            )
                except Exception as e:
                    current_app.logger.error(f"[NOTIFICATION_TRANSLATE] Error translating with locale {locale_to_use}: {e}", exc_info=True)
                    # Fallback to English
                    from flask_babel import gettext
                    with force_locale('en'):
                        translated = gettext(source_string)
            else:
                # Use current request locale (canonical session/request language)
                current_babel_locale = get_translation_key()
                # Import gettext to ensure it uses current locale
                from flask_babel import gettext
                translated = gettext(source_string)
                # Check if translation changed
                if str(translated) == source_string and current_babel_locale != 'en' and current_babel_locale != 'unknown':
                    current_app.logger.warning(
                        f"[NOTIFICATION_TRANSLATE] Missing translation: key='{translation_key}', locale='{current_babel_locale}'"
                    )

            # Format with parameters if provided (support both %(name)s and {name} style)
            if params and isinstance(params, dict):
                # Filter out internal params (prefixed with _)
                format_params = {k: v for k, v in params.items() if not (isinstance(k, str) and k.startswith('_'))}
                if format_params:
                    try:
                        # Prefer .format() for {name} placeholders (avoids gettext % escaping issues)
                        if '{' in str(translated):
                            result = translated.format(**format_params)
                        else:
                            result = translated % format_params
                        return result
                    except (KeyError, TypeError) as e:
                        params_keys = list(format_params.keys())
                        current_app.logger.warning(
                            f"[NOTIFICATION_TRANSLATE] Error formatting key='{translation_key}' params_keys={params_keys}: {e}"
                        )
                        return str(translated)

            return str(translated)
        except Exception as e:
            current_app.logger.error(f"[NOTIFICATION_TRANSLATE] Error translating key='{translation_key}': {e}", exc_info=True)

    # Fallback: return the key or a default message
    current_app.logger.warning(f"[NOTIFICATION_TRANSLATE] Unknown key='{translation_key}' (not in translation map)")
    return translation_key



# Removed country-based helper; notifications are entity-scoped or user-scoped now.


def is_notification_type_enabled_for_user(
    user_id: int,
    notification_type: 'NotificationType',
    preferences_cache: Optional[Dict[int, Any]] = None
) -> bool:
    """
    Check if a notification type is enabled for a user based on their preferences.

    Args:
        user_id (int): User ID to check
        notification_type (NotificationType): The notification type to check
        preferences_cache (dict, optional): Cache of user preferences {user_id: preferences}
                                            to avoid repeated database queries

    Returns:
        bool: True if notification type is enabled, False otherwise

    Logic:
        - If preferences don't exist, default to enabled (create default preferences)
        - If notification_types_enabled is empty/None, all types are enabled
        - If notification_types_enabled has values, only those types are enabled
    """
    try:
        # Get notification type as string value
        if hasattr(notification_type, 'value'):
            notification_type_str = notification_type.value
        else:
            notification_type_str = str(notification_type)

        # Use cache if provided, otherwise fetch from database
        if preferences_cache and user_id in preferences_cache:
            preferences = preferences_cache[user_id]
        else:
            preferences = NotificationPreferences.query.filter_by(user_id=user_id).first()

            # Create default preferences if they don't exist
            if not preferences:
                preferences = NotificationPreferences(
                    user_id=user_id,
                    email_notifications=True,
                    notification_types_enabled=[],  # Empty = all enabled
                    notification_frequency='instant',
                    sound_enabled=False
                )
                db.session.add(preferences)
                try:
                    db.session.commit()
                    current_app.logger.debug(f"Created default notification preferences for user {user_id}")
                except Exception as e:
                    current_app.logger.error(f"Error creating default preferences for user {user_id}: {str(e)}")
                    db.session.rollback()
                    # If we can't create preferences, default to enabled
                    return True

            # Update cache if provided
            if preferences_cache is not None:
                preferences_cache[user_id] = preferences

        # If notification_types_enabled is empty/None, all types are enabled
        enabled_types = preferences.notification_types_enabled or []
        if not enabled_types:
            return True

        # Check if this specific type is in the enabled list
        return notification_type_str in enabled_types

    except Exception as e:
        current_app.logger.error(f"Error checking notification type for user {user_id}: {str(e)}")
        # On error, default to enabled to avoid blocking notifications
        return True


def get_user_preferences_batch(user_ids: List[int]) -> Dict[int, Any]:
    """
    Efficiently load notification preferences for multiple users in a single query.

    Args:
        user_ids (list): List of user IDs

    Returns:
        dict: Dictionary mapping user_id to NotificationPreferences object
    """
    if not user_ids:
        return {}

    try:
        # Query all preferences at once
        preferences_list = NotificationPreferences.query.filter(
            NotificationPreferences.user_id.in_(user_ids)
        ).all()

        # Create dictionary mapping user_id to preferences
        preferences_dict = {pref.user_id: pref for pref in preferences_list}

        # Create default preferences for users who don't have any
        missing_user_ids = set(user_ids) - set(preferences_dict.keys())
        if missing_user_ids:
            default_prefs = []
            for user_id in missing_user_ids:
                default_pref = NotificationPreferences(
                    user_id=user_id,
                    email_notifications=True,
                    notification_types_enabled=[],  # Empty = all enabled
                    notification_frequency='instant',
                    sound_enabled=False
                )
                default_prefs.append(default_pref)
                preferences_dict[user_id] = default_pref

            if default_prefs:
                db.session.bulk_save_objects(default_prefs)
                try:
                    db.session.commit()
                    current_app.logger.debug(f"Created default preferences for {len(default_prefs)} users")
                except Exception as e:
                    current_app.logger.error(f"Error creating default preferences: {str(e)}")
                    db.session.rollback()
                    # Remove failed preferences from dict
                    for user_id in missing_user_ids:
                        preferences_dict.pop(user_id, None)

        return preferences_dict

    except Exception as e:
        current_app.logger.error(f"Error loading batch preferences: {str(e)}")
        return {}


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

        # Get TTL configuration
        ttl_days = current_app.config.get('NOTIFICATION_TTL_DAYS', {}).get(
            notif_type_str,
            90  # Default 90 days
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


def create_notification(
    user_ids: Union[int, List[int]],
    notification_type: 'NotificationType',
    title_key: str,
    message_key: str,
    title_params: Optional[Dict[str, Any]] = None,
    message_params: Optional[Dict[str, Any]] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    related_object_type: Optional[str] = None,
    related_object_id: Optional[int] = None,
    related_url: Optional[str] = None,
    priority: str = 'normal',
    icon: Optional[str] = None,
    respect_preferences: bool = True,
    action_buttons: Optional[List[Dict[str, Any]]] = None,
    # Admin override for email preferences
    override_email_preferences: bool = False,
    # Side-effect controls (for routes that handle push/email themselves)
    send_email_notifications: bool = True,
    send_push_notifications: bool = True,
    # Phase 4: User Experience Enhancements
    category: Optional[str] = None,
    tags: Optional[List[str]] = None,
    _retry_on_conflict: bool = True
) -> List[Any]:
    """
    Create notifications for one or more users (optimized for bulk inserts).
    Now respects user notification preferences by default.
    Requires translation keys for internationalization support.

    Args:
        user_ids (list): List of user IDs to notify, or single user ID
        notification_type (NotificationType): Type of notification
        entity_type (str, optional): Type of entity ('country', 'ns_branch', 'department', etc.)
        entity_id (int, optional): ID of the entity
        related_object_type (str): Type of related object ('assignment', 'submission', etc.)
        related_object_id (int): ID of related object
        related_url (str): Direct URL to related object
        priority (str): Priority level ('low', 'normal', 'high', 'urgent')
        icon (str): FontAwesome icon class
        respect_preferences (bool): If True, filter users based on notification preferences (default: True)
        action_buttons (list, optional): List of action button dicts. Each dict should have:
            - label (str): Button text
            - action (str): Action identifier (e.g., 'approve', 'reject')
            - endpoint (str, optional): URL to navigate to after action
            - style (str, optional): Button style ('primary', 'danger', or default)
        title_key (str, required): Translation key for title (e.g., 'notification.assignment_created.title')
        title_params (dict, optional): Parameters for title translation
        message_key (str, required): Translation key for message
        message_params (dict, optional): Parameters for message translation
        override_email_preferences (bool, optional): If True, bypass user email preferences and send email anyway (admin override). Default: False
        category (str, optional): Notification category for filtering (e.g., 'assignment', 'system', 'alert')
        tags (list, optional): List of tags for flexible categorization (e.g., ['urgent', 'action-required'])

    Returns:
        list: List of created Notification objects or dicts, or None on error

    Note:
        - title_key and message_key are required for internationalization support.
        - Title and message are generated from translation keys at runtime based on user locale.

    Example action_buttons:
        [
            {
                'label': 'Approve',
                'action': 'approve',
                'endpoint': '/api/assignments/123/approve',
                'style': 'primary'
            },
            {
                'label': 'Reject',
                'action': 'reject',
                'endpoint': '/api/assignments/123/reject',
                'style': 'danger'
            }
        ]
    """
    try:
        # Resolve priority from settings (Admin > Notifications tab); if not set, default to normal
        from app.services.app_settings_service import get_notification_priority
        priority = get_notification_priority(notification_type, default='normal')

        # Validate that translation keys are provided (required)
        if not title_key or not message_key:
            current_app.logger.error("create_notification called without required translation keys (title_key and message_key)")
            raise ValueError("title_key and message_key are required for notification creation")

        # Generate English fallback text for database storage (used as fallback if translation fails)
        # This is stored in the title/message fields for database compatibility
        from flask_babel import force_locale
        with force_locale('en'):
            title = translate_notification_message(title_key, title_params, locale='en')
            message = translate_notification_message(message_key, message_params, locale='en')

        # Ensure we have title and message
        if not title or not message:
            current_app.logger.error(f"Failed to generate title/message from translation keys: title_key={title_key}, message_key={message_key}")
            raise ValueError("Failed to generate notification content from translation keys")

        # INPUT VALIDATION: Validate content length
        if title and len(title) > 255:
            current_app.logger.error(f"Notification title exceeds maximum length of 255 characters: {len(title)}")
            raise ValueError(f"Title exceeds maximum length of 255 characters (got {len(title)})")

        if message and len(message) > MAX_NOTIFICATION_MESSAGE_LENGTH:
            current_app.logger.error(f"Notification message exceeds maximum length of {MAX_NOTIFICATION_MESSAGE_LENGTH} characters: {len(message)}")
            raise ValueError(f"Message exceeds maximum length of {MAX_NOTIFICATION_MESSAGE_LENGTH} characters (got {len(message)})")

        # Validate user_ids
        if not user_ids:
            return []

        # Validate notification_type
        if not notification_type:
            current_app.logger.error("create_notification called without notification_type")
            raise ValueError("notification_type is required")

        # Validate priority
        valid_priorities = ['low', 'normal', 'high', 'urgent']
        if priority not in valid_priorities:
            current_app.logger.warning(f"Invalid priority '{priority}', defaulting to 'normal'")
            priority = 'normal'

        # Validate action_buttons structure and endpoints
        if action_buttons:
            if not isinstance(action_buttons, list):
                current_app.logger.error("action_buttons must be a list")
                raise ValueError("action_buttons must be a list of dictionaries")

            # Limit maximum number of action buttons
            max_action_buttons = current_app.config.get('MAX_NOTIFICATION_ACTION_BUTTONS', 5)
            if len(action_buttons) > max_action_buttons:
                current_app.logger.error(f"Too many action buttons: {len(action_buttons)} (max: {max_action_buttons})")
                raise ValueError(f"Maximum {max_action_buttons} action buttons allowed per notification")

            for i, btn in enumerate(action_buttons):
                if not isinstance(btn, dict):
                    current_app.logger.error(f"Action button at index {i} is not a dictionary")
                    raise ValueError(f"Action button at index {i} must be a dictionary")

                # Required fields
                if 'action' not in btn or 'label' not in btn:
                    current_app.logger.error(f"Action button at index {i} missing required fields (action, label)")
                    raise ValueError(f"Action button at index {i} must have 'action' and 'label' keys")

                # Validate label length and content
                label = btn.get('label', '')
                if not isinstance(label, str):
                    current_app.logger.error(f"Action button at index {i} label must be a string")
                    raise ValueError(f"Action button at index {i} label must be a string")

                max_label_length = current_app.config.get('MAX_ACTION_BUTTON_LABEL_LENGTH', 100)
                if len(label) > max_label_length:
                    current_app.logger.error(f"Action button at index {i} label too long: {len(label)} chars (max: {max_label_length})")
                    raise ValueError(f"Action button label must be {max_label_length} characters or less")

                if len(label.strip()) == 0:
                    current_app.logger.error(f"Action button at index {i} label cannot be empty")
                    raise ValueError(f"Action button label cannot be empty")

                # Validate action identifier
                action = btn.get('action', '')
                if not isinstance(action, str):
                    current_app.logger.error(f"Action button at index {i} action must be a string")
                    raise ValueError(f"Action button at index {i} action must be a string")

                max_action_length = current_app.config.get('MAX_ACTION_BUTTON_ACTION_LENGTH', 50)
                if len(action) > max_action_length:
                    current_app.logger.error(f"Action button at index {i} action too long: {len(action)} chars (max: {max_action_length})")
                    raise ValueError(f"Action button action must be {max_action_length} characters or less")

                # Validate style if provided
                if 'style' in btn:
                    valid_styles = ['primary', 'danger', 'secondary', 'success', 'warning', 'info']
                    if btn['style'] not in valid_styles:
                        current_app.logger.warning(f"Action button at index {i} has invalid style '{btn['style']}', defaulting to 'primary'")
                        btn['style'] = 'primary'

                # Validate endpoint if provided
                if btn.get('endpoint'):
                    if not isinstance(btn['endpoint'], str):
                        current_app.logger.error(f"Action button at index {i} endpoint must be a string")
                        raise ValueError(f"Action button at index {i} endpoint must be a string")

                    max_endpoint_length = current_app.config.get('MAX_ACTION_BUTTON_ENDPOINT_LENGTH', 500)
                    if len(btn['endpoint']) > max_endpoint_length:
                        current_app.logger.error(f"Action button at index {i} endpoint too long: {len(btn['endpoint'])} chars (max: {max_endpoint_length})")
                        raise ValueError(f"Action button endpoint must be {max_endpoint_length} characters or less")

                    if not validate_action_button_endpoint(btn['endpoint']):
                        current_app.logger.error(f"Action button at index {i} has unsafe endpoint: {btn['endpoint']}")
                        raise ValueError(f"Action button endpoint contains unsafe content: {btn['endpoint']}")

        # Validate related_url length and safety if provided
        if related_url:
            if len(related_url) > 500:
                current_app.logger.error(f"Notification related_url exceeds maximum length of 500 characters: {len(related_url)}")
                raise ValueError(f"Related URL exceeds maximum length of 500 characters (got {len(related_url)})")

            # Validate URL safety to prevent open redirects and XSS
            if not validate_notification_url(related_url):
                current_app.logger.error(f"Notification related_url failed safety validation: {related_url}")
                raise ValueError("Related URL contains unsafe content (potential security risk)")

        # Ensure user_ids is a list
        if not isinstance(user_ids, list):
            user_ids = [user_ids]
        else:
            user_ids = list(user_ids)

        # Validate user_ids are integers
        validated_user_ids = []
        for uid in user_ids:
            try:
                validated_user_ids.append(int(uid))
            except (ValueError, TypeError):
                current_app.logger.warning(f"Invalid user_id in create_notification: {uid} (skipping)")
                continue

        if not validated_user_ids:
            current_app.logger.warning("create_notification called with no valid user_ids - returning empty list")
            return []

        user_ids = validated_user_ids

        # Rate limiting: Check limits (global first for fail-fast, then per-user)
        max_per_user = current_app.config.get('MAX_NOTIFICATIONS_PER_USER_PER_HOUR', 100)
        max_global = current_app.config.get('MAX_NOTIFICATIONS_GLOBAL_PER_HOUR', 10000)

        # Check global rate limit FIRST (fail-fast optimization)
        if max_global > 0:
            hour_ago = utcnow() - timedelta(hours=1)
            global_recent_count = Notification.query.filter(
                Notification.created_at >= hour_ago
            ).count()
            if global_recent_count >= max_global:
                current_app.logger.error(
                    f"Global notification rate limit exceeded: {global_recent_count} notifications in last hour (limit: {max_global})"
                )
                # Don't create any notifications if global limit exceeded
                return []

        # Check per-user rate limits (only if global limit not exceeded)
        rate_limited_users = []
        if max_per_user > 0:
            hour_ago = utcnow() - timedelta(hours=1)
            # Use a single query with IN clause for better performance
            user_ids_tuple = tuple(user_ids)
            if user_ids_tuple:
                # Get counts for all users in one query
                from sqlalchemy import func
                user_counts = db.session.query(
                    Notification.user_id,
                    func.count(Notification.id).label('count')
                ).filter(
                    Notification.user_id.in_(user_ids),
                    Notification.created_at >= hour_ago
                ).group_by(Notification.user_id).all()

                # Build a dict for quick lookup
                user_count_map = {uid: count for uid, count in user_counts}

                # Check each user against their limit
                for user_id in user_ids:
                    recent_count = user_count_map.get(user_id, 0)
                    if recent_count >= max_per_user:
                        rate_limited_users.append(user_id)
                        current_app.logger.warning(
                            f"Rate limit exceeded for user {user_id}: {recent_count} notifications in last hour (limit: {max_per_user})"
                        )

        # Remove rate-limited users from the list
        if rate_limited_users:
            user_ids = [uid for uid in user_ids if uid not in rate_limited_users]
            current_app.logger.warning(
                f"Filtered out {len(rate_limited_users)} user(s) due to rate limiting. "
                f"Remaining users: {len(user_ids)}"
            )
            if not user_ids:
                current_app.logger.warning("All users were rate-limited, no notifications created")
                return []

        # Prefetch user emails for logging to avoid N+1 lookups
        try:
            users_for_logging = User.query.filter(User.id.in_(user_ids)).all()
            user_email_map = {u.id: (u.email or 'Unknown') for u in users_for_logging}
        except Exception as e:
            current_app.logger.debug("Prefetch user emails for logging: %s", e)
            user_email_map = {}

        # Filter users based on preferences if enabled
        if respect_preferences:
            # Load preferences for all users in a single batch query
            preferences_cache = get_user_preferences_batch(user_ids)

            # Filter user_ids to only include those who have this notification type enabled
            filtered_user_ids = [
                user_id for user_id in user_ids
                if is_notification_type_enabled_for_user(
                    user_id,
                    notification_type,
                    preferences_cache=preferences_cache
                )
            ]

            # Log filtering results
            filtered_count = len(user_ids) - len(filtered_user_ids)
            if filtered_count > 0:
                current_app.logger.info(
                    f"Filtered out {filtered_count} user(s) based on notification preferences "
                    f"for type {notification_type.value if hasattr(notification_type, 'value') else notification_type}"
                )

            user_ids = filtered_user_ids

            # If all users were filtered out, return empty list
            if not user_ids:
                return []

        # Default icon based on notification type
        if not icon:
            icon = get_default_icon_for_notification_type(notification_type)

        # Calculate expiration date
        expires_at = calculate_notification_expiration(notification_type)

        retry_context = {
            'user_ids': list(user_ids),
            'notification_type': notification_type,
            'title_key': title_key,
            'message_key': message_key,
            'title_params': title_params,
            'message_params': message_params,
            'entity_type': entity_type,
            'entity_id': entity_id,
            'related_object_type': related_object_type,
            'related_object_id': related_object_id,
            'related_url': related_url,
            'priority': priority,
            'icon': icon,
            'respect_preferences': respect_preferences,
            'action_buttons': action_buttons,
            'override_email_preferences': override_email_preferences,
            'send_email_notifications': send_email_notifications,
            'send_push_notifications': send_push_notifications,
            'category': category,
            'tags': tags
        }

        # Phase 2: Generate group IDs for notifications (grouping)
        # Group ID is generated per user, so we'll do it during notification creation
        group_ids = {}
        for user_id in user_ids:
            group_id = generate_group_id(user_id, notification_type, related_object_id, entity_type, entity_id)
            group_ids[user_id] = group_id

        # Phase 1: Deduplication - Filter out duplicates
        deduplicated_user_ids = []
        skipped_count = 0
        skipped_details = []

        nt_val = getattr(notification_type, 'value', str(notification_type))
        skip_dedup = nt_val in ('assignment_submitted', 'assignment_reopened')
        # For skip_dedup types: add event timestamp so each submit/reopen gets a unique hash.
        # Otherwise the DB unique constraint (user_id, notification_hash) would reject inserts
        # when notifications from a prior submit already exist.
        event_ts = utcnow().isoformat() if skip_dedup else None

        for user_id in user_ids:
            # Generate hash for this notification
            # Use translation keys for hash if available (for better deduplication),
            # otherwise fall back to title/message text
            hash_title = title_key if title_key else title
            # Add entity discriminator to hash (prevents dedup across different entities for same assignment/user)
            entity_discriminator = None
            if message_params and isinstance(message_params, dict):
                et = message_params.get('_entity_type')
                ei = message_params.get('_entity_id')
                if et and ei is not None:
                    entity_discriminator = f"{et}:{ei}"
            if message_key:
                hash_message = f"{message_key}|{entity_discriminator}" if entity_discriminator else message_key
            else:
                hash_message = f"{message}|{entity_discriminator}" if (message and entity_discriminator) else message
            if event_ts:
                hash_message = f"{hash_message}|event:{event_ts}"
            notification_hash = generate_notification_hash(
                user_id,
                notification_type,
                related_object_id,
                hash_title,
                message=hash_message  # Include message for admin_message type
            )

            is_duplicate = False
            if not skip_dedup:
                is_duplicate = check_duplicate_notification(
                    user_id,
                    notification_hash,
                    notification_type=notification_type
                )
            if is_duplicate:
                skipped_count += 1
                user_email = user_email_map.get(user_id, 'Unknown')
                skipped_details.append((user_id, user_email, notification_hash))
                continue

            deduplicated_user_ids.append((user_id, notification_hash))

        if not deduplicated_user_ids:
            return []

        # Use bulk insert for better performance when creating multiple notifications
        if len(deduplicated_user_ids) > 5:
            # Bulk insert for many notifications with proper transaction handling
            notification_mappings = [
                {
                    'user_id': user_id,
                    'entity_type': entity_type,
                    'entity_id': entity_id,
                    'notification_type': notification_type,
                    'title': title,
                    'message': message,
                    'related_object_type': related_object_type,
                    'related_object_id': related_object_id,
                    'related_url': related_url,
                    'priority': priority,
                    'icon': icon,
                    'created_at': utcnow(),
                    'is_read': False,
                    'is_archived': False,
                    'notification_hash': notification_hash,
                    'expires_at': expires_at,
                    'group_id': group_ids.get(user_id),  # Phase 2: Add group_id
                    'action_buttons': action_buttons,  # Phase 3: Action buttons
                    # Phase 4: Internationalization
                    'title_key': title_key,
                    'title_params': title_params,
                    'message_key': message_key,
                    'message_params': message_params,
                    # Phase 4: User Experience Enhancements
                    'category': category,
                    'tags': tags if tags else None
                }
                for user_id, notification_hash in deduplicated_user_ids
            ]

            try:
                # Perform bulk insert within transaction
                db.session.bulk_insert_mappings(Notification, notification_mappings)
                db.session.commit()

                # Phase 2: Broadcast notifications via WebSocket for bulk inserts (non-blocking)
                # This is separate from the transaction - if it fails, notifications are already saved
                try:
                    from app.utils.ws_manager import broadcast_notification, broadcast_unread_count
                    from app.services.notification.service import NotificationService

                    # Query back the created notifications to get IDs for WebSocket broadcasting
                    # Use notification_hash for more reliable matching (avoids title encoding issues)
                    # Get notifications created in the last few seconds for these users
                    recent_cutoff = utcnow() - timedelta(seconds=5)
                    notification_hashes = [nh for _, nh in deduplicated_user_ids]
                    created_notifications = Notification.query.filter(
                        and_(
                            Notification.user_id.in_([uid for uid, _ in deduplicated_user_ids]),
                            Notification.notification_type == notification_type,
                            Notification.created_at >= recent_cutoff,
                            Notification.notification_hash.in_(notification_hashes)
                        )
                    ).all()

                    # Track users we've already sent unread count updates to
                    users_updated = set()

                    for notification in created_notifications:
                        # Format notification for WebSocket
                        notification_data = {
                            'id': notification.id,
                            'title': notification.title,
                            'message': notification.message,
                            'notification_type': notification.notification_type.value if hasattr(notification.notification_type, 'value') else str(notification.notification_type),
                            'is_read': notification.is_read,
                            'created_at': notification.created_at.isoformat(),
                            'priority': notification.priority,
                            'icon': notification.icon,
                        'related_url': notification.related_url,
                        'group_id': getattr(notification, 'group_id', None),
                        'viewed_at': notification.viewed_at.isoformat() if getattr(notification, 'viewed_at', None) else None,
                        'category': getattr(notification, 'category', None),
                        'tags': getattr(notification, 'tags', None)
                        }

                        # Broadcast to user (non-blocking - failures won't rollback notifications)
                        try:
                            broadcast_notification(notification.user_id, notification_data)
                        except Exception as broadcast_error:
                            current_app.logger.warning(f"Failed to broadcast notification {notification.id} via WebSocket: {broadcast_error}")

                        # Update unread count (only once per user)
                        if notification.user_id not in users_updated:
                            try:
                                unread_count = NotificationService.get_unread_count(notification.user_id)
                                broadcast_unread_count(notification.user_id, unread_count)
                            except Exception as count_error:
                                current_app.logger.warning(f"Failed to broadcast unread count for user {notification.user_id}: {count_error}")
                            users_updated.add(notification.user_id)
                except Exception as e:
                    # Don't fail notification creation if WebSocket fails
                    current_app.logger.warning(f"Failed to broadcast bulk notifications via WebSocket: {str(e)}")

                # Handle IntegrityError for unique constraint violations (race condition)
            except IntegrityError as e:
                db.session.rollback()
                # Check if this is the unique constraint violation for notification_hash
                error_str = str(e.orig) if hasattr(e, 'orig') else str(e)
                if 'uq_notification_user_hash' in error_str or 'duplicate key value violates unique constraint' in error_str:
                    # Race condition: another process inserted the same notification
                    # Retry with individual inserts that handle conflicts gracefully
                    # Retry with individual inserts, handling conflicts per notification
                    successfully_created = []
                    for user_id, notification_hash in deduplicated_user_ids:
                        try:
                            notification = Notification(
                                user_id=user_id,
                                entity_type=entity_type,
                                entity_id=entity_id,
                                notification_type=notification_type,
                                title=title,
                                message=message,
                                related_object_type=related_object_type,
                                related_object_id=related_object_id,
                                related_url=related_url,
                                priority=priority,
                                icon=icon,
                                notification_hash=notification_hash,
                                expires_at=expires_at,
                                group_id=group_ids.get(user_id),
                                action_buttons=action_buttons,
                                title_key=title_key,
                                title_params=title_params,
                                message_key=message_key,
                                message_params=message_params,
                                category=category,
                                tags=tags if tags else None
                            )
                            db.session.add(notification)
                            db.session.flush()  # Flush to trigger constraint check
                            successfully_created.append((user_id, notification_hash))
                        except IntegrityError as individual_error:
                            # This specific notification already exists (race condition)
                            db.session.rollback()
                            error_str_individual = str(individual_error.orig) if hasattr(individual_error, 'orig') else str(individual_error)
                            if 'uq_notification_user_hash' in error_str_individual:
                                continue
                            else:
                                # Different integrity error, re-raise
                                raise

                    if successfully_created:
                        try:
                            db.session.commit()

                            # Query back successfully created notifications for WebSocket broadcasting
                            try:
                                from app.utils.ws_manager import broadcast_notification, broadcast_unread_count
                                from app.services.notification.service import NotificationService

                                recent_cutoff = utcnow() - timedelta(seconds=5)
                                created_hashes = [nh for _, nh in successfully_created]
                                created_notifications = Notification.query.filter(
                                    and_(
                                        Notification.user_id.in_([uid for uid, _ in successfully_created]),
                                        Notification.notification_type == notification_type,
                                        Notification.created_at >= recent_cutoff,
                                        Notification.notification_hash.in_(created_hashes)
                                    )
                                ).all()

                                users_updated = set()
                                for notification in created_notifications:
                                    notification_data = {
                                        'id': notification.id,
                                        'title': notification.title,
                                        'message': notification.message,
                                        'notification_type': notification.notification_type.value if hasattr(notification.notification_type, 'value') else str(notification.notification_type),
                                        'is_read': notification.is_read,
                                        'created_at': notification.created_at.isoformat(),
                                        'priority': notification.priority,
                                        'icon': notification.icon,
                                        'related_url': notification.related_url,
                                        'group_id': getattr(notification, 'group_id', None),
                                        'viewed_at': notification.viewed_at.isoformat() if getattr(notification, 'viewed_at', None) else None,
                                        'category': getattr(notification, 'category', None),
                                        'tags': getattr(notification, 'tags', None)
                                    }

                                    try:
                                        broadcast_notification(notification.user_id, notification_data)
                                    except Exception as broadcast_error:
                                        current_app.logger.warning(f"Failed to broadcast notification {notification.id} via WebSocket: {broadcast_error}")

                                    if notification.user_id not in users_updated:
                                        try:
                                            unread_count = NotificationService.get_unread_count(notification.user_id)
                                            broadcast_unread_count(notification.user_id, unread_count)
                                        except Exception as count_error:
                                            current_app.logger.warning(f"Failed to broadcast unread count for user {notification.user_id}: {count_error}")
                                        users_updated.add(notification.user_id)
                            except Exception as e:
                                current_app.logger.warning(f"Failed to broadcast bulk notifications via WebSocket: {str(e)}")

                            # Return mock notification objects
                            return [{'user_id': user_id} for user_id, _ in successfully_created]
                        except Exception as commit_error:
                            db.session.rollback()
                            current_app.logger.error(f"Error committing retried notifications: {str(commit_error)}", exc_info=True)
                            raise
                    else:
                        # All notifications were duplicates due to race condition
                        return []
                else:
                    # Different integrity error, re-raise
                    current_app.logger.error(f"Error creating bulk notifications: {str(e)}", exc_info=True)
                    raise
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Error creating bulk notifications: {str(e)}", exc_info=True)
                raise

            # Send push notifications for bulk inserts (optional)
            if send_push_notifications:
                try:
                    from app.services.notification.push import PushNotificationService

                    # Send push notifications to all users who received notifications
                    user_ids_to_notify = list(set([uid for uid, _ in deduplicated_user_ids]))
                    if user_ids_to_notify:
                        PushNotificationService.send_bulk_push_notifications(
                            user_ids=user_ids_to_notify,
                            title=title,
                            body=message,
                            data={
                                'notification_type': notification_type.value if hasattr(notification_type, 'value') else str(notification_type),
                                'related_url': related_url,
                                'priority': priority
                            } if related_url else None,
                            priority=priority
                        )
                except Exception as e:
                    # Don't fail notification creation if push notifications fail
                    current_app.logger.warning(f"Failed to send push notifications: {str(e)}")

            # Send instant email notifications for bulk inserts (optional)
            if send_email_notifications:
                try:
                    from app.services.notification.emails import send_instant_notification_email

                    # Query back the created notifications to get IDs for email sending
                    # Use notification_hash for more reliable matching (avoids title encoding issues)
                    # Get notifications created in the last few seconds for these users
                    recent_cutoff = utcnow() - timedelta(seconds=5)
                    notification_hashes = [nh for _, nh in deduplicated_user_ids]
                    created_notifications_for_email = Notification.query.filter(
                        and_(
                            Notification.user_id.in_([uid for uid, _ in deduplicated_user_ids]),
                            Notification.notification_type == notification_type,
                            Notification.created_at >= recent_cutoff,
                            Notification.notification_hash.in_(notification_hashes)
                        )
                    ).all()

                    # Get users and preferences in batch
                    user_ids_list = [uid for uid, _ in deduplicated_user_ids]
                    users = User.query.filter(User.id.in_(user_ids_list)).all()
                    user_map = {u.id: u for u in users}

                    # Get preferences for all users in one query
                    preferences_list = NotificationPreferences.query.filter(
                        NotificationPreferences.user_id.in_(user_ids_list)
                    ).all()
                    preferences_map = {p.user_id: p for p in preferences_list}

                    for notification in created_notifications_for_email:
                        user = user_map.get(notification.user_id)
                        if not user or not user.email:
                            continue

                        preferences = preferences_map.get(user.id)

                        # Determine if email should be sent
                        should_send = False

                        if override_email_preferences:
                            # Admin override: send email regardless of user preferences
                            should_send = True
                            current_app.logger.debug(
                                f"[EMAIL_NOTIFICATION] Admin override enabled: sending email to {user.email} "
                                f"(notification_id={notification.id})"
                            )
                        elif preferences and preferences.email_notifications:
                            # Check user preferences
                            if preferences.notification_frequency == 'instant':
                                should_send = True
                            elif priority in ['high', 'urgent']:
                                # Override: send instant email for high-priority notifications
                                should_send = True

                            if should_send:
                                # Check if notification type is enabled
                                if preferences.notification_types_enabled and \
                                   notification.notification_type.value not in preferences.notification_types_enabled:
                                    should_send = False

                        if should_send:
                            try:
                                # Preferences already verified above; pass override_preferences=True
                                # to skip the redundant second preference check inside the function.
                                send_instant_notification_email(user, notification, override_preferences=True)
                                current_app.logger.debug(
                                    f"[EMAIL_NOTIFICATION] Instant email sent: to={user.email}, notification_id={notification.id}"
                                )
                            except Exception as e:
                                current_app.logger.warning(
                                    f"[EMAIL_NOTIFICATION] Failed to send instant email for notification {notification.id}: {e}"
                                )
                except Exception as e:
                    current_app.logger.warning(f"[EMAIL_NOTIFICATION] Error sending instant notification emails for bulk insert: {e}")

            # Return mock notification objects (can't return actual objects with bulk_insert_mappings)
            return [{'user_id': user_id} for user_id, _ in deduplicated_user_ids]
        else:
            # Regular insert for few notifications (allows returning actual objects)
            notifications = []
            for user_id, notification_hash in deduplicated_user_ids:
                user_email = user_email_map.get(user_id, 'Unknown')
                notification = Notification(
                    user_id=user_id,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    notification_type=notification_type,
                    title=title,
                    message=message,
                    related_object_type=related_object_type,
                    related_object_id=related_object_id,
                    related_url=related_url,
                    priority=priority,
                    icon=icon,
                    notification_hash=notification_hash,
                    expires_at=expires_at,
                    group_id=group_ids.get(user_id),  # Phase 2: Add group_id
                    action_buttons=action_buttons,  # Phase 3: Action buttons
                    # Phase 4: Internationalization
                    title_key=title_key,
                    title_params=title_params,
                    message_key=message_key,
                    message_params=message_params,
                    # Phase 4: User Experience Enhancements
                    category=category,
                    tags=tags if tags else None
                )
                notifications.append(notification)
                db.session.add(notification)

            try:
                db.session.flush()  # Flush to get IDs

                # Log notification IDs and user assignments
                notification_details = [
                    (n.id, n.user_id, user_email_map.get(n.user_id, 'Unknown'))
                    for n in notifications
                ]
                db.session.commit()
            except IntegrityError as e:
                db.session.rollback()
                # Check if this is the unique constraint violation for notification_hash
                error_str = str(e.orig) if hasattr(e, 'orig') else str(e)
                if 'uq_notification_user_hash' in error_str or 'duplicate key value violates unique constraint' in error_str:
                    # Race condition: another process inserted the same notification
                    # Remove the conflicting notifications and retry with only the ones that don't conflict
                    # Check which notifications already exist
                    notification_hashes_to_check = [nh for _, nh in deduplicated_user_ids]
                    existing_notifications = Notification.query.filter(
                        and_(
                            Notification.user_id.in_([uid for uid, _ in deduplicated_user_ids]),
                            Notification.notification_hash.in_(notification_hashes_to_check)
                        )
                    ).all()

                    # Build a set of existing (user_id, notification_hash) pairs
                    existing_pairs = {(n.user_id, n.notification_hash) for n in existing_notifications}

                    # Filter out user_id/hash pairs that already exist and create new notification objects
                    filtered_notifications = []
                    for user_id, notification_hash in deduplicated_user_ids:
                        if (user_id, notification_hash) not in existing_pairs:
                            # Create new notification object for retry
                            user_email = user_email_map.get(user_id, 'Unknown')
                            notification = Notification(
                                user_id=user_id,
                                entity_type=entity_type,
                                entity_id=entity_id,
                                notification_type=notification_type,
                                title=title,
                                message=message,
                                related_object_type=related_object_type,
                                related_object_id=related_object_id,
                                related_url=related_url,
                                priority=priority,
                                icon=icon,
                                notification_hash=notification_hash,
                                expires_at=expires_at,
                                group_id=group_ids.get(user_id),
                                action_buttons=action_buttons,
                                title_key=title_key,
                                title_params=title_params,
                                message_key=message_key,
                                message_params=message_params,
                                category=category,
                                tags=tags if tags else None
                            )
                            filtered_notifications.append(notification)
                        else:
                            pass

                    if filtered_notifications:
                        # Retry with only the non-conflicting notifications
                        notifications = filtered_notifications
                        db.session.add_all(notifications)
                        try:
                            db.session.flush()
                            notification_details = [
                                (n.id, n.user_id, user_email_map.get(n.user_id, 'Unknown'))
                                for n in notifications
                            ]
                            db.session.commit()
                        except IntegrityError as retry_error:
                            # Still have conflicts, log and continue with what we have
                            db.session.rollback()
                            error_str_retry = str(retry_error.orig) if hasattr(retry_error, 'orig') else str(retry_error)
                            if 'uq_notification_user_hash' in error_str_retry:
                                # Return empty list or partial results - at this point it's better to fail gracefully
                                return []
                            else:
                                raise
                    else:
                        # All notifications were duplicates
                        return []
                else:
                    # Different integrity error, re-raise
                    current_app.logger.error(f"Error creating notifications: {str(e)}", exc_info=True)
                    raise
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Error creating notifications: {str(e)}", exc_info=True)
                raise

            # Phase 2: Broadcast notifications via WebSocket
            try:
                from app.utils.ws_manager import broadcast_notification, broadcast_unread_count
                from app.services.notification.service import NotificationService

                # Track users we've already sent unread count updates to
                users_updated = set()

                for notification in notifications:
                    # Format notification for WebSocket
                    notification_data = {
                        'id': notification.id,
                        'title': notification.title,
                        'message': notification.message,
                        'notification_type': notification.notification_type.value if hasattr(notification.notification_type, 'value') else str(notification.notification_type),
                        'is_read': notification.is_read,
                        'created_at': notification.created_at.isoformat(),
                        'priority': notification.priority,
                        'icon': notification.icon,
                        'related_url': notification.related_url,
                        'group_id': getattr(notification, 'group_id', None),
                        'viewed_at': notification.viewed_at.isoformat() if getattr(notification, 'viewed_at', None) else None,
                        'category': getattr(notification, 'category', None),
                        'tags': getattr(notification, 'tags', None)
                    }

                    # Broadcast to user
                    broadcast_notification(notification.user_id, notification_data)

                    # Update unread count (only once per user)
                    if notification.user_id not in users_updated:
                        unread_count = NotificationService.get_unread_count(notification.user_id)
                        broadcast_unread_count(notification.user_id, unread_count)
                        users_updated.add(notification.user_id)
            except Exception as e:
                # Don't fail notification creation if WebSocket fails
                current_app.logger.warning(f"Failed to broadcast notification via WebSocket: {str(e)}")

            # Send push notifications for regular inserts (optional)
            if send_push_notifications:
                try:
                    from app.services.notification.push import PushNotificationService

                    # Send push notifications to all users who received notifications
                    user_ids_to_notify = list(set([n.user_id for n in notifications]))
                    if user_ids_to_notify:
                        current_app.logger.debug(
                            f"[PUSH_NOTIFICATION] Attempting to send push notifications: users={len(user_ids_to_notify)}"
                        )

                        push_result = PushNotificationService.send_bulk_push_notifications(
                            user_ids=user_ids_to_notify,
                            title=title,
                            body=message,
                            data={
                                'notification_type': notification_type.value if hasattr(notification_type, 'value') else str(notification_type),
                                'related_url': related_url,
                                'priority': priority
                            } if related_url else None,
                            priority=priority
                        )

                        if push_result:
                            total_devices = push_result.get('total_devices', 0)
                            total_failure = push_result.get('total_failure', 0)
                            # INFO only when something actually happened (devices>0) or there were failures.
                            if total_devices or total_failure:
                                current_app.logger.info(
                                    f"[PUSH_NOTIFICATION] Push result: success={push_result.get('success')}, "
                                    f"users={push_result.get('total_users')}, devices={total_devices}, "
                                    f"sent={push_result.get('total_success')}, failed={total_failure}"
                                )
                            else:
                                current_app.logger.debug(
                                    f"[PUSH_NOTIFICATION] Push result: users={push_result.get('total_users')}, devices=0"
                                )
                        else:
                            current_app.logger.warning(
                                f"[PUSH_NOTIFICATION] Push notification service returned no result"
                            )
                    else:
                        current_app.logger.debug(
                            f"[PUSH_NOTIFICATION] No users to send push notifications to"
                        )
                except Exception as e:
                    # Don't fail notification creation if push notifications fail
                    current_app.logger.warning(
                        f"[PUSH_NOTIFICATION] Failed to send push notifications: {str(e)}",
                        exc_info=True
                    )

            # Send instant email notifications for regular inserts (optional)
            if send_email_notifications:
                try:
                    from app.services.notification.emails import send_instant_notification_email

                    for notification in notifications:
                        user = User.query.get(notification.user_id)
                        if not user or not user.email:
                            continue

                        # Get user preferences
                        preferences = NotificationPreferences.query.filter_by(
                            user_id=user.id
                        ).first()

                        # Determine if email should be sent
                        should_send = False

                        if override_email_preferences:
                            # Admin override: send email regardless of user preferences
                            should_send = True
                            current_app.logger.debug(
                                f"[EMAIL_NOTIFICATION] Admin override enabled: sending email to {user.email} "
                                f"(notification_id={notification.id})"
                            )
                        elif preferences and preferences.email_notifications:
                            # Check user preferences
                            if preferences.notification_frequency == 'instant':
                                should_send = True
                            elif priority in ['high', 'urgent']:
                                # Override: send instant email for high-priority notifications
                                should_send = True

                            if should_send:
                                # Check if notification type is enabled
                                if preferences.notification_types_enabled and \
                                   notification.notification_type.value not in preferences.notification_types_enabled:
                                    should_send = False

                        if should_send:
                            try:
                                # Preferences already verified above; pass override_preferences=True
                                # to skip the redundant second preference check inside the function.
                                send_instant_notification_email(user, notification, override_preferences=True)
                                current_app.logger.debug(
                                    f"[EMAIL_NOTIFICATION] Instant email sent: to={user.email}, notification_id={notification.id}"
                                )
                            except Exception as e:
                                current_app.logger.warning(
                                    f"[EMAIL_NOTIFICATION] Failed to send instant email for notification {notification.id}: {e}"
                                )
                except Exception as e:
                    current_app.logger.warning(f"[EMAIL_NOTIFICATION] Error sending instant notification emails: {e}")

            return notifications

    except IntegrityError as e:
        db.session.rollback()
        if _retry_on_conflict and retry_context:
            current_app.logger.warning(
                "Notification creation encountered a race condition; retrying once after refreshing duplicates."
            )
            return create_notification(
                **retry_context,
                _retry_on_conflict=False
            )
        current_app.logger.error(
            f"Integrity error while creating notifications: {e}", exc_info=True
        )
        return []
    except Exception as e:
        current_app.logger.error(f"Error creating notification: {str(e)}", exc_info=True)
        db.session.rollback()
        return None


def log_entity_activity(
    entity_type,
    entity_id,
    activity_type,
    activity_description,
    *,
    summary_key,
    summary_params=None,
    related_object_type=None,
    related_object_id=None,
    assignment_id=None,
    related_url=None,
    activity_category='general',
    icon=None,
    user_id=None
):
    """
    Log an entity-specific activity that other focal points can see.

    Args:
        entity_type (str): Entity type ('country', 'ns_branch', 'ns_subbranch', etc.)
        entity_id (int): Entity ID where activity occurred
        activity_type (str): Type of activity ('form_submit', 'document_upload', etc.)
        activity_description (str): Detailed description of activity
        summary_key (str): I18n message key for localized summary
        summary_params (dict): Parameters for summary message formatting
        related_object_type (str): Type of related object
        related_object_id (int): ID of related object
        assignment_id (int): ID of the assignment being modified (optional)
        related_url (str): Direct URL to view related object
        activity_category (str): Category for styling ('form', 'document', 'admin', 'system')
        icon (str): FontAwesome icon class
        user_id (int): User ID (defaults to current user)
    """
    try:
        from app.services.entity_service import EntityService

        if not user_id and current_user.is_authenticated:
            user_id = current_user.id

        if not user_id:
            current_app.logger.warning("Cannot log entity activity without user ID")
            return None

        # Derive country_id from entity (for database schema compatibility)
        country_id = None
        if entity_type == 'country':
            country_id = entity_id
        else:
            country = EntityService.get_country_for_entity(entity_type, entity_id)
            country_id = country.id if country else None

        # Default icon based on activity category
        if not icon:
            icon = get_default_icon_for_activity_category(activity_category)

        activity_log = EntityActivityLog(
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            country_id=country_id,
            activity_type=activity_type,
            activity_description=activity_description,
            summary_key=summary_key,
            summary_params=summary_params or {},
            related_object_type=related_object_type,
            related_object_id=related_object_id,
            assignment_id=assignment_id,
            related_url=related_url,
            activity_category=activity_category,
            icon=icon
        )

        try:
            db.session.add(activity_log)
            db.session.commit()
            return activity_log
        except Exception as commit_error:
            current_app.logger.error(f"Error committing entity activity log: {str(commit_error)}", exc_info=True)
            db.session.rollback()
            return None

    except Exception as e:
        current_app.logger.error(f"Error logging entity activity: {str(e)}", exc_info=True)
        current_app.logger.error(f"Activity details: type={activity_type}, entity_type={entity_type}, entity_id={entity_id}, user_id={user_id}")
        db.session.rollback()
        return None




def cleanup_old_notifications(days: int = 90) -> Dict[str, int]:
    """
    Delete archived notifications older than specified days.
    Also deletes expired notifications (regardless of archived status).

    Args:
        days (int): Number of days to keep archived notifications

    Returns:
        dict: Statistics about cleanup (archived_deleted, expired_deleted, total_deleted)
    """
    try:
        now = utcnow()
        cutoff = now - timedelta(days=days)

        # Delete dependent email_delivery_log rows first (FK: notification.id)
        expired_notif_ids = db.session.query(Notification.id).filter(
            Notification.expires_at.isnot(None),
            Notification.expires_at < now,
        )
        EmailDeliveryLog.query.filter(
            EmailDeliveryLog.notification_id.in_(expired_notif_ids)
        ).delete(synchronize_session=False)

        # Delete expired notifications (regardless of archived status)
        expired_deleted = Notification.query.filter(
            Notification.expires_at.isnot(None),
            Notification.expires_at < now
        ).delete(synchronize_session=False)

        archived_notif_ids = db.session.query(Notification.id).filter(
            Notification.is_archived == True,
            Notification.archived_at < cutoff,
        )
        EmailDeliveryLog.query.filter(
            EmailDeliveryLog.notification_id.in_(archived_notif_ids)
        ).delete(synchronize_session=False)

        # Delete archived notifications older than cutoff
        archived_deleted = Notification.query.filter(
            Notification.is_archived == True,
            Notification.archived_at < cutoff
        ).delete(synchronize_session=False)

        try:
            db.session.commit()
        except Exception as commit_error:
            current_app.logger.error(f"Error committing notification cleanup: {str(commit_error)}", exc_info=True)
            db.session.rollback()
            return {
                'archived_deleted': 0,
                'expired_deleted': 0,
                'total_deleted': 0
            }

        total_deleted = expired_deleted + archived_deleted

        if total_deleted > 0:
            current_app.logger.info(
                f"Cleaned up {total_deleted} old notifications "
                f"({expired_deleted} expired, {archived_deleted} archived)"
            )

        return {
            'archived_deleted': archived_deleted,
            'expired_deleted': expired_deleted,
            'total_deleted': total_deleted
        }
    except Exception as e:
        current_app.logger.error(f"Error cleaning up notifications: {str(e)}", exc_info=True)
        db.session.rollback()
        return {
            'archived_deleted': 0,
            'expired_deleted': 0,
            'total_deleted': 0
        }


def get_country_recent_activities(country_id, days=7, limit=50):
    """
    Get recent activities for a country with enhanced audit trail information.

    Args:
        country_id (int): Country ID
        days (int): Number of days to look back
        limit (int): Maximum number of activities to return

    Returns:
        List of enhanced activity objects with audit trail information
    """
    since_date = utcnow() - timedelta(days=days)

    # Get country activities - this is the main source of activities
    # Use entity-based query for consistency
    country_activities = EntityActivityLog.query.filter(
        and_(
            EntityActivityLog.entity_type == 'country',
            EntityActivityLog.entity_id == country_id,
            EntityActivityLog.timestamp >= since_date
        )
    ).order_by(desc(EntityActivityLog.timestamp)).limit(limit).all()

    current_app.logger.debug(f"Found {len(country_activities)} country activities for country {country_id}")

    # Enhanced activity objects with audit trail information
    enhanced_activities = []

    # Process country activities
    for activity in country_activities:
        enhanced_activity = enhance_activity_with_audit_data(activity, [], [])  # Simplified for now
        enhanced_activities.append(enhanced_activity)

    # Sort all activities by timestamp and limit
    enhanced_activities.sort(key=lambda x: x.timestamp, reverse=True)
    return enhanced_activities[:limit]


def enhance_activity_with_audit_data(activity, user_activities, admin_activities):
    """
    Enhance an EntityActivityLog with additional audit trail information.
    """
    # Find matching audit entries within a small time window (5 minutes)
    time_window = timedelta(minutes=5)

    # Look for matching user activities
    matching_user_activities = [
        ua for ua in user_activities
        if (ua.user_id == activity.user_id and
            abs((ua.timestamp - activity.timestamp).total_seconds()) <= time_window.total_seconds())
    ]

    # Look for matching admin activities
    matching_admin_activities = [
        aa for aa in admin_activities
        if (aa.admin_user_id == activity.user_id and
            abs((aa.timestamp - activity.timestamp).total_seconds()) <= time_window.total_seconds())
    ]

    # Create enhanced activity object
    enhanced_activity = ActivityWithAuditData(activity)

    # Add audit trail information
    if matching_user_activities:
        enhanced_activity.add_user_audit_data(matching_user_activities[0])

    if matching_admin_activities:
        enhanced_activity.add_admin_audit_data(matching_admin_activities[0])

    return enhanced_activity


def create_activity_from_audit_log(audit_log, audit_type, country_id):
    """
    Create an activity from audit log data when no country activity exists.
    """
    # Skip if this is not a relevant activity
    if audit_type == 'user_activity':
        if audit_log.activity_type in ['page_view', 'login', 'logout']:
            return None  # Skip these low-value activities

    # Create activity-like object from audit data
    activity = ActivityFromAuditLog(audit_log, audit_type, country_id)
    return activity


class ActivityWithAuditData:
    """
    Wrapper class that enhances EntityActivityLog with audit trail data.
    """
    def __init__(self, country_activity):
        # Copy all attributes from the original activity
        for attr in dir(country_activity):
            if not attr.startswith('_'):
                setattr(self, attr, getattr(country_activity, attr))

        self._original_activity = country_activity
        self._user_audit_data = None
        self._admin_audit_data = None

    def add_user_audit_data(self, user_activity):
        """Add user audit data to enhance the activity."""
        self._user_audit_data = user_activity

        # Enhance context_data with audit information
        if not self.context_data:
            self.context_data = {}
        elif isinstance(self.context_data, str):
            try:
                self.context_data = json.loads(self.context_data)
            except json.JSONDecodeError:
                self.context_data = {}

        # Add detailed audit information
        self.context_data.update({
            'audit_endpoint': user_activity.endpoint,
            'audit_method': user_activity.http_method,
            'audit_response_time': user_activity.response_time_ms,
            'audit_status_code': user_activity.response_status_code,
            'audit_user_agent': user_activity.user_agent,
            'audit_ip_address': user_activity.ip_address
        })

        # Do not mutate summary text; rely on i18n summary_key

    def add_admin_audit_data(self, admin_activity):
        """Add admin audit data to enhance the activity."""
        self._admin_audit_data = admin_activity

        # Enhance context_data with admin audit information
        if not self.context_data:
            self.context_data = {}
        elif isinstance(self.context_data, str):
            try:
                self.context_data = json.loads(self.context_data)
            except json.JSONDecodeError:
                self.context_data = {}

        # Add detailed admin audit information
        self.context_data.update({
            'admin_action_type': admin_activity.action_type,
            'admin_risk_level': admin_activity.risk_level,
            'admin_target_type': admin_activity.target_type,
            'admin_target_id': admin_activity.target_id,
            'admin_old_values': admin_activity.old_values,
            'admin_new_values': admin_activity.new_values,
            'audit_requires_review': admin_activity.requires_review
        })

        # Do not mutate summary text; rely on i18n summary_key


class ActivityFromAuditLog:
    """
    Create an activity-like object from audit log data.
    """
    def __init__(self, audit_log, audit_type, country_id):
        from app.models import Country

        self.id = f"{audit_type}_{audit_log.id}"
        self.user_id = audit_log.user_id if audit_type == 'user_activity' else audit_log.admin_user_id
        self.user = audit_log.user if audit_type == 'user_activity' else audit_log.admin_user
        self.country_id = country_id
        self.country = Country.query.get(country_id)
        self.timestamp = audit_log.timestamp

        # Create activity details based on audit type
        if audit_type == 'user_activity':
            self.activity_type = audit_log.activity_type
            self.activity_description = audit_log.activity_description or f"User {audit_log.activity_type}"
            self.summary_key = 'activity.audit_user_activity'
            self.summary_params = {'action': audit_log.activity_type.replace('_', ' ')}
            self.activity_category = self._get_activity_category_from_user_activity(audit_log)
            self.icon = self._get_icon_for_user_activity(audit_log)
        else:  # admin_action
            self.activity_type = audit_log.action_type
            self.activity_description = audit_log.action_description or f"Admin {audit_log.action_type}"
            self.summary_key = 'activity.audit_admin_action'
            self.summary_params = {'action': audit_log.action_type.replace('_', ' '), 'target': audit_log.target_type or 'item'}
            self.activity_category = 'admin'
            self.icon = 'fas fa-user-shield'

        # Set related object information
        self.related_object_type = audit_log.target_type if audit_type == 'admin_action' else None
        self.related_object_id = audit_log.target_id if audit_type == 'admin_action' else None
        self.related_url = None

        # Set context data
        self.context_data = {
            'audit_source': audit_type,
            'audit_endpoint': getattr(audit_log, 'endpoint', None),
            'audit_method': getattr(audit_log, 'http_method', None),
            'audit_ip_address': audit_log.ip_address,
        }

        if audit_type == 'admin_action':
            self.context_data.update({
                'admin_risk_level': audit_log.risk_level,
                'admin_requires_review': audit_log.requires_review,
                'admin_old_values': audit_log.old_values,
                'admin_new_values': audit_log.new_values
            })


    def _get_activity_category_from_user_activity(self, audit_log):
        """Determine activity category from user activity."""
        if audit_log.activity_type in ['form_submit', 'form_save']:
            return 'form'
        elif audit_log.activity_type == 'file_upload':
            return 'document'
        else:
            return 'general'

    def _get_icon_for_user_activity(self, audit_log):
        """Get appropriate icon for user activity."""
        icon_map = {
            'form_submit': 'fas fa-paper-plane',
            'form_save': 'fas fa-save',
            'file_upload': 'fas fa-upload',
            'data_export': 'fas fa-download',
            'page_view': 'fas fa-eye'
        }
        return icon_map.get(audit_log.activity_type, 'fas fa-user')

    # Add time_ago property
    @property
    def time_ago(self):
        """Calculate time ago string."""
        time_diff = utcnow() - self.timestamp
        if time_diff.days > 0:
            return f"{time_diff.days} day{'s' if time_diff.days != 1 else ''} ago"
        elif time_diff.seconds > 3600:
            hours = time_diff.seconds // 3600
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif time_diff.seconds > 60:
            minutes = time_diff.seconds // 60
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        else:
            return "Just now"

    # Add category styling properties
    @property
    def category_bg_class(self):
        """Get background class for activity category."""
        class_map = {
            'form': 'bg-blue-50',
            'document': 'bg-green-50',
            'admin': 'bg-purple-50',
            'general': 'bg-gray-50'
        }
        return class_map.get(self.activity_category, 'bg-gray-50')

    @property
    def category_class(self):
        """Get text color class for activity category."""
        class_map = {
            'form': 'text-blue-600',
            'document': 'text-green-600',
            'admin': 'text-purple-600',
            'general': 'text-gray-600'
        }
        return class_map.get(self.activity_category, 'text-gray-600')


def notify_entity_focal_points(
    entity_type,
    entity_id,
    notification_type,
    title_key: str,
    message_key: str,
    exclude_user_id=None,
    exclude_user_ids=None,
    title_params=None,
    message_params=None,
    **kwargs
):
    """
    Send notifications to all focal points of a specific entity (country, NS branch, etc.).

    Args:
        entity_type (str): Entity type ('country', 'ns_branch', 'ns_subbranch', etc.)
        entity_id (int): Entity ID
        notification_type (NotificationType): Type of notification
        title_key (str, required): Translation key for title
        title_params (dict, optional): Parameters for title translation
        message_key (str, required): Translation key for message
        message_params (dict, optional): Parameters for message translation
        exclude_user_id (int): User ID to exclude from notifications
        exclude_user_ids (iterable): User IDs to exclude (e.g. admins who get a separate notification)
        **kwargs: Additional arguments passed to create_notification

    Returns:
        list: Created notification objects
    """
    try:
        from app.models.core import UserEntityPermission
        from app.services.entity_service import EntityService

        exclude_set = set()
        if exclude_user_id is not None:
            exclude_set.add(exclude_user_id)
        if exclude_user_ids:
            exclude_set.update(exclude_user_ids)

        # Get all focal points for this entity via UserEntityPermission (RBAC-only)
        from app.models.rbac import RbacUserRole, RbacRole
        permissions = UserEntityPermission.query.filter_by(
            entity_type=entity_type,
            entity_id=entity_id
        ).join(User, UserEntityPermission.user_id == User.id).join(
            RbacUserRole, RbacUserRole.user_id == User.id
        ).join(
            RbacRole, RbacUserRole.role_id == RbacRole.id
        ).filter(
            RbacRole.code == "assignment_editor_submitter"
        ).all()

        # Get user IDs, excluding the specified users if provided
        focal_point_ids = [
            perm.user_id for perm in permissions
            if perm.user_id not in exclude_set
        ]

        if not focal_point_ids:
            return []

        return create_notification(
            user_ids=focal_point_ids,
            notification_type=notification_type,
            title_key=title_key,
            title_params=title_params,
            message_key=message_key,
            message_params=message_params,
            entity_type=entity_type,
            entity_id=entity_id,
            **kwargs
        )

    except Exception as e:
        current_app.logger.error(
            f"Error notifying {entity_type} {entity_id} focal points: {str(e)}",
            exc_info=True
        )
        return []


def get_default_icon_for_notification_type(notification_type):
    """Get default FontAwesome icon for notification type."""
    icon_map = {
        NotificationType.assignment_created: 'fas fa-plus-circle',
        NotificationType.assignment_submitted: 'fas fa-paper-plane',
        NotificationType.assignment_approved: 'fas fa-check-circle',
        NotificationType.assignment_reopened: 'fas fa-undo',
        NotificationType.public_submission_received: 'fas fa-inbox',
        NotificationType.form_updated: 'fas fa-pen',
        NotificationType.document_uploaded: 'fas fa-file-upload',
        NotificationType.user_added_to_country: 'fas fa-user-plus',
        NotificationType.template_updated: 'fas fa-file-alt',
        NotificationType.self_report_created: 'fas fa-clipboard-list',
        NotificationType.deadline_reminder: 'fas fa-clock',
        NotificationType.access_request_received: 'fas fa-user-plus'
    }
    return icon_map.get(notification_type, 'fas fa-bell')


def get_default_icon_for_activity_category(activity_category):
    """Get default FontAwesome icon for activity category."""
    icon_map = {
        'form': 'fas fa-pen',
        'document': 'fas fa-file-upload',
        'admin': 'fas fa-cog',
        'system': 'fas fa-server',
        'general': 'fas fa-activity'
    }
    return icon_map.get(activity_category, 'fas fa-activity')


# Convenience functions for common notification scenarios

def notify_assignment_created(assignment_entity_status):
    """Notify focal points when a new assignment is created for any entity type."""
    aes = assignment_entity_status
    entity_type = aes.entity_type
    entity_id = aes.entity_id

    from app.services.entity_service import EntityService
    from app.models.forms import FormTemplate

    # Get template directly via template_id to avoid stale relationship data
    assigned_form = aes.assigned_form
    template = FormTemplate.query.get(assigned_form.template_id) if assigned_form and assigned_form.template_id else None
    template_name = template.name if template else "Unknown Template"

    # Debug: Log template lookup to help diagnose any issues
    if assigned_form and template:
        current_app.logger.debug(
            f"[NOTIFY_ASSIGNMENT_CREATED] Template lookup for AES {aes.id}: "
            f"AssignedForm {assigned_form.id}, template_id={assigned_form.template_id}, "
            f"template_name='{template_name}'"
        )

    # Log activity for the entity
    log_entity_activity(
        entity_type=entity_type,
        entity_id=entity_id,
        activity_type='assignment_created',
        activity_description=f"New assignment '{template_name}' for period '{assigned_form.period_name}' was created",
        summary_key='activity.assignment_created',
        summary_params={'template': template_name},
        related_object_type='assignment',
        related_object_id=aes.id,
        assignment_id=aes.id,
        related_url=url_for('forms.view_edit_form', form_type='assignment', form_id=aes.id),
        activity_category='admin',
        icon=None,
        user_id=None
    )

    # Create notifications for focal points using translation keys
    # Use assigned_form_id instead of AES ID for related_object_id to ensure proper deduplication
    # across multiple entities in the same assignment
    due_date_str = aes.due_date.strftime('%Y-%m-%d') if aes.due_date else _('No deadline set')

    notifications = notify_entity_focal_points(
        entity_type=entity_type,
        entity_id=entity_id,
        notification_type=NotificationType.assignment_created,
        title_key='notification.assignment_created.title',
        title_params=None,
        message_key='notification.assignment_created.message',
        message_params={
            'template': template_name,
            'period': assigned_form.period_name,
            'due_date': due_date_str,
            '_entity_type': entity_type,  # Store entity info for label (prefixed with _ to avoid translation)
            '_entity_id': entity_id
        },
        related_object_type='assignment',
        related_object_id=aes.assigned_form_id,
        related_url=url_for('forms.view_edit_form', form_type='assignment', form_id=aes.id),
        priority='normal'
    )

    return notifications


def notify_assignment_submitted(assignment_entity_status):
    """Notify focal points and admins when an assignment is submitted for any entity type."""
    aes = assignment_entity_status
    entity_type = aes.entity_type
    entity_id = aes.entity_id

    from app.services.entity_service import EntityService
    from app.models.forms import FormTemplate

    # Get template directly via template_id to avoid stale relationship data
    assigned_form = aes.assigned_form
    template = FormTemplate.query.get(assigned_form.template_id) if assigned_form and assigned_form.template_id else None
    template_name = template.name if template else "Unknown Template"

    # Log activity for the entity
    log_entity_activity(
        entity_type=entity_type,
        entity_id=entity_id,
        activity_type='assignment_submitted',
        activity_description=f"Assignment '{template_name}' for period '{assigned_form.period_name}' was submitted",
        summary_key='activity.assignment_submitted',
        summary_params={'template': template_name},
        related_object_type='assignment',
        related_object_id=aes.id,
        assignment_id=aes.id,
        related_url=url_for('forms.view_edit_form', form_type='assignment', form_id=aes.id),
        activity_category='form',
        icon=None,
        user_id=None
    )

    # Identify admin users first so we can exclude them from focal-point notifications.
    # Users who are both admin and focal point get only the admin notification (avoids duplicate emails).
    from app.models.rbac import RbacUserRole, RbacRole

    admin_role_ids = select(RbacRole.id).where(
        or_(
            RbacRole.code == "system_manager",
            RbacRole.code == "admin_core",
            RbacRole.code.like("admin\\_%", escape="\\"),
        )
    )

    admin_users = (
        User.query.join(RbacUserRole, User.id == RbacUserRole.user_id)
        .filter(RbacUserRole.role_id.in_(admin_role_ids))
        .distinct()
        .all()
    )
    admin_user_ids = [u.id for u in admin_users]

    # Notify other focal points in the same entity (exclude submitter and admins)
    notifications = notify_entity_focal_points(
        entity_type=entity_type,
        entity_id=entity_id,
        notification_type=NotificationType.assignment_submitted,
        title_key='notification.assignment_submitted.title',
        title_params={'template': template_name, 'period': assigned_form.period_name},
        message_key='notification.assignment_submitted.message',
        message_params={
            'template': template_name,
            'period': assigned_form.period_name,
            '_entity_type': entity_type,
            '_entity_id': entity_id
        },
        related_object_type='assignment',
        related_object_id=aes.id,
        related_url=url_for('forms.view_edit_form', form_type='assignment', form_id=aes.id),
        priority='normal',
        exclude_user_id=current_user.id if current_user.is_authenticated else None,
        exclude_user_ids=admin_user_ids
    )

    # Get entity name for the notification message
    from app.services.entity_service import EntityService
    entity_name = EntityService.get_localized_entity_name(entity_type, entity_id, include_hierarchy=True)
    if not entity_name or entity_name.startswith('Unknown'):
        # Fallback to entity type if name not found
        entity_name = entity_type.replace('_', ' ').title()

    submitter_name = current_user.name if (current_user and current_user.is_authenticated) else "A focal point"

    admin_notifications = create_notification(
        user_ids=admin_user_ids,
        notification_type=NotificationType.assignment_submitted,
        title_key='notification.assignment_submitted.admin.title',
        title_params={
            'submitter_name': submitter_name,
            'period': assigned_form.period_name,
        },
        message_key='notification.assignment_submitted.admin.message',
        message_params={
            'template': template_name,
            'country': entity_name,
            'period': assigned_form.period_name,
            'submitter_name': submitter_name,
            '_entity_type': entity_type,
            '_entity_id': entity_id
        },
        entity_type=entity_type,
        entity_id=entity_id,
        related_object_type='assignment',
        related_object_id=aes.id,
        related_url=url_for('forms.view_edit_form', form_type='assignment', form_id=aes.id),
        priority='high',
        override_email_preferences=True  # Always email admins for action-required review
    )

    return notifications + (admin_notifications or [])


def notify_document_uploaded(assignment_entity_status, document_name):
    """Notify focal points when a document is uploaded for any entity type.

    Note: Activity logging for document uploads is handled by the field_changes
    mechanism in forms.py (via form_data_updated activity entries), so we only
    send focal-point notifications here to avoid duplicate activity entries.
    """
    aes = assignment_entity_status
    entity_type = aes.entity_type
    entity_id = aes.entity_id

    # Notify other focal points using translation keys
    return notify_entity_focal_points(
        entity_type=entity_type,
        entity_id=entity_id,
        notification_type=NotificationType.document_uploaded,
        title_key='notification.document_uploaded.title',
        title_params=None,
        message_key='notification.document_uploaded.message',
        message_params={
            'document': document_name,
            'document_type': _('Document'),
            '_entity_type': entity_type,
            '_entity_id': entity_id
        },
        related_object_type='assignment',
        related_object_id=aes.id,
        related_url=url_for('forms.view_edit_form', form_type='assignment', form_id=aes.id),
        priority='normal',
        exclude_user_id=current_user.id if current_user.is_authenticated else None
    )


def notify_assignment_approved(assignment_entity_status):
    """Notify focal points when an assignment is approved for any entity type."""
    aes = assignment_entity_status
    entity_type = aes.entity_type
    entity_id = aes.entity_id

    from app.services.entity_service import EntityService
    from app.models.forms import FormTemplate

    # Get template directly via template_id to avoid stale relationship data
    assigned_form = aes.assigned_form
    template = FormTemplate.query.get(assigned_form.template_id) if assigned_form and assigned_form.template_id else None
    template_name = template.name if template else "Unknown Template"

    # Log activity for the entity
    log_entity_activity(
        entity_type=entity_type,
        entity_id=entity_id,
        activity_type='assignment_approved',
        activity_description=f"Assignment '{template_name}' for period '{assigned_form.period_name}' was approved",
        summary_key='activity.assignment_approved',
        summary_params={'template': template_name},
        related_object_type='assignment',
        related_object_id=aes.id,
        assignment_id=aes.id,
        related_url=url_for('forms.view_edit_form', form_type='assignment', form_id=aes.id),
        activity_category='admin',
        icon=None,
        user_id=None
    )

    # Create notifications for focal points using translation keys
    return notify_entity_focal_points(
        entity_type=entity_type,
        entity_id=entity_id,
        notification_type=NotificationType.assignment_approved,
        title_key='notification.assignment_approved.title',
        title_params=None,
        message_key='notification.assignment_approved.message',
        message_params={
            'template': template_name,
            '_entity_type': entity_type,
            '_entity_id': entity_id
        },
        related_object_type='assignment',
        related_object_id=aes.id,
        related_url=url_for('forms.view_edit_form', form_type='assignment', form_id=aes.id),
        priority='normal'
    )


def notify_assignment_reopened(assignment_entity_status):
    """Notify focal points when an assignment is reopened for any entity type."""
    aes = assignment_entity_status
    entity_type = aes.entity_type
    entity_id = aes.entity_id

    from app.services.entity_service import EntityService
    from app.models.forms import FormTemplate

    # Get template directly via template_id to avoid stale relationship data
    assigned_form = aes.assigned_form
    template = FormTemplate.query.get(assigned_form.template_id) if assigned_form and assigned_form.template_id else None
    template_name = template.name if template else "Unknown Template"

    # Log activity for the entity
    log_entity_activity(
        entity_type=entity_type,
        entity_id=entity_id,
        activity_type='assignment_reopened',
        activity_description=f"Assignment '{template_name}' for period '{assigned_form.period_name}' was reopened",
        summary_key='activity.assignment_reopened',
        summary_params={'template': template_name},
        related_object_type='assignment',
        related_object_id=aes.id,
        assignment_id=aes.id,
        related_url=url_for('forms.view_edit_form', form_type='assignment', form_id=aes.id),
        activity_category='admin',
        icon=None,
        user_id=None
    )

    # Create notifications for focal points using translation keys
    notifications = notify_entity_focal_points(
        entity_type=entity_type,
        entity_id=entity_id,
        notification_type=NotificationType.assignment_reopened,
        title_key='notification.assignment_reopened.title',
        title_params=None,
        message_key='notification.assignment_reopened.message',
        message_params={
            'template': template_name,
            '_entity_type': entity_type,
            '_entity_id': entity_id
        },
        related_object_type='assignment',
        related_object_id=aes.id,
        related_url=url_for('forms.view_edit_form', form_type='assignment', form_id=aes.id),
        priority='normal'
    )
    return notifications


def notify_user_added_to_country(user_id, country_id):
    """Notify user when they are added as a focal point to a country."""
    try:
        user = User.query.get(user_id)
        country = Country.query.get(country_id)

        if not user or not country:
            current_app.logger.warning(f"Cannot notify user {user_id} about country {country_id}: user or country not found")
            return []

        # Get localized country name (will be translated when notification is displayed)
        country_name = country.name

        # Create notification for the user using translation keys
        return create_notification(
            user_ids=[user_id],
            notification_type=NotificationType.user_added_to_country,
            title_key='notification.user_added_to_country.title',
            title_params=None,
            message_key='notification.user_added_to_country.message',
            message_params={
                'country': country_name
            },
        entity_type='country',
        entity_id=country_id,
            related_object_type='country',
            related_object_id=country_id,
            related_url=url_for('main.dashboard'),
            priority='high',  # High priority so email is sent even if user has digest preferences
            icon='fas fa-user-plus'
        )
    except Exception as e:
        current_app.logger.error(f"Error notifying user {user_id} about being added to country {country_id}: {str(e)}", exc_info=True)
        return []


def notify_template_updated(template):
    """Notify users when a template they have assignments for is updated."""
    try:
        from app.models.rbac import RbacUserRole, RbacRole
        # Find all active assignments using this template
        active_assignments = AssignmentEntityStatus.query.join(
            AssignmentEntityStatus.assigned_form
        ).filter(
            AssignmentEntityStatus.assigned_form.has(template_id=template.id),
            AssignmentEntityStatus.status.in_(['Pending', 'In Progress', 'Submitted'])
        ).all()

        # Get unique user IDs from focal points of countries with active assignments
        from app.models.core import UserEntityPermission
        user_ids_to_notify = set()
        for aes in active_assignments:
            if aes.entity_type == 'country':
                # Get focal points via UserEntityPermission
                permissions = UserEntityPermission.query.filter_by(
                    entity_type='country',
                    entity_id=aes.entity_id
                ).join(User, UserEntityPermission.user_id == User.id).join(
                    RbacUserRole, RbacUserRole.user_id == User.id
                ).join(
                    RbacRole, RbacUserRole.role_id == RbacRole.id
                ).filter(
                    RbacRole.code == "assignment_editor_submitter"
                ).all()

                for perm in permissions:
                    user_ids_to_notify.add(perm.user_id)

        if not user_ids_to_notify:
            current_app.logger.debug(f"No users to notify about template {template.id} update")
            return []

        # Get localized template name (will be translated when notification is displayed)
        template_name = template.name

        # Create notifications for all affected focal points
        return create_notification(
            user_ids=list(user_ids_to_notify),
            notification_type=NotificationType.template_updated,
            title_key='notification.template_updated.title',
            title_params=None,
            message_key='notification.template_updated.message',
            message_params={
                'template': template_name
            },
        entity_type=None,  # Template-level (global)
        entity_id=None,
            related_object_type='template',
            related_object_id=template.id,
            related_url=url_for('form_builder.edit_template', template_id=template.id),
            priority='normal',
            icon='fas fa-file-alt'
        )
    except Exception as e:
        current_app.logger.error(f"Error notifying users about template {template.id} update: {str(e)}", exc_info=True)
        return []


def notify_self_report_created(assignment_entity_status):
    """Notify focal points when a self-report is created for any entity type."""
    aes = assignment_entity_status
    entity_type = aes.entity_type
    entity_id = aes.entity_id

    from app.services.entity_service import EntityService
    from app.models.forms import FormTemplate

    # Get template directly via template_id to avoid stale relationship data
    assigned_form = aes.assigned_form
    template = FormTemplate.query.get(assigned_form.template_id) if assigned_form and assigned_form.template_id else None
    template_name = template.name if template else "Unknown Template"

    # Log activity for the entity
    log_entity_activity(
        entity_type=entity_type,
        entity_id=entity_id,
        activity_type='self_report_created',
        activity_description=f"Self-report '{template_name}' for period '{assigned_form.period_name}' was created",
        summary_key='activity.self_report_created',
        summary_params={'template': template_name},
        related_object_type='assignment',
        related_object_id=aes.id,
        assignment_id=aes.id,
        related_url=url_for('forms.view_edit_form', form_type='assignment', form_id=aes.id),
        activity_category='admin',
        icon=None,
        user_id=None
    )

    # Create notifications for focal points using translation keys
    return notify_entity_focal_points(
        entity_type=entity_type,
        entity_id=entity_id,
        notification_type=NotificationType.self_report_created,
        title_key='notification.self_report_created.title',
        title_params=None,
        message_key='notification.self_report_created.message',
        message_params={
            'template': template_name,
            '_entity_type': entity_type,
            '_entity_id': entity_id
        },
        related_object_type='assignment',
        related_object_id=aes.id,
        related_url=url_for('forms.view_edit_form', form_type='assignment', form_id=aes.id),
        priority='normal'
    )


def notify_public_submission_received(public_submission):
    """Notify admins when a public submission is received."""
    try:
        from app.models import User
        from app.models.rbac import RbacUserRole, RbacRole
        from sqlalchemy import or_

        # Get all admin-capable users (RBAC-only): system managers + any admin_* role + admin_core
        admin_role_ids = (
            select(RbacRole.id)
            .where(
                or_(
                    RbacRole.code == "system_manager",
                    RbacRole.code == "admin_core",
                    RbacRole.code.like("admin\\_%", escape="\\"),
                )
            )
        )

        admin_users = (
            User.query.join(RbacUserRole, User.id == RbacUserRole.user_id)
            .filter(RbacUserRole.role_id.in_(admin_role_ids))
            .distinct()
            .all()
        )

        if not admin_users:
            current_app.logger.debug("No admins to notify about public submission")
            return []

        # Get template and country information
        from app.models.forms import FormTemplate

        template_name = 'Unknown Template'
        country_name = 'Unknown Country'
        if public_submission.assigned_form and public_submission.assigned_form.template_id:
            template = FormTemplate.query.get(public_submission.assigned_form.template_id)
            if template:
                template_name = template.name
        if public_submission.country:
            country_name = public_submission.country.name

        # Create notifications for all admins
        return create_notification(
            user_ids=[admin.id for admin in admin_users],
            notification_type=NotificationType.public_submission_received,
            title_key='notification.public_submission_received.title',
            title_params=None,
            message_key='notification.public_submission_received.message',
            message_params={
                'template': template_name,
                'country': country_name,
                'submitter': public_submission.submitter_name or public_submission.submitter_email or 'Unknown'
            },
        entity_type='country' if public_submission.country_id else None,
        entity_id=public_submission.country_id if public_submission.country_id else None,
            related_object_type='public_submission',
            related_object_id=public_submission.id,
            related_url=url_for('form_builder.manage_templates'),  # Could be enhanced to link to submission review page
            priority='normal',
            icon='fas fa-inbox'
        )
    except Exception as e:
        current_app.logger.error(f"Error notifying admins about public submission {public_submission.id}: {str(e)}", exc_info=True)
        return []


def notify_standalone_document_uploaded(document, country_id):
    """Notify relevant users when a standalone document is uploaded (not linked to an assignment).

    Args:
        document: SubmittedDocument object
        country_id: Country ID for the document

    Returns:
        list: Created notification objects
    """

    notifications = []

    try:
        current_app.logger.info(
            f"[DOCUMENT_NOTIFICATION] Starting notification process for document ID {document.id}, "
            f"filename: '{document.filename}', type: '{document.document_type}', "
            f"status: '{document.status}', is_public: {document.is_public}, country_id: {country_id}"
        )

        # Get country once and reuse
        country = Country.query.get(country_id) if country_id else None
        country_name = country.name if country else 'Unknown Country'

        current_app.logger.info(
            f"[DOCUMENT_NOTIFICATION] Country: {country_name} (ID: {country_id})"
        )

        # Log activity against the linked entity (country, NS branch, secretariat unit, …)
        _log_et = getattr(document, "linked_entity_type", None) or "country"
        _log_eid = getattr(document, "linked_entity_id", None)
        if _log_eid is None and country_id is not None:
            _log_et, _log_eid = "country", country_id
        if _log_eid is None:
            current_app.logger.warning(
                "[DOCUMENT_NOTIFICATION] Skipping entity activity log (no linked entity): document %s",
                getattr(document, "id", None),
            )
        else:
            log_entity_activity(
                entity_type=_log_et,
                entity_id=_log_eid,
                activity_type='document_uploaded',
                activity_description=f"Document '{document.filename}' ({document.document_type}) was uploaded",
                summary_key='activity.document_uploaded',
                summary_params={'document': document.filename, 'type': document.document_type},
                related_object_type='document',
                related_object_id=document.id,
                related_url=url_for('content_management.manage_documents'),
                activity_category='document',
                icon=None,
                user_id=current_user.id if current_user.is_authenticated else None,
            )

        # Track which users we've already notified to avoid duplicates
        notified_user_ids = set()
        uploader_id = current_user.id if current_user.is_authenticated else None
        uploader_email = current_user.email if current_user.is_authenticated else 'Unknown'

        current_app.logger.info(
            f"[DOCUMENT_NOTIFICATION] Uploader: ID {uploader_id}, email: {uploader_email}"
        )

        # Determine who should receive notifications based on document status
        #
        # Logic:
        # 1. If status is "Pending": Only notify admins/system managers (for approval)
        # 2. If status is "Approved": Notify focal points (they should know about approved documents)
        # 3. Never notify the uploader
        # 4. Users who are both admins and focal points only get one notification (admin takes priority)

        if document.status == 'Pending':
            current_app.logger.info(
                f"[DOCUMENT_NOTIFICATION] Document status is 'Pending' - will notify admins/system managers only"
            )

            # Pending documents: Only notify admin-capable users (RBAC-only)
            from app.models.rbac import RbacUserRole, RbacRole

            admin_role_ids = (
                select(RbacRole.id)
                .where(
                    or_(
                        RbacRole.code == "system_manager",
                        RbacRole.code == "admin_core",
                        RbacRole.code.like("admin\\_%", escape="\\"),
                    )
                )
            )

            admin_users = (
                User.query.join(RbacUserRole, User.id == RbacUserRole.user_id)
                .filter(RbacUserRole.role_id.in_(admin_role_ids))
                .distinct()
                .all()
            )

            current_app.logger.info(
                f"[DOCUMENT_NOTIFICATION] Found {len(admin_users)} total admins/system managers"
            )

            # Exclude the uploader
            admin_user_ids = [
                admin.id for admin in admin_users
                if not uploader_id or admin.id != uploader_id
            ]

            excluded_admin_ids = [
                admin.id for admin in admin_users
                if uploader_id and admin.id == uploader_id
            ]

            if excluded_admin_ids:
                current_app.logger.info(
                    f"[DOCUMENT_NOTIFICATION] Excluding uploader (admin/system manager) from notifications: {excluded_admin_ids}"
                )

            current_app.logger.info(
                f"[DOCUMENT_NOTIFICATION] Will notify {len(admin_user_ids)} admins/system managers: {admin_user_ids}"
            )

            if admin_user_ids:
                # Get user emails for logging
                admin_emails = [
                    User.query.get(uid).email for uid in admin_user_ids
                ]
                current_app.logger.info(
                    f"[DOCUMENT_NOTIFICATION] Admin/System Manager emails to notify: {admin_emails}"
                )

                admin_notifications = create_notification(
                    user_ids=admin_user_ids,
                    notification_type=NotificationType.document_uploaded,
                    title_key='notification.document_uploaded.pending.title',
                    title_params=None,
                    message_key='notification.document_uploaded.pending.message',
                    message_params={
                        'document': document.filename,
                        'document_type': document.document_type or _('Document'),
                        '_entity_type': 'country',
                        '_entity_id': country_id
                    },
                        entity_type='country',
                        entity_id=country_id,
                    related_object_type='document',
                    related_object_id=document.id,
                    related_url=url_for('content_management.manage_documents'),
                    priority='high'
                )

                if admin_notifications:
                    current_app.logger.info(
                        f"[DOCUMENT_NOTIFICATION] Created {len(admin_notifications)} admin notifications"
                    )
                    notifications.extend(admin_notifications)
                    # Track notified users to prevent duplicates
                    notified_user_ids.update(admin_user_ids)
                    current_app.logger.info(
                        f"[DOCUMENT_NOTIFICATION] Tracked notified user IDs: {notified_user_ids}"
                    )
                else:
                    current_app.logger.warning(
                        f"[DOCUMENT_NOTIFICATION] No admin notifications were created (may have been filtered by preferences)"
                    )
            else:
                current_app.logger.info(
                    f"[DOCUMENT_NOTIFICATION] No admins/system managers to notify (all excluded or none exist)"
                )
        else:
            current_app.logger.info(
                f"[DOCUMENT_NOTIFICATION] Document status is '{document.status}' - will notify focal points only"
            )

            # Approved/Rejected documents: Notify focal points
            # (Admins already know since they approved/rejected it)
            if country:
                # Get all admins/system managers to exclude them from focal point notifications
                # (they already know about the document)
                from app.models.rbac import RbacUserRole, RbacRole
                admin_role_ids = (
                    select(RbacRole.id)
                    .where(
                        or_(
                            RbacRole.code == "system_manager",
                            RbacRole.code == "admin_core",
                            RbacRole.code.like("admin\\_%", escape="\\"),
                        )
                    )
                )
                admin_system_manager_users = (
                    User.query.join(RbacUserRole, User.id == RbacUserRole.user_id)
                    .filter(RbacUserRole.role_id.in_(admin_role_ids))
                    .distinct()
                    .all()
                )

                admin_system_manager_ids = {user.id for user in admin_system_manager_users}
                admin_system_manager_emails = [user.email for user in admin_system_manager_users]

                current_app.logger.info(
                    f"[DOCUMENT_NOTIFICATION] Found {len(admin_system_manager_ids)} admins/system managers to exclude: "
                    f"IDs {admin_system_manager_ids}, emails {admin_system_manager_emails}"
                )

                # Get all users for this country via UserEntityPermission
                from app.models.core import UserEntityPermission
                country_permissions = UserEntityPermission.query.filter_by(
                    entity_type='country',
                    entity_id=country_id
                ).join(User, UserEntityPermission.user_id == User.id).all()

                all_country_users = [perm.user for perm in country_permissions]
                current_app.logger.info(
                    f"[DOCUMENT_NOTIFICATION] Country has {len(all_country_users)} total users assigned"
                )

                # Get focal point IDs, excluding:
                # 1. The uploader
                # 2. Admins/system managers (they already know)
                # 3. Users already notified (shouldn't happen here, but safety check)
                # Focal points are represented as assignment editor/submitter in RBAC
                focal_point_permissions = (
                    UserEntityPermission.query.filter_by(
                        entity_type="country",
                        entity_id=country_id,
                    )
                    .join(User, UserEntityPermission.user_id == User.id)
                    .join(RbacUserRole, RbacUserRole.user_id == User.id)
                    .join(RbacRole, RbacUserRole.role_id == RbacRole.id)
                    .filter(RbacRole.code == "assignment_editor_submitter")
                    .all()
                )
                focal_point_candidates = [perm.user for perm in focal_point_permissions]

                current_app.logger.info(
                    f"[DOCUMENT_NOTIFICATION] Found {len(focal_point_candidates)} focal point candidates: "
                    f"IDs {[u.id for u in focal_point_candidates]}, emails {[u.email for u in focal_point_candidates]}"
                )

                excluded_focal_points = []
                focal_point_ids = []

                for user in focal_point_candidates:
                    exclusion_reason = None
                    if uploader_id and user.id == uploader_id:
                        exclusion_reason = "uploader"
                    elif user.id in admin_system_manager_ids:
                        exclusion_reason = "admin/system_manager"
                    elif user.id in notified_user_ids:
                        exclusion_reason = "already_notified"

                    if exclusion_reason:
                        excluded_focal_points.append((user.id, user.email, exclusion_reason))
                    else:
                        focal_point_ids.append(user.id)

                if excluded_focal_points:
                    current_app.logger.info(
                        f"[DOCUMENT_NOTIFICATION] Excluded {len(excluded_focal_points)} focal points: {excluded_focal_points}"
                    )

                current_app.logger.info(
                    f"[DOCUMENT_NOTIFICATION] Will notify {len(focal_point_ids)} focal points: {focal_point_ids}"
                )

                if focal_point_ids:
                    focal_point_emails = [
                        User.query.get(uid).email for uid in focal_point_ids
                    ]
                    current_app.logger.info(
                        f"[DOCUMENT_NOTIFICATION] Focal point emails to notify: {focal_point_emails}"
                    )

                    focal_point_notifications = create_notification(
                        user_ids=focal_point_ids,
                        notification_type=NotificationType.document_uploaded,
                        title_key='notification.document_uploaded.title',
                        title_params=None,
                        message_key='notification.document_uploaded.message',
                        message_params={
                            'document': document.filename,
                            'document_type': document.document_type or _('Document'),
                            '_entity_type': 'country',
                            '_entity_id': country_id
                        },
                        entity_type='country',
                        entity_id=country_id,
                        related_object_type='document',
                        related_object_id=document.id,
                        related_url=url_for('content_management.manage_documents'),
                        priority='normal'
                    )

                    if focal_point_notifications:
                        current_app.logger.info(
                            f"[DOCUMENT_NOTIFICATION] Created {len(focal_point_notifications)} focal point notifications"
                        )
                        notifications.extend(focal_point_notifications)
                    else:
                        current_app.logger.warning(
                            f"[DOCUMENT_NOTIFICATION] No focal point notifications were created (may have been filtered by preferences)"
                        )
                else:
                    current_app.logger.info(
                        f"[DOCUMENT_NOTIFICATION] No focal points to notify (all excluded or none exist)"
                    )
            else:
                current_app.logger.warning(
                    f"[DOCUMENT_NOTIFICATION] No country found for country_id {country_id}, cannot notify focal points"
                )

        current_app.logger.info(
            f"[DOCUMENT_NOTIFICATION] Notification process completed. Total notifications created: {len(notifications)}. "
            f"Notification IDs: {[n.id if hasattr(n, 'id') else 'N/A' for n in notifications]}"
        )

        return notifications

    except Exception as e:
        current_app.logger.error(
            f"[DOCUMENT_NOTIFICATION] Error sending standalone document upload notifications: {str(e)}",
            exc_info=True
        )
        return []


def notify_form_data_updated(assignment_entity_status, completion_percentage=None, field_changes=None):
    """Notify focal points when form data is updated with detailed field change information for any entity type."""
    aes = assignment_entity_status
    entity_type = aes.entity_type
    entity_id = aes.entity_id

    from app.models.forms import FormTemplate

    # Get template directly via template_id to avoid stale relationship data
    assigned_form = aes.assigned_form
    template = FormTemplate.query.get(assigned_form.template_id) if assigned_form and assigned_form.template_id else None
    template_name = template.name if template else "Unknown Template"

    # Create activity summary based on field changes
    activity_description = f"Form data updated for assignment '{template_name}'"

    # Enhance summary and description with field changes
    summary_key = 'activity.form_data_updated.multiple'
    summary_params = {'count': 0, 'template': template_name}
    if field_changes:
        change_count = len(field_changes)
        if change_count == 1:
            change = field_changes[0]
            activity_description = f"Updated field '{change['field_name']}' from '{change.get('old_value') or ''}' to '{change.get('new_value') or ''}'"
            summary_key = 'activity.form_data_updated.single'
            summary_params = {'field': change['field_name'], 'old': change.get('old_value') or '', 'new': change.get('new_value') or ''}
        else:
            activity_description = f"Updated {change_count} fields in assignment '{template_name}'"
            summary_key = 'activity.form_data_updated.multiple'
            summary_params = {'count': change_count, 'template': template_name}

    # Add completion percentage to summary
    completion_text = f" (now {completion_percentage:.1f}% complete)" if completion_percentage else ""
    activity_description += completion_text

    # Log activity with detailed field changes for the entity
    log_entity_activity(
        entity_type=entity_type,
        entity_id=entity_id,
        activity_type='form_data_updated',
        activity_description=activity_description,
        summary_key=summary_key,
        summary_params=summary_params,
        related_object_type='assignment',
        related_object_id=aes.id,
        assignment_id=aes.id,
        related_url=url_for('forms.view_edit_form', form_type='assignment', form_id=aes.id),
        activity_category='form',
        icon=None,
        user_id=None
    )


def capture_field_changes(assignment_entity_status_id, field_updates):
    """
    Capture field-level changes during form processing.

    Args:
        assignment_entity_status_id: ID of the assignment
        field_updates: List of dictionaries with field update information
            [{'type': str, 'form_item_id': int, 'field_name': str, 'old_value': any, 'new_value': any}]

    Returns:
        List of formatted field changes for activity logging
    """
    from app.models import FormItem, IndicatorBank

    field_changes = []

    for update in field_updates:
        change_type = update.get('type', 'updated')
        form_item_id = update.get('form_item_id')
        field_name = update.get('field_name', 'Unknown Field')
        old_value = update.get('old_value')
        new_value = update.get('new_value')

        # Format values based on field type - try formatting first, fallback to string
        formatted_old = format_indicator_value(old_value) if old_value is not None else None
        formatted_new = format_indicator_value(new_value, comparison_value=old_value) if new_value is not None else None

        # Also handle question values (Yes/No, multiple choice, etc.)
        if formatted_old == str(old_value) and old_value is not None:
            formatted_old = format_question_value(old_value)
        if formatted_new == str(new_value) and new_value is not None:
            formatted_new = format_question_value(new_value)

        current_app.logger.debug(f"Field {form_item_id} formatting:")
        current_app.logger.debug(f"  old_value: {old_value} -> {formatted_old}")
        current_app.logger.debug(f"  new_value: {new_value} -> {formatted_new}")

        # Try to get more context from the form item for better formatting (optional enhancement)
        try:
            form_item = FormItem.query.get(form_item_id)
            if form_item and form_item.item_type == 'indicator':
                indicator = IndicatorBank.query.get(form_item.indicator_bank_id)
                if indicator:
                    # Re-format with indicator context for better units/labels
                    formatted_old = format_indicator_value(old_value, indicator) if old_value is not None else None
                    formatted_new = format_indicator_value(new_value, indicator, comparison_value=old_value) if new_value is not None else None
                    current_app.logger.debug(f"  Enhanced with indicator context: {formatted_old} -> {formatted_new}")
        except Exception as e:
            current_app.logger.debug(f"Optional enhancement failed for field {form_item_id}: {e}")
            # Continue with basic formatting

        # Truncate long field names and values for readability
        field_name = truncate_text(field_name, 50)
        formatted_old = truncate_text(formatted_old, 100) if formatted_old else None
        formatted_new = truncate_text(formatted_new, 100) if formatted_new else None

        # Ensure values are strings or None for template safety
        safe_old_value = str(formatted_old) if formatted_old is not None else None
        safe_new_value = str(formatted_new) if formatted_new is not None else None

        field_changes.append({
            'type': change_type,
            'field_name': field_name or 'Unknown Field',
            'old_value': safe_old_value,
            'new_value': safe_new_value,
            'form_item_id': form_item_id
        })

    return field_changes


def compare_disaggregated_data(old_value, new_value):
    """
    Compare two disaggregated data structures and return only the fields that changed.
    Returns a formatted string showing the specific changes made.
    """
    try:
        # Parse both values
        old_data = old_value if isinstance(old_value, dict) else json.loads(old_value) if isinstance(old_value, str) else {}
        new_data = new_value if isinstance(new_value, dict) else json.loads(new_value) if isinstance(new_value, str) else {}

        # Extract values dictionaries
        old_values = old_data.get('values', {}) if old_data.get('mode') in ['sex_age', 'sex', 'age'] else {}
        new_values = new_data.get('values', {}) if new_data.get('mode') in ['sex_age', 'sex', 'age'] else {}

        if not old_values and not new_values:
            return None

        # Find all categories that changed
        changed_categories = []
        all_categories = set(old_values.keys()) | set(new_values.keys())

        for category in all_categories:
            old_val = old_values.get(category, 0)
            new_val = new_values.get(category, 0)

            # Only track meaningful changes (not 0 → 0)
            if old_val != new_val and (old_val != 0 or new_val != 0):
                readable_category = category.replace('_', ' ').title()
                if old_val == 0:
                    changed_categories.append(f"{readable_category}: Added {new_val}")
                elif new_val == 0:
                    changed_categories.append(f"{readable_category}: Removed {old_val}")
                else:
                    changed_categories.append(f"{readable_category}: {old_val} → {new_val}")

        if changed_categories:
            if len(changed_categories) == 1:
                return changed_categories[0]
            elif len(changed_categories) <= 3:
                return ", ".join(changed_categories)
            else:
                # Show first 3 changes + count of remaining
                shown_changes = changed_categories[:3]
                remaining_count = len(changed_categories) - 3
                return f"{', '.join(shown_changes)} +{remaining_count} more changes"

        return None

    except (json.JSONDecodeError, AttributeError, TypeError) as e:
        current_app.logger.debug(f"Error comparing disaggregated data: {e}")
        return None


def format_indicator_value(value, indicator=None, comparison_value=None):
    """Format indicator values for display in activities."""
    if value is None or value == '' or value == {}:
        return None

    current_app.logger.debug(f"format_indicator_value called with: {value} (type: {type(value)})")

    # If we have a comparison value, try to show specific changes for disaggregated data
    if comparison_value is not None:
        changes = compare_disaggregated_data(comparison_value, value)
        if changes:
            current_app.logger.debug(f"Found specific disaggregated changes: {changes}")
            return changes

    try:
        # Try to parse as JSON for disaggregated data
        if isinstance(value, str) and value.strip().startswith('{'):
            try:
                data = json.loads(value)
            except json.JSONDecodeError:
                # Use empty dict on parse failure; avoid ast.literal_eval on untrusted input
                data = {}
            mode = data.get('mode', 'standard')
            values = data.get('values', {})

            if mode == 'total':
                total = values.get('total')
                if total is not None:
                    unit = f" {indicator.unit}" if indicator and hasattr(indicator, 'unit') and indicator.unit else ""
                    return f"{total}{unit}"
            elif mode == 'sex':
                sex_values = []
                for key, val in values.items():
                    if val is not None:
                        sex_name = key.replace('_', ' ').title()
                        unit = f" {indicator.unit}" if indicator and hasattr(indicator, 'unit') and indicator.unit else ""
                        sex_values.append(f"{sex_name}: {val}{unit}")
                if sex_values:
                    return ", ".join(sex_values)
            elif mode == 'age':
                age_values = []
                for key, val in values.items():
                    if val is not None:
                        age_name = key.replace('_', ' ').title()
                        unit = f" {indicator.unit}" if indicator and hasattr(indicator, 'unit') and indicator.unit else ""
                        age_values.append(f"{age_name}: {val}{unit}")
                if age_values:
                    return ", ".join(age_values)
            elif mode == 'sex_age':
                # For complex sex-age breakdowns, show key non-zero values
                non_zero_values = {k: v for k, v in values.items() if v and v != 0}
                if non_zero_values:
                    unit = f" {indicator.unit}" if indicator and hasattr(indicator, 'unit') and indicator.unit else ""

                    # If only one non-zero value, show it directly
                    if len(non_zero_values) == 1:
                        key, val = next(iter(non_zero_values.items()))
                        readable_key = key.replace('_', ' ').title()
                        return f"{readable_key}: {val}{unit}"

                    # Multiple values - show top 2 most significant + total
                    sorted_values = sorted(non_zero_values.items(), key=lambda x: x[1], reverse=True)
                    top_values = sorted_values[:2]

                    parts = []
                    for key, val in top_values:
                        readable_key = key.replace('_', ' ').title()
                        parts.append(f"{readable_key}: {val}")

                    total_count = sum(non_zero_values.values())
                    if len(non_zero_values) > 2:
                        return f"Total: {total_count}{unit} ({', '.join(parts)} +{len(non_zero_values)-2} more)"
                    else:
                        return f"Total: {total_count}{unit} ({', '.join(parts)})"
            elif mode == 'standard':
                std_value = values.get('value')
                if std_value is not None:
                    unit = f" {indicator.unit}" if indicator and hasattr(indicator, 'unit') and indicator.unit else ""
                    return f"{std_value}{unit}"

        # If it's a dict/object but not JSON string, try to parse it directly
        if isinstance(value, dict):
            current_app.logger.debug(f"Processing dict object: {value}")
            mode = value.get('mode', 'standard') if isinstance(value.get('mode'), str) else 'standard'
            values = value.get('values', {}) if isinstance(value.get('values'), (dict, list)) else {}
            current_app.logger.debug(f"Extracted mode: {mode}, values: {values}")

            if mode == 'total' and values.get('total') is not None:
                unit = f" {indicator.unit}" if indicator and hasattr(indicator, 'unit') and indicator.unit else ""
                return f"{values['total']}{unit}"
            elif mode == 'sex_age':
                # Handle sex_age breakdowns for dict objects
                current_app.logger.debug(f"Processing sex_age mode for dict")
                non_zero_values = {k: v for k, v in values.items() if v and v != 0}
                current_app.logger.debug(f"Non-zero values: {non_zero_values}")
                if non_zero_values:
                    unit = f" {indicator.unit}" if indicator and hasattr(indicator, 'unit') and indicator.unit else ""

                    # If only one non-zero value, show it directly
                    if len(non_zero_values) == 1:
                        key, val = next(iter(non_zero_values.items()))
                        readable_key = key.replace('_', ' ').title()
                        return f"{readable_key}: {val}{unit}"

                    # Multiple values - show top 2 most significant + total
                    sorted_values = sorted(non_zero_values.items(), key=lambda x: x[1], reverse=True)
                    top_values = sorted_values[:2]

                    parts = []
                    for key, val in top_values:
                        readable_key = key.replace('_', ' ').title()
                        parts.append(f"{readable_key}: {val}")

                    total_count = sum(non_zero_values.values())
                    if len(non_zero_values) > 2:
                        return f"Total: {total_count}{unit} ({', '.join(parts)} +{len(non_zero_values)-2} more)"
                    else:
                        return f"Total: {total_count}{unit} ({', '.join(parts)})"
            elif mode == 'standard' and values.get('value') is not None:
                unit = f" {indicator.unit}" if indicator and hasattr(indicator, 'unit') and indicator.unit else ""
                return f"{values['value']}{unit}"
            else:
                # Handle simple disaggregation dicts like {'direct': 10, 'indirect': 20} or other category maps
                # Detect if the dict looks like a flat category->number map
                flat_map = None
                if values and isinstance(values, dict):
                    flat_map = values
                else:
                    # If no 'values' key, the dict itself may be the map
                    # Only treat as flat map if values are primitives (int/float/str)
                    if all(isinstance(v, (int, float, str, type(None))) for v in value.values()):
                        flat_map = value
                if flat_map is not None:
                    def format_number(n):
                        try:
                            return f"{int(n):,}"
                        except Exception as e1:
                            try:
                                return f"{float(n):,}"
                            except Exception as e2:
                                current_app.logger.debug("format_number fallback to str: %s, %s", e1, e2)
                                return str(n)
                    # Preferred order for common keys
                    preferred_order = ['total', 'direct', 'indirect']
                    keys = list(flat_map.keys())
                    ordered_keys = [k for k in preferred_order if k in keys] + [k for k in keys if k not in preferred_order]
                    parts = []
                    unit = f" {indicator.unit}" if indicator and hasattr(indicator, 'unit') and indicator.unit else ""
                    for k in ordered_keys:
                        v = flat_map.get(k)
                        if v is None or v == 0:
                            continue
                        label = k.replace('_', ' ').title()
                        parts.append(f"{label}: {format_number(v)}{unit}")
                    if parts:
                        return ", ".join(parts)

        # Simple value (not JSON)
        unit = f" {indicator.unit}" if indicator and hasattr(indicator, 'unit') and indicator.unit else ""
        return f"{value}{unit}"

    except (json.JSONDecodeError, AttributeError, TypeError):
        # Fallback to simple string representation
        return str(value)


def format_question_value(value, question=None):
    """Format question values for display in activities."""
    if value is None:
        return None

    try:
        # Handle different question types if question object is available
        if question and hasattr(question, 'type'):
            if question.type == 'yesno':
                return 'Yes' if str(value).lower() in ['yes', '1', 'true'] else 'No'
            elif question.type == 'single_choice':
                return str(value)
            elif question.type == 'multiple_choice':
                if isinstance(value, str) and value.strip().startswith('['):
                    choices = json.loads(value)
                    return ", ".join(choices) if isinstance(choices, list) else str(value)
                return str(value)

        # Smart fallback formatting when no question type info available
        value_str = str(value).lower()

        # Detect Yes/No values
        if value_str in ['yes', 'no', 'true', 'false', '1', '0']:
            if value_str in ['yes', 'true', '1']:
                return 'Yes'
            elif value_str in ['no', 'false', '0']:
                return 'No'

        # Try to detect if it's JSON array (multiple choice)
        if isinstance(value, str) and value.strip().startswith('['):
            with suppress(json.JSONDecodeError):
                choices = json.loads(value)
                return ", ".join(choices) if isinstance(choices, list) else str(value)

        # Handle lists directly (if already parsed)
        if isinstance(value, list):
            return ", ".join(str(item) for item in value)

        return str(value)

    except (json.JSONDecodeError, AttributeError):
        return str(value)


def truncate_text(text, max_length):
    """Truncate text to maximum length with ellipsis."""
    if not text:
        return text
    text_str = str(text)
    return text_str[:max_length] + "..." if len(text_str) > max_length else text_str
