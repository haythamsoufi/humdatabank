# File: Backoffice/app/routes/admin/notifications.py
"""
Admin Notifications Module - Notifications Center for admins (send notifications and view all notifications)
"""

from flask import Blueprint, render_template, request, flash, current_app, redirect, url_for
from flask_login import current_user
from app.extensions import csrf, db
from app.models import User, NotificationType, Notification, NotificationCampaign
from app.routes.admin.shared import permission_required
from app.utils.sql_utils import safe_ilike_pattern
from app.utils.notifications import create_notification, get_default_icon_for_notification_type
from app.utils.request_validation import enforce_api_or_csrf_protection
from app.services.push_notification_service import PushNotificationService
from app.services.notification_service import NotificationService
from app.utils.email_client import send_email as send_email_message
from app.services.authorization_service import AuthorizationService
from app.utils.app_settings import get_notification_templates, get_email_template
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE, get_json_safe
from app.utils.api_pagination import validate_pagination_params
from app.utils.error_handling import handle_json_view_exception
from app.utils.api_responses import json_bad_request, json_ok, json_server_error
from flask_babel import gettext as _
from datetime import datetime
from sqlalchemy import and_, or_, func
from contextlib import suppress

bp = Blueprint("admin_notifications", __name__, url_prefix="/admin")


@bp.route("/notifications/center", methods=["GET"])
@permission_required("admin.notifications.manage")
def notifications_center():
    """Render the admin notifications center page"""
    from sqlalchemy import cast, String

    # Get all notification types for the filter dropdown
    notification_types = [nt.value for nt in NotificationType]

    # Fetch notifications for the table (server-side rendering)
    page, per_page = validate_pagination_params(request.args, default_per_page=50, max_per_page=100)
    offset = (page - 1) * per_page

    # Get filter parameters
    unread_only = request.args.get('unread_only', 'false').lower() == 'true'
    notification_type = request.args.get('type', None)
    user_id = request.args.get('user_id', None, type=int)
    priority = request.args.get('priority', None)
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

    # Build query for all notifications
    query = Notification.query.join(User, Notification.user_id == User.id)

    # Apply filters
    if unread_only:
        query = query.filter(Notification.is_read == False)

    if notification_type:
        query = query.filter(cast(Notification.notification_type, String) == notification_type)

    if user_id:
        query = query.filter(Notification.user_id == user_id)

    if priority:
        query = query.filter(Notification.priority == priority)

    if archived_only:
        query = query.filter(Notification.is_archived == True)
    else:
        query = query.filter(Notification.is_archived == False)

    if date_from:
        query = query.filter(Notification.created_at >= date_from)
    if date_to:
        query = query.filter(Notification.created_at <= date_to)

    # Get total count
    total_count = query.count()

    # Apply pagination and ordering
    notifications = query.order_by(Notification.created_at.desc()).offset(offset).limit(per_page).all()

    # Format notifications for template
    notifications_data = []
    for notification in notifications:
        user = notification.user
        message, title = NotificationService._translate_notification_content(notification)
        if message is None:
            message = notification.message

        # Use dynamically constructed title if available, otherwise use stored title
        if title is None:
            title = notification.title

        # Format notification type for display
        notification_type_value = notification.notification_type.value if hasattr(notification.notification_type, 'value') else str(notification.notification_type)
        notification_type_display = notification_type_value.replace('_', ' ').title()

        # Format priority for display
        priority = notification.priority or 'normal'
        priority_display = priority.title()

        # Determine status display
        if notification.is_archived:
            status_display = 'archived'
        elif notification.is_read:
            status_display = 'read'
        else:
            status_display = 'unread'

        notifications_data.append({
            'id': notification.id,
            'user_id': notification.user_id,
            'user_name': user.name or user.email,
            'user_email': user.email,
            'user_title': user.title or '',
            'user_active': bool(user.active),
            'user_profile_color': user.profile_color or '',
            'rbac_role_codes': [],  # populated client-side / via API endpoints
            'notification_type': notification_type_value,
            'notification_type_display': notification_type_display,  # Formatted for display
            'title': title,
            'message': message,
            'is_read': notification.is_read,
            'is_archived': notification.is_archived,
            'status_display': status_display,  # Formatted status
            'priority': priority,
            'priority_display': priority_display,  # Formatted priority
            'created_at': notification.created_at.strftime('%Y-%m-%d %H:%M:%S') if notification.created_at else '',
            'read_at': notification.read_at.strftime('%Y-%m-%d %H:%M:%S') if notification.read_at else '',
            'related_url': notification.related_url,
            'icon': get_default_icon_for_notification_type(notification.notification_type)
        })

    # Fetch campaigns for the campaigns tab
    campaigns = NotificationCampaign.query.order_by(NotificationCampaign.created_at.desc()).all()
    campaigns_data = []
    for campaign in campaigns:
        creator = User.query.get(campaign.created_by)
        # Format priority for display
        campaign_priority = campaign.priority or 'normal'
        campaign_priority_display = campaign_priority.title()

        # Format status for display
        campaign_status = campaign.status or 'draft'
        campaign_status_display = campaign_status.title()

        campaigns_data.append({
            'id': campaign.id,
            'name': campaign.name,
            'description': campaign.description or '',
            'title': campaign.title,
            'message': campaign.message,
            'priority': campaign_priority,
            'priority_display': campaign_priority_display,  # Formatted priority
            'category': campaign.category or '',
            'tags': campaign.tags or [],
            'send_email': campaign.send_email,
            'send_push': campaign.send_push,
            'override_preferences': campaign.override_preferences,
            'redirect_type': campaign.redirect_type or '',
            'redirect_url': campaign.redirect_url or '',
            'scheduled_for': campaign.scheduled_for.strftime('%Y-%m-%d %H:%M:%S') if campaign.scheduled_for else '',
            'scheduled_for_display': campaign.scheduled_for.strftime('%Y-%m-%d %H:%M:%S') if campaign.scheduled_for else None,  # For display logic
            'status': campaign_status,
            'status_display': campaign_status_display,  # Formatted status
            'user_selection_type': campaign.user_selection_type,
            'user_ids': campaign.user_ids or [],
            'created_by': campaign.created_by,
            'created_by_id': campaign.created_by,
            'created_by_name': creator.name if creator else 'Unknown',
            'created_by_email': creator.email if creator else '',
            'created_by_title': creator.title if creator else '',
            'created_by_active': bool(creator.active) if creator else True,
            'created_by_profile_color': (creator.profile_color if creator else '') or '',
            'created_at': campaign.created_at.strftime('%Y-%m-%d %H:%M:%S') if campaign.created_at else '',
            'updated_at': campaign.updated_at.strftime('%Y-%m-%d %H:%M:%S') if campaign.updated_at else '',
            'sent_at': campaign.sent_at.strftime('%Y-%m-%d %H:%M:%S') if campaign.sent_at else '',
            'sent_count': campaign.sent_count,
            'failed_count': campaign.failed_count,
            'recipients_count': len(campaign.user_ids) if campaign.user_ids else 0
        })

    # Load notification quick-templates from the database
    notification_templates = get_notification_templates()

    return render_template(
        "admin/notifications/center.html",
        notification_types=notification_types,
        notifications=notifications_data,
        total_count=total_count,
        page=page,
        per_page=per_page,
        total_pages=(total_count + per_page - 1) // per_page,
        campaigns=campaigns_data,
        notification_templates=notification_templates,
    )


