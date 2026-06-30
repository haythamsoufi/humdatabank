# File: Backoffice/app/routes/admin/communication.py
"""
Admin Communication Module - Communication Center for admins (view notifications and email delivery, send campaigns).
"""

import csv
import io

from flask import Blueprint, Response, render_template, request, flash, current_app
from flask_login import current_user
from app.extensions import csrf, db
from app.models import User, NotificationType, Notification, NotificationCampaign, EmailDeliveryLog
from app.routes.admin.shared import permission_required
from app.utils.sql_utils import safe_ilike_pattern
from app.services.notification.core import create_notification, get_default_icon_for_notification_type
from app.utils.request_validation import enforce_api_or_csrf_protection
from app.services.notification.push import PushNotificationService
from app.services.notification_service import NotificationService
from app.services.email.client import send_email as send_email_message
from app.services.email.delivery import log_email_attempt, mark_email_sent, mark_email_failed
from app.services.authorization_service import AuthorizationService
from app.services.app_settings_service import get_email_template
from app.services.campaign_email_templates_service import (
    CAMPAIGN_EMAIL_TEMPLATE_KEYS,
    get_all_campaign_email_templates,
    get_campaign_compose_templates,
    set_all_campaign_email_templates,
)
from app.utils.organization_helpers import get_org_name
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE, get_json_safe
from app.utils.error_handling import handle_json_view_exception
from app.utils.api_responses import json_bad_request, json_ok, json_server_error
from flask_babel import gettext as _
from datetime import datetime, timedelta
from sqlalchemy import and_, or_, func, cast, String
from contextlib import suppress
from app.utils.datetime_helpers import utcnow

bp = Blueprint("admin_communication", __name__, url_prefix="/admin")


def _latest_admin_notifications_by_user(user_ids, within_seconds=30):
    """Map user_id -> most recent admin_message notification created within the window."""
    if not user_ids:
        return {}
    recent_cutoff = utcnow() - timedelta(seconds=within_seconds)
    rows = (
        Notification.query.filter(
            Notification.user_id.in_(user_ids),
            cast(Notification.notification_type, String) == NotificationType.admin_message.value,
            Notification.created_at >= recent_cutoff,
        )
        .order_by(Notification.user_id, Notification.created_at.desc())
        .all()
    )
    by_user = {}
    for notification in rows:
        if notification.user_id not in by_user:
            by_user[notification.user_id] = notification
    return by_user


