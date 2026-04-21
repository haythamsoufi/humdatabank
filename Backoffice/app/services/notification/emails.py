"""
Email Notification Service

Background tasks for sending notification digests via email.
"""

from datetime import datetime, timedelta
from typing import Optional
from flask import current_app, render_template_string
from markupsafe import escape
from app import db
from app.services.email.client import send_email
from app.services.email.delivery import log_email_attempt, mark_email_sent, mark_email_failed
from app.models import Notification, NotificationPreferences, User, EmailDeliveryLog
from sqlalchemy import and_
from app.utils.datetime_helpers import utcnow
from app.utils.organization_helpers import get_org_name

# Try to import pytz for timezone support
try:
    import pytz
    PYTZ_AVAILABLE = True
except ImportError:
    PYTZ_AVAILABLE = False


def sanitize_for_email(text: str) -> str:
    """
    Sanitize text for safe use in email templates.
    Explicitly escapes HTML to prevent XSS in email clients.

    Args:
        text: Text to sanitize

    Returns:
        Escaped HTML-safe string
    """
    if not text:
        return ''
    # Explicitly escape HTML (MarkupSafe.escape handles this)
    return escape(str(text))


def _parse_time_string(time_str: str) -> Optional[tuple[int, int]]:
    try:
        hour, minute = map(int, time_str.split(':'))
        return max(0, min(hour, 23)), max(0, min(minute, 59))
    except (ValueError, AttributeError):
        return None


def _minutes_since(target: datetime, reference: datetime) -> float:
    return (reference - target).total_seconds() / 60.0


def _should_trigger_daily_digest(user_local_time: datetime, digest_time: str, window_minutes: int) -> bool:
    parsed = _parse_time_string(digest_time)
    if not parsed:
        return False
    hour, minute = parsed
    scheduled = user_local_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if scheduled > user_local_time:
        scheduled -= timedelta(days=1)
    delta_minutes = _minutes_since(scheduled, user_local_time)
    return 0 <= delta_minutes < window_minutes


def _weekday_index(day_name: str) -> Optional[int]:
    if not day_name:
        return None
    mapping = {
        'monday': 0,
        'tuesday': 1,
        'wednesday': 2,
        'thursday': 3,
        'friday': 4,
        'saturday': 5,
        'sunday': 6,
    }
    return mapping.get(day_name.strip().lower())


def _should_trigger_weekly_digest(
    user_local_time: datetime,
    digest_day: str,
    digest_time: str,
    window_minutes: int
) -> bool:
    parsed_time = _parse_time_string(digest_time)
    weekday_idx = _weekday_index(digest_day)
    if not parsed_time or weekday_idx is None:
        return False

    hour, minute = parsed_time
    days_since_target = (user_local_time.weekday() - weekday_idx) % 7
    scheduled = user_local_time - timedelta(days=days_since_target)
    scheduled = scheduled.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if scheduled > user_local_time:
        scheduled -= timedelta(days=7)
    delta_minutes = _minutes_since(scheduled, user_local_time)
    return 0 <= delta_minutes < window_minutes


