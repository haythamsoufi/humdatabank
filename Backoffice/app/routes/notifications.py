"""
Dedicated blueprint for notification management.
Extracted from main.py for better organization.

This blueprint handles:
- Getting user notifications with filtering and pagination
- Marking notifications as read
- Archiving notifications
- Deleting notifications
- Managing notification preferences
- Notification center UI
"""
# ========== Notifications Routes ==========
from app.utils.datetime_helpers import utcnow
from app.utils.sql_utils import safe_ilike_pattern

from flask import Blueprint, render_template, request, redirect, url_for, current_app, flash, session
from flask_login import login_required, current_user
from app.extensions import csrf, db, limiter
from app.services.notification_service import NotificationService
from app.services.push_notification_service import PushNotificationService
from app.services.notification_analytics import NotificationAnalytics
from app.services.authorization_service import AuthorizationService
# WebSocket implementation - see app/routes/notifications_ws.py
from app.utils.transactions import no_auto_transaction, request_transaction_rollback
from app.utils.notifications import create_notification
from app.utils.request_validation import enforce_api_or_csrf_protection
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE, get_json_safe
from app.utils.request_utils import get_json_or_form, is_json_request
from app.routes.admin.shared import permission_required
from app.utils.api_responses import json_bad_request, json_created, json_forbidden, json_not_found, json_ok, json_ok_result, json_server_error, json_error_handler, require_json_data
from app.utils.error_handling import handle_json_view_exception
from app.models import Notification, NotificationType, NotificationCampaign
from config import Config
from datetime import datetime
from contextlib import suppress

bp = Blueprint("notifications", __name__, url_prefix="/notifications")

def _get_current_user_id() -> int:
    """
    Resolve the current user id robustly.

    In some edge/test scenarios, `current_user` can be a detached SQLAlchemy instance
    (e.g., after session cleanup/commit). If so, fall back to the Flask-Login session.
    """
    try:
        uid = getattr(current_user, "id", None)
        if uid is not None:
            return int(uid)
    except Exception as e:
        current_app.logger.debug("current_user.id extraction failed: %s", e)
    with suppress(Exception):
        sid = session.get("_user_id")
        if sid is not None:
            return int(sid)
    raise RuntimeError("Could not resolve current user id")


def get_notification_types_for_user(user):
    """
    Get notification types available for a user based on RBAC.

    Returns:
        dict: {
            'all': list of all notification type values,
            'for_user': list of notification types relevant to the user's role,
            'by_category': dict with 'focal_point', 'admin', 'both' keys
        }
    """
    all_types = [nt.value for nt in NotificationType]

    # Define which notification types are relevant for which roles
    focal_point_types = {
        'assignment_created',      # Focal points get new assignments
        'assignment_submitted',    # Focal points see when assignments are submitted
        'assignment_approved',     # Focal points get notified when their assignment is approved
        'assignment_reopened',     # Focal points get notified when assignment is reopened
        'form_updated',           # Focal points update forms
        'document_uploaded',      # Focal points see document uploads (when approved)
        'user_added_to_country',  # Focal points see new team members
        'self_report_created',    # Focal points create self-reports
        'deadline_reminder',      # Focal points have deadlines
        'admin_message',          # Focal points receive admin messages
    }

    admin_types = {
        'assignment_submitted',       # Admins review submitted assignments
        'assignment_approved',        # Admins approve assignments
        'assignment_reopened',        # Admins may reopen assignments
        'public_submission_received', # Admins review public submissions
        'document_uploaded',          # Admins review pending documents
        'template_updated',           # Admins manage templates
        'user_added_to_country',      # Admins manage users
        'admin_message',              # Admins receive admin messages
        'access_request_received',    # Admins receive country access requests
    }

    # Types available to both roles
    both_types = {
        'assignment_submitted',
        'assignment_approved',
        'assignment_reopened',
        'document_uploaded',
        'user_added_to_country',
        'admin_message',  # Admin messages can go to both roles
    }

    # Determine user's capabilities (RBAC-only)
    is_admin = AuthorizationService.is_admin(user)
    # "Focal point" is represented as assignment editor/submitter in RBAC
    is_focal_point = AuthorizationService.has_role(user, "assignment_editor_submitter")

    # Get relevant types for this user
    if is_admin and is_focal_point:
        # User has both roles - show all types
        relevant_types = all_types
    elif is_admin:
        # Admin only - show admin types
        relevant_types = [t for t in all_types if t in admin_types]
    elif is_focal_point:
        # Focal point only - show focal point types
        relevant_types = [t for t in all_types if t in focal_point_types]
    else:
        # Other roles - show minimal types
        relevant_types = []

    return {
        'all': all_types,
        'for_user': relevant_types,
        'by_category': {
            'focal_point': [t for t in all_types if t in focal_point_types and t not in both_types],
            'admin': [t for t in all_types if t in admin_types and t not in both_types],
            'both': list(both_types)
        }
    }


@bp.route("/", methods=["GET"])
@login_required
def notifications_center():
    """Notification center UI"""
    from flask_babel import gettext as _

    preferences = NotificationService.get_notification_preferences(current_user.id)
    notification_types_info = get_notification_types_for_user(current_user)
    notification_types = notification_types_info['for_user']

    # Create a dictionary mapping notification types to their translated labels
    notification_type_labels = {
        'assignment_created': _('Assignment Created'),
        'assignment_submitted': _('Assignment Submitted'),
        'assignment_approved': _('Assignment Approved'),
        'assignment_reopened': _('Assignment Reopened'),
        'public_submission_received': _('Public Submission Received'),
        'form_updated': _('Form Updated'),
        'document_uploaded': _('Document Uploaded'),
        'user_added_to_country': _('User Added to Country'),
        'template_updated': _('Template Updated'),
        'self_report_created': _('Self Report Created'),
        'deadline_reminder': _('Deadline Reminder'),
        'admin_message': _('Admin Message'),
        'access_request_received': _('Access Request Received'),
    }


    return render_template(
        "notifications/center.html",
        title="Notifications",
        preferences=preferences,
        notification_types=notification_types,
        notification_types_info=notification_types_info,
        notification_type_labels=notification_type_labels
    )


@bp.route("/mark-read", methods=["POST"])
@login_required
@limiter.limit("30 per minute")  # Rate limit: 30 requests per minute per user
@csrf.exempt  # Exempt from CSRF protection for API endpoints used by mobile app
def mark_notifications_read():
    """Mark notifications as read"""
    enforce_api_or_csrf_protection()
    try:
        current_app.logger.info(f"Mark notifications as read request from user {current_user.id}")

        # Check if request has JSON data
        if not is_json_request():
            current_app.logger.warning("Request is not JSON, trying form data")

        data = get_json_or_form()
        notification_ids = data.get('notification_ids', [])

        current_app.logger.info(f"Received notification_ids: {notification_ids} (type: {type(notification_ids)})")

        if not notification_ids:
            current_app.logger.warning("No notification_ids provided")
            return json_bad_request('No notifications specified')

        # Convert to list of ints if needed
        if isinstance(notification_ids, str):
            notification_ids = [int(id.strip()) for id in notification_ids.split(',') if id.strip().isdigit()]
        elif not isinstance(notification_ids, list):
            notification_ids = [notification_ids] if notification_ids else []

        # Ensure all IDs are integers
        try:
            notification_ids = [int(id) for id in notification_ids]
        except (ValueError, TypeError) as e:
            current_app.logger.error(f"Invalid notification_ids format: {e}")
            return json_bad_request('Invalid notification IDs format')

        current_app.logger.info(f"Processing {len(notification_ids)} notification IDs: {notification_ids}")

        success = NotificationService.mark_as_read(notification_ids, current_user.id)

        if success:
            # Get updated counts
            unread_count = NotificationService.get_unread_count(current_user.id)
            archived_count = NotificationService.get_archived_count(current_user.id)
            all_count = NotificationService.get_all_count(current_user.id)

            # Update device activity if device_token provided in header (non-blocking)
            device_token = request.headers.get('X-Device-Token')
            if device_token:
                with suppress(Exception):  # Ignore errors - non-critical
                    PushNotificationService.update_device_activity(
                        user_id=current_user.id,
                        device_token=device_token,
                        throttle_minutes=5
                    )

            current_app.logger.info(f"Successfully marked {len(notification_ids)} notifications as read for user {current_user.id}")

            return json_ok(
                success=True,
                unread_count=unread_count,
                archived_count=archived_count,
                all_count=all_count
            )
        else:
            current_app.logger.warning(f"Failed to mark notifications as read for user {current_user.id}. IDs: {notification_ids}")
            return json_server_error('Failed to update notifications. Some notifications may not be accessible.')

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/mark-unread", methods=["POST"])
@login_required
@csrf.exempt  # Exempt from CSRF protection for API endpoints used by mobile app
def mark_notifications_unread():
    """Mark notifications as unread"""
    enforce_api_or_csrf_protection()
    try:
        current_app.logger.info(f"Mark notifications as unread request from user {current_user.id}")

        # Check if request has JSON data
        if not is_json_request():
            current_app.logger.warning("Request is not JSON, trying form data")

        data = get_json_or_form()
        notification_ids = data.get('notification_ids', [])

        current_app.logger.info(f"Received notification_ids: {notification_ids} (type: {type(notification_ids)})")

        if not notification_ids:
            current_app.logger.warning("No notification_ids provided")
            return json_bad_request('No notifications specified')

        # Convert to list of ints if needed
        if isinstance(notification_ids, str):
            notification_ids = [int(id.strip()) for id in notification_ids.split(',') if id.strip().isdigit()]
        elif not isinstance(notification_ids, list):
            notification_ids = [notification_ids] if notification_ids else []

        # Ensure all IDs are integers
        try:
            notification_ids = [int(id) for id in notification_ids]
        except (ValueError, TypeError) as e:
            current_app.logger.error(f"Invalid notification_ids format: {e}")
            return json_bad_request('Invalid notification IDs format')

        current_app.logger.info(f"Processing {len(notification_ids)} notification IDs: {notification_ids}")

        success = NotificationService.mark_as_unread(notification_ids, current_user.id)

        if success:
            # Get updated counts
            unread_count = NotificationService.get_unread_count(current_user.id)
            archived_count = NotificationService.get_archived_count(current_user.id)
            all_count = NotificationService.get_all_count(current_user.id)

            current_app.logger.info(f"Successfully marked {len(notification_ids)} notifications as unread for user {current_user.id}")

            return json_ok(
                success=True,
                unread_count=unread_count,
                archived_count=archived_count,
                all_count=all_count
            )
        else:
            current_app.logger.warning(f"Failed to mark notifications as unread for user {current_user.id}. IDs: {notification_ids}")
            return json_server_error('Failed to update notifications. Some notifications may not be accessible.')

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api", methods=["GET"])
@login_required
@limiter.limit("60 per minute")  # Rate limit: 60 requests per minute per user
def api_get_notifications():
    """Get notifications for the current user via API with pagination and filtering"""
    try:
        # Set language from query parameter if provided (for Flutter app)
        language = request.args.get('language')
        supported = current_app.config.get('SUPPORTED_LANGUAGES', Config.LANGUAGES)
        if language and language in (supported or []):
            session['language'] = language
            session.permanent = True  # Ensure session persists
            # Force Babel to use the new locale for this request
            from flask_babel import force_locale, refresh, get_locale
            try:
                # Refresh translations to pick up the new locale
                refresh()
                # Verify locale is set
                from app.utils.form_localization import get_translation_key
                current_locale = get_translation_key()
                current_app.logger.info(
                    f"Set session language to {language} from API request. "
                    f"Session language: {session.get('language')}, Babel locale: {current_locale}"
                )
            except Exception as e:
                current_app.logger.warning(f"Error refreshing Babel after setting language: {e}")
                # Continue anyway - force_locale will still work

        # Get pagination parameters
        from app.utils.api_pagination import validate_pagination_params
        page, per_page = validate_pagination_params(request.args, default_per_page=20, max_per_page=100)
        offset = (page - 1) * per_page

        # Get filter parameters
        unread_only = request.args.get('unread_only', 'false').lower() == 'true'
        notification_type = request.args.get('type', None)
        include_archived = request.args.get('include_archived', 'false').lower() == 'true'
        archived_only = request.args.get('archived_only', 'false').lower() == 'true'
        category = request.args.get('category', None)

        # Tags filter (comma-separated)
        tags = None
        if request.args.get('tags'):
            tags = [tag.strip() for tag in request.args.get('tags').split(',') if tag.strip()]

        # Date filters
        date_from = None
        date_to = None
        if request.args.get('date_from'):
            with suppress(ValueError):
                date_from = datetime.fromisoformat(request.args.get('date_from'))
        if request.args.get('date_to'):
            with suppress(ValueError):
                date_to = datetime.fromisoformat(request.args.get('date_to'))

        # Get notifications with pagination
        notifications_data, total_count = NotificationService.get_user_notifications(
            current_user.id,
            unread_only=unread_only,
            notification_type=notification_type,
            date_from=date_from,
            date_to=date_to,
            include_archived=include_archived,
            archived_only=archived_only,
            category=category,
            tags=tags,
            limit=per_page,
            offset=offset
        )

        # Get counts for all tabs
        unread_count = NotificationService.get_unread_count(current_user.id)
        archived_count = NotificationService.get_archived_count(current_user.id)
        all_count = NotificationService.get_all_count(current_user.id)
        has_more = (offset + len(notifications_data)) < total_count

        # Update device activity if device_token provided in header (non-blocking)
        device_token = request.headers.get('X-Device-Token')
        if device_token:
            with suppress(Exception):  # Ignore errors - non-critical
                PushNotificationService.update_device_activity(
                    user_id=current_user.id,
                    device_token=device_token,
                    throttle_minutes=5
                )

        return json_ok(
            success=True,
            notifications=notifications_data,
            unread_count=unread_count,
            archived_count=archived_count,
            all_count=all_count,
            total_count=total_count,
            page=page,
            per_page=per_page,
            has_more=has_more
        )

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/count", methods=["GET"])
@login_required
@limiter.limit("60 per minute")  # Rate limit: 60 requests per minute per user
def api_get_notification_count():
    """Get unread notification count for the current user"""
    try:
        user_id = _get_current_user_id()
        unread_count = NotificationService.get_unread_count(user_id)

        # Update device activity if device_token provided in header (non-blocking)
        device_token = request.headers.get('X-Device-Token')
        if device_token:
            with suppress(Exception):  # Ignore errors - non-critical
                PushNotificationService.update_device_activity(
                    user_id=user_id,
                    device_token=device_token,
                    throttle_minutes=5
                )

        return json_ok(success=True, unread_count=unread_count)

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/stream/status", methods=["GET"])
@login_required
def api_notification_stream_status():
    """
    Check if WebSocket is enabled on the server.
    Used by frontend to determine if WebSocket connection should be attempted.
    Login-required version with full diagnostics.
    """
    # IMPORTANT: Return a minimal boolean for the frontend, but also include
    # diagnostic fields to troubleshoot env/config mismatches in deployments.
    # This endpoint is login-protected, so the extra fields are not publicly exposed.
    import os

    websocket_enabled = bool(current_app.config.get('WEBSOCKET_ENABLED', True))

    raw_env_value = os.environ.get('WEBSOCKET_ENABLED')
    normalized_env_value = (raw_env_value if raw_env_value is not None else '').strip().lower()
    parsed_env_value = (normalized_env_value == 'true') if raw_env_value is not None else None

    # Optional: detect whether websocket dependency is installed (endpoint registration depends on it)
    try:
        import flask_sock  # type: ignore
        flask_sock_available = True
        flask_sock_error = None
    except Exception as e:
        flask_sock_available = False
        flask_sock_error = GENERIC_ERROR_MESSAGE

    # Feature flag exists but is separate from global websocket enablement.
    notifications_feature_enabled = None
    try:
        features = current_app.config.get('FEATURES') or {}
        notifications_feature_enabled = features.get('notifications_websocket_enabled')
    except Exception as e:
        current_app.logger.debug("FEATURES config lookup failed: %s", e)
        notifications_feature_enabled = None

    return json_ok(
        success=True,
        enabled=websocket_enabled,
        websocket_enabled=websocket_enabled,
        websocket_endpoint='/api/notifications/ws',
        diagnostics={
            'flask_config': current_app.config.get('FLASK_CONFIG') or os.environ.get('FLASK_CONFIG'),
            'config_websocket_enabled': websocket_enabled,
            'env_WEBSOCKET_ENABLED_raw': raw_env_value,
            'env_WEBSOCKET_ENABLED_normalized': normalized_env_value,
            'env_WEBSOCKET_ENABLED_parsed': parsed_env_value,
            'flask_sock_available': flask_sock_available,
            'flask_sock_error': flask_sock_error,
            'features_notifications_websocket_enabled': notifications_feature_enabled,
        }
    )