@bp.route("/communication/center", methods=["GET"])
@permission_required("admin.communication.manage")
def communication_center():
    """Render the admin Communication Center page"""
    # Get all notification types for the filter dropdown
    notification_types = [nt.value for nt in NotificationType]

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

    # All matching rows for the grid (client-side AG Grid pagination)
    notifications = query.order_by(Notification.created_at.desc()).all()
    total_count = len(notifications)

    assignment_status_cache, _ = NotificationService._build_assignment_caches_for_notifications(notifications)
    actor_fields_by_id = NotificationService.build_actor_display_fields_map(
        notifications, assignment_status_cache
    )
    email_fields_by_id = NotificationService.build_email_delivery_fields_map(
        [n.id for n in notifications],
        notifications=notifications,
        actor_fields_by_id=actor_fields_by_id,
    )

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

        ad = actor_fields_by_id.get(notification.id, {})
        actor_obj = ad.get('actor')
        actor_action_icon = ad.get('actor_action_icon')
        primary_is_message = ad.get('primary_is_message', False)
        if primary_is_message:
            display_title = message or title
            display_message = title if (title and title != display_title) else ''
        else:
            display_title = title
            display_message = message

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
            'title': display_title,
            'message': display_message,
            'primary_is_message': primary_is_message,
            'actor': actor_obj,
            'actor_action_icon': actor_action_icon,
            'is_read': notification.is_read,
            'is_archived': notification.is_archived,
            'status_display': status_display,  # Formatted status
            'priority': priority,
            'priority_display': priority_display,  # Formatted priority
            'created_at': notification.created_at.strftime('%Y-%m-%d %H:%M:%S') if notification.created_at else '',
            'read_at': notification.read_at.strftime('%Y-%m-%d %H:%M:%S') if notification.read_at else '',
            'related_url': notification.related_url,
            'icon': get_default_icon_for_notification_type(notification.notification_type),
            **email_fields_by_id.get(notification.id, NotificationService._serialize_email_delivery_log(None)),
        })

    # Fetch campaigns for the campaigns tab
    campaigns = NotificationCampaign.query.order_by(NotificationCampaign.created_at.desc()).all()
    creator_ids = {campaign.created_by for campaign in campaigns if campaign.created_by}
    creators_by_id = {}
    if creator_ids:
        creators_by_id = {u.id: u for u in User.query.filter(User.id.in_(creator_ids)).all()}
    campaigns_data = []
    for campaign in campaigns:
        creator = creators_by_id.get(campaign.created_by)
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

    failed_email_delivery_count = EmailDeliveryLog.query.filter(
        cast(EmailDeliveryLog.status, String).in_(('failed', 'retrying'))
    ).count()

    campaign_compose_templates = get_campaign_compose_templates()
    campaign_email_templates = get_all_campaign_email_templates()

    return render_template(
        "admin/communication/center.html",
        notification_types=notification_types,
        notifications=notifications_data,
        total_count=total_count,
        page=1,
        per_page=total_count,
        total_pages=1 if total_count else 0,
        campaigns=campaigns_data,
        failed_email_delivery_count=failed_email_delivery_count,
        campaign_compose_templates=campaign_compose_templates,
        campaign_email_templates=campaign_email_templates,
    )


@bp.route("/communication/registry")
@permission_required("admin.communication.manage")
def communication_registry():
    """
    Read-only catalog of NotificationType keys: labels, priorities, TTL, and descriptions.

    Mirrors the Activity endpoint catalog pattern (search + optional CSV export).
    """
    from app.services.app_settings_service import get_notification_priority
    from app.services.notification_service import NotificationService
    from app.utils.notification_registry import build_registry_rows

    ttl_map = current_app.config.get("NOTIFICATION_TTL_DAYS", {}) or {}

    def ttl_resolve(type_key: str) -> int:
        try:
            return int(ttl_map.get(type_key, 90))
        except (TypeError, ValueError):
            return 90

    raw_rows = build_registry_rows(ttl_resolve, lambda tk: get_notification_priority(tk, "normal"))

    nt_by_value = {nt.value: nt for nt in NotificationType}

    q = (request.args.get("q") or "").strip().lower()

    rows_out = []
    for r in raw_rows:
        tk = r["type_key"]
        nt = nt_by_value.get(tk)
        icon_cls = (
            get_default_icon_for_notification_type(nt)
            if nt is not None
            else "fas fa-bell"
        )
        label = NotificationService._get_translated_notification_type_label(tk)
        hay_parts = [
            r["group"],
            tk,
            r["description"],
            label,
            str(r["ttl_days"]),
            r["default_priority"],
            icon_cls,
            "active" if r.get("emitter_active") else "hypothetical",
        ]
        hay = " ".join(hay_parts).lower()
        if q and q not in hay:
            continue
        rows_out.append(
            {
                **r,
                "label": label,
                "group_display": _(r["group"]),
                "description_display": _(r["description"]),
                "icon_class": icon_cls,
                "emitter_status_display": _("Active") if r.get("emitter_active") else _("Hypothetical"),
            }
        )

    total_specs = len(raw_rows)

    if request.args.get("export") == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                _("Group"),
                _("Type key"),
                _("Label"),
                _("Emitter active"),
                _("Default priority"),
                _("TTL (days)"),
                _("Description"),
                _("Icon"),
            ]
        )
        for rw in rows_out:
            writer.writerow(
                [
                    rw["group_display"],
                    rw["type_key"],
                    rw["label"],
                    _("Yes") if rw.get("emitter_active") else _("No"),
                    rw["default_priority"],
                    rw["ttl_days"],
                    rw["description_display"],
                    rw["icon_class"],
                ]
            )
        data = buf.getvalue()
        return Response(
            "\ufeff" + data,
            mimetype="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": "attachment; filename=notification_type_registry.csv"
            },
        )

    return render_template(
        "admin/communication/registry.html",
        rows=rows_out,
        total_catalog=total_specs,
        filtered_count=len(rows_out),
        q=request.args.get("q") or "",
    )