def send_notification_emails():
    """
    Background task to send notification digest emails.
    Should be called by scheduler hourly - function checks if it's time for each user.
    """
    try:
        now = utcnow()
        current_hour = now.hour
        current_minute = now.minute
        current_day = now.strftime('%A').lower()  # 'monday', 'tuesday', etc.

        # Get all users with email notifications enabled
        preferences = NotificationPreferences.query.filter_by(
            email_notifications=True
        ).all()

        sent_count = 0

        digest_window_minutes = current_app.config.get('NOTIFICATION_DIGEST_TRIGGER_WINDOW_MINUTES', 60)
        default_digest_time = current_app.config.get('NOTIFICATION_DIGEST_DEFAULT_TIME', '09:00')

        for pref in preferences:
            user = User.query.get(pref.user_id)
            if not user or not user.email:
                continue

            # Get user's timezone or default to UTC
            user_timezone = getattr(pref, 'timezone', None) or 'UTC'

            # Convert user's local time to UTC for comparison
            user_local_time = None
            try:
                if PYTZ_AVAILABLE and user_timezone != 'UTC':
                    try:
                        user_tz = pytz.timezone(user_timezone)
                        # Get current time in user's timezone
                        user_local_now = datetime.now(user_tz)
                        user_local_time = user_local_now
                    except pytz.exceptions.UnknownTimeZoneError:
                        current_app.logger.warning(
                            f"Unknown timezone '{user_timezone}' for user {user.id} ({user.email}). "
                            f"Falling back to UTC. User should update their timezone preference."
                        )
                        user_local_time = now
                    except Exception as tz_error:
                        current_app.logger.warning(
                            f"Error processing timezone '{user_timezone}' for user {user.id} ({user.email}): {tz_error}. "
                            f"Falling back to UTC."
                        )
                        user_local_time = now
                else:
                    # Fallback to UTC if pytz not available or timezone is UTC
                    user_local_time = now
            except Exception as e:
                current_app.logger.warning(
                    f"Unexpected error getting timezone '{user_timezone}' for user {user.id} ({user.email}): {e}. "
                    f"Using UTC as fallback."
                )
                user_local_time = now

            # Idempotency guard: skip this user if a digest was already claimed/sent
            # within the current trigger window. This prevents duplicate sends when
            # the scheduler fires more than once in the same window (e.g. worker restart).
            last_sent = getattr(pref, 'last_digest_sent_at', None)
            if last_sent is not None:
                minutes_since_last = (now - last_sent).total_seconds() / 60.0
                if minutes_since_last < digest_window_minutes:
                    current_app.logger.debug(
                        f"Skipping digest for user {user.id} ({user.email}): "
                        f"already sent {minutes_since_last:.1f}m ago (window={digest_window_minutes}m)"
                    )
                    continue

            # Check if it's time to send based on user's preferences
            if pref.notification_frequency == 'instant':
                continue
            elif pref.notification_frequency == 'daily':
                digest_time = pref.digest_time or default_digest_time
                if _should_trigger_daily_digest(user_local_time, digest_time, digest_window_minutes):
                    if send_daily_digest(user, pref):
                        sent_count += 1
            elif pref.notification_frequency == 'weekly':
                if pref.digest_day:
                    digest_time = pref.digest_time or default_digest_time
                    if _should_trigger_weekly_digest(
                        user_local_time,
                        pref.digest_day,
                        digest_time,
                        digest_window_minutes
                    ):
                        if send_weekly_digest(user, pref):
                            sent_count += 1

        if sent_count > 0:
            current_app.logger.info(f"Email notification digests sent to {sent_count} users")

    except Exception as e:
        current_app.logger.error(f"Error sending notification emails: {str(e)}", exc_info=True)