@bp.route("/api/archive", methods=["POST"])
@login_required
def api_archive_notifications():
    """Archive selected notifications"""
    try:
        data = get_json_safe()
        notification_ids = data.get('notification_ids', [])

        if not notification_ids:
            return json_bad_request('No notifications specified', success=False)

        user_id = _get_current_user_id()
        # Archive notifications (service handles ownership validation)
        success = NotificationService.archive_notifications(notification_ids, user_id)

        if success:
            # Get updated counts
            unread_count = NotificationService.get_unread_count(user_id)
            archived_count = NotificationService.get_archived_count(user_id)
            all_count = NotificationService.get_all_count(user_id)

            return json_ok(
                success=True,
                unread_count=unread_count,
                archived_count=archived_count,
                all_count=all_count
            )
        else:
            return json_server_error('Failed to archive notifications', success=False)

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/delete", methods=["DELETE"])
@login_required
def api_delete_notifications():
    """Delete selected notifications"""
    try:
        data = get_json_safe()
        notification_ids = data.get('notification_ids', [])

        if not notification_ids:
            return json_bad_request('No notifications specified', success=False)

        user_id = _get_current_user_id()
        # Delete notifications (service handles ownership validation)
        success = NotificationService.delete_notifications(notification_ids, user_id)

        if success:
            # Get updated counts
            unread_count = NotificationService.get_unread_count(user_id)
            archived_count = NotificationService.get_archived_count(user_id)
            all_count = NotificationService.get_all_count(user_id)

            return json_ok(
                success=True,
                unread_count=unread_count,
                archived_count=archived_count,
                all_count=all_count
            )
        else:
            return json_server_error('Failed to delete notifications', success=False)

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/preferences", methods=["GET"])
@login_required
def api_get_notification_preferences():
    """Get notification preferences for current user"""
    try:
        preferences = NotificationService.get_notification_preferences(current_user.id)

        return json_ok(
            success=True,
            preferences={
                'email_notifications': preferences.email_notifications,
                'notification_types_enabled': preferences.notification_types_enabled,
                'notification_frequency': preferences.notification_frequency,
                'sound_enabled': preferences.sound_enabled,
                'push_notifications': getattr(preferences, 'push_notifications', True),
                'push_notification_types_enabled': getattr(preferences, 'push_notification_types_enabled', []),
                'digest_day': getattr(preferences, 'digest_day', None),
                'digest_time': getattr(preferences, 'digest_time', None),
                'timezone': getattr(preferences, 'timezone', None)
            }
        )

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/preferences", methods=["POST"])
@login_required
@csrf.exempt  # Exempt from CSRF protection for API endpoints used by mobile app
def api_update_notification_preferences():
    """Update notification preferences for current user"""
    enforce_api_or_csrf_protection()
    try:
        # Try to get JSON data - handle both JSON and form data
        data = None
        current_app.logger.info(f"Request method: {request.method}")
        current_app.logger.info(f"Content-Type: {request.content_type}")
        current_app.logger.info(f"is_json: {is_json_request()}")
        current_app.logger.info(f"Request data length: {len(request.data) if request.data else 0}")

        if is_json_request():
            data = get_json_safe()
            current_app.logger.info("Got data from get_json_safe()")
        elif request.content_type and 'application/json' in request.content_type:
            # Force JSON parsing even if is_json is False
            try:
                import json
                data = json.loads(request.data)
                current_app.logger.info("Got data from manual JSON parsing")
            except Exception as e:
                current_app.logger.error(f"Failed to parse JSON: {e}", exc_info=True)
                return json_bad_request(GENERIC_ERROR_MESSAGE, success=False)
        else:
            # Try to get from form data as fallback
            current_app.logger.warning(f"Request is not JSON, content-type: {request.content_type}")
            data = request.form.to_dict()
            err = require_json_data(data, 'No data provided. Request must be JSON with Content-Type: application/json')
            if err:
                current_app.logger.warning("No data in request")
                return err

        if data is None:
            current_app.logger.error("Request data is None after all attempts")
            return json_bad_request('Invalid request data - could not parse JSON', success=False)

        user_id = _get_current_user_id()
        current_app.logger.info(f"Updating preferences for user {user_id}")
        current_app.logger.info(f"Request data: {data}")
        current_app.logger.info(f"Content-Type: {request.content_type}")
        current_app.logger.info(f"is_json: {is_json_request()}")

        # Update preferences - pass all fields, including None values for digest fields
        # The service will handle None appropriately
        try:
            preferences = NotificationService.update_notification_preferences(
                user_id,
                email_notifications=data.get('email_notifications'),
                notification_types_enabled=data.get('notification_types_enabled'),
                notification_frequency=data.get('notification_frequency'),
                sound_enabled=data.get('sound_enabled'),
                push_notifications=data.get('push_notifications'),
                push_notification_types_enabled=data.get('push_notification_types_enabled'),
                digest_day=data.get('digest_day'),  # Will be None if not provided or explicitly null
                digest_time=data.get('digest_time'),  # Will be None if not provided or explicitly null
                timezone=data.get('timezone')  # Will be None if not provided or explicitly null
            )
        except Exception as service_error:
            return handle_json_view_exception(service_error, 'Service error.', status_code=500)

        if preferences:
            return json_ok(
                success=True,
                preferences={
                    'email_notifications': preferences.email_notifications,
                    'notification_types_enabled': preferences.notification_types_enabled,
                    'notification_frequency': preferences.notification_frequency,
                    'sound_enabled': preferences.sound_enabled,
                    'push_notifications': getattr(preferences, 'push_notifications', True),
                    'push_notification_types_enabled': getattr(preferences, 'push_notification_types_enabled', []),
                    'digest_day': getattr(preferences, 'digest_day', None),
                    'digest_time': getattr(preferences, 'digest_time', None),
                    'timezone': getattr(preferences, 'timezone', None)
                }
            )
        else:
            current_app.logger.error("Service returned None - preferences update failed")
            return json_server_error('Failed to update preferences - service returned None', success=False)

    except ValueError as e:
        current_app.logger.error(f"Validation error updating preferences: {str(e)}")
        return json_bad_request(GENERIC_ERROR_MESSAGE, success=False)
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


# ========== Analytics Endpoints ==========

@bp.route("/api/analytics/summary", methods=["GET"])
@login_required
@permission_required('admin.analytics.view')
@json_error_handler('Notification analytics summary')
def api_get_analytics_summary():
    """Get notification analytics summary (admin only)"""
    days = request.args.get('days', 30, type=int)
    result = NotificationAnalytics.get_summary(days=days)
    return json_ok_result(result)


@bp.route("/api/analytics/delivery-rates", methods=["GET"])
@login_required
@permission_required('admin.analytics.view')
@json_error_handler('Notification delivery rates')
def api_get_delivery_rates():
    """Get notification delivery rates by type (admin only)"""
    days = request.args.get('days', 30, type=int)
    result = NotificationAnalytics.get_delivery_rates(days=days)
    return json_ok_result(result)


@bp.route("/api/analytics/read-rates", methods=["GET"])
@login_required
@permission_required('admin.analytics.view')
@json_error_handler('Notification read rates')
def api_get_read_rates():
    """Get notification read rates by type and priority (admin only)"""
    days = request.args.get('days', 30, type=int)
    result = NotificationAnalytics.get_read_rates(days=days)
    return json_ok_result(result)


