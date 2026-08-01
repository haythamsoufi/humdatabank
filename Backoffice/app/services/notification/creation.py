"""Core notification creation pipeline."""
from datetime import timedelta
from typing import Optional, Dict, Any, List, Union

from flask import current_app
from flask_babel import force_locale
from sqlalchemy import and_
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import Notification, NotificationPreferences, User, NotificationType
from app.utils.constants import MAX_NOTIFICATION_MESSAGE_LENGTH
from app.utils.datetime_helpers import utcnow

from app.services.notification.validators import (
    validate_notification_url,
    validate_action_button_endpoint,
)
from app.services.notification.dedup import (
    generate_notification_hash,
    check_duplicate_notification,
    calculate_notification_expiration,
    generate_group_id,
)

IN_APP_ONLY_NOTIFICATION_TYPES = frozenset({
    NotificationType.document_uploaded,
    NotificationType.email_digest,
})


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
    from app.services.notification.core import (
        translate_notification_message,
        get_default_icon_for_notification_type,
    )

    try:
        # Resolve priority from settings (Admin > Notifications tab); if not set, default to normal
        from app.services.platform.app_settings_service import get_notification_priority
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

        if notification_type in IN_APP_ONLY_NOTIFICATION_TYPES:
            send_email_notifications = False
            override_email_preferences = False

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

                    user_ids_list = list({n.user_id for n in notifications if n.user_id})
                    user_map = {}
                    preferences_map = {}
                    if user_ids_list:
                        users = User.query.filter(User.id.in_(user_ids_list)).all()
                        user_map = {u.id: u for u in users}
                        preferences_list = NotificationPreferences.query.filter(
                            NotificationPreferences.user_id.in_(user_ids_list)
                        ).all()
                        preferences_map = {p.user_id: p for p in preferences_list}

                    for notification in notifications:
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