def send_daily_digest(user, preferences, retry_count=0, max_retries=3, existing_log=None):
    """
    Send daily digest email to user with retry logic.

    Args:
        user: User instance
        preferences: NotificationPreferences instance
        retry_count: Current retry attempt (default: 0)
        max_retries: Maximum number of retries (default: 3)
        existing_log: Optional EmailDeliveryLog instance to reuse for retries
    """
    # Get unread notifications from last 24 hours
    since = utcnow() - timedelta(days=1)

    notifications = Notification.query.filter(
        and_(
            Notification.user_id == user.id,
            Notification.is_read == False,
            Notification.is_archived == False,
            Notification.created_at >= since
        )
    ).order_by(Notification.created_at.desc()).limit(50).all()

    if not notifications:
        return False  # No notifications to send

    # Filter by enabled notification types if specified
    if preferences.notification_types_enabled:
        notifications = [
            n for n in notifications
            if n.notification_type.value in preferences.notification_types_enabled
        ]

    if not notifications:
        return False

    # Claim the digest slot BEFORE sending to prevent concurrent workers from
    # double-sending. Writing last_digest_sent_at now means any other worker
    # that reads this row after our commit will see the window as occupied and skip.
    if retry_count == 0 and hasattr(preferences, 'last_digest_sent_at'):
        try:
            preferences.last_digest_sent_at = utcnow()
            db.session.commit()
        except Exception as claim_err:
            current_app.logger.warning(
                f"Could not claim digest slot for user {user.id}: {claim_err}. Proceeding anyway."
            )
            db.session.rollback()

    # Send email — translate digest content into the user's preferred language
    user_locale = getattr(user, 'preferred_language', None) or 'en'
    subject = f"Daily Notification Digest - {len(notifications)} new notification(s)"
    body = render_digest_email(user, notifications, 'Daily', locale=user_locale)

    # Log email attempt (only on first attempt, not retries)
    log = existing_log
    if not log:
        if retry_count == 0:
            log = log_email_attempt(None, user.id, user.email, subject)
        else:
            # For retries, find existing log entry
            log = EmailDeliveryLog.query.filter_by(
                user_id=user.id,
                email_address=user.email,
                subject=subject,
                status='retrying'
            ).order_by(EmailDeliveryLog.created_at.desc()).first()

    if not log:
        log = log_email_attempt(None, user.id, user.email, subject)

    try:
        success = send_email(
            subject=subject,
            recipients=[user.email],
            html=body,
            sender=current_app.config.get('MAIL_NOREPLY_SENDER', current_app.config['MAIL_DEFAULT_SENDER'])
        )

        if success:
            mark_email_sent(log.id)
            current_app.logger.info(f"Daily digest sent to {user.email} (retry {retry_count})")
            return True
        else:
            if retry_count < max_retries:
                mark_email_failed(log.id, "Email send returned False", retry=True, max_retries=max_retries)
                current_app.logger.warning(f"Failed to send daily digest to {user.email}, will retry (attempt {retry_count + 1}/{max_retries})")
            else:
                mark_email_failed(log.id, "Email send returned False", retry=False, max_retries=max_retries)
                current_app.logger.error(f"Failed to send daily digest to {user.email} after {max_retries} retries")
            return False

    except Exception as e:
        if retry_count < max_retries:
            mark_email_failed(log.id, str(e), retry=True, max_retries=max_retries)
            current_app.logger.warning(f"Error sending daily digest to {user.email}, will retry: {str(e)}")
        else:
            mark_email_failed(log.id, str(e), retry=False, max_retries=max_retries)
            current_app.logger.error(f"Error sending daily digest to {user.email} after {max_retries} retries: {str(e)}")
        return False