@bp.route("/api/analytics/peak-times", methods=["GET"])
@login_required
@permission_required('admin.analytics.view')
@json_error_handler('Notification peak times')
def api_get_peak_times():
    """Get peak notification times (admin only)"""
    days = request.args.get('days', 30, type=int)
    result = NotificationAnalytics.get_peak_times(days=days)
    return json_ok_result(result)


@bp.route("/api/analytics/user-engagement", methods=["GET"])
@login_required
@permission_required('admin.analytics.view')
@json_error_handler('Notification user engagement')
def api_get_user_engagement():
    """Get user engagement statistics (admin only)"""
    days = request.args.get('days', 30, type=int)
    limit = request.args.get('limit', 20, type=int)
    result = NotificationAnalytics.get_user_engagement(days=days, limit=limit)
    return json_ok_result(result)


# ========== Action Buttons ==========

@bp.route("/api/<int:notification_id>/view", methods=["POST"])
@login_required
def api_view_notification(notification_id):
    """Track when a notification is viewed (distinct from read)"""
    try:
        notification = Notification.query.filter_by(
            id=notification_id,
            user_id=current_user.id
        ).first()

        if not notification:
            return json_not_found('Notification not found', success=False)

        # Only set viewed_at if not already set
        if not notification.viewed_at:
            try:
                notification.viewed_at = utcnow()
                db.session.flush()
            except Exception as commit_error:
                return handle_json_view_exception(commit_error, GENERIC_ERROR_MESSAGE, status_code=500)

        return json_ok(
            success=True,
            viewed_at=notification.viewed_at.isoformat() if notification.viewed_at else None
        )

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/<int:notification_id>/action", methods=["POST"])
@login_required
def api_notification_action(notification_id):
    """Handle action button click for a notification"""
    try:
        data = get_json_safe()
        action = data.get('action')

        if not action:
            return json_bad_request('No action specified', success=False)

        notification = Notification.query.filter_by(
            id=notification_id,
            user_id=current_user.id
        ).first()

        if not notification:
            return json_not_found('Notification not found', success=False)

        # Check if action is valid
        if not notification.action_buttons:
            return json_bad_request('No actions available', success=False)

        valid_actions = [btn.get('action') for btn in notification.action_buttons]
        if action not in valid_actions:
            return json_bad_request('Invalid action', success=False)

        # Authorization check: Verify user has permission to perform this action.
        # Actions like 'approve', 'reject' require admin privileges.
        from app.services.authorization_service import AuthorizationService
        if action in ('approve', 'reject') and not AuthorizationService.is_admin(current_user):
            current_app.logger.warning(
                f"User {current_user.id} attempted unauthorized action '{action}' "
                f"on notification {notification_id}"
            )
            return json_forbidden('Unauthorized to perform this action', success=False)

        # Record action taken
        try:
            notification.action_taken = action
            notification.action_taken_at = utcnow()
            from app import db
            db.session.flush()
        except Exception as commit_error:
            return handle_json_view_exception(commit_error, GENERIC_ERROR_MESSAGE, status_code=500)

        # Find the action button to get endpoint
        action_button = next((btn for btn in notification.action_buttons if btn.get('action') == action), None)

        # Validate endpoint before returning it
        endpoint = action_button.get('endpoint') if action_button else None
        if endpoint:
            from app.utils.notifications import validate_action_button_endpoint
            if not validate_action_button_endpoint(endpoint):
                current_app.logger.warning(
                    f"User {current_user.id} attempted to use unsafe endpoint '{endpoint}' "
                    f"from notification {notification_id}"
                )
                # Return success but without endpoint (client should handle gracefully)
                endpoint = None

        return json_ok(success=True, action=action, endpoint=endpoint)

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


# ========== Scheduling ==========

@bp.route("/api/schedule", methods=["POST"])
@login_required
@permission_required('admin.notifications.manage')
def api_schedule_notification():
    """Schedule a notification to be sent at a future time"""
    try:
        data = get_json_safe()
        user_ids = data.get('user_ids', [])
        notification_type_str = data.get('notification_type')
        scheduled_for_str = data.get('scheduled_for')
        title = data.get('title')
        message = data.get('message')

        if not user_ids:
            return json_bad_request('No users specified', success=False)

        if not notification_type_str:
            return json_bad_request('Notification type is required', success=False)

        if not scheduled_for_str:
            return json_bad_request('Scheduled time is required', success=False)

        # Parse notification type
        try:
            notification_type = NotificationType[notification_type_str]
        except (KeyError, AttributeError):
            return json_bad_request(f'Invalid notification type: {notification_type_str}', success=False)

        # Parse scheduled_for datetime
        try:
            scheduled_for = datetime.fromisoformat(scheduled_for_str.replace('Z', '+00:00'))
        except ValueError:
            return json_bad_request('Invalid scheduled_for format. Use ISO 8601 format.', success=False)

        # Create scheduled notification
        from app.utils.notification_scheduling import create_scheduled_notification

        notifications = create_scheduled_notification(
            user_ids=user_ids,
            notification_type=notification_type,
            scheduled_for=scheduled_for,
            title=title,
            message=message,
            category=data.get('category'),
            tags=data.get('tags'),
            priority=data.get('priority', 'normal')
        )

        return json_ok(
            success=True,
            count=len(notifications),
            scheduled_for=scheduled_for.isoformat(),
            notification_ids=[n.id for n in notifications]
        )

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


# ========== Search ==========

@bp.route("/api/search", methods=["GET"])
@login_required
def api_search_notifications():
    """Search notifications"""
    try:
        query = (request.args.get('q') or '').strip()
        notification_type = request.args.get('type')
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')

        # Parse date filters
        date_from_dt = None
        date_to_dt = None
        if date_from:
            with suppress(ValueError):
                date_from_dt = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
        if date_to:
            with suppress(ValueError):
                date_to_dt = datetime.fromisoformat(date_to.replace('Z', '+00:00'))

        # Enhanced search: Try full-text search if PostgreSQL is available
        search_results = []
        if query:
            try:
                from sqlalchemy import func, or_
                from app.models import Notification
                from sqlalchemy.dialects.postgresql import TSVECTOR

                # Try PostgreSQL full-text search
                query_lower = query.lower()
                search_query = Notification.query.filter(
                    Notification.user_id == current_user.id,
                    # Filter out expired notifications
                    or_(
                        Notification.expires_at.is_(None),
                        Notification.expires_at > utcnow()
                    )
                )

                # Add text search conditions
                safe_pattern = safe_ilike_pattern(query)
                text_conditions = or_(
                    Notification.title.ilike(safe_pattern),
                    Notification.message.ilike(safe_pattern),
                    # Search in entity names via notification data
                    cast(Notification.message_params, String).ilike(safe_pattern)
                )
                search_query = search_query.filter(text_conditions)

                # Apply additional filters
                if notification_type:
                    from sqlalchemy import cast, String
                    from app.models.enums import NotificationType as _NT
                    try:
                        if isinstance(notification_type, _NT):
                            nt_value = notification_type.value
                        else:
                            nt_value = str(notification_type)
                    except Exception as e:
                        current_app.logger.debug("notification_type.value extraction failed: %s", e)
                        nt_value = str(notification_type)
                    search_query = search_query.filter(cast(Notification.notification_type, String) == nt_value)

                if date_from_dt:
                    search_query = search_query.filter(Notification.created_at >= date_from_dt)
                if date_to_dt:
                    search_query = search_query.filter(Notification.created_at <= date_to_dt)

                # Get notifications with relevance scoring
                notifications_list = search_query.order_by(
                    Notification.created_at.desc()
                ).limit(100).all()

                # Format results using service method for consistency
                if notifications_list:
                    # Use service method to format properly
                    search_results, _ = NotificationService.get_user_notifications(
                        user_id=current_user.id,
                        unread_only=False,
                        notification_type=notification_type,
                        date_from=date_from_dt,
                        date_to=date_to_dt,
                        include_archived=False,
                        archived_only=False,
                        limit=100,
                        offset=0
                    )
                    # Filter by query text (title, message, entity_name)
                    query_lower = query.lower()
                    search_results = [
                        n for n in search_results
                        if (query_lower in n.get('title', '').lower() or
                            query_lower in n.get('message', '').lower() or
                            query_lower in (n.get('entity_name', '') or '').lower())
                    ]
                else:
                    search_results = []

            except Exception as e:
                current_app.logger.warning(f"Error in enhanced search, falling back to simple search: {e}")
                # Fallback to simple search
                notifications, total = NotificationService.get_user_notifications(
                    user_id=current_user.id,
                    unread_only=False,
                    notification_type=notification_type,
                    date_from=date_from_dt,
                    date_to=date_to_dt,
                    include_archived=False,
                    archived_only=False,
                    limit=100,
                    offset=0
                )

                query_lower = query.lower()
                search_results = [
                    n for n in notifications
                    if (query_lower in n.get('title', '').lower() or
                        query_lower in n.get('message', '').lower() or
                        query_lower in (n.get('entity_name', '') or '').lower())
                ]
        else:
            # No search query, just return filtered results
            search_results, total = NotificationService.get_user_notifications(
                user_id=current_user.id,
                unread_only=False,
                notification_type=notification_type,
                date_from=date_from_dt,
                date_to=date_to_dt,
                include_archived=False,
                archived_only=False,
                limit=100,
                offset=0
            )

        notifications = search_results

        return json_ok(success=True, notifications=notifications, total=len(notifications))

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


# ========== Export ==========

@bp.route("/api/export", methods=["GET"])
@login_required
def api_export_notifications():
    """Export notifications as CSV or JSON"""
    try:
        format_type = request.args.get('format', 'json').lower()
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')

        # Parse date filters
        date_from_dt = None
        date_to_dt = None
        if date_from:
            with suppress(ValueError):
                date_from_dt = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
        if date_to:
            with suppress(ValueError):
                date_to_dt = datetime.fromisoformat(date_to.replace('Z', '+00:00'))

        # Get all user's notifications with proper parameters
        notifications, total = NotificationService.get_user_notifications(
            user_id=current_user.id,
            unread_only=False,
            notification_type=None,
            date_from=date_from_dt,
            date_to=date_to_dt,
            include_archived=False,
            archived_only=False,
            limit=10000,  # Large limit for export
            offset=0
        )

        if format_type == 'csv':
            from flask import Response
            import csv
            import io

            output = io.StringIO()
            writer = csv.writer(output)

            # Write header
            writer.writerow(['ID', 'Title', 'Message', 'Type', 'Priority', 'Read', 'Created At', 'Related URL'])

            # Write data
            for n in notifications:
                writer.writerow([
                    n.get('id'),
                    n.get('title', ''),
                    n.get('message', ''),
                    n.get('type', ''),
                    n.get('priority', ''),
                    'Yes' if n.get('is_read') else 'No',
                    n.get('created_at', ''),
                    n.get('related_url', '')
                ])

            output.seek(0)
            return Response(
                output.getvalue(),
                mimetype='text/csv',
                headers={'Content-Disposition': f'attachment; filename=notifications_{utcnow().strftime("%Y%m%d")}.csv'}
            )
        else:
            # JSON export
            return json_ok(
                success=True,
                notifications=notifications,
                total=len(notifications),
                exported_at=utcnow().isoformat()
            )

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/devices/register", methods=["POST"])
@login_required
@json_error_handler('Device register')
def register_device():
    """Register a device for push notifications"""
    try:
        data = get_json_or_form()

        device_token = data.get('device_token')
        platform = data.get('platform')  # 'ios' or 'android'
        app_version = data.get('app_version')
        device_model = data.get('device_model')
        device_name = data.get('device_name')
        os_version = data.get('os_version')
        timezone = data.get('timezone')

        # Get IP address from request
        ip_address = None
        if request.headers.getlist("X-Forwarded-For"):
            ip_address = request.headers.getlist("X-Forwarded-For")[0].split(',')[0].strip()
        elif request.remote_addr:
            ip_address = request.remote_addr

        if not device_token:
            return json_bad_request('device_token is required', success=False)

        if not platform or platform not in ['ios', 'android']:
            return json_bad_request('platform must be "ios" or "android"', success=False)

        result = PushNotificationService.register_device(
            user_id=current_user.id,
            device_token=device_token,
            platform=platform,
            app_version=app_version,
            device_model=device_model,
            device_name=device_name,
            os_version=os_version,
            ip_address=ip_address,
            timezone=timezone
        )

        if result.get('success'):
            return json_ok(**result)
        else:
            return json_bad_request(result.get('error', result.get('message', 'Operation failed')), **result)

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/devices/unregister", methods=["POST"])
@login_required
@json_error_handler('Device unregister')
def unregister_device():
    """Unregister a device for push notifications"""
    try:
        data = get_json_or_form()

        device_token = data.get('device_token')

        if not device_token:
            return json_bad_request('device_token is required', success=False)

        result = PushNotificationService.unregister_device(
            user_id=current_user.id,
            device_token=device_token
        )

        if result.get('success'):
            return json_ok(**result)
        else:
            return json_bad_request(result.get('error', result.get('message', 'Operation failed')), **result)

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/devices/heartbeat", methods=["POST"])
@login_required
@csrf.exempt  # Exempt from CSRF protection for API endpoints used by mobile app
def device_heartbeat():
    """
    Lightweight heartbeat endpoint to update device last_active_at.
    Throttled to prevent excessive database writes (max once per 5 minutes per device).
    """
    enforce_api_or_csrf_protection()
    try:
        # Get device_token from body or header
        data = get_json_or_form()
        device_token = data.get('device_token') or request.headers.get('X-Device-Token')

        if not device_token:
            return json_bad_request('device_token is required', success=False)

        # Update device activity (throttled internally)
        updated = PushNotificationService.update_device_activity(
            user_id=current_user.id,
            device_token=device_token,
            throttle_minutes=5
        )

        return json_ok(
            success=True,
            updated=updated,
            message='Heartbeat received' if updated else 'Heartbeat throttled (too soon since last update)'
        )

    except Exception as e:
        current_app.logger.debug(f"Error in device heartbeat (non-critical): {str(e)}")
        # Return success even on error - heartbeat is non-critical
        return json_ok(updated=False)