@bp.route("/api/notifications/send", methods=["POST"])
@csrf.exempt  # Exempt from CSRF protection for API endpoints used by mobile app
@permission_required("admin.communication.manage")
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
            from app.services.notification.core import validate_notification_url

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

        # Create notification records when email and/or push is requested
        if send_email or send_push:
            notifications = create_notification(
                user_ids=valid_user_ids,
                notification_type=NotificationType.admin_message,
                title_key='notification.admin_message.title',
                title_params={'custom_title': title},
                message_key='notification.admin_message.message',
                message_params={'message': message},
                related_url=redirect_url if redirect_url else None,
                priority=priority,
                respect_preferences=False,
                send_email_notifications=False,
                send_push_notifications=False,
            )

            if not notifications:
                error_message = 'No notifications created. All notifications were duplicates - the same notification was already sent to the selected user(s) within the last few minutes. Please wait a moment before sending again, or modify the title/message to create a unique notification.'
                current_app.logger.warning(
                    f"Failed to create notification records for admin communication from {current_user.id} ({current_user.email}). "
                    f"All notifications were likely duplicates"
                )
                flash(error_message, 'danger')
                return json_bad_request(
                    error_message,
                    success=False,
                    flash_message=error_message,
                    flash_category='danger'
                )

        notification_by_user = _latest_admin_notifications_by_user(valid_user_ids) if (send_email or send_push) else {}

        # Track results
        email_results = {'success': False, 'sent': 0, 'failed': 0}
        push_results = {'success': False, 'devices': 0, 'sent': 0, 'failed': 0}

        # Send emails if requested
        if send_email:
            email_sent_count = 0
            email_failed_count = 0

            # Create HTML email content using DB template with fallback
            from app.services.email.rendering import render_admin_email_template

            default_email_template = """
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>{{ title }}</title>
                <style>
                    body { margin: 0; padding: 0; background: #eef2f7; color: #1f2937;
                      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                      line-height: 1.65; -webkit-font-smoothing: antialiased; }
                    .email-outer { max-width: 960px; width: 100%; margin: 0 auto; padding: 28px 20px; box-sizing: border-box; }
                    .email-card { background: #ffffff; border: 1px solid #e2e8f0; }
                    .email-header { background: #0d9488; color: #ffffff; padding: 28px 40px; text-align: center; }
                    .email-header h1 { margin: 0; font-size: 24px; font-weight: 600; letter-spacing: -0.02em; }
                    .email-body { padding: 32px 40px; background: #ffffff; }
                    .message { background: #f8fafc; border: 1px solid #e2e8f0; border-left: 4px solid #0d9488;
                      padding: 22px 24px; white-space: pre-wrap; font-size: 15px; color: #334155; }
                    .email-footer { padding: 22px 40px; text-align: center; font-size: 12px; color: #64748b;
                      background: #f8fafc; border-top: 1px solid #e2e8f0; }
                    .email-footer p { margin: 0; }
                </style>
            </head>
            <body>
                <div class="email-outer">
                    <div class="email-card">
                        <div style="background-color:#0d9488;color:#ffffff;padding:28px 40px;text-align:center;">
                            <h1 style="margin:0;font-size:24px;font-weight:600;line-height:1.3;color:#ffffff;">{{ title }}</h1>
                        </div>
                        <div class="email-body">
                            <div class="message">{{ message }}</div>
                        </div>
                        <div class="email-footer">
                            <p>This is an automated message from {{ org_name }}.</p>
                        </div>
                    </div>
                </div>
            </body>
            </html>
            """
            email_template = get_email_template(
                'email_template_notification',
                default=default_email_template,
            )

            email_html = render_admin_email_template(
                email_template,
                title=title,
                message=message,
                org_name=get_org_name(),
            )

            for uid in valid_user_ids:
                recipient = user_emails.get(uid)
                if not recipient:
                    continue
                notification = notification_by_user.get(uid)
                notification_id = notification.id if notification else None
                log = log_email_attempt(notification_id, uid, recipient, title)
                try:
                    email_success = send_email_message(
                        subject=title,
                        recipients=[recipient],
                        html=email_html,
                    )
                    if email_success:
                        mark_email_sent(log.id)
                        email_sent_count += 1
                    else:
                        mark_email_failed(log.id, "Email send returned False")
                        email_failed_count += 1
                except Exception as e:
                    mark_email_failed(log.id, str(e))
                    email_failed_count += 1
                    current_app.logger.error(
                        f"Error sending email notification to {recipient}: {str(e)}"
                    )

            if email_sent_count or email_failed_count:
                email_results = {
                    'success': email_sent_count > 0 and email_failed_count == 0,
                    'sent': email_sent_count,
                    'failed': email_failed_count,
                }
                if email_sent_count:
                    current_app.logger.info(
                        f"Admin {current_user.id} ({current_user.email}) sent email notification to {email_sent_count} users"
                    )
                if email_failed_count:
                    current_app.logger.error(
                        f"Admin {current_user.id} ({current_user.email}) failed to send email notification to {email_failed_count} users"
                    )

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
@permission_required("admin.communication.manage")
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
@permission_required("admin.communication.manage")
def api_get_all_notifications():
    """Get all notifications from all users (admin view)"""
    try:
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

        notifications = query.order_by(Notification.created_at.desc()).all()
        total_count = len(notifications)

        notif_user_ids = list({n.user_id for n in notifications if getattr(n, "user_id", None) is not None})
        rbac_role_codes_by_user_id = AuthorizationService.prefetch_role_codes(notif_user_ids)

        assignment_status_cache, _ = NotificationService._build_assignment_caches_for_notifications(notifications)
        actor_fields_by_id = NotificationService.build_actor_display_fields_map(
            notifications, assignment_status_cache
        )
        email_fields_by_id = NotificationService.build_email_delivery_fields_map(
            [n.id for n in notifications],
            notifications=notifications,
            actor_fields_by_id=actor_fields_by_id,
        )

        # Format notifications
        notifications_data = []
        for notification in notifications:
            user = notification.user
            message, title = NotificationService._translate_notification_content(notification)
            if message is None:
                message = notification.message
            if title is None:
                title = notification.title

            ad = actor_fields_by_id.get(notification.id, {})
            actor_obj = ad.get('actor')
            actor_action_icon = ad.get('actor_action_icon')
            primary_is_message = ad.get('primary_is_message', False)
            if primary_is_message:
                display_title = message or title
                display_message = title if (title and title != display_title) else ''
            else:
                display_title = title
                display_message = message

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
                'title': display_title,
                'message': display_message,
                'primary_is_message': primary_is_message,
                'actor': actor_obj,
                'actor_action_icon': actor_action_icon,
                'is_read': notification.is_read,
                'is_archived': notification.is_archived,
                'priority': notification.priority,
                'created_at': notification.created_at.isoformat() if notification.created_at else None,
                'read_at': notification.read_at.isoformat() if notification.read_at else None,
                'related_url': notification.related_url,
                'icon': get_default_icon_for_notification_type(notification.notification_type),
                **email_fields_by_id.get(notification.id, NotificationService._serialize_email_delivery_log(None)),
            })

        return json_ok(
            success=True,
            notifications=notifications_data,
            pagination={
                'page': 1,
                'per_page': total_count,
                'total': total_count,
                'pages': 1 if total_count else 0,
            },
        )

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/notifications/campaigns/<int:campaign_id>/recipients", methods=["GET"])
@permission_required("admin.communication.manage")
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


