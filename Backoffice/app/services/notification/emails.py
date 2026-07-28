"""
Email Notification Service

Background tasks for sending notification digests via email.
"""

import html as html_lib
import re
import threading
from datetime import datetime, timedelta
from typing import Optional
from flask import current_app
from markupsafe import escape
from app import db
from app.services.email.client import send_email
from app.services.email.delivery import log_email_attempt, mark_email_sent, mark_email_failed, classify_orphan_email_log
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


def _notifications_eligible_for_email(notifications):
    """Exclude in-app-only notification types from digest/instant email delivery."""
    from app.services.notification.core import IN_APP_ONLY_NOTIFICATION_TYPES

    return [
        n for n in notifications
        if n.notification_type not in IN_APP_ONLY_NOTIFICATION_TYPES
    ]


def _create_digest_delivery_notification(
    user,
    bundled_notifications,
    frequency: str,
    subject: str,
) -> Optional[int]:
    """Create a delivery-receipt notification linked to a digest email log."""
    from app.models.enums import NotificationType
    from app.services.notification.core import create_notification

    count = len(bundled_notifications)
    freq_lower = frequency.lower()
    message = (
        f"{frequency} email digest delivered with {count} notification(s). "
        "Open your notification center for details."
    )

    created = create_notification(
        user_ids=user.id,
        notification_type=NotificationType.email_digest,
        title_key='notification.email_digest.title',
        title_params={'custom_title': subject, 'frequency': freq_lower, 'count': count},
        message_key='notification.email_digest.message',
        message_params={'message': message, 'frequency': freq_lower, 'count': count},
        related_url='/notifications',
        priority='low',
        icon='fa-envelope-open-text',
        category='system',
        tags=['email-digest', freq_lower],
        respect_preferences=False,
        send_email_notifications=False,
        send_push_notifications=False,
    )
    return created[0].id if created else None


def _resolve_digest_email_log(
    user,
    bundled_notifications,
    frequency: str,
    subject: str,
    retry_count: int,
    existing_log: Optional[EmailDeliveryLog],
) -> EmailDeliveryLog:
    """Create or reuse EmailDeliveryLog with notification_id for digest sends."""
    notification_id = None
    if existing_log and existing_log.notification_id:
        notification_id = existing_log.notification_id
    elif retry_count == 0:
        notification_id = _create_digest_delivery_notification(
            user, bundled_notifications, frequency, subject
        )

    log = existing_log
    if not log:
        if retry_count == 0:
            log = log_email_attempt(notification_id, user.id, user.email, subject)
        else:
            log = EmailDeliveryLog.query.filter_by(
                user_id=user.id,
                email_address=user.email,
                subject=subject,
                status='retrying',
            ).order_by(EmailDeliveryLog.created_at.desc()).first()

    if not log:
        log = log_email_attempt(notification_id, user.id, user.email, subject)
    elif notification_id and not log.notification_id:
        log.notification_id = notification_id
        db.session.commit()

    return log


def _get_or_create_digest_preferences(user):
    preferences = NotificationPreferences.query.filter_by(user_id=user.id).first()
    if not preferences:
        preferences = NotificationPreferences(
            user_id=user.id,
            email_notifications=True,
            notification_types_enabled=[],
            notification_frequency='instant',
            sound_enabled=False,
        )
        db.session.add(preferences)
        db.session.commit()
    return preferences


def _retry_digest_email_log(user, log) -> bool:
    orphan_kind = classify_orphan_email_log(log.subject)
    if orphan_kind not in ('daily_digest', 'weekly_digest'):
        mark_email_failed(
            log.id,
            f"Retry not supported for digest email (subject: {log.subject or '(empty)'})",
            retry=False,
        )
        return False

    preferences = _get_or_create_digest_preferences(user)
    if orphan_kind == 'weekly_digest':
        result = send_weekly_digest(user, preferences, retry_count=log.retry_count, existing_log=log)
    else:
        result = send_daily_digest(user, preferences, retry_count=log.retry_count, existing_log=log)

    db.session.refresh(log)
    return result or log.status == 'sent'