@bp.route("/api/admin/assignments", methods=["GET"])
@login_required
@permission_required('admin.notifications.manage')
def api_admin_assignments():
    """List assignments for attachment dropdown (admin only). Returns id and label (template name - period)."""
    try:
        from app.models import AssignedForm
        assignments = AssignedForm.query.order_by(AssignedForm.period_name.desc(), AssignedForm.assigned_at.desc()).all()
        from app.utils.form_localization import get_localized_template_name, get_translation_key
        translation_key = get_translation_key()
        result = []
        for af in assignments:
            template_name = getattr(af.template, 'name', None) if af.template else None
            if af.template and hasattr(af.template, 'published_version_id') and af.template.published_version_id:
                try:
                    from app.models import FormTemplateVersion
                    ver = FormTemplateVersion.query.get(af.template.published_version_id)
                    if ver and getattr(ver, 'name_translations', None):
                        names = ver.name_translations or {}
                        template_name = (names.get(translation_key) or names.get('en') or template_name) or str(af.template_id)
                except Exception as e:
                    current_app.logger.debug("assignment label template_name fallback failed: %s", e)
            label = f"{template_name or 'Assignment'} - {af.period_name}"
            result.append({'id': af.id, 'label': label})
        return json_ok(assignments=result)
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/admin/send-push", methods=["POST"])
@login_required
@permission_required('admin.notifications.manage')
@limiter.limit("10 per minute")  # Rate limit: 10 admin push notifications per minute
@csrf.exempt  # Exempt from CSRF protection for API endpoints used by mobile app
def api_admin_send_push():
    """Send custom push notification to selected users (admin only)"""
    enforce_api_or_csrf_protection()
    try:
        def flash_if_html(message: str, category: str) -> None:
            # For JSON/AJAX calls, don't store flash in session (prevents stale flashes later).
            if not is_json_request():
                flash(message, category)

        data = get_json_safe()
        user_ids = data.get('user_ids', [])
        # Sanitize input to prevent XSS attacks
        from markupsafe import escape
        title = escape((data.get('title') or '').strip())
        message = escape((data.get('message') or '').strip())
        priority = data.get('priority', 'normal')
        redirect_url = (data.get('redirect_url') or '').strip()
        override_preferences = data.get('override_preferences', False)  # Admin override flag
        send_email = data.get('send_email', False)  # Default to False - must be explicitly enabled
        send_push = data.get('send_push', False)  # Default to False - must be explicitly enabled
        category = data.get('category')  # Optional category
        tags = data.get('tags')  # Optional tags (list or comma-separated string)

        # Validation - All validation should be done server-side for security
        # At least one delivery method must be selected
        if not send_email and not send_push:
            error_message = 'Please select at least one delivery method (Email or Push Notification).'
            flash_if_html(error_message, 'danger')
            return json_bad_request(error_message, success=False, flash_message=error_message, flash_category='danger')

        if not user_ids:
            error_message = 'No users selected. Please select at least one user.'
            flash_if_html(error_message, 'danger')
            return json_bad_request(error_message, success=False, flash_message=error_message, flash_category='danger')

        if not title:
            error_message = 'Title is required.'
            flash_if_html(error_message, 'danger')
            return json_bad_request(error_message, success=False, flash_message=error_message, flash_category='danger')

        if not message:
            error_message = 'Message is required.'
            flash_if_html(error_message, 'danger')
            return json_bad_request(error_message, success=False, flash_message=error_message, flash_category='danger')

        if len(title) > 100:
            error_message = 'Title must be 100 characters or less.'
            flash_if_html(error_message, 'danger')
            return json_bad_request(error_message, success=False, flash_message=error_message, flash_category='danger')

        if len(message) > 500:
            error_message = 'Message must be 500 characters or less.'
            flash_if_html(error_message, 'danger')
            return json_bad_request(error_message, success=False, flash_message=error_message, flash_category='danger')

        if priority not in ['normal', 'high']:
            priority = 'normal'

        # Validate redirect URL if provided (only relevant if push is enabled)
        if send_push and redirect_url:
            # SECURITY: Avoid open redirects in push notifications.
            # Only allow internal relative paths.
            if not redirect_url.startswith('/'):
                error_message = 'Redirect URL must start with /'
                flash_if_html(error_message, 'danger')
                return json_bad_request(error_message, success=False, flash_message=error_message, flash_category='danger')
            if len(redirect_url) > 500:
                error_message = 'Redirect URL must be 500 characters or less.'
                flash_if_html(error_message, 'danger')
                return json_bad_request(error_message, success=False, flash_message=error_message, flash_category='danger')
        elif not send_push and redirect_url:
            # If push is not enabled, ignore redirect URL
            redirect_url = None

        # Ensure user_ids is a list
        if isinstance(user_ids, str):
            try:
                user_ids = [int(id.strip()) for id in user_ids.split(',') if id.strip().isdigit()]
            except ValueError:
                return json_bad_request('Invalid user IDs format', success=False)
        elif not isinstance(user_ids, list):
            user_ids = [user_ids] if user_ids else []

        # Validate user IDs exist
        from app.models import User
        valid_user_ids = []
        for user_id in user_ids:
            try:
                user_id = int(user_id)
                user = User.query.get(user_id)
                if user:
                    valid_user_ids.append(user_id)
            except (ValueError, TypeError):
                continue

        if not valid_user_ids:
            error_message = 'No valid users found. Please select valid users.'
            flash_if_html(error_message, 'danger')
            return json_bad_request(error_message, success=False, flash_message=error_message, flash_category='danger')

        # Email protection (dev/staging): fail fast if any selected user email is not in allowlist.
        # This keeps JS/backend behavior consistent: we only return success if email sending is actually permitted.
        if send_email:
            from app.utils.email_protection import check_email_recipients_allowed
            users = User.query.filter(User.id.in_(valid_user_ids)).all()
            requested_emails = [u.email for u in users if getattr(u, 'email', None)]
            protection = check_email_recipients_allowed(requested_emails)

            if protection.enabled and (not protection.allowed or protection.blocked_requested):
                # Build a concise, user-facing message
                blocked_preview = ", ".join(protection.blocked_requested[:5])
                extra = ""
                if len(protection.blocked_requested) > 5:
                    extra = f" (+{len(protection.blocked_requested) - 5} more)"
                if not protection.allowed:
                    error_message = protection.reason or (
                        f"Email sending is restricted in {protection.environment} and no allowlist is configured."
                    )
                else:
                    error_message = (
                        (protection.reason or f"Email sending is restricted in {protection.environment}.")
                        + (f" Blocked recipient(s): {blocked_preview}{extra}" if blocked_preview else "")
                    )

                # Record a failed campaign attempt (immediate send) with explanation
                try:
                    campaign_name = f"Immediate Send: {title[:50]}"
                    campaign = NotificationCampaign(
                        name=campaign_name,
                        description=f"Immediate notification send (blocked) - {utcnow().strftime('%Y-%m-%d %H:%M:%S')}",
                        title=title,
                        message=message,
                        priority=priority,
                        category=category,
                        tags=tags if isinstance(tags, list) else (tags.split(',') if isinstance(tags, str) else None),
                        send_email=send_email,
                        send_push=send_push,
                        override_preferences=override_preferences,
                        redirect_type=redirect_url and (redirect_url.startswith('/') and 'app' or 'custom') or None,
                        redirect_url=redirect_url or None,
                        scheduled_for=None,
                        status='failed',
                        user_selection_type='manual',
                        user_ids=valid_user_ids,
                        user_filters=None,
                        created_by=current_user.id,
                        sent_at=utcnow(),
                        sent_count=0,
                        failed_count=len(valid_user_ids),
                        error_message=error_message[:2000],
                    )
                    db.session.add(campaign)
                    db.session.flush()
                except Exception as commit_error:
                    current_app.logger.error(
                        f"Error committing failed campaign record for blocked immediate send: {str(commit_error)}",
                        exc_info=True
                    )
                    request_transaction_rollback()
                    campaign = None

                flash_if_html(error_message, 'danger')
                return json_bad_request(
                    error_message,
                    success=False,
                    error=error_message,
                    flash_message=error_message,
                    flash_category='danger',
                    campaign_id=campaign.id if campaign else None
                )

        # Create notification records in the database
        # Use respect_preferences=False to ensure all selected users get the notification
        # since admin is explicitly sending to them
        # For admin messages, store custom title and message directly (they're user-generated content)
        # We still use translation keys for structure, but the actual content comes from admin input
        notifications = create_notification(
            user_ids=valid_user_ids,
            notification_type=NotificationType.admin_message,
            title_key='notification.admin_message.title',
            title_params={'custom_title': title},  # Pass custom admin title
            message_key='notification.admin_message.message',
            message_params={'message': message},  # Pass custom admin message as parameter
            related_url=redirect_url if redirect_url else None,
            priority=priority,
            respect_preferences=False,  # Admin explicitly chose these users, so send regardless of preferences
            override_email_preferences=override_preferences,  # Allow admin to override email preferences
            # IMPORTANT: this route controls delivery; create_notification should not auto-send push/email
            send_email_notifications=send_email,
            send_push_notifications=False
        )

        if not notifications:
            error_message = 'No notifications created. All notifications were duplicates - the same notification was already sent to the selected user(s) within the last few minutes. Please wait a moment before sending again, or modify the title/message to create a unique notification.'
            current_app.logger.warning(
                f"Failed to create notification records for admin push notification from {current_user.id} ({current_user.email}). "
                f"All notifications were likely duplicates (same notification sent to same users within deduplication window)"
            )
            # Set flash message for error
            flash_if_html(error_message, 'danger')
            return json_bad_request(
                error_message,
                success=False,
                error=error_message,
                flash_message=error_message,
                flash_category='danger'
            )

        # Notification creation is already logged in create_notification(); keep route logs minimal.
        current_app.logger.debug(
            f"Admin {current_user.id} ({current_user.email}) created {len(notifications)} notification record(s) for custom notification"
        )

        # Only send push notifications if send_push is True
        result = None
        total_devices = 0
        success = False

        if send_push:
            # Build notification data payload for push notification
            notification_data = {
                'notification_type': 'admin_message',
                'admin_sent': 'true',
                'sender_id': str(current_user.id),
                'sender_name': current_user.name or current_user.email
            }

            # Add redirect URL if provided
            if redirect_url:
                notification_data['redirect_url'] = redirect_url

            # Send push notifications
            result = PushNotificationService.send_bulk_push_notifications(
                user_ids=valid_user_ids,
                title=title,
                body=message,
                data=notification_data,
                priority=priority
            )

            current_app.logger.info(
                f"Admin {current_user.id} ({current_user.email}) sent push notification to {len(valid_user_ids)} users. "
                f"Result: success={result.get('success')}, total_devices={result.get('total_devices')}, "
                f"success_count={result.get('total_success')}, failure_count={result.get('total_failure')}"
            )

            # Determine appropriate message based on result
            total_devices = result.get('total_devices', 0)
            success = result.get('success', False)

        # Determine flash message category and message based on delivery methods
        if send_email and send_push:
            # Both email and push selected
            if total_devices == 0:
                flash_message = f"Notification created in database for {len(valid_user_ids)} user(s). Email delivery initiated. Push notification was not sent: selected user(s) have no registered devices. Users will see the notification when they open the app."
                flash_category = 'warning'
            elif not success:
                failed_count = result.get('total_failure', 0)
                flash_message = f"Notification created in database for {len(valid_user_ids)} user(s). Email delivery initiated. Push notification sent to {result.get('total_success', 0)} device(s), but {failed_count} device(s) failed. Users will see the notification when they open the app."
                flash_category = 'warning'
            else:
                flash_message = f"Notification created. Email delivery initiated. Push notification sent to {len(valid_user_ids)} user(s) ({total_devices} device(s))."
                flash_category = 'success'
        elif send_email:
            # Only email selected
            flash_message = f"Notification created. Email delivery initiated for {len(valid_user_ids)} user(s)."
            flash_category = 'success'
        elif send_push:
            # Only push selected
            if total_devices == 0:
                flash_message = f"Notification created in database for {len(valid_user_ids)} user(s), but push notification was not sent: selected user(s) have no registered devices. Users will see the notification when they open the app."
                flash_category = 'warning'
            elif not success:
                failed_count = result.get('total_failure', 0)
                flash_message = f"Notification created in database for {len(valid_user_ids)} user(s). Push notification sent to {result.get('total_success', 0)} device(s), but {failed_count} device(s) failed. Users will see the notification when they open the app."
                flash_category = 'warning'
            else:
                flash_message = f"Notification created and push notification sent successfully to {len(valid_user_ids)} user(s) ({total_devices} device(s))"
                flash_category = 'success'

        # Set flash message in session (for traditional page loads)
        flash_if_html(flash_message, flash_category)

        # Build result data
        result_data = {
            'total_users': len(valid_user_ids),
            'total_devices': total_devices if send_push else 0,
            'success_count': result.get('total_success', 0) if send_push and result else 0,
            'failure_count': result.get('total_failure', 0) if send_push and result else 0,
            'users_without_devices': 0
        }

        # Only include users_without_devices if push was sent
        if send_push and result:
            user_results = result.get('user_results', [])
            users_without_devices = [
                r for r in user_results
                if r.get('result', {}).get('devices_count', 0) == 0
            ]
            result_data['users_without_devices'] = len(users_without_devices)

        # Create a campaign record for this immediate send
        campaign = None
        try:
            # Generate campaign name
            campaign_name = f"Immediate Send: {title[:50]}"  # Truncate if too long

            # Calculate total sent count
            total_sent = len(notifications) if notifications else 0
            if send_push and result:
                # Use push notification results for more accurate count
                total_sent = result.get('total_success', total_sent)

            # Create campaign record
            campaign = NotificationCampaign(
                name=campaign_name,
                description=f"Immediate notification send - {utcnow().strftime('%Y-%m-%d %H:%M:%S')}",
                title=title,
                message=message,
                priority=priority,
                category=category,
                tags=tags if isinstance(tags, list) else (tags.split(',') if isinstance(tags, str) else None),
                send_email=send_email,
                send_push=send_push,
                override_preferences=override_preferences,
                redirect_type=redirect_url and (redirect_url.startswith('/') and 'app' or 'custom') or None,
                redirect_url=redirect_url or None,
                scheduled_for=None,  # Immediate send, not scheduled
                status='sent',
                user_selection_type='manual',
                user_ids=valid_user_ids,
                user_filters=None,
                created_by=current_user.id,
                sent_at=utcnow(),
                sent_count=total_sent,
                failed_count=result.get('total_failure', 0) if result else 0,
                error_message=None
            )

            try:
                db.session.add(campaign)
                db.session.flush()

                current_app.logger.debug(
                    f"Created campaign record for immediate send: campaign_id={campaign.id}, "
                    f"sent_count={total_sent}, user_count={len(valid_user_ids)}"
                )
            except Exception as commit_error:
                current_app.logger.error(f"Error committing campaign record for immediate send: {str(commit_error)}", exc_info=True)
                request_transaction_rollback()
                # Don't fail the request if campaign creation fails
                campaign = None
        except Exception as e:
            current_app.logger.error(f"Error creating campaign record for immediate send: {str(e)}", exc_info=True)
            request_transaction_rollback()
            # Don't fail the request if campaign creation fails
            campaign = None

        return json_ok(
            success=True,
            message=flash_message,
            flash_message=flash_message,
            flash_category=flash_category,
            push_success=success if send_push else None,
            result=result_data,
            campaign_id=campaign.id if campaign else None
        )

    except Exception as e:
        current_app.logger.error(f"Error sending admin push notification: {str(e)}", exc_info=True)
        error_message = 'Server error.'
        # Set flash message for error
        flash_if_html(error_message, 'danger')
        return json_server_error(
            error_message,
            success=False,
            error=error_message,
            flash_message=error_message,
            flash_category='danger'
        )