@bp.route("/api/communications/email-delivery/<int:log_id>/retry", methods=["POST"])
@permission_required("admin.communication.manage")
def api_retry_email_delivery(log_id):
    """Manually retry a failed email delivery log."""
    enforce_api_or_csrf_protection()
    try:
        from app.services.email.delivery import admin_retry_email_delivery_log

        success, message = admin_retry_email_delivery_log(log_id)
        if success:
            return json_ok(success=True, message=message)
        return json_bad_request(message, success=False)
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/communications/email-delivery/retry-failed", methods=["POST"])
@permission_required("admin.communication.manage")
def api_retry_failed_email_deliveries():
    """Manually retry all failed email delivery logs (or a subset by log id)."""
    enforce_api_or_csrf_protection()
    try:
        from app.services.email.delivery import admin_retry_failed_email_delivery_logs

        data = get_json_safe() or {}
        log_ids = data.get('log_ids')
        if log_ids is not None and not isinstance(log_ids, list):
            return json_bad_request('log_ids must be a list when provided')

        result = admin_retry_failed_email_delivery_logs(log_ids=log_ids)
        overall_success = result['failure_count'] == 0 and result['attempted'] > 0
        message = (
            f"Retried {result['attempted']} email(s): "
            f"{result['success_count']} sent, {result['failure_count']} failed."
        )
        return json_ok(success=overall_success, message=message, **result)
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/communications/email-delivery/<int:log_id>/cancel", methods=["POST"])
@permission_required("admin.communication.manage")
def api_cancel_email_delivery(log_id):
    """Dismiss a failed email delivery log without retrying."""
    enforce_api_or_csrf_protection()
    try:
        from app.services.email.delivery import cancel_email_delivery_log

        success, message = cancel_email_delivery_log(log_id)
        if success:
            return json_ok(success=True, message=message)
        return json_bad_request(message, success=False)
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/communications/email-delivery/cancel-failed", methods=["POST"])
@permission_required("admin.communication.manage")
def api_cancel_failed_email_deliveries():
    """Dismiss failed email delivery logs (all or selected log ids)."""
    enforce_api_or_csrf_protection()
    try:
        from app.services.email.delivery import admin_cancel_email_delivery_logs

        data = get_json_safe() or {}
        log_ids = data.get('log_ids')
        if log_ids is not None and not isinstance(log_ids, list):
            return json_bad_request('log_ids must be a list when provided')

        result = admin_cancel_email_delivery_logs(log_ids=log_ids)
        message = (
            f"Dismissed {result['success_count']} email failure(s)."
            if result['success_count']
            else 'No email failures were dismissed.'
        )
        if result['failure_count']:
            message += f" {result['failure_count']} could not be dismissed."
        return json_ok(success=result['failure_count'] == 0, message=message, **result)
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