# Keep the old route for backward compatibility
@bp.route("/notifications/send", methods=["GET"])
@permission_required("admin.notifications.manage")
def send_notifications_page():
    """Redirect to notifications center"""
    return redirect(url_for('admin_notifications.notifications_center'))


@bp.route("/api/notifications/send", methods=["POST"])
@csrf.exempt  # Exempt from CSRF protection for API endpoints used by mobile app
@permission_required("admin.notifications.manage")
def api_send_notifications():
    """Send custom notifications (email and/or push) to selected users (admin only)"""
    enforce_api_or_csrf_protection()
    try:
        data = get_json_safe()
        user_ids = data.get('user_ids', [])
        title = (data.get('title') or '').strip()
        message = (data.get('message') or '').strip()
        priority = data.get('priority', 'normal')
        redirect_url = (data.get('redirect_url') or '').strip()
        send_email = data.get('send_email', False)
        send_push = data.get('send_push', False)
        override_preferences = data.get('override_preferences', False)

        # Validation
        if not user_ids:
            return json_bad_request('No users selected')

        if not send_email and not send_push:
            return json_bad_request('Please select at least one delivery method (Email or Push Notification)')

        if not title:
            return json_bad_request('Title is required')

        if not message:
            return json_bad_request('Message is required')

        if len(title) > 100:
            return json_bad_request('Title must be 100 characters or less')

        if len(message) > 500:
            return json_bad_request('Message must be 500 characters or less')

        if priority not in ['normal', 'high']:
            priority = 'normal'

        # Sanitize HTML/script tags from admin-provided content to prevent XSS
        # While templates auto-escape, it's safer to sanitize at input
        from markupsafe import escape
        from html import unescape
        import re

        # Remove script tags and other dangerous HTML
        def sanitize_html(text):
            """Remove potentially dangerous HTML while preserving basic formatting."""
            if not text:
                return ''
            # Remove script tags and their content
            text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.IGNORECASE | re.DOTALL)
            # Remove event handlers (onclick, onerror, etc.)
            text = re.sub(r'\s*on\w+\s*=\s*["\'][^"\']*["\']', '', text, flags=re.IGNORECASE)
            # Remove javascript: and data: URLs
            text = re.sub(r'javascript:', '', text, flags=re.IGNORECASE)
            text = re.sub(r'data:', '', text, flags=re.IGNORECASE)
            # Escape remaining HTML (this will be unescaped by templates if needed)
            return escape(text)

        # Sanitize title and message
        title = sanitize_html(title)
        message = sanitize_html(message)

        # Validate redirect URL if provided
        if redirect_url:
            # Import validation function
            from app.utils.notifications import validate_notification_url

            if len(redirect_url) > 500:
                return json_bad_request('Redirect URL must be 500 characters or less')

            # Validate URL safety to prevent open redirects and XSS
            if not validate_notification_url(redirect_url):
                return json_bad_request('Redirect URL contains unsafe content (potential security risk). Only relative paths or whitelisted domains are allowed.')

        # Ensure user_ids is a list
        if isinstance(user_ids, str):
            try:
                user_ids = [int(id.strip()) for id in user_ids.split(',') if id.strip().isdigit()]
            except ValueError:
                return json_bad_request('Invalid user IDs format')
        elif not isinstance(user_ids, list):
            user_ids = [user_ids] if user_ids else []

        # Validate user IDs exist and get user emails
        valid_user_ids = []
        user_emails = {}
        for user_id in user_ids:
            try:
                user_id = int(user_id)
                user = User.query.get(user_id)
                if user:
                    valid_user_ids.append(user_id)
                    user_emails[user_id] = user.email
            except (ValueError, TypeError):
                continue

        if not valid_user_ids:
            return json_bad_request('No valid users found')

        # Create notification records in the database
        notifications = []
        if send_push:
            # Create notification records for push notifications
            notifications = create_notification(
                user_ids=valid_user_ids,
                notification_type=NotificationType.admin_message,
                title_key='notification.admin_message.title',
                title_params={'custom_title': title},
                message_key='notification.admin_message.message',
                message_params={'message': message},
                related_url=redirect_url if redirect_url else None,
                priority=priority,
                respect_preferences=False,  # Admin explicitly chose these users
                # This route sends push/email itself; avoid duplicate delivery attempts.
                send_email_notifications=False,
                send_push_notifications=False
            )

            if not notifications:
                error_message = 'No notifications created. All notifications were duplicates - the same notification was already sent to the selected user(s) within the last few minutes. Please wait a moment before sending again, or modify the title/message to create a unique notification.'
                current_app.logger.warning(
                    f"Failed to create notification records for admin push notification from {current_user.id} ({current_user.email}). "
                    f"All notifications were likely duplicates"
                )
                flash(error_message, 'danger')
                return json_bad_request(
                    error_message,
                    success=False,
                    flash_message=error_message,
                    flash_category='danger'
                )

        # Track results
        email_results = {'success': False, 'sent': 0, 'failed': 0}
        push_results = {'success': False, 'devices': 0, 'sent': 0, 'failed': 0}

        # Send emails if requested
        if send_email:
            email_sent_count = 0
            email_failed_count = 0

            # Create HTML email content using DB template with fallback
            from app.utils.email_rendering import render_admin_email_template

            default_email_template = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background-color: #e31e24; color: white; padding: 20px; text-align: center; }
        .content { background-color: #f9f9f9; padding: 20px; margin-top: 20px; }
        .message { background-color: white; padding: 15px; border-left: 4px solid #e31e24; margin: 15px 0; white-space: pre-wrap; }
        .footer { text-align: center; color: #666; font-size: 12px; margin-top: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{{ title }}</h1>
        </div>
        <div class="content">
            <div class="message">
                {{ message }}
            </div>
        </div>
        <div class="footer">
            <p>This is an automated message from {{ org_name }}.</p>
        </div>
    </div>
</body>
</html>"""

            email_template = get_email_template(
                'email_template_notification',
                default=default_email_template,
            )

            email_html = render_admin_email_template(
                email_template,
                title=title,
                message=message,
                org_name=current_app.config.get('ORG_NAME', 'System'),
            )

            # Send email to each user
            recipients = [user_emails[uid] for uid in valid_user_ids if user_emails.get(uid)]

            if recipients:
                try:
                    email_success = send_email_message(
                        subject=title,
                        recipients=recipients,
                        html=email_html
                    )

                    if email_success:
                        email_sent_count = len(recipients)
                        email_results = {'success': True, 'sent': email_sent_count, 'failed': 0}
                        current_app.logger.info(
                            f"Admin {current_user.id} ({current_user.email}) sent email notification to {email_sent_count} users"
                        )
                    else:
                        email_failed_count = len(recipients)
                        email_results = {'success': False, 'sent': 0, 'failed': email_failed_count}
                        current_app.logger.error(
                            f"Admin {current_user.id} ({current_user.email}) failed to send email notification to {len(recipients)} users"
                        )
                except Exception as e:
                    current_app.logger.error(f"Error sending email notifications: {str(e)}")
                    email_results = {'success': False, 'sent': 0, 'failed': len(recipients)}

        # Send push notifications if requested
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

            push_results = {
                'success': result.get('success', False),
                'devices': result.get('total_devices', 0),
                'sent': result.get('total_success', 0),
                'failed': result.get('total_failure', 0)
            }

            current_app.logger.info(
                f"Admin {current_user.id} ({current_user.email}) sent push notification to {len(valid_user_ids)} users. "
                f"Result: success={push_results['success']}, total_devices={push_results['devices']}, "
                f"success_count={push_results['sent']}, failure_count={push_results['failed']}"
            )

        # Build response message
        messages = []
        if send_email:
            if email_results['success']:
                messages.append(f"Email sent successfully to {email_results['sent']} user(s).")
            else:
                messages.append(f"Email failed to send to {email_results['failed']} user(s).")

        if send_push:
            if push_results['devices'] == 0:
                messages.append(f"Push notification: No registered devices found. Users will see the notification when they open the app.")
            elif push_results['success']:
                messages.append(f"Push notification sent to {push_results['sent']} device(s).")
            else:
                messages.append(f"Push notification: {push_results['sent']} device(s) succeeded, {push_results['failed']} device(s) failed.")

        # Determine overall success
        overall_success = (
            (not send_email or email_results['success']) and
            (not send_push or push_results['devices'] > 0 or push_results['success'])
        )

        # Determine flash message category
        if overall_success:
            flash_category = 'success'
        elif (send_email and not email_results['success']) or (send_push and push_results['devices'] == 0):
            flash_category = 'warning'
        else:
            flash_category = 'error'

        flash_message = ' '.join(messages)
        flash(flash_message, flash_category)

        return json_ok(
            success=overall_success,
            message=flash_message,
            flash_message=flash_message,
            flash_category=flash_category,
            email_results=email_results,
            push_results=push_results,
        )

    except Exception as e:
        current_app.logger.error(f"Error in api_send_notifications: {str(e)}", exc_info=True)
        error_message = GENERIC_ERROR_MESSAGE
        flash(error_message, 'danger')
        return json_server_error(error_message)


@bp.route("/api/notifications/search-users", methods=["GET"])
@permission_required("admin.notifications.manage")
def api_search_users():
    """Search users by name or email for notification sending"""
    try:
        query = request.args.get('q', '').strip()
        if not query or len(query) < 2:
            return json_ok(users=[])

        # Search users by name or email
        safe_pattern = safe_ilike_pattern(query)
        users = User.query.filter(
            db.or_(
                User.name.ilike(safe_pattern),
                User.email.ilike(safe_pattern)
            )
        ).limit(20).all()

        user_ids = [u.id for u in users]
        rbac_role_codes_by_user_id = AuthorizationService.prefetch_role_codes(user_ids)

        results = [
            {
                'id': user.id,
                'name': user.name or user.email,
                'email': user.email,
                'rbac_role_codes': rbac_role_codes_by_user_id.get(user.id, [])
            }
            for user in users
        ]

        return json_ok(users=results)
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/notifications/all", methods=["GET"])
@permission_required("admin.notifications.manage")
def api_get_all_notifications():
    """Get all notifications from all users (admin view)"""
    try:
        page, per_page = validate_pagination_params(request.args, default_per_page=20, max_per_page=100)
        offset = (page - 1) * per_page

        # Get filter parameters
        unread_only = request.args.get('unread_only', 'false').lower() == 'true'
        notification_type = request.args.get('type', None)
        user_id = request.args.get('user_id', None, type=int)
        include_archived = request.args.get('include_archived', 'false').lower() == 'true'
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

        # Build query for all notifications
        query = Notification.query.join(User, Notification.user_id == User.id)

        # Apply filters
        if unread_only:
            query = query.filter(Notification.is_read == False)

        if notification_type:
            query = query.filter(Notification.notification_type == notification_type)

        if user_id:
            query = query.filter(Notification.user_id == user_id)

        if not include_archived:
            query = query.filter(Notification.is_archived == False)
        elif archived_only:
            query = query.filter(Notification.is_archived == True)

        if date_from:
            query = query.filter(Notification.created_at >= date_from)
        if date_to:
            query = query.filter(Notification.created_at <= date_to)

        # Get total count
        total_count = query.count()

        # Apply pagination and ordering
        notifications = query.order_by(Notification.created_at.desc()).offset(offset).limit(per_page).all()

        notif_user_ids = list({n.user_id for n in notifications if getattr(n, "user_id", None) is not None})
        rbac_role_codes_by_user_id = AuthorizationService.prefetch_role_codes(notif_user_ids)

        # Format notifications
        notifications_data = []
        for notification in notifications:
            user = notification.user
            message, title = NotificationService._translate_notification_content(notification)
        if message is None:
            message = notification.message

            # Use dynamically constructed title if available, otherwise use stored title
            if title is None:
                title = notification.title

            notifications_data.append({
                'id': notification.id,
                'user_id': notification.user_id,
                'user_name': user.name or user.email,
                'user_email': user.email,
                'user_title': user.title or '',
                'user_active': bool(user.active),
                'user_profile_color': user.profile_color or '',
                'rbac_role_codes': rbac_role_codes_by_user_id.get(notification.user_id, []),
                'notification_type': notification.notification_type.value if hasattr(notification.notification_type, 'value') else str(notification.notification_type),
                'title': title,
                'message': message,
                'is_read': notification.is_read,
                'is_archived': notification.is_archived,
                'priority': notification.priority,
                'created_at': notification.created_at.isoformat() if notification.created_at else None,
                'read_at': notification.read_at.isoformat() if notification.read_at else None,
                'related_url': notification.related_url,
                'icon': get_default_icon_for_notification_type(notification.notification_type)
            })

        return json_ok(
            success=True,
            notifications=notifications_data,
            pagination={
                'page': page,
                'per_page': per_page,
                'total': total_count,
                'pages': (total_count + per_page - 1) // per_page
            },
        )

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/notifications/campaigns/<int:campaign_id>/recipients", methods=["GET"])
@permission_required("admin.notifications.manage")
def api_get_campaign_recipients(campaign_id):
    """Get recipients for a notification campaign"""
    try:
        # Get campaign
        campaign = NotificationCampaign.query.get_or_404(campaign_id)

        # Get user IDs from campaign
        user_ids = campaign.user_ids or []

        if not user_ids:
            return json_ok(success=True, recipients=[], total=0)

        # Get search query if provided
        search_query = request.args.get('q', '').strip().lower()

        # Query users
        query = User.query.filter(User.id.in_(user_ids))

        # Apply search filter if provided
        if search_query:
            safe_pattern = safe_ilike_pattern(search_query)
            query = query.filter(
                db.or_(
                    User.name.ilike(safe_pattern),
                    User.email.ilike(safe_pattern)
                )
            )

        # Get all matching users
        users = query.all()

        user_ids = [u.id for u in users]
        rbac_role_codes_by_user_id = AuthorizationService.prefetch_role_codes(user_ids)

        # Format results
        recipients = []
        for user in users:
            recipients.append({
                'id': user.id,
                'name': user.name or user.email,
                'email': user.email,
                'rbac_role_codes': rbac_role_codes_by_user_id.get(user.id, [])
            })

        return json_ok(success=True, recipients=recipients, total=len(recipients))

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)