def send_weekly_digest(user, preferences, retry_count=0, max_retries=3, existing_log=None):
    """
    Send weekly digest email to user with retry logic.

    Args:
        user: User instance
        preferences: NotificationPreferences instance
        retry_count: Current retry attempt (default: 0)
        max_retries: Maximum number of retries (default: 3)
    """
    # Get unread notifications from last 7 days
    since = utcnow() - timedelta(days=7)

    notifications = Notification.query.filter(
        and_(
            Notification.user_id == user.id,
            Notification.is_read == False,
            Notification.is_archived == False,
            Notification.created_at >= since
        )
    ).order_by(Notification.created_at.desc()).limit(100).all()

    if not notifications:
        return False  # No notifications to send

    # Filter by enabled notification types if specified
    if preferences.notification_types_enabled:
        notifications = [
            n for n in notifications
            if n.notification_type.value in preferences.notification_types_enabled
        ]

    if not notifications:
        return False

    # Claim the digest slot BEFORE sending (same idempotency pattern as send_daily_digest).
    if retry_count == 0 and hasattr(preferences, 'last_digest_sent_at'):
        try:
            preferences.last_digest_sent_at = utcnow()
            db.session.commit()
        except Exception as claim_err:
            current_app.logger.warning(
                f"Could not claim weekly digest slot for user {user.id}: {claim_err}. Proceeding anyway."
            )
            db.session.rollback()

    # Send email — translate digest content into the user's preferred language
    user_locale = getattr(user, 'preferred_language', None) or 'en'
    subject = f"Weekly Notification Digest - {len(notifications)} new notification(s)"
    body = render_digest_email(user, notifications, 'Weekly', locale=user_locale)

    # Log email attempt (only on first attempt, not retries)
    log = existing_log
    if not log:
        if retry_count == 0:
            log = log_email_attempt(None, user.id, user.email, subject)
        else:
            # For retries, find existing log entry
            log = EmailDeliveryLog.query.filter_by(
                user_id=user.id,
                email_address=user.email,
                subject=subject,
                status='retrying'
            ).order_by(EmailDeliveryLog.created_at.desc()).first()

    if not log:
        log = log_email_attempt(None, user.id, user.email, subject)

    try:
        success = send_email(
            subject=subject,
            recipients=[user.email],
            html=body,
            sender=current_app.config.get('MAIL_NOREPLY_SENDER', current_app.config['MAIL_DEFAULT_SENDER'])
        )

        if success:
            mark_email_sent(log.id)
            current_app.logger.info(f"Weekly digest sent to {user.email} (retry {retry_count})")
            return True
        else:
            if retry_count < max_retries:
                mark_email_failed(log.id, "Email send returned False", retry=True, max_retries=max_retries)
                current_app.logger.warning(f"Failed to send weekly digest to {user.email}, will retry (attempt {retry_count + 1}/{max_retries})")
            else:
                mark_email_failed(log.id, "Email send returned False", retry=False, max_retries=max_retries)
                current_app.logger.error(f"Failed to send weekly digest to {user.email} after {max_retries} retries")
            return False

    except Exception as e:
        if retry_count < max_retries:
            mark_email_failed(log.id, str(e), retry=True, max_retries=max_retries)
            current_app.logger.warning(f"Error sending weekly digest to {user.email}, will retry: {str(e)}")
        else:
            mark_email_failed(log.id, str(e), retry=False, max_retries=max_retries)
            current_app.logger.error(f"Error sending weekly digest to {user.email} after {max_retries} retries: {str(e)}")
        return False


def retry_email_delivery_log(log):
    """
    Retry sending an email for the provided EmailDeliveryLog record.

    Args:
        log: EmailDeliveryLog instance

    Returns:
        bool: True if retry succeeded, False otherwise
    """
    if not log:
        return False

    try:
        user = User.query.get(log.user_id)
        if not user or not user.email:
            mark_email_failed(log.id, "User missing for retry", retry=False)
            return False

        if log.notification_id:
            notification = Notification.query.get(log.notification_id)
            if not notification:
                mark_email_failed(log.id, "Notification missing for retry", retry=False)
                return False

            subject = f"New Notification: {notification.title}"
            body = render_instant_email(user, notification)

            try:
                success = send_email(
                    subject=subject,
                    recipients=[user.email],
                    html=body,
                    sender=current_app.config.get('MAIL_NOREPLY_SENDER', current_app.config['MAIL_DEFAULT_SENDER'])
                )

                if success:
                    mark_email_sent(log.id)
                    return True

                mark_email_failed(log.id, "Retry failed: Email send returned False", retry=True)
                return False
            except Exception as e:
                mark_email_failed(log.id, f"Retry failed: {str(e)}", retry=True)
                current_app.logger.error(f"Error retrying notification email log {log.id}: {e}", exc_info=True)
                return False

        # Digest retries (no notification_id)
        preferences = NotificationPreferences.query.filter_by(user_id=user.id).first()
        if not preferences:
            preferences = NotificationPreferences(
                user_id=user.id,
                email_notifications=True,
                notification_types_enabled=[],
                notification_frequency='instant',
                sound_enabled=False
            )
            db.session.add(preferences)
            db.session.commit()

        subject_text = (log.subject or '').lower()
        initial_retry_count = log.retry_count

        if 'weekly notification digest' in subject_text:
            result = send_weekly_digest(user, preferences, retry_count=log.retry_count, existing_log=log)
        elif 'daily notification digest' in subject_text:
            result = send_daily_digest(user, preferences, retry_count=log.retry_count, existing_log=log)
        else:
            mark_email_failed(log.id, "Unknown digest email subject", retry=False)
            return False

        # Refresh log to get the latest status updates
        db.session.refresh(log)

        if result or log.status == 'sent':
            return True

        # If no change occurred, mark as failed without further retries
        if log.retry_count == initial_retry_count and log.status == 'retrying':
            mark_email_failed(log.id, "Digest retry skipped - no pending notifications", retry=False)

        return False

    except Exception as e:
        current_app.logger.error(f"Error retrying email delivery log {log.id}: {e}", exc_info=True)
        mark_email_failed(log.id, f"Retry processing failed: {e}", retry=True)
        return False