def _b64decode_utf8(value: str) -> str:
    import base64

    if not value or not isinstance(value, str):
        return ""
    try:
        return base64.b64decode(value).decode("utf-8")
    except Exception:
        return ""


@bp.route("/api/communication/campaign-email-templates", methods=["POST"])
@permission_required("admin.settings.manage")
def api_campaign_email_templates_save():
    """Save campaign email templates (HTML + compose defaults)."""
    from flask_login import current_user

    data = get_json_safe()
    templates_b64 = data.get("email_templates_b64") or {}
    metadata = data.get("template_metadata") or {}

    if templates_b64 and not isinstance(templates_b64, dict):
        return json_bad_request("email_templates_b64 must be an object")
    if metadata and not isinstance(metadata, dict):
        return json_bad_request("template_metadata must be an object")

    email_templates_data: dict = {}
    for tpl_key in CAMPAIGN_EMAIL_TEMPLATE_KEYS:
        raw_lang_map = templates_b64.get(tpl_key) if isinstance(templates_b64, dict) else None
        if not raw_lang_map or not isinstance(raw_lang_map, dict):
            email_templates_data[tpl_key] = {}
            continue
        decoded_langs: dict = {}
        for lang, encoded in raw_lang_map.items():
            if not isinstance(lang, str) or not lang.strip():
                continue
            decoded = _b64decode_utf8(encoded)
            if decoded and decoded.strip():
                decoded_langs[lang.strip()] = decoded
        email_templates_data[tpl_key] = decoded_langs

    user_id = current_user.id if current_user.is_authenticated else None
    try:
        ok = set_all_campaign_email_templates(
            email_templates_data,
            metadata=metadata,
            user_id=user_id,
        )
    except ValueError:
        return json_bad_request("Invalid campaign email template data.")
    except Exception as e:
        current_app.logger.warning("Save campaign email templates failed: %s", e, exc_info=True)
        return json_server_error("Failed to save campaign email templates.")
    return json_ok(success=ok)