@bp.route("/api/admin/users/search", methods=["GET"])
@login_required
@permission_required('admin.notifications.manage')
def api_admin_search_users():
    """Search users for admin push notification (admin only)"""
    try:
        query = (request.args.get('q') or '').strip()

        if not query or len(query) < 2:
            return json_ok(users=[])

        from app.models import User, UserDevice
        # Search users by name or email
        safe_pattern = safe_ilike_pattern(query)
        users = User.query.filter(
            db.or_(
                User.name.ilike(safe_pattern),
                User.email.ilike(safe_pattern)
            )
        ).limit(20).all()

        role_codes_by_user_id = AuthorizationService.prefetch_role_codes([u.id for u in users])

        users_data = []
        for user in users:
            # Check if user has active registered devices (exclude logged-out devices)
            device_count = UserDevice.query.filter_by(
                user_id=user.id
            ).filter(
                UserDevice.logged_out_at.is_(None)
            ).count()
            users_data.append({
                'id': user.id,
                'name': user.name or '',
                'email': user.email,
                'rbac_role_codes': role_codes_by_user_id.get(user.id, []),
                'device_count': device_count,
                'has_devices': device_count > 0
            })

        return json_ok(success=True, users=users_data)

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/admin/users/devices/check", methods=["POST"])
@login_required
@permission_required('admin.notifications.manage')
def api_admin_check_user_devices():
    """Check device registration status for selected users (admin only)"""
    try:
        data = get_json_safe()
        user_ids = data.get('user_ids', [])

        if not user_ids:
            return json_bad_request('No user IDs provided', success=False)

        from app.models import User, UserDevice

        # Ensure user_ids is a list
        if isinstance(user_ids, str):
            try:
                user_ids = [int(id.strip()) for id in user_ids.split(',') if id.strip().isdigit()]
            except ValueError:
                return json_bad_request('Invalid user IDs format', success=False)
        elif not isinstance(user_ids, list):
            user_ids = [user_ids] if user_ids else []

        # Get device counts for each user
        device_info = []
        for user_id in user_ids:
            try:
                user_id = int(user_id)
                user = User.query.get(user_id)
                if user:
                    # Count only active devices (exclude logged-out devices)
                    device_count = UserDevice.query.filter_by(
                        user_id=user_id
                    ).filter(
                        UserDevice.logged_out_at.is_(None)
                    ).count()
                    device_info.append({
                        'user_id': user_id,
                        'email': user.email,
                        'name': user.name or '',
                        'device_count': device_count,
                        'has_devices': device_count > 0
                    })
            except (ValueError, TypeError):
                continue

        total_users = len(device_info)
        users_with_devices = sum(1 for info in device_info if info['has_devices'])
        users_without_devices = total_users - users_with_devices

        return json_ok(
            success=True,
            total_users=total_users,
            users_with_devices=users_with_devices,
            users_without_devices=users_without_devices,
            device_info=device_info
        )

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/admin/users/bulk", methods=["GET"])
@login_required
@permission_required('admin.notifications.manage')
def api_admin_get_users_bulk():
    """Get users by role, country, and/or entity for bulk selection (admin only)
    All filters are combined with AND logic - users must match all selected filters"""
    try:

        from app.models import User, UserEntityPermission

        # Get filter parameters - support both single and multiple values
        roles = request.args.getlist('role')  # Support multiple roles
        country_ids = request.args.getlist('country_id')  # Multiple supported
        entity_type = request.args.get('entity_type')
        search = request.args.get('search', '').strip()  # Text search
        active = request.args.get('active')  # None, 'true', 'false'
        exclude_user_ids = request.args.getlist('exclude_user_id')  # Users to exclude

        # Template IDs for filtering assignments
        template_ids = request.args.getlist('template_id')  # Support multiple template IDs

        # Assigned Form IDs for filtering by specific assignments
        assigned_form_ids = request.args.getlist('assigned_form_id')  # Support multiple assignment IDs

        # If no filters provided, return all users
        query = User.query

        # Collect user ID filters to intersect them
        user_id_filters = []

        # Filter by RBAC role codes if provided
        if roles:
            roles = [str(r).strip() for r in roles if str(r).strip()]
            if roles:
                try:
                    from app.models.rbac import RbacUserRole, RbacRole
                    query = (
                        query.join(RbacUserRole, User.id == RbacUserRole.user_id)
                        .join(RbacRole, RbacUserRole.role_id == RbacRole.id)
                        .filter(RbacRole.code.in_(roles))
                    )
                except Exception as e:
                    current_app.logger.debug("RBAC role query failed, using safe default: %s", e)
                    # If RBAC tables are unavailable, return no users for role filtering (safe default)
                    query = query.filter(db.text("1=0"))

        # Filter by active/inactive status
        if active is not None and active != '':
            if active.lower() == 'true':
                query = query.filter(User.active == True)
            elif active.lower() == 'false':
                query = query.filter(User.active == False)
            # If active is 'all' or empty string, don't filter

        # Text search filter (name, email, title)
        if search:
            search_pattern = safe_ilike_pattern(search)
            query = query.filter(
                db.or_(
                    User.name.ilike(search_pattern),
                    User.email.ilike(search_pattern),
                    User.title.ilike(search_pattern)
                )
            )

        # Exclude specific user IDs
        if exclude_user_ids:
            with suppress((ValueError, TypeError)):  # Invalid IDs, ignore
                exclude_ids = [int(uid) for uid in exclude_user_ids if uid]
                if exclude_ids:
                    query = query.filter(~User.id.in_(exclude_ids))

        # Filter by assignment status if provided (supports multiple statuses)
        assignment_statuses = request.args.getlist('assignment_status')
        if assignment_statuses:
            from app.models.assignments import AssignmentEntityStatus, AssignedForm

            # Find all assignments with any of the specified statuses
            assignment_query = AssignmentEntityStatus.query.filter(
                AssignmentEntityStatus.status.in_(assignment_statuses)
            )

            # Filter by template(s) if provided
            if template_ids:
                with suppress((ValueError, TypeError)):  # Invalid template IDs, ignore filter
                    template_ids_int = [int(tid) for tid in template_ids if tid]
                    if template_ids_int:
                        assignment_query = assignment_query.join(AssignedForm).filter(
                            AssignedForm.template_id.in_(template_ids_int)
                        )

            # Get entity_type and entity_id pairs from assignments
            assignments = assignment_query.with_entities(
                AssignmentEntityStatus.entity_type,
                AssignmentEntityStatus.entity_id
            ).distinct().all()

            if not assignments:
                # No assignments with this status, return empty list
                return json_ok(
                    success=True,
                    users=[],
                    total=0,
                    page=page,
                    per_page=per_page,
                    total_pages=0
                )

            # Build query to find users with permissions to entities that have assignments
            user_ids_with_assignments = set()
            for entity_type_val, entity_id_val in assignments:
                # Find users with permission to this entity
                perm_users = db.session.query(UserEntityPermission.user_id).filter(
                    UserEntityPermission.entity_type == entity_type_val,
                    UserEntityPermission.entity_id == entity_id_val
                ).distinct().all()
                user_ids_with_assignments.update([uid[0] for uid in perm_users])

            if not user_ids_with_assignments:
                # No users with access to entities with assignments
                return json_ok(
                    success=True,
                    users=[],
                    total=0,
                    page=page,
                    per_page=per_page,
                    total_pages=0
                )

            user_id_filters.append(list(user_ids_with_assignments))

        # Filter by specific assigned forms if provided (standalone, not requiring assignment status)
        if assigned_form_ids:
            with suppress((ValueError, TypeError)):  # Invalid assignment form IDs, ignore
                assigned_form_ids_int = [int(afid) for afid in assigned_form_ids if afid]
                if assigned_form_ids_int:
                    from app.models.assignments import AssignmentEntityStatus

                    # Get all entity assignments for these assigned forms
                    form_assignments = AssignmentEntityStatus.query.filter(
                        AssignmentEntityStatus.assigned_form_id.in_(assigned_form_ids_int)
                    ).with_entities(
                        AssignmentEntityStatus.entity_type,
                        AssignmentEntityStatus.entity_id
                    ).distinct().all()

                    if not form_assignments:
                        return json_ok(
                            success=True,
                            users=[],
                            total=0,
                            page=page,
                            per_page=per_page,
                            total_pages=0
                        )

                    # Find users with permissions to these entities
                    user_ids_with_forms = set()
                    for entity_type_val, entity_id_val in form_assignments:
                        perm_users = db.session.query(UserEntityPermission.user_id).filter(
                            UserEntityPermission.entity_type == entity_type_val,
                            UserEntityPermission.entity_id == entity_id_val
                        ).distinct().all()
                        user_ids_with_forms.update([uid[0] for uid in perm_users])

                    if not user_ids_with_forms:
                        return json_ok(
                            success=True,
                            users=[],
                            total=0,
                            page=page,
                            per_page=per_page,
                            total_pages=0
                        )

                    user_id_filters.append(list(user_ids_with_forms))

        # Filter by templates if provided (standalone, not requiring assignment status)
        if template_ids and not assignment_statuses:
            with suppress((ValueError, TypeError)):  # Invalid template IDs, ignore
                template_ids_int = [int(tid) for tid in template_ids if tid]
                if template_ids_int:
                    from app.models.assignments import AssignmentEntityStatus, AssignedForm

                    # Get all entity assignments for these templates
                    template_assignments = AssignmentEntityStatus.query.join(AssignedForm).filter(
                        AssignedForm.template_id.in_(template_ids_int)
                    ).with_entities(
                        AssignmentEntityStatus.entity_type,
                        AssignmentEntityStatus.entity_id
                    ).distinct().all()

                    if not template_assignments:
                        return json_ok(
                            success=True,
                            users=[],
                            total=0,
                            page=page,
                            per_page=per_page,
                            total_pages=0
                        )

                    # Find users with permissions to these entities
                    user_ids_with_templates = set()
                    for entity_type_val, entity_id_val in template_assignments:
                        perm_users = db.session.query(UserEntityPermission.user_id).filter(
                            UserEntityPermission.entity_type == entity_type_val,
                            UserEntityPermission.entity_id == entity_id_val
                        ).distinct().all()
                        user_ids_with_templates.update([uid[0] for uid in perm_users])

                    if not user_ids_with_templates:
                        return json_ok(
                            success=True,
                            users=[],
                            total=0,
                            page=page,
                            per_page=per_page,
                            total_pages=0
                        )

                    user_id_filters.append(list(user_ids_with_templates))

        # Filter by country(ies) if provided
        if country_ids:
            with suppress((ValueError, TypeError)):  # Invalid country IDs, ignore
                country_ids_int = [int(cid) for cid in country_ids if cid]
                if country_ids_int:
                    # Get user IDs with access to any of these countries
                    country_user_ids_result = db.session.query(UserEntityPermission.user_id).filter(
                        UserEntityPermission.entity_type == 'country',
                        UserEntityPermission.entity_id.in_(country_ids_int)
                    ).distinct().all()
                    country_user_ids = [uid[0] for uid in country_user_ids_result]
                    if not country_user_ids:
                        # No users with access to these countries
                        return json_ok(users=[])
                    user_id_filters.append(country_user_ids)

        # Filter by entity type if provided
        if entity_type:
            # Get user IDs with access to this entity type
            entity_user_ids_result = db.session.query(UserEntityPermission.user_id).filter(
                UserEntityPermission.entity_type == entity_type
            ).distinct().all()
            entity_user_ids = [uid[0] for uid in entity_user_ids_result]
            if not entity_user_ids:
                # No users with access to this entity type
                return json_ok(users=[])
            user_id_filters.append(entity_user_ids)

        # Pagination parameters
        from app.utils.api_pagination import validate_pagination_params
        page, per_page = validate_pagination_params(request.args, default_per_page=100, max_per_page=500)

        # Intersect all user ID filters (users must match all filters)
        if user_id_filters:
            # Start with first filter, then intersect with others
            final_user_ids = set(user_id_filters[0])
            for user_ids in user_id_filters[1:]:
                final_user_ids = final_user_ids.intersection(set(user_ids))

            if not final_user_ids:
                # No users match all filters
                return json_ok(
                    success=True,
                    users=[],
                    total=0,
                    page=page,
                    per_page=per_page,
                    total_pages=0
                )

            query = query.filter(User.id.in_(list(final_user_ids)))

        # Get total count before pagination
        total_count = query.count()

        users = query.offset((page - 1) * per_page).limit(per_page).all()

        # Get user's entity permissions for preview
        user_ids = [user.id for user in users]
        user_permissions_map = {}
        if user_ids:
            permissions = UserEntityPermission.query.filter(
                UserEntityPermission.user_id.in_(user_ids)
            ).all()
            for perm in permissions:
                if perm.user_id not in user_permissions_map:
                    user_permissions_map[perm.user_id] = []
                user_permissions_map[perm.user_id].append({
                    'entity_type': perm.entity_type,
                    'entity_id': perm.entity_id
                })

        rbac_role_codes_by_user_id = AuthorizationService.prefetch_role_codes(user_ids)

        users_data = []
        for user in users:
            users_data.append({
                'id': user.id,
                'name': user.name or '',
                'email': user.email,
                'rbac_role_codes': rbac_role_codes_by_user_id.get(user.id, []),
                'title': user.title or '',
                'active': user.active,
                'entity_permissions': user_permissions_map.get(user.id, [])
            })

        return json_ok(
            success=True,
            users=users_data,
            total=total_count,
            page=page,
            per_page=per_page,
            total_pages=(total_count + per_page - 1) // per_page
        )

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/admin/countries", methods=["GET"])
@login_required
@permission_required('admin.notifications.manage')
def api_admin_get_countries():
    """Get list of countries for bulk selection (admin only)"""
    try:
        from app.models import Country

        countries = Country.query.order_by(Country.name).all()

        countries_data = []
        for country in countries:
            countries_data.append({
                'id': country.id,
                'name': country.name,
                'code': country.iso3 or country.iso2 or ''
            })

        return json_ok(success=True, countries=countries_data)
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/admin/entity-types", methods=["GET"])
@login_required
@permission_required('admin.notifications.manage')
def api_admin_get_entity_types():
    """Get list of entity types for bulk selection (admin only)"""
    try:
        from app.models.enums import EntityType
        from app.services.entity_service import EntityService

        entity_types = []
        for entity_type in EntityType:
            entity_types.append({
                'value': entity_type.value,
                'label': EntityService.get_entity_type_label(entity_type.value)
            })

        return json_ok(success=True, entity_types=entity_types)
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/admin/assignments", methods=["GET"])
@login_required
@permission_required('admin.notifications.manage')
def api_admin_get_assignments():
    """Get list of assignments (AssignedForm) for bulk selection (admin only)"""
    try:
        from app.models.assignments import AssignedForm

        assignments = AssignedForm.query.order_by(AssignedForm.assigned_at.desc()).all()

        assignments_data = []
        for assignment in assignments:
            # Get template name from published version or first version
            template_name = assignment.template.name if assignment.template else 'Unknown Template'

            assignments_data.append({
                'id': assignment.id,
                'name': f"{template_name} - {assignment.period_name}",
                'template_id': assignment.template_id,
                'template_name': template_name,
                'period_name': assignment.period_name,
                'assigned_at': assignment.assigned_at.isoformat() if assignment.assigned_at else None
            })

        return json_ok(success=True, assignments=assignments_data)
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/admin/templates", methods=["GET"])
@login_required
@permission_required('admin.notifications.manage')
def api_admin_get_templates():
    """Get list of form templates for bulk selection (admin only)"""
    try:
        from app.models import FormTemplate

        templates = FormTemplate.query.all()

        templates_data = []
        for template in templates:
            # Use the name property which gets it from published version or first version
            template_name = template.name  # This is a property that handles the logic

            templates_data.append({
                'id': template.id,
                'name': template_name
            })

        # Sort by name
        templates_data.sort(key=lambda x: x['name'])

        return json_ok(success=True, templates=templates_data)
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/admin/all", methods=["GET"])
@login_required
@permission_required('admin.notifications.manage')
def api_admin_get_all_notifications():
    """Get all notifications across all users (admin only)"""
    try:
        # Get pagination parameters
        from app.utils.api_pagination import validate_pagination_params
        page, per_page = validate_pagination_params(request.args, default_per_page=20, max_per_page=100)
        offset = (page - 1) * per_page

        # Get filter parameters
        user_id = request.args.get('user_id', type=int)
        notification_type = request.args.get('type', None)
        priority = request.args.get('priority', None)
        unread_only = request.args.get('unread_only', 'false').lower() == 'true'
        archived_only = request.args.get('archived_only', 'false').lower() == 'true'

        # Date filters
        date_from = None
        date_to = None
        if request.args.get('date_from'):
            with suppress(ValueError):
                date_from = datetime.fromisoformat(request.args.get('date_from'))
        if request.args.get('date_to'):
            with suppress(ValueError):
                date_to = datetime.fromisoformat(request.args.get('date_to'))

        # Build query - admin can see all notifications
        query = Notification.query

        # Apply filters
        if user_id:
            query = query.filter(Notification.user_id == user_id)

        if unread_only:
            query = query.filter(Notification.is_read == False)

        if archived_only:
            query = query.filter(Notification.is_archived == True)
        else:
            # By default, exclude archived for admin view
            query = query.filter(Notification.is_archived == False)

        if notification_type:
            from sqlalchemy import cast, String
            query = query.filter(cast(Notification.notification_type, String) == notification_type)

        if priority:
            query = query.filter(Notification.priority == priority)

        if date_from:
            query = query.filter(Notification.created_at >= date_from)

        if date_to:
            query = query.filter(Notification.created_at <= date_to)

        # Get total count
        total_count = query.count()

        # Apply pagination and ordering
        notifications = query.order_by(
            Notification.created_at.desc()
        ).offset(offset).limit(per_page).all()

        # Format notifications
        from app.models import User
        notifications_data = []
        for notification in notifications:
            user = User.query.get(notification.user_id)
            notifications_data.append({
                'id': notification.id,
                'user_id': notification.user_id,
                'user_email': user.email if user else 'Unknown',
                'user_name': user.name if user else 'Unknown',
                'title': notification.title or 'Notification',
                'message': notification.message or '',
                'notification_type': notification.notification_type.value if hasattr(notification.notification_type, 'value') else str(notification.notification_type),
                'is_read': notification.is_read,
                'is_archived': notification.is_archived,
                'priority': notification.priority or 'normal',
                'created_at': notification.created_at.isoformat() if notification.created_at else None,
                'related_url': notification.related_url
            })

        return json_ok(
            success=True,
            notifications=notifications_data,
            total_count=total_count,
            page=page,
            per_page=per_page,
            has_more=(offset + len(notifications_data)) < total_count
        )

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