def _retry_instant_notification_email_log(user, log, notification) -> bool:
    locale = _user_locale(user)
    subject = _instant_notification_subject(notification, locale)
    body = render_instant_email(user, notification, locale=locale)

    try:
        success = send_email(
            subject=subject,
            recipients=[user.email],
            html=body,
            sender=current_app.config.get('MAIL_NOREPLY_SENDER', current_app.config['MAIL_DEFAULT_SENDER']),
        )

        if success:
            mark_email_sent(log.id)
            return True

        mark_email_failed(log.id, "Retry failed: Email send returned False", retry=False)
        return False
    except Exception as e:
        mark_email_failed(log.id, f"Retry failed: {str(e)}", retry=False)
        current_app.logger.error(f"Error retrying notification email log {log.id}: {e}", exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Compiled Jinja2 template cache
#
# render_template_string() parses and compiles the template from source on
# every call.  For digest sends that touch hundreds of users this adds up.
# We cache the compiled template objects so compilation only happens once.
# ---------------------------------------------------------------------------

_template_lock = threading.Lock()
_compiled_digest_template = None
_compiled_instant_template = None


def _get_digest_template():
    """Return the cached compiled Jinja2 digest-email template."""
    global _compiled_digest_template
    if _compiled_digest_template is None:
        with _template_lock:
            if _compiled_digest_template is None:
                _compiled_digest_template = current_app.jinja_env.from_string(_DIGEST_TEMPLATE_SRC)
    return _compiled_digest_template


def _get_instant_template():
    """Return the cached compiled Jinja2 instant-email template."""
    global _compiled_instant_template
    if _compiled_instant_template is None:
        with _template_lock:
            if _compiled_instant_template is None:
                _compiled_instant_template = current_app.jinja_env.from_string(_INSTANT_TEMPLATE_SRC)
    return _compiled_instant_template


def _user_locale(user) -> str:
    return getattr(user, 'preferred_language', None) or 'en'


def _with_user_locale(locale: str, callback):
    """Run *callback(gettext)* under *locale*, falling back to English."""
    from flask_babel import force_locale, gettext as _g

    try:
        with force_locale(locale):
            return callback(_g)
    except Exception:
        try:
            with force_locale('en'):
                return callback(_g)
        except Exception:
            return None


def _digest_subject(frequency: str, count: int, locale: str) -> str:
    freq_lower = frequency.lower()
    msgid = (
        'Weekly Notification Digest - %(count)d new notification(s)'
        if freq_lower == 'weekly'
        else 'Daily Notification Digest - %(count)d new notification(s)'
    )

    def _make(_g):
        return _g(msgid, count=count)

    translated = _with_user_locale(locale, _make)
    if translated is not None:
        return translated
    return f"{frequency} Notification Digest - {count} new notification(s)"


def _instant_notification_subject(notification, locale: str) -> str:
    if notification.priority in ('high', 'urgent'):
        return notification.title

    def _make(_g):
        return _g('New Notification: %(title)s', title=notification.title)

    translated = _with_user_locale(locale, _make)
    if translated is not None:
        return translated
    return f"New Notification: {notification.title}"


def _build_digest_email_i18n(locale: str, user_name: str, notification_count: int, frequency: str) -> dict:
    freq_lower = frequency.lower()

    def _make(_g):
        freq_label = _g('Weekly') if freq_lower == 'weekly' else _g('Daily')
        return {
            'digest_heading': _g('%(frequency)s notification digest', frequency=freq_label),
            'digest_subtitle': _g(
                '%(count)d new notification(s) for %(name)s',
                count=notification_count,
                name=user_name,
            ),
            'greeting': _g('Hello %(name)s,', name=user_name),
            'intro': _g("Here's your %(frequency)s notification digest:", frequency=freq_label.lower()),
            'view_details': _g('View details'),
            'view_all': _g('View all notifications'),
            'footer_note': _g("You're receiving this email because you have email notifications enabled."),
            'manage_prefs': _g('Manage your notification preferences'),
        }

    translated = _with_user_locale(locale, _make)
    if translated is not None:
        return translated
    return {
        'digest_heading': f'{frequency} notification digest',
        'digest_subtitle': f'{notification_count} new notification(s) for {user_name}',
        'greeting': f'Hello {user_name},',
        'intro': f"Here's your {frequency.lower()} notification digest:",
        'view_details': 'View details',
        'view_all': 'View all notifications',
        'footer_note': "You're receiving this email because you have email notifications enabled.",
        'manage_prefs': 'Manage your notification preferences',
    }


def _build_instant_email_i18n(
    locale: str,
    user_name: str,
    is_action_required: bool,
    notification_type_value: str,
) -> dict:
    def _make(_g):
        if notification_type_value in ('assignment_submitted', 'assignment_reopened'):
            button_label = _g('View Submission')
        else:
            button_label = _g('View Details')
        return {
            'greeting': _g('Hello %(name)s,', name=user_name),
            'header_label': _g('Action Required') if is_action_required else _g('Notification'),
            'header_subtitle': '' if is_action_required else _g('For your information'),
            'button_label': button_label,
            'view_all': _g('View all notifications'),
            'manage_prefs': _g('Manage preferences'),
        }

    translated = _with_user_locale(locale, _make)
    if translated is not None:
        return translated
    button_label = (
        'View Submission'
        if notification_type_value in ('assignment_submitted', 'assignment_reopened')
        else 'View Details'
    )
    return {
        'greeting': f'Hello {user_name},',
        'header_label': 'Action Required' if is_action_required else 'Notification',
        'header_subtitle': '' if is_action_required else 'For your information',
        'button_label': button_label,
        'view_all': 'View all notifications',
        'manage_prefs': 'Manage preferences',
    }


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


_DIGEST_SUBJECT_PREFIXES = (
    'Daily Notification Digest',
    'Weekly Notification Digest',
)


def html_to_plain_text(value: Optional[str]) -> str:
    """Convert HTML or escaped HTML to readable plain text for admin grids."""
    text = str(value or '')
    if not text:
        return ''

    text = re.sub(r'<\s*br\s*/?\s*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</\s*(p|div|li|tr|h[1-6])\s*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html_lib.unescape(text)
    text = text.replace('\xa0', ' ')
    text = re.sub(r'[ \t\f\v]+', ' ', text)
    text = re.sub(r'\n[ \t]+', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def derive_email_content_plain(subject: Optional[str], message: Optional[str]) -> str:
    """
    Best-effort plain-text preview of email body for admin Communication Center.

    Email HTML is not persisted on EmailDeliveryLog; digest subjects are shown as-is.
    """
    subject_text = (subject or '').strip()
    for prefix in _DIGEST_SUBJECT_PREFIXES:
        if subject_text.startswith(prefix):
            return subject_text

    plain = html_to_plain_text(message)
    if plain:
        return plain
    return subject_text


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
    Should be called by scheduler periodically — function checks if it's time for each user.

    A PostgreSQL advisory lock (``DIGEST_EMAIL_LOCK_ID``) prevents two App Service instances
    from running the sweep concurrently when ``REDIS_URL`` is unset, so no user ever receives
    two digest emails from the same scheduler window.  The per-user atomic UPDATE claim in
    ``send_daily_digest``/``send_weekly_digest`` acts as belt-and-suspenders if the session
    lock is released mid-sweep (e.g. pool recycle).
    """
    use_pg_lock = False
    lock_acquired = False
    lock_id = None
    try:
        from app.utils.constants import DEFAULT_DIGEST_EMAIL_LOCK_ID
        from app.utils.pg_advisory_lock import release_session_advisory_lock, try_session_advisory_lock

        use_pg_lock = db.engine.dialect.name == "postgresql"
        if use_pg_lock:
            lock_id = int(current_app.config.get('DIGEST_EMAIL_LOCK_ID', DEFAULT_DIGEST_EMAIL_LOCK_ID))
            lock_acquired = try_session_advisory_lock(db.session, lock_id)
            if not lock_acquired:
                current_app.logger.debug(
                    "Skipping digest email sweep — another instance is already running it"
                )
                return

        now = utcnow()
        current_hour = now.hour
        current_minute = now.minute
        current_day = now.strftime('%A').lower()  # 'monday', 'tuesday', etc.

        # Early-exit: skip the full preferences load when no digest users exist.
        # This makes the common case (no users, or all users on 'instant') a single
        # lightweight COUNT query instead of a full table scan + User join.
        has_digest_user = (
            db.session.query(NotificationPreferences.user_id)
            .filter(
                NotificationPreferences.email_notifications.is_(True),
                NotificationPreferences.notification_frequency.in_(['daily', 'weekly']),
            )
            .limit(1)
            .first()
        )
        if has_digest_user is None:
            return

        # Get all users with email notifications enabled
        preferences = NotificationPreferences.query.filter_by(
            email_notifications=True
        ).all()

        user_ids = {pref.user_id for pref in preferences if pref.user_id}
        users_by_id = {}
        if user_ids:
            users_by_id = {u.id: u for u in User.query.filter(User.id.in_(user_ids)).all()}

        sent_count = 0

        digest_window_minutes = current_app.config.get('NOTIFICATION_DIGEST_TRIGGER_WINDOW_MINUTES', 60)
        default_digest_time = current_app.config.get('NOTIFICATION_DIGEST_DEFAULT_TIME', '09:00')

        for pref in preferences:
            user = users_by_id.get(pref.user_id)
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
    finally:
        if use_pg_lock and lock_id is not None:
            try:
                release_session_advisory_lock(db.session, lock_id, acquired=lock_acquired)
            except Exception:
                pass


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

    notifications = _notifications_eligible_for_email(notifications)
    if not notifications:
        return False

    # Filter by enabled notification types if specified
    if preferences.notification_types_enabled:
        notifications = [
            n for n in notifications
            if n.notification_type.value in preferences.notification_types_enabled
        ]

    if not notifications:
        return False

    # Atomic claim: a single UPDATE WHERE wins the slot for exactly one concurrent caller.
    # The advisory lock on send_notification_emails is the primary guard; this is
    # belt-and-suspenders for edge cases where the session lock is released mid-sweep
    # (e.g. pool recycle) and a second instance races to the same user.
    if retry_count == 0 and hasattr(preferences, 'last_digest_sent_at'):
        try:
            from sqlalchemy import update as _sa_update, or_ as _sa_or_

            _window_m = int(current_app.config.get('NOTIFICATION_DIGEST_TRIGGER_WINDOW_MINUTES', 60))
            _cutoff = utcnow() - timedelta(minutes=_window_m)
            claimed = db.session.execute(
                _sa_update(NotificationPreferences)
                .where(
                    NotificationPreferences.user_id == preferences.user_id,
                    _sa_or_(
                        NotificationPreferences.last_digest_sent_at.is_(None),
                        NotificationPreferences.last_digest_sent_at < _cutoff,
                    ),
                )
                .values(last_digest_sent_at=utcnow())
                .execution_options(synchronize_session=False)
            ).rowcount
            db.session.commit()
            if claimed == 0:
                current_app.logger.debug(
                    "Daily digest slot already claimed for user %s — skipping duplicate", user.id
                )
                return False
        except Exception as claim_err:
            current_app.logger.warning(
                "Could not atomically claim daily digest slot for user %s: %s. Proceeding anyway.",
                user.id, claim_err,
            )
            db.session.rollback()

    # Send email — translate digest content into the user's preferred language
    user_locale = _user_locale(user)
    subject = _digest_subject('Daily', len(notifications), user_locale)
    body = render_digest_email(user, notifications, 'Daily', locale=user_locale)

    log = _resolve_digest_email_log(
        user, notifications, 'Daily', subject, retry_count, existing_log
    )

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
            mark_email_failed(log.id, "Email send returned False", retry=False)
            current_app.logger.error(f"Failed to send daily digest to {user.email}")
            return False

    except Exception as e:
        mark_email_failed(log.id, str(e), retry=False)
        current_app.logger.error(f"Error sending daily digest to {user.email}: {str(e)}")
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

    notifications = _notifications_eligible_for_email(notifications)
    if not notifications:
        return False

    # Filter by enabled notification types if specified
    if preferences.notification_types_enabled:
        notifications = [
            n for n in notifications
            if n.notification_type.value in preferences.notification_types_enabled
        ]

    if not notifications:
        return False

    # Atomic claim — same belt-and-suspenders pattern as send_daily_digest.
    if retry_count == 0 and hasattr(preferences, 'last_digest_sent_at'):
        try:
            from sqlalchemy import update as _sa_update, or_ as _sa_or_

            _window_m = int(current_app.config.get('NOTIFICATION_DIGEST_TRIGGER_WINDOW_MINUTES', 60))
            _cutoff = utcnow() - timedelta(minutes=_window_m)
            claimed = db.session.execute(
                _sa_update(NotificationPreferences)
                .where(
                    NotificationPreferences.user_id == preferences.user_id,
                    _sa_or_(
                        NotificationPreferences.last_digest_sent_at.is_(None),
                        NotificationPreferences.last_digest_sent_at < _cutoff,
                    ),
                )
                .values(last_digest_sent_at=utcnow())
                .execution_options(synchronize_session=False)
            ).rowcount
            db.session.commit()
            if claimed == 0:
                current_app.logger.debug(
                    "Weekly digest slot already claimed for user %s — skipping duplicate", user.id
                )
                return False
        except Exception as claim_err:
            current_app.logger.warning(
                "Could not atomically claim weekly digest slot for user %s: %s. Proceeding anyway.",
                user.id, claim_err,
            )
            db.session.rollback()

    # Send email — translate digest content into the user's preferred language
    user_locale = _user_locale(user)
    subject = _digest_subject('Weekly', len(notifications), user_locale)
    body = render_digest_email(user, notifications, 'Weekly', locale=user_locale)

    log = _resolve_digest_email_log(
        user, notifications, 'Weekly', subject, retry_count, existing_log
    )

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
            mark_email_failed(log.id, "Email send returned False", retry=False)
            current_app.logger.error(f"Failed to send weekly digest to {user.email}")
            return False

    except Exception as e:
        mark_email_failed(log.id, str(e), retry=False)
        current_app.logger.error(f"Error sending weekly digest to {user.email}: {str(e)}")
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

            from app.models.enums import NotificationType

            if notification.notification_type == NotificationType.email_digest:
                return _retry_digest_email_log(user, log)

            if notification.notification_type == NotificationType.account_welcome:
                from app.services.email.service import send_welcome_email
                result = send_welcome_email(user, existing_log=log)
                db.session.refresh(log)
                return result or log.status == 'sent'

            return _retry_instant_notification_email_log(user, log, notification)

        # Legacy orphan logs (no notification_id): digests, welcome emails, etc.
        orphan_kind = classify_orphan_email_log(log.subject)

        if orphan_kind == 'unsupported':
            mark_email_failed(
                log.id,
                f"Retry not supported for this email type (subject: {log.subject or '(empty)'})",
                retry=False,
            )
            return False

        if orphan_kind == 'welcome':
            from app.services.email.service import send_welcome_email
            result = send_welcome_email(user, existing_log=log)
            db.session.refresh(log)
            return result or log.status == 'sent'

        if orphan_kind == 'fds_access_request_digest':
            from app.services.organization.country_access_request_service import (
                pending_country_access_requests_by_fds_member,
            )
            from app.services.email.fds_access_request_digest import (
                send_fds_access_request_digest_email,
            )
            requests = pending_country_access_requests_by_fds_member().get(user.id, [])
            if not requests:
                mark_email_failed(
                    log.id,
                    "No pending access requests remain for this FDS member",
                    retry=False,
                )
                return False
            result = send_fds_access_request_digest_email(user, requests, existing_log=log)
            db.session.refresh(log)
            return result or log.status == 'sent'

        return _retry_digest_email_log(user, log)

    except Exception as e:
        current_app.logger.error(f"Error retrying email delivery log {log.id}: {e}", exc_info=True)
        mark_email_failed(log.id, f"Retry processing failed: {e}", retry=False)
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
    from app.services.notification.core import IN_APP_ONLY_NOTIFICATION_TYPES

    if notification.notification_type in IN_APP_ONLY_NOTIFICATION_TYPES:
        return False

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

    user_locale = _user_locale(user)
    if notification.priority in ('high', 'urgent'):
        subject = notification.title
    else:
        subject = _instant_notification_subject(notification, user_locale)
    body = render_instant_email(user, notification, locale=user_locale)

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
            mark_email_failed(log.id, "Email send returned False", retry=False)
            current_app.logger.error(f"Failed to send instant notification to {user.email}")

    except Exception as e:
        mark_email_failed(log.id, str(e), retry=False)
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
        if message_params is None:
            message_params = {}
        elif not isinstance(message_params, dict):
            try:
                import json
                message_params = json.loads(message_params) if isinstance(message_params, str) else {}
            except Exception:
                message_params = {}
        else:
            message_params = message_params.copy()
        from app.services.notification.service import NotificationService
        message_params = NotificationService._apply_localized_country_param(
            notif, message_key, message_params, locale=locale
        )
        with force_locale(locale):
            title = translate_notification_message(title_key, tp, locale=locale) if title_key else notif.title
            message = translate_notification_message(message_key, message_params, locale=locale) if message_key else notif.message
        return title or notif.title, message or notif.message
    except Exception as e:
        current_app.logger.warning(f"Failed to translate notification {notif.id} for digest (locale={locale}): {e}")
        return notif.title, notif.message


_DIGEST_TEMPLATE_SRC = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body { margin: 0; padding: 0; background: #eef2f7; color: #1f2937;
              font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
              line-height: 1.65; -webkit-font-smoothing: antialiased; }
            .email-outer { max-width: 960px; width: 100%; margin: 0 auto; padding: 28px 20px; box-sizing: border-box; }
            .email-card { background: #ffffff; border: 1px solid #e2e8f0; }
            .email-header { background: #0d9488; color: #ffffff; padding: 28px 36px; text-align: center; }
            .email-header h1 { margin: 0 0 8px; font-size: 24px; font-weight: 600; }
            .email-header p { margin: 0; font-size: 15px; opacity: 0.95; }
            .email-body { padding: 32px 36px; background: #ffffff; }
            .email-body > p { margin: 0 0 14px; }
            .notification { border: 1px solid #e2e8f0; border-left: 4px solid #0d9488; padding: 18px 20px; margin: 16px 0; background: #f8fafc; }
            .notification.unread { background: #f0fdfa; border-left-color: #0d9488; }
            .notification h3 { margin: 0 0 8px; color: #0f172a; font-size: 17px; font-weight: 600; }
            .notification p { margin: 6px 0; color: #334155; }
            .notification .meta { font-size: 12px; color: #64748b; margin-top: 8px; }
            .action-button { display: inline-block; background: #0d9488; color: #ffffff !important; padding: 10px 20px;
              text-decoration: none; font-weight: 600; font-size: 14px; margin-top: 10px; border: 1px solid #0f766e; }
            .email-footer { padding: 22px 36px; text-align: center; font-size: 12px; color: #64748b;
              background: #f8fafc; border-top: 1px solid #e2e8f0; }
            .email-footer a { color: #0d9488; }
            .email-footer p { margin: 6px 0; }
        </style>
    </head>
    <body>
        <div class="email-outer">
            <div class="email-card">
                <div style="background-color:#0d9488;color:#ffffff;padding:28px 36px;text-align:center;">
                    <h1 style="margin:0 0 8px;font-size:24px;font-weight:600;line-height:1.3;color:#ffffff;">{{ digest_heading }}</h1>
                    <p style="margin:0;font-size:15px;line-height:1.4;opacity:0.95;color:#ffffff;">{{ digest_subtitle }}</p>
                </div>
                <div class="email-body">
                    <p>{{ greeting }}</p>
                    <p>{{ intro }}</p>
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
                            <span style="color: #dc2626; font-weight: 600;">{{ notification.priority.upper() }}</span>
                            {% endif %}
                        </div>
                        {% if notification.related_url %}
                        <a href="{{ (base_url ~ notification.related_url) | e }}" class="action-button">{{ view_details }}</a>
                        {% endif %}
                    </div>
                    {% endfor %}
                    <div style="text-align: center; margin-top: 28px;">
                        <a href="{{ (base_url ~ '/notifications') | e }}" class="action-button">{{ view_all }}</a>
                    </div>
                </div>
                <div class="email-footer">
                    <p>{{ footer_note }}</p>
                    <p><a href="{{ (base_url ~ '/notifications') | e }}">{{ manage_prefs }}</a></p>
                    <p>{{ org_name | e }}</p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """


def render_digest_email(user, notifications, frequency, locale: Optional[str] = None):
    """Render HTML email template for notification digest."""
    base_url = (current_app.config.get('BASE_URL') or 'http://localhost:5000').rstrip('/')
    user_locale = locale or _user_locale(user)
    user_name = sanitize_for_email(user.name or user.email)
    i18n = _build_digest_email_i18n(user_locale, user_name, len(notifications), frequency)

    # Sanitize (and translate) notification content for safe rendering.
    # Translate at send time using the user's preferred locale so digest emails
    # respect the user's language, not just the stored English fallback.
    sanitized_notifications = []
    for notif in notifications:
        translated_title, translated_message = _translate_notification_for_email(notif, user_locale)
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

    return _get_digest_template().render(
        user={'name': user_name, 'email': user.email},
        notifications=sanitized_notifications,
        base_url=base_url,
        org_name=org_name,
        **i18n,
    )


_INSTANT_TEMPLATE_SRC = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body { margin: 0; padding: 0; background: #eef2f7; color: #1f2937;
              font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
              line-height: 1.65; -webkit-font-smoothing: antialiased; }
            .email-outer { max-width: 960px; width: 100%; margin: 0 auto; padding: 28px 20px; box-sizing: border-box; }
            .email-card { background: #ffffff; border: 1px solid #e2e8f0; }
            .email-header { color: #ffffff; padding: 28px 36px; text-align: center; }
            .email-header.informational { background: #0d9488; }
            .email-header.action-required { background: #b91c1c; }
            .email-header h1 { margin: 0; font-size: 24px; font-weight: 600; }
            .email-header .subtitle { font-size: 15px; opacity: 0.95; margin: 8px 0 0; }
            .email-body { padding: 32px 36px; background: #ffffff; }
            .email-body > p { margin: 0 0 16px; }
            .message-panel { border: 1px solid #e2e8f0; border-left: 4px solid #0d9488; padding: 22px 24px; background: #f8fafc; }
            .message-panel.action-required { border-left-color: #dc2626; background: #fffafa; }
            .message-panel h2 { margin: 0 0 12px; color: #0f172a; font-size: 20px; font-weight: 600; }
            .message-panel p { margin: 10px 0; color: #334155; }
            .meta { font-size: 12px; color: #64748b; margin-top: 12px; }
            .action-button { display: inline-block; padding: 12px 24px; text-decoration: none; font-weight: 600; font-size: 15px; margin: 12px 0 0; color: #ffffff !important; }
            .action-button.informational { background: #0d9488; border: 1px solid #0f766e; }
            .action-button.action-required { background: #dc2626; border: 1px solid #b91c1c; }
            .email-footer { padding: 22px 36px; text-align: center; font-size: 12px; color: #64748b;
              background: #f8fafc; border-top: 1px solid #e2e8f0; }
            .email-footer a { color: #0d9488; }
        </style>
    </head>
    <body>
        <div class="email-outer">
            <div class="email-card">
                <div style="color:#ffffff;padding:28px 36px;text-align:center;background-color:{% if is_action_required %}#b91c1c{% else %}#0d9488{% endif %};">
                    <h1 style="margin:0;font-size:24px;font-weight:600;line-height:1.3;color:#ffffff;">{{ header_label }}</h1>
                    {% if header_subtitle %}<p style="margin:8px 0 0;font-size:15px;font-weight:500;line-height:1.4;opacity:0.95;color:#ffffff;">{{ header_subtitle }}</p>{% endif %}
                </div>
                <div class="email-body">
                    <p>{{ greeting }}</p>
                    <div class="message-panel {% if is_action_required %}action-required{% endif %}">
                        <h2>{{ notification.title }}</h2>
                        <p>{{ notification.message }}</p>
                        <p class="meta">
                            {{ notification.notification_type.value.replace('_', ' ').title() }}
                            {% if notification.priority and notification.priority != 'normal' %}
                            &nbsp;•&nbsp;<span style="color: #dc2626; font-weight: 600;">{{ notification.priority.upper() }}</span>
                            {% endif %}
                        </p>
                        {% if notification.related_url %}
                        <a href="{{ (base_url ~ notification.related_url) | e }}"
                           class="action-button {% if is_action_required %}action-required{% else %}informational{% endif %}">{{ button_label }}</a>
                        {% endif %}
                    </div>
                </div>
                <div class="email-footer">
                    <p>
                        <a href="{{ (base_url ~ '/notifications') | e }}">{{ view_all }}</a>
                        &nbsp;|&nbsp;
                        <a href="{{ (base_url ~ '/notifications') | e }}">{{ manage_prefs }}</a>
                    </p>
                    <p>{{ org_name | e }}</p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """


def render_instant_email(user, notification, locale: Optional[str] = None):
    """Render HTML email template for instant notification."""
    is_action_required = (notification.priority or 'normal') in ('high', 'urgent')
    user_locale = locale or _user_locale(user)
    user_name = sanitize_for_email(user.name or user.email)
    nt_val = getattr(notification.notification_type, 'value', str(notification.notification_type))
    i18n = _build_instant_email_i18n(user_locale, user_name, is_action_required, nt_val)

    base_url = (current_app.config.get('BASE_URL') or 'http://localhost:5000').rstrip('/')

    # Get organization branding
    org_name = get_org_name()

    # Sanitize notification content for safe rendering
    sanitized_notification = {
        'title': sanitize_for_email(notification.title),
        'message': sanitize_for_email(notification.message),
        'notification_type': notification.notification_type,
        'priority': sanitize_for_email(notification.priority),
        'related_url': notification.related_url  # URL is validated separately
    }

    return _get_instant_template().render(
        user={'name': user_name, 'email': user.email},
        notification=sanitized_notification,
        base_url=base_url,
        org_name=org_name,
        is_action_required=is_action_required,
        **i18n,
    )