def send_instant_notification_email(user, notification, override_preferences=False):
    """
    Send instant email notification for a single notification.
    Call this when creating high-priority notifications.

    Args:
        user: User instance
        notification: Notification instance
        override_preferences: If True, bypass user preferences and send email anyway (admin override)
    """
    # If override is enabled, skip preference checks
    if not override_preferences:
        # Check if user has email notifications enabled
        preferences = NotificationPreferences.query.filter_by(user_id=user.id).first()

        if not preferences or not preferences.email_notifications:
            return

        if preferences.notification_frequency != 'instant':
            # Allow high and urgent notifications to bypass digest preference
            urgent_priorities = {'high', 'urgent'}
            if (notification.priority or 'normal').lower() not in urgent_priorities:
                return
            current_app.logger.debug(
                f"[EMAIL_NOTIFICATION] Urgent priority override: sending email to {user.email} "
                f"despite digest preference ({preferences.notification_frequency})"
            )

        # Check if notification type is enabled
        if preferences.notification_types_enabled:
            if notification.notification_type.value not in preferences.notification_types_enabled:
                return

    # Send email - use title as full subject for high/urgent (already action-oriented)
    if notification.priority in ('high', 'urgent'):
        subject = notification.title
    else:
        subject = f"New Notification: {notification.title}"
    body = render_instant_email(user, notification)

    # Determine email importance: pass actual priority so subject shows [URGENT] vs [HIGH PRIORITY]
    importance = (notification.priority or 'normal').lower() if notification.priority in ('high', 'urgent') else None

    # Log email attempt
    log = log_email_attempt(notification.id, user.id, user.email, subject)

    try:
        filtered_out = []
        success = send_email(
            subject=subject,
            recipients=[user.email],
            html=body,
            sender=current_app.config.get('MAIL_NOREPLY_SENDER', current_app.config['MAIL_DEFAULT_SENDER']),
            importance=importance,
            _filtered_out=filtered_out,
        )

        if success:
            mark_email_sent(log.id)
        elif filtered_out:
            pass  # Recipient filtered (e.g. ALLOWED_EMAIL_RECIPIENTS_DEV) - not a failure
        else:
            mark_email_failed(log.id, "Email send returned False", retry=True, max_retries=3)
            current_app.logger.error(f"Failed to send instant notification to {user.email}")

    except Exception as e:
        mark_email_failed(log.id, str(e), retry=True, max_retries=3)
        current_app.logger.error(f"Error sending instant notification to {user.email}: {str(e)}")


def _translate_notification_for_email(notif, locale: Optional[str]) -> tuple:
    """
    Return (translated_title, translated_message) for a notification using the given locale.
    Falls back to the stored English title/message on any error or missing keys.
    """
    if not locale:
        return notif.title, notif.message

    title_key = getattr(notif, 'title_key', None)
    title_params = getattr(notif, 'title_params', None)
    message_key = getattr(notif, 'message_key', None)
    message_params = getattr(notif, 'message_params', None)

    if not title_key and not message_key:
        return notif.title, notif.message

    try:
        from flask_babel import force_locale
        from app.services.notification.core import translate_notification_message
        tp = title_params
        if tp is None:
            tp = {}
        elif not isinstance(tp, dict):
            try:
                import json
                tp = json.loads(tp) if isinstance(tp, str) else {}
            except Exception:
                tp = {}
        else:
            tp = tp.copy()
        if title_key == 'notification.assignment_submitted.admin.title':
            if 'submitter_name' not in tp:
                tp['submitter_name'] = 'A focal point'
            if 'period' not in tp:
                tp['period'] = '—'
        with force_locale(locale):
            title = translate_notification_message(title_key, tp, locale=locale) if title_key else notif.title
            message = translate_notification_message(message_key, message_params, locale=locale) if message_key else notif.message
        return title or notif.title, message or notif.message
    except Exception as e:
        current_app.logger.warning(f"Failed to translate notification {notif.id} for digest (locale={locale}): {e}")
        return notif.title, notif.message