# ========== Campaign Management ==========

@bp.route("/api/admin/campaigns", methods=["GET"])
@login_required
@permission_required('admin.notifications.manage')
def api_get_campaigns():
    """Get all notification campaigns (admin only)"""
    try:
        # Get filter parameters
        status = request.args.get('status', None)

        query = NotificationCampaign.query

        if status:
            query = query.filter(NotificationCampaign.status == status)

        campaigns = query.order_by(NotificationCampaign.created_at.desc()).all()

        campaigns_data = []
        for campaign in campaigns:
            campaigns_data.append({
                'id': campaign.id,
                'name': campaign.name,
                'description': campaign.description,
                'title': campaign.title,
                'message': campaign.message,
                'priority': campaign.priority,
                'category': campaign.category,
                'tags': campaign.tags,
                'send_email': campaign.send_email,
                'send_push': campaign.send_push,
                'override_preferences': campaign.override_preferences,
                'redirect_type': campaign.redirect_type,
                'redirect_url': campaign.redirect_url,
                'scheduled_for': campaign.scheduled_for.isoformat() if campaign.scheduled_for else None,
                'status': campaign.status,
                    'error_message': getattr(campaign, 'error_message', None),
                'user_selection_type': campaign.user_selection_type,
                'user_ids': campaign.user_ids,
                'user_filters': campaign.user_filters,
                'created_by': campaign.created_by,
                'created_at': campaign.created_at.isoformat() if campaign.created_at else None,
                'updated_at': campaign.updated_at.isoformat() if campaign.updated_at else None,
                'sent_at': campaign.sent_at.isoformat() if campaign.sent_at else None,
                'sent_count': campaign.sent_count,
                'failed_count': campaign.failed_count
            })

        return json_ok(success=True, campaigns=campaigns_data)

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/admin/campaigns", methods=["POST"])
@login_required
@permission_required('admin.notifications.manage')
def api_create_campaign():
    """Create a new notification campaign (admin only)"""
    try:
        data = get_json_safe()

        # Validate required fields
        name = data.get('name', '').strip()
        title = data.get('title', '').strip()
        message = data.get('message', '').strip()

        if not name:
            error_message = 'Campaign name is required'
            flash(error_message, 'danger')
            return json_bad_request(error_message, success=False)
        if not title:
            error_message = 'Title is required'
            flash(error_message, 'danger')
            return json_bad_request(error_message, success=False)
        if not message:
            error_message = 'Message is required'
            flash(error_message, 'danger')
            return json_bad_request(error_message, success=False)

        # Validate delivery methods
        send_email = data.get('send_email', True)
        send_push = data.get('send_push', True)
        if not send_email and not send_push:
            error_message = 'At least one delivery method must be selected'
            flash(error_message, 'danger')
            return json_bad_request(error_message, success=False)

        # Handle description - can be None or empty string
        description = data.get('description')
        if description is not None:
            description = description.strip() if description else None

        # Handle redirect_url - can be None or empty string
        redirect_url = data.get('redirect_url')
        if redirect_url is not None:
            redirect_url = redirect_url.strip() if redirect_url else None

        # Create campaign
        user_selection_type = data.get('user_selection_type', 'manual')

        # Validate entity-based campaigns
        if user_selection_type == 'entity':
            if not send_email:
                error_message = 'Entity-based campaigns require email to be enabled'
                flash(error_message, 'danger')
                return json_bad_request(error_message, success=False)
            entity_selection = data.get('entity_selection', [])
            if not entity_selection or len(entity_selection) == 0:
                error_message = 'At least one entity must be selected for entity-based campaigns'
                flash(error_message, 'danger')
                return json_bad_request(error_message, success=False)

        campaign = NotificationCampaign(
            name=name,
            description=description,
            title=title,
            message=message,
            priority=data.get('priority', 'normal'),
            category=data.get('category'),
            tags=data.get('tags'),
            send_email=send_email,
            send_push=send_push,
            override_preferences=data.get('override_preferences', False),
            redirect_type=data.get('redirect_type'),
            redirect_url=redirect_url,
            scheduled_for=datetime.fromisoformat(data['scheduled_for'].replace('Z', '+00:00')) if data.get('scheduled_for') else None,
            status='scheduled' if data.get('scheduled_for') else 'draft',
            user_selection_type=user_selection_type,
            user_ids=data.get('user_ids', []) if user_selection_type != 'entity' else None,
            user_filters=data.get('user_filters') if user_selection_type == 'filter' else None,
            entity_selection=data.get('entity_selection') if user_selection_type == 'entity' else None,
            email_distribution_rules=data.get('email_distribution_rules') if user_selection_type == 'entity' else None,
            attachment_config=data.get('attachment_config') if user_selection_type == 'entity' else None,
            created_by=current_user.id
        )

        try:
            db.session.add(campaign)
            db.session.flush()
        except Exception as commit_error:
            current_app.logger.error(f"Error committing campaign creation: {str(commit_error)}", exc_info=True)
            request_transaction_rollback()
            flash(GENERIC_ERROR_MESSAGE, 'danger')
            return json_server_error(GENERIC_ERROR_MESSAGE, success=False)

        flash_message = (
            f"Campaign '{campaign.name}' created successfully."
            + (" Scheduled." if campaign.status == 'scheduled' else " Saved as draft.")
        )
        flash(flash_message, 'success')

        return json_created(
            success=True,
            campaign={
                'id': campaign.id,
                'name': campaign.name,
                'status': campaign.status,
                'scheduled_for': campaign.scheduled_for.isoformat() if campaign.scheduled_for else None
            }
        )

    except Exception as e:
        current_app.logger.error(f"Error creating campaign: {str(e)}", exc_info=True)
        request_transaction_rollback()
        flash(GENERIC_ERROR_MESSAGE, 'danger')
        return json_server_error(GENERIC_ERROR_MESSAGE, success=False)