@bp.route("/api/communication/campaign-email-template-preview", methods=["POST"])
@permission_required("admin.settings.manage")
def api_campaign_email_template_preview():
    from app.routes.admin.settings import _parse_email_template_api_request_body
    from app.services.email.preview_context import get_campaign_email_template_preview_context
    from app.services.email.rendering import (
        render_admin_email_template_for_preview,
        sanitize_admin_email_html_for_api,
    )

    data, parse_err = _parse_email_template_api_request_body()
    if parse_err:
        return parse_err
    template_key = (data.get("template_key") or "").strip()
    html_b64 = data.get("html_b64")
    template_language = data.get("template_language") or data.get("lang")
    if template_key not in CAMPAIGN_EMAIL_TEMPLATE_KEYS:
        return json_bad_request("Invalid or missing template_key.")
    if not isinstance(html_b64, str) or not html_b64.strip():
        return json_bad_request("html_b64 is required.")

    source = _b64decode_utf8(html_b64)
    if not source.strip():
        return json_bad_request("Template content is empty or could not be decoded.")

    context = get_campaign_email_template_preview_context(template_key, template_language=template_language)
    rendered, err = render_admin_email_template_for_preview(source, **context)
    if err:
        return json_bad_request(err)
    return json_ok(html=sanitize_admin_email_html_for_api(rendered))


@bp.route("/api/communication/campaign-email-compose-preview", methods=["POST"])
@permission_required("admin.communication.manage")
def api_campaign_email_compose_preview():
    """Preview campaign email HTML using compose form title and message."""
    from app.routes.admin.settings import _parse_email_template_api_request_body
    from app.services.email.preview_context import get_campaign_compose_preview_context
    from app.services.email.rendering import (
        render_admin_email_template_for_preview,
        sanitize_admin_email_html_for_api,
    )

    data, parse_err = _parse_email_template_api_request_body()
    if parse_err:
        return parse_err
    template_key = (data.get("template_key") or "").strip()
    html_b64 = data.get("html_b64")
    template_language = data.get("template_language") or data.get("lang")
    title = (data.get("title") or "").strip()
    message = (data.get("message") or "").strip()
    if template_key not in CAMPAIGN_EMAIL_TEMPLATE_KEYS:
        return json_bad_request("Invalid or missing template_key.")
    if not isinstance(html_b64, str) or not html_b64.strip():
        return json_bad_request("html_b64 is required.")

    source = _b64decode_utf8(html_b64)
    if not source.strip():
        return json_bad_request("Template content is empty or could not be decoded.")

    context = get_campaign_compose_preview_context(
        template_key,
        title=title,
        message=message,
        template_language=template_language,
    )
    rendered, err = render_admin_email_template_for_preview(source, **context)
    if err:
        return json_bad_request(err)
    return json_ok(html=sanitize_admin_email_html_for_api(rendered))