def render_digest_email(user, notifications, frequency, locale: Optional[str] = None):
    """Render HTML email template for notification digest."""
    template = """
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
            .container { max-width: 600px; margin: 0 auto; padding: 20px; }
            .header { background-color: #dc2626; color: white; padding: 20px; text-align: center; }
            .notification { border-left: 3px solid #2563eb; padding: 15px; margin: 15px 0; background-color: #f9fafb; }
            .notification.unread { background-color: #eff6ff; }
            .notification h3 { margin: 0 0 10px 0; color: #111827; }
            .notification p { margin: 5px 0; color: #4b5563; }
            .notification .meta { font-size: 12px; color: #6b7280; }
            .footer { text-align: center; padding: 20px; color: #6b7280; font-size: 12px; }
            .button { display: inline-block; padding: 10px 20px; background-color: #2563eb; color: white; text-decoration: none; border-radius: 5px; margin: 10px 0; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>{{ frequency }} Notification Digest</h1>
                <p>{{ notifications|length }} new notification(s) for {{ user.name }}</p>
            </div>

            <div style="padding: 20px;">
                <p>Hello {{ user.name }},</p>
                <p>Here's your {{ frequency.lower() }} notification digest:</p>

                {% for notification in notifications %}
                <div class="notification {% if not notification.is_read %}unread{% endif %}">
                    <h3>{{ notification.title }}</h3>
                    <p>{{ notification.message }}</p>
                    <div class="meta">
                        <span>{{ notification.notification_type.value.replace('_', ' ').title() }}</span>
                        <span> • </span>
                        <span>{{ notification.created_at.strftime('%Y-%m-%d %H:%M') }}</span>
                        {% if notification.priority != 'normal' %}
                        <span> • </span>
                        <span style="color: #dc2626; font-weight: bold;">{{ notification.priority.upper() }}</span>
                        {% endif %}
                    </div>
                    {% if notification.related_url %}
                    <a href="{{ base_url }}{{ notification.related_url }}" class="button">View Details</a>
                    {% endif %}
                </div>
                {% endfor %}

                <div style="text-align: center; margin-top: 30px;">
                    <a href="{{ base_url }}/notifications" class="button">View All Notifications</a>
                </div>
            </div>

            <div class="footer">
                <p>You're receiving this email because you have email notifications enabled.</p>
                <p><a href="{{ base_url }}/notifications">Manage your notification preferences</a></p>
                <p>{{ org_name }}</p>
            </div>
        </div>
    </body>
    </html>
    """

    base_url = current_app.config.get('BASE_URL', 'http://localhost:5000')

    # Sanitize (and translate) notification content for safe rendering.
    # Translate at send time using the user's preferred locale so digest emails
    # respect the user's language, not just the stored English fallback.
    sanitized_notifications = []
    for notif in notifications:
        translated_title, translated_message = _translate_notification_for_email(notif, locale)
        sanitized_notifications.append({
            'title': sanitize_for_email(translated_title or notif.title),
            'message': sanitize_for_email(translated_message or notif.message),
            'notification_type': notif.notification_type,
            'is_read': notif.is_read,
            'created_at': notif.created_at,
            'priority': sanitize_for_email(notif.priority),
            'related_url': notif.related_url  # URL is validated separately
        })

    # Get organization branding
    org_name = get_org_name()

    return render_template_string(
        template,
        user={'name': sanitize_for_email(user.name or user.email), 'email': user.email},
        notifications=sanitized_notifications,
        frequency=sanitize_for_email(frequency),
        base_url=base_url,
        org_name=org_name
    )