@bp.route("/api/admin/campaigns/<int:campaign_id>", methods=["GET"])
@login_required
@permission_required('admin.notifications.manage')
def api_get_campaign(campaign_id):
    """Get a specific campaign (admin only)"""
    try:
        campaign = NotificationCampaign.query.get_or_404(campaign_id)

        return json_ok(
            success=True,
            campaign={
                'id': campaign.id,
                'name': campaign.name,
                'description': campaign.description,
                'title': campaign.title,
                'message': campaign.message,
                'priority': campaign.priority,
                'category': campaign.category,
                'tags': campaign.tags,
                'send_email': campaign.send_email,
                'send_push': campaign.send_push,
                'override_preferences': campaign.override_preferences,
                'redirect_type': campaign.redirect_type,
                'redirect_url': campaign.redirect_url,
                'scheduled_for': campaign.scheduled_for.isoformat() if campaign.scheduled_for else None,
                'status': campaign.status,
                'error_message': getattr(campaign, 'error_message', None),
                'user_selection_type': campaign.user_selection_type,
                'user_ids': campaign.user_ids,
                'user_filters': campaign.user_filters,
                'entity_selection': campaign.entity_selection,
                'email_distribution_rules': campaign.email_distribution_rules,
                'created_by': campaign.created_by,
                'created_at': campaign.created_at.isoformat() if campaign.created_at else None,
                'updated_at': campaign.updated_at.isoformat() if campaign.updated_at else None,
                'sent_at': campaign.sent_at.isoformat() if campaign.sent_at else None,
                'sent_count': campaign.sent_count,
                'failed_count': campaign.failed_count
            }
        )

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/admin/campaigns/<int:campaign_id>", methods=["PUT"])
@login_required
@permission_required('admin.notifications.manage')
def api_update_campaign(campaign_id):
    """Update a campaign (admin only)"""
    try:
        campaign = NotificationCampaign.query.get_or_404(campaign_id)
        data = get_json_safe()

        # Only allow updates to draft or scheduled campaigns
        if campaign.status not in ['draft', 'scheduled']:
            error_message = 'Cannot update campaign that has already been sent'
            flash(error_message, 'danger')
            return json_bad_request(error_message, success=False)

        # Update fields
        if 'name' in data:
            campaign.name = data['name'].strip()
        if 'description' in data:
            description = data.get('description')
            if description is not None:
                campaign.description = description.strip() if description else None
            else:
                campaign.description = None
        if 'title' in data:
            campaign.title = data['title'].strip()
        if 'message' in data:
            campaign.message = data['message'].strip()
        if 'priority' in data:
            campaign.priority = data['priority']
        if 'category' in data:
            campaign.category = data.get('category')
        if 'tags' in data:
            campaign.tags = data.get('tags')
        if 'send_email' in data:
            campaign.send_email = data['send_email']
        if 'send_push' in data:
            campaign.send_push = data['send_push']
        if 'override_preferences' in data:
            campaign.override_preferences = data['override_preferences']
        if 'redirect_type' in data:
            campaign.redirect_type = data.get('redirect_type')
        if 'redirect_url' in data:
            redirect_url = data.get('redirect_url')
            if redirect_url is not None:
                campaign.redirect_url = redirect_url.strip() if redirect_url else None
            else:
                campaign.redirect_url = None
        if 'scheduled_for' in data:
            if data['scheduled_for']:
                campaign.scheduled_for = datetime.fromisoformat(data['scheduled_for'].replace('Z', '+00:00'))
                campaign.status = 'scheduled'
            else:
                campaign.scheduled_for = None
                campaign.status = 'draft'
        if 'user_ids' in data:
            campaign.user_ids = data['user_ids']
        if 'user_filters' in data:
            campaign.user_filters = data.get('user_filters')

        try:
            campaign.updated_at = utcnow()
            db.session.flush()
        except Exception as commit_error:
            current_app.logger.error(f"Error committing campaign update: {str(commit_error)}", exc_info=True)
            request_transaction_rollback()
            flash(GENERIC_ERROR_MESSAGE, 'danger')
            return json_server_error(GENERIC_ERROR_MESSAGE, success=False)

        flash_message = f"Campaign '{campaign.name}' updated successfully."
        flash(flash_message, 'success')

        return json_ok(
            success=True,
            campaign={
                'id': campaign.id,
                'name': campaign.name,
                'status': campaign.status
            }
        )

    except Exception as e:
        current_app.logger.error(f"Error updating campaign: {str(e)}", exc_info=True)
        request_transaction_rollback()
        flash(GENERIC_ERROR_MESSAGE, 'danger')
        return json_server_error(GENERIC_ERROR_MESSAGE, success=False)


@bp.route("/api/admin/campaigns/<int:campaign_id>", methods=["DELETE"])
@login_required
@permission_required('admin.notifications.manage')
def api_delete_campaign(campaign_id):
    """Delete a campaign (admin only)"""
    try:
        campaign = NotificationCampaign.query.get_or_404(campaign_id)

        # Only allow deletion of draft campaigns
        if campaign.status != 'draft':
            error_message = 'Cannot delete campaign that is scheduled or has been sent'
            flash(error_message, 'danger')
            return json_bad_request(error_message, success=False)

        try:
            db.session.delete(campaign)
            db.session.flush()
        except Exception as commit_error:
            current_app.logger.error(f"Error committing campaign deletion: {str(commit_error)}", exc_info=True)
            request_transaction_rollback()
            flash(GENERIC_ERROR_MESSAGE, 'danger')
            return json_server_error(GENERIC_ERROR_MESSAGE, success=False)

        flash('Campaign deleted successfully.', 'success')
        return json_ok()

    except Exception as e:
        current_app.logger.error(f"Error deleting campaign: {str(e)}", exc_info=True)
        request_transaction_rollback()
        flash(GENERIC_ERROR_MESSAGE, 'danger')
        return json_server_error(GENERIC_ERROR_MESSAGE, success=False)