@bp.route("/api/communication/campaign-email-templates/seed", methods=["POST"])
@permission_required("admin.settings.manage")
def api_campaign_email_templates_seed():
    from flask_login import current_user
    from scripts.seed_campaign_email_templates import seed_campaign_templates

    data = get_json_safe() or {}
    force = bool(data.get("force"))
    try:
        stats = seed_campaign_templates(
            force=force,
            user_id=current_user.id if current_user.is_authenticated else None,
        )
    except Exception as e:
        current_app.logger.warning("Campaign email template seed failed: %s", e, exc_info=True)
        return json_server_error("Failed to seed campaign email templates.")
    return json_ok(stats=stats, force=force)


@bp.route("/api/communication/campaign-email-template-test-send", methods=["POST"])
@permission_required("admin.settings.manage")
def api_campaign_email_template_test_send():
    """Send a test email using a campaign template (unsaved editor content)."""
    from app.routes.admin.settings import (
        _parse_email_template_api_request_body,
        _personalize_email_preview_context_for_user,
        _resolve_email_template_test_recipient,
        _response_for_email_test_send_failure,
        _message_for_email_test_send_failure,
    )
    from app.services.email.client import send_email
    from app.services.email.preview_context import (
        get_campaign_email_template_preview_context,
        normalize_template_language,
    )
    from app.services.email.rendering import (
        render_admin_email_template_for_preview,
        sanitize_admin_email_html_for_api,
    )

    data, parse_err = _parse_email_template_api_request_body()
    if parse_err:
        return parse_err

    recipient_email, recipient_user, recipient_err = _resolve_email_template_test_recipient(data)
    if recipient_err:
        return recipient_err

    template_key = (data.get("template_key") or "").strip()
    html_b64 = data.get("html_b64")
    template_language = data.get("template_language") or data.get("lang")
    if template_key not in CAMPAIGN_EMAIL_TEMPLATE_KEYS:
        return json_bad_request("Invalid or missing template_key.")
    if not isinstance(html_b64, str) or not html_b64.strip():
        return json_bad_request("html_b64 is required.")

    source = _b64decode_utf8(html_b64)
    if not source.strip():
        return json_bad_request("Template content is empty or could not be decoded.")

    tlang = normalize_template_language(template_language)
    context = get_campaign_email_template_preview_context(template_key, template_language=template_language)
    if recipient_user is not None:
        context = _personalize_email_preview_context_for_user(context, recipient_user)
    rendered, err = render_admin_email_template_for_preview(source, **context)
    if err:
        return json_bad_request(err)
    if not (rendered or "").strip():
        return json_bad_request("Rendered message is empty.")

    meta = get_campaign_compose_templates().get(template_key) or {}
    label = (meta.get("label") or template_key).strip()
    subject = f"[Test email] {label} ({tlang})"

    try:
        failure: list = []
        ok = send_email(
            subject=subject,
            recipients=[recipient_email],
            html=sanitize_admin_email_html_for_api(rendered),
            sender=current_app.config.get("MAIL_DEFAULT_SENDER"),
            _failure_info=failure,
        )
    except Exception as e:
        current_app.logger.warning("Campaign email template test send failed: %s", e, exc_info=True)
        return json_server_error("Failed to send email. Check mail configuration and logs.")

    if not ok:
        msg = _message_for_email_test_send_failure(failure)
        return _response_for_email_test_send_failure(failure, msg)

    return json_ok(success=True, sent_to=recipient_email, subject=subject)