def render_instant_email(user, notification):
    """Render HTML email template for instant notification."""
    # Determine header style: action-required for high/urgent, informational for normal
    is_action_required = (notification.priority or 'normal') in ('high', 'urgent')
    header_label = 'Action Required' if is_action_required else 'Notification'
    header_subtitle = '' if is_action_required else 'For your information'

    template = """
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
            .container { max-width: 600px; margin: 0 auto; padding: 20px; }
            .header { background-color: #dc2626; color: white; padding: 20px; text-align: center; }
            .header.action-required { background-color: #b91c1c; }
            .header .subtitle { font-size: 14px; opacity: 0.9; margin-top: 4px; }
            .content { padding: 30px; background-color: #f9fafb; }
            .notification { border-left: 4px solid #2563eb; padding: 20px; background-color: white; }
            .notification.action-required { border-left-color: #dc2626; }
            .notification h2 { margin: 0 0 15px 0; color: #111827; }
            .notification p { margin: 10px 0; color: #4b5563; }
            .button { display: inline-block; padding: 12px 24px; background-color: #2563eb; color: white; text-decoration: none; border-radius: 5px; margin: 15px 0; }
            .button.action-required { background-color: #dc2626; }
            .footer { text-align: center; padding: 20px; color: #6b7280; font-size: 12px; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header {% if is_action_required %}action-required{% endif %}">
                <h1>{{ header_label }}</h1>
                {% if header_subtitle %}<p class="subtitle">{{ header_subtitle }}</p>{% endif %}
            </div>

            <div class="content">
                <p>Hello {{ user.name }},</p>

                <div class="notification {% if is_action_required %}action-required{% endif %}">
                    <h2>{{ notification.title }}</h2>
                    <p>{{ notification.message }}</p>
                    <p style="font-size: 12px; color: #6b7280;">
                        {{ notification.notification_type.value.replace('_', ' ').title() }}
                        {% if notification.priority and notification.priority != 'normal' %}
                        • <span style="color: #dc2626; font-weight: bold;">{{ notification.priority.upper() }}</span>
                        {% endif %}
                    </p>
                    {% if notification.related_url %}
                    <a href="{{ base_url }}{{ notification.related_url }}" class="button {% if is_action_required %}action-required{% endif %}">{{ button_label }}</a>
                    {% endif %}
                </div>
            </div>

            <div class="footer">
                <p><a href="{{ base_url }}/notifications">View all notifications</a> | <a href="{{ base_url }}/notifications">Manage preferences</a></p>
                <p>{{ org_name }}</p>
            </div>
        </div>
    </body>
    </html>
    """

    base_url = current_app.config.get('BASE_URL', 'http://localhost:5000')

    # Get organization branding
    org_name = get_org_name()

    # Button label: "View Submission" for assignment submit/reopen, "View Details" otherwise
    nt_val = getattr(notification.notification_type, 'value', str(notification.notification_type))
    button_label = 'View Submission' if nt_val in ('assignment_submitted', 'assignment_reopened') else 'View Details'

    # Sanitize notification content for safe rendering
    sanitized_notification = {
        'title': sanitize_for_email(notification.title),
        'message': sanitize_for_email(notification.message),
        'notification_type': notification.notification_type,
        'priority': sanitize_for_email(notification.priority),
        'related_url': notification.related_url  # URL is validated separately
    }

    return render_template_string(
        template,
        user={'name': sanitize_for_email(user.name or user.email), 'email': user.email},
        notification=sanitized_notification,
        base_url=base_url,
        org_name=org_name,
        button_label=button_label,
        is_action_required=is_action_required,
        header_label=header_label,
        header_subtitle=header_subtitle
    )