@bp.route("/api/admin/campaigns/<int:campaign_id>/send", methods=["POST"])
@login_required
@permission_required('admin.notifications.manage')
def api_send_campaign(campaign_id):
    """Send a campaign immediately (admin only)"""
    try:
        campaign = NotificationCampaign.query.get_or_404(campaign_id)

        # Only allow sending draft or scheduled campaigns
        if campaign.status not in ['draft', 'scheduled']:
            error_message = 'Campaign has already been sent'
            flash(error_message, 'danger')
            return json_bad_request(error_message, success=False)

        # Handle entity-based campaigns differently
        if campaign.user_selection_type == 'entity' and campaign.entity_selection:
            # Entity-based email campaign - send one email per entity
            from app.utils.entity_email_campaigns import send_multiple_entity_email_campaigns
            from app.utils.notification_emails import sanitize_for_email

            if not campaign.send_email:
                error_message = 'Entity-based campaigns require email to be enabled'
                flash(error_message, 'danger')
                return json_bad_request(error_message, success=False)

            # Get distribution rules (default: organization in CC, non-organization in To)
            # New format: {'to': ['non_organization'], 'cc': ['organization']}
            # Legacy format (deprecated): {'ifrc_in': 'cc', 'non_ifrc_in': 'to'} or {'organization_in': 'cc', 'non_organization_in': 'to'}
            from app.utils.organization_helpers import is_org_email
            distribution_rules = campaign.email_distribution_rules
            if not distribution_rules:
                distribution_rules = {'to': ['non_organization'], 'cc': ['organization']}
            elif 'ifrc_in' in distribution_rules or 'organization_in' in distribution_rules:
                # Convert legacy format to new format (support both old ifrc_in and new organization_in)
                org_key = 'organization_in' if 'organization_in' in distribution_rules else 'ifrc_in'
                non_org_key = 'non_organization_in' if 'non_organization_in' in distribution_rules else 'non_ifrc_in'

                distribution_rules = {
                    'to': ['non_organization'] if distribution_rules.get(non_org_key) == 'to' else [],
                    'cc': ['organization'] if distribution_rules.get(org_key) == 'cc' else []
                }
                if distribution_rules.get(org_key) == 'to':
                    distribution_rules['to'].append('organization')
                if distribution_rules.get(non_org_key) == 'cc':
                    distribution_rules['cc'].append('non_organization')

            # Render simple email template
            html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        h2 {{ color: #2563eb; }}
        .priority-high {{ color: #dc2626; font-weight: bold; }}
    </style>
</head>
<body>
    <div class="container">
        <h2>{sanitize_for_email(campaign.title)}</h2>
        <div>{sanitize_for_email(campaign.message).replace(chr(10), '<br>')}</div>
    </div>
</body>
</html>"""
            text_content = f"{campaign.title}\n\n{campaign.message}"

            # Build attachments from attachment_config
            static_attachments = None
            assignment_pdf_assigned_form_id = None
            get_pdf_bytes_for_aes = None
            attachment_config = getattr(campaign, 'attachment_config', None) or {}
            if attachment_config:
                static_list = attachment_config.get('static_attachments') or []
                if static_list:
                    try:
                        import base64
                        static_attachments = []
                        for att in static_list:
                            fn = att.get('filename') or 'attachment'
                            b64 = att.get('content_base64')
                            ct = att.get('content_type') or 'application/octet-stream'
                            if b64:
                                static_attachments.append((fn, base64.b64decode(b64), ct))
                    except Exception as e:
                        current_app.logger.warning(f"Could not decode static attachments: {e}")
                af_id = attachment_config.get('assignment_pdf_assigned_form_id')
                if af_id:
                    assignment_pdf_assigned_form_id = int(af_id) if af_id else None
                    if assignment_pdf_assigned_form_id:
                        from flask import url_for
                        def _get_pdf_bytes_for_aes(aes_id):
                            try:
                                with current_app.test_client() as client:
                                    with client.session_transaction() as sess:
                                        sess['_user_id'] = str(current_user.id)
                                    url = url_for('forms.export_assignment_pdf', aes_id=aes_id)
                                    resp = client.get(url)
                                    if resp.status_code == 200 and resp.data:
                                        filename = f"assignment_{aes_id}.pdf"
                                        cd = resp.headers.get('Content-Disposition')
                                        if cd and 'filename=' in cd:
                                            import re
                                            m = re.search(r'filename[*]?=(?:UTF-8\'\')?["\']?([^"\';]+)', cd)
                                            if m:
                                                filename = m.group(1).strip()
                                        return (bytes(resp.data), filename)
                            except Exception as e:
                                current_app.logger.warning(f"Could not fetch PDF for aes_id={aes_id}: {e}")
                            return (None, None)
                        get_pdf_bytes_for_aes = _get_pdf_bytes_for_aes

            # Send emails to all selected entities
            result = send_multiple_entity_email_campaigns(
                entity_selections=campaign.entity_selection,
                subject=campaign.title,
                html_content=html_content,
                text_content=text_content,
                distribution_rules=distribution_rules,
                importance=campaign.priority,
                static_attachments=static_attachments,
                assignment_pdf_assigned_form_id=assignment_pdf_assigned_form_id,
                get_pdf_bytes_for_aes=get_pdf_bytes_for_aes,
            )

            # Update campaign status
            try:
                campaign.status = 'sent'
                campaign.sent_at = utcnow()
                campaign.sent_count = result['success_count']
                campaign.failed_count = result['failure_count']
                if result['failure_count'] > 0:
                    campaign.error_message = f"Failed to send to {result['failure_count']} entity/entities"
                else:
                    campaign.error_message = None
                db.session.flush()
            except Exception as commit_error:
                current_app.logger.error(f"Error committing entity campaign send status: {str(commit_error)}", exc_info=True)
                request_transaction_rollback()
                flash(GENERIC_ERROR_MESSAGE, 'danger')
                return json_server_error(GENERIC_ERROR_MESSAGE, success=False)

            if result['failure_count'] > 0:
                flash_message = f"Campaign '{campaign.name}' sent to {result['success_count']} entity/entities, but {result['failure_count']} failed."
                flash_category = 'warning'
            else:
                flash_message = f"Campaign '{campaign.name}' sent successfully to {result['success_count']} entity/entities."
                flash_category = 'success'

            flash(flash_message, flash_category)
            return json_ok(
                success=True,
                sent_count=result['success_count'],
                failed_count=result['failure_count'],
                flash_message=flash_message,
                flash_category=flash_category,
            )

        # Get user IDs from campaign (for manual and filter-based campaigns)
        user_ids = []
        if campaign.user_selection_type == 'manual' and campaign.user_ids:
            user_ids = campaign.user_ids
        elif campaign.user_selection_type == 'filter' and campaign.user_filters:
            # Use the bulk user selection logic to get users based on filters
            from app.models import User, UserEntityPermission
            from app.models.assignments import AssignmentEntityStatus, AssignedForm

            query = User.query

            # Apply filters from campaign.user_filters
            filters = campaign.user_filters
            if filters.get('roles'):
                roles = [str(r).strip() for r in (filters.get('roles') or []) if str(r).strip()]
                if roles:
                    try:
                        from app.models.rbac import RbacUserRole, RbacRole
                        query = (
                            query.join(RbacUserRole, User.id == RbacUserRole.user_id)
                            .join(RbacRole, RbacUserRole.role_id == RbacRole.id)
                            .filter(RbacRole.code.in_(roles))
                        )
                    except Exception as e:
                        current_app.logger.debug("RBAC join for campaign filter failed: %s", e)
                        query = query.filter(db.text("1=0"))
            if filters.get('active') is not None:
                query = query.filter(User.active == filters['active'])
            if filters.get('search'):
                search_pattern = safe_ilike_pattern(filters['search'])
                query = query.filter(
                    db.or_(
                        User.name.ilike(search_pattern),
                        User.email.ilike(search_pattern),
                        User.title.ilike(search_pattern)
                    )
                )
            # Add more filter logic as needed based on user_filters structure

            users = query.all()
            user_ids = [user.id for user in users]

        if not user_ids:
            error_message = 'No users selected for campaign'
            flash(error_message, 'danger')
            return json_bad_request(error_message, success=False)

        # Email protection (dev/staging): fail fast if any target recipient is not allowlisted.
        if campaign.send_email:
            from app.models import User
            from app.utils.email_protection import check_email_recipients_allowed

            users = User.query.filter(User.id.in_(user_ids)).all()
            requested_emails = [u.email for u in users if getattr(u, 'email', None)]
            protection = check_email_recipients_allowed(requested_emails)

            if protection.enabled and (not protection.allowed or protection.blocked_requested):
                blocked_preview = ", ".join(protection.blocked_requested[:5])
                extra = ""
                if len(protection.blocked_requested) > 5:
                    extra = f" (+{len(protection.blocked_requested) - 5} more)"

                if not protection.allowed:
                    error_message = protection.reason or (
                        f"Email sending is restricted in {protection.environment} and no allowlist is configured."
                    )
                else:
                    error_message = (
                        (protection.reason or f"Email sending is restricted in {protection.environment}.")
                        + (f" Blocked recipient(s): {blocked_preview}{extra}" if blocked_preview else "")
                    )

                # Persist failed status + reason
                try:
                    campaign.status = 'failed'
                    campaign.sent_at = utcnow()
                    campaign.sent_count = 0
                    campaign.failed_count = len(user_ids)
                    campaign.error_message = error_message[:2000]
                    db.session.flush()
                except Exception as commit_error:
                    current_app.logger.error(
                        f"Error committing campaign failed status due to email protection: {str(commit_error)}",
                        exc_info=True
                    )
                    request_transaction_rollback()

                flash(error_message, 'danger')

                return json_bad_request(
                    error_message,
                    success=False,
                    error=error_message,
                    flash_message=error_message,
                    flash_category='danger',
                    campaign_id=campaign.id,
                )

        # Send notifications using existing admin send endpoint logic
        notifications = create_notification(
            user_ids=user_ids,
            notification_type=NotificationType.admin_message,
            title_key='notification.admin_message.title',
            title_params={'custom_title': campaign.title},
            message_key='notification.admin_message.message',
            message_params={'message': campaign.message},
            related_url=campaign.redirect_url if campaign.redirect_url else None,
            priority=campaign.priority,
            respect_preferences=not campaign.override_preferences,
            override_email_preferences=campaign.override_preferences,
            category=campaign.category,
            tags=campaign.tags,
            # IMPORTANT: this route controls delivery; avoid duplicate push/email side effects
            send_email_notifications=campaign.send_email,
            send_push_notifications=False
        )

        # Send push notifications if enabled
        if campaign.send_push:
            from app.services.push_notification_service import PushNotificationService
            PushNotificationService.send_bulk_push_notifications(
                user_ids=user_ids,
                title=campaign.title,
                body=campaign.message,
                data={'notification_type': 'admin_message', 'campaign_id': campaign.id},
                priority=campaign.priority
            )

        # Update campaign status
        try:
            campaign.status = 'sent'
            campaign.sent_at = utcnow()
            campaign.sent_count = len(notifications)
            campaign.error_message = None
            db.session.flush()
        except Exception as commit_error:
            current_app.logger.error(f"Error committing campaign send status: {str(commit_error)}", exc_info=True)
            request_transaction_rollback()
            flash(GENERIC_ERROR_MESSAGE, 'danger')
            return json_server_error(GENERIC_ERROR_MESSAGE, success=False)

        flash(f"Campaign '{campaign.name}' sent successfully.", 'success')
        return json_ok(
            success=True,
            sent_count=len(notifications),
            flash_message=f"Campaign sent successfully! {len(notifications)} notification(s) created.",
            flash_category='success',
        )

    except Exception as e:
        current_app.logger.error(f"Error sending campaign: {str(e)}", exc_info=True)
        request_transaction_rollback()
        flash(GENERIC_ERROR_MESSAGE, 'danger')
        return json_server_error(GENERIC_ERROR_MESSAGE, success=False)
