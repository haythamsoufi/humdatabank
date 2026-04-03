"""
Notification Scheduling Utilities

Functions for creating and processing scheduled notifications.
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Union, Tuple
from flask import current_app
from app import db
from app.models import Notification, User
from flask_babel import force_locale
from app.utils.notifications import (
    create_notification,
    translate_notification_message,
    get_user_preferences_batch,
    is_notification_type_enabled_for_user,
)
from app.models.enums import NotificationType
from app.utils.datetime_helpers import utcnow

DEFAULT_TITLE_KEY = 'notification.admin_message.title'
DEFAULT_MESSAGE_KEY = 'notification.admin_message.message'


def _resolve_notification_content(
    title: Optional[str],
    message: Optional[str],
    title_key: Optional[str],
    message_key: Optional[str],
    title_params: Optional[Dict[str, Any]],
    message_params: Optional[Dict[str, Any]],
) -> Tuple[str, str, Optional[Dict[str, Any]], Optional[Dict[str, Any]], str, str]:
    """
    Normalize translation inputs and derive English fallbacks for storage.
    Returns (title_key, message_key, title_params, message_params, fallback_title, fallback_message).
    """
    resolved_title_key = title_key or DEFAULT_TITLE_KEY
    resolved_message_key = message_key or DEFAULT_MESSAGE_KEY

    # Copy params to avoid mutating caller dictionaries
    resolved_title_params = dict(title_params) if title_params else {}
    resolved_message_params = dict(message_params) if message_params else {}

    if not title_key and title:
        resolved_title_params['custom_title'] = title
    if not message_key and message is not None:
        resolved_message_params['message'] = message

    fallback_title = title or ''
    fallback_message = message or ''

    # Generate English fallbacks if caller did not supply literal text
    if not fallback_title:
        with force_locale('en'):
            fallback_title = translate_notification_message(
                resolved_title_key,
                resolved_title_params,
                locale='en'
            ) or ''
    if not fallback_message:
        with force_locale('en'):
            fallback_message = translate_notification_message(
                resolved_message_key,
                resolved_message_params,
                locale='en'
            ) or ''

    return (
        resolved_title_key,
        resolved_message_key,
        resolved_title_params or None,
        resolved_message_params or None,
        fallback_title,
        fallback_message,
    )


def create_scheduled_notification(
    user_ids: Union[int, List[int]],
    notification_type: NotificationType,
    scheduled_for: datetime,
    title: Optional[str] = None,
    message: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    related_object_type: Optional[str] = None,
    related_object_id: Optional[int] = None,
    related_url: Optional[str] = None,
    priority: str = 'normal',
    icon: Optional[str] = None,
    action_buttons: Optional[List[Dict[str, Any]]] = None,
    title_key: Optional[str] = None,
    title_params: Optional[Dict[str, Any]] = None,
    message_key: Optional[str] = None,
    message_params: Optional[Dict[str, Any]] = None,
    category: Optional[str] = None,
    tags: Optional[List[str]] = None,
    respect_preferences: bool = True,
) -> List[Notification]:
    """
    Create a scheduled notification that will be sent at a future time.

    Args:
        user_ids: User ID(s) to notify
        notification_type: Type of notification
        scheduled_for: Datetime when notification should be sent
        ... (other parameters same as create_notification)

    Returns:
        List of Notification objects (created but not yet sent)

    Note:
        Notifications are created immediately but will not be broadcast
        (WebSocket/push/email) until scheduled_for time is reached.
    """
    try:
        # Ensure user_ids is a list of integers
        if not isinstance(user_ids, list):
            user_ids = [user_ids]

        validated_user_ids = []
        for uid in user_ids:
            try:
                validated_user_ids.append(int(uid))
            except (TypeError, ValueError):
                current_app.logger.warning(f"Invalid user_id provided for scheduled notification: {uid}")
        if not validated_user_ids:
            current_app.logger.warning("No valid user IDs provided to create_scheduled_notification")
            return []
        user_ids = validated_user_ids

        resolved_title_key, resolved_message_key, resolved_title_params, resolved_message_params, fallback_title, fallback_message = _resolve_notification_content(
            title=title,
            message=message,
            title_key=title_key,
            message_key=message_key,
            title_params=title_params,
            message_params=message_params,
        )

        # Optionally filter user IDs based on preferences at creation time
        if respect_preferences:
            preferences_cache = get_user_preferences_batch(user_ids)
            filtered_user_ids = [
                user_id for user_id in user_ids
                if is_notification_type_enabled_for_user(
                    user_id,
                    notification_type,
                    preferences_cache=preferences_cache
                )
            ]
            if not filtered_user_ids:
                current_app.logger.info(
                    f"All users filtered out based on notification preferences for scheduled notification "
                    f"type {notification_type}"
                )
                return []
            if len(filtered_user_ids) != len(user_ids):
                current_app.logger.info(
                    f"Filtered out {len(user_ids) - len(filtered_user_ids)} user(s) when scheduling notification "
                    f"type {notification_type}"
                )
            user_ids = filtered_user_ids

        # Validate scheduled_for is in the future
        if scheduled_for <= utcnow():
            current_app.logger.warning(
                f"Scheduled notification time {scheduled_for} is in the past, "
                f"creating as immediate notification instead"
            )
            # Create as immediate notification routed through the same service
            return create_notification(
                user_ids=user_ids,
                notification_type=notification_type,
                entity_type=entity_type,
                entity_id=entity_id,
                related_object_type=related_object_type,
                related_object_id=related_object_id,
                related_url=related_url,
                priority=priority,
                icon=icon,
                action_buttons=action_buttons,
                title_key=resolved_title_key,
                title_params=resolved_title_params,
                message_key=resolved_message_key,
                message_params=resolved_message_params,
                category=category,
                tags=tags,
                respect_preferences=respect_preferences,
            )

        # Create notifications with scheduled_for timestamp
        notifications = []
        for user_id in user_ids:
            notification = Notification(
                user_id=user_id,
                entity_type=entity_type,
                entity_id=entity_id,
                notification_type=notification_type,
                title=fallback_title or '',
                message=fallback_message or '',
                related_object_type=related_object_type,
                related_object_id=related_object_id,
                related_url=related_url,
                priority=priority,
                icon=icon,
                scheduled_for=scheduled_for,
                category=category,
                tags=tags if tags else None,
                title_key=resolved_title_key,
                title_params=resolved_title_params,
                message_key=resolved_message_key,
                message_params=resolved_message_params,
                action_buttons=action_buttons,
                is_read=False,
                is_archived=False
            )
            notifications.append(notification)
            db.session.add(notification)

        db.session.commit()
        current_app.logger.info(
            f"Created {len(notifications)} scheduled notification(s) for {scheduled_for}"
        )
        return notifications

    except Exception as e:
        current_app.logger.error(f"Error creating scheduled notification: {str(e)}", exc_info=True)
        db.session.rollback()
        raise


def process_scheduled_notifications() -> int:
    """
    Process scheduled notifications that are ready to be sent.

    This function should be called periodically (e.g., every minute) to check
    for scheduled notifications that have reached their scheduled time.

    Returns:
        Number of notifications processed
    """
    try:
        now = utcnow()

        # Find all notifications scheduled for now or earlier that haven't been sent
        scheduled_notifications = Notification.query.filter(
            Notification.scheduled_for.isnot(None),
            Notification.scheduled_for <= now,
            Notification.sent_at.is_(None)  # Not yet sent
        ).all()

        if not scheduled_notifications:
            return 0

        processed_count = 0
        skipped_count = 0
        user_ids = [n.user_id for n in scheduled_notifications]
        preferences_cache = get_user_preferences_batch(user_ids)

        for notification in scheduled_notifications:
            try:
                if not is_notification_type_enabled_for_user(
                    notification.user_id,
                    notification.notification_type,
                    preferences_cache=preferences_cache
                ):
                    notification.sent_at = now
                    notification.is_archived = True
                    notification.archived_at = now
                    skipped_count += 1
                    current_app.logger.info(
                        f"Skipping scheduled notification {notification.id} for user {notification.user_id} "
                        f"because the notification type is disabled"
                    )
                    continue

                # Mark as sent
                notification.sent_at = now

                # Broadcast via WebSocket, push, email (same as immediate notifications)
                from app.utils.ws_manager import broadcast_notification, broadcast_unread_count
                from app.services.notification_service import NotificationService
                from app.services.push_notification_service import PushNotificationService
                from app.utils.notification_emails import send_instant_notification_email
                from app.models import User as UserModel

                # Broadcast via WebSocket
                try:
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
                        'category': getattr(notification, 'category', None),
                        'tags': getattr(notification, 'tags', None)
                    }
                    broadcast_notification(notification.user_id, notification_data)

                    # Update unread count
                    unread_count = NotificationService.get_unread_count(notification.user_id)
                    broadcast_unread_count(notification.user_id, unread_count)
                except Exception as e:
                    current_app.logger.warning(f"Failed to broadcast scheduled notification {notification.id} via WebSocket: {e}")

                # Send push notification
                try:
                    user = UserModel.query.get(notification.user_id)
                    if user:
                        PushNotificationService.send_push_notification(
                            user_id=notification.user_id,
                            title=notification.title,
                            body=notification.message,
                            data={
                                'notification_type': notification.notification_type.value if hasattr(notification.notification_type, 'value') else str(notification.notification_type),
                                'related_url': notification.related_url,
                                'priority': notification.priority
                            } if notification.related_url else None,
                            priority=notification.priority
                        )
                except Exception as e:
                    current_app.logger.warning(f"Failed to send push notification for scheduled notification {notification.id}: {e}")

                # Send email if user preferences allow
                try:
                    user = UserModel.query.get(notification.user_id)
                    if user and user.email:
                        send_instant_notification_email(user, notification, override_preferences=False)
                except Exception as e:
                    current_app.logger.warning(f"Failed to send email for scheduled notification {notification.id}: {e}")

                processed_count += 1

            except Exception as e:
                current_app.logger.error(f"Error processing scheduled notification {notification.id}: {e}", exc_info=True)
                # Continue processing other notifications

        db.session.commit()
        current_app.logger.info(
            f"Processed {processed_count} scheduled notification(s)"
            + (f", skipped {skipped_count} due to preferences" if skipped_count else "")
        )
        return processed_count

    except Exception as e:
        current_app.logger.error(f"Error processing scheduled notifications: {str(e)}", exc_info=True)
        db.session.rollback()
        return 0
