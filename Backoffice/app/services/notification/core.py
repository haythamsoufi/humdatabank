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
from typing import Optional, Dict, Any, Tuple, List, Union

from app.services.platform.app_settings_service import audience_bucket_enabled
from app.services.notification.audience import (
    collect_entity_admin_audience_recipient_ids,
    get_assignment_editor_submitter_user_ids_for_entity,
)

# Hidden from end-user notification lists (admin Communication Center still shows them).
USER_HIDDEN_NOTIFICATION_TYPES = frozenset({
    NotificationType.email_digest,
})


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================



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
        'notification.assignment_created.title': _notification_msgid(
            'New assignment: %(assignment_title)s'
        ),
        'notification.assignment_created.message': _notification_msgid(
            '%(country)s — due %(due_date)s.'
        ),

        'notification.assignment_submitted.submitter.title': _notification_msgid('Submission successful'),
        'notification.assignment_submitted.submitter.message': _notification_msgid(
            'You submitted %(assignment_title)s for %(country)s successfully.'
        ),

        'notification.assignment_submitted.title': _notification_msgid(
            'Team update: %(assignment_title)s submitted'
        ),
        'notification.assignment_submitted.message': _notification_msgid(
            '%(submitter_name)s submitted %(assignment_title)s for %(country)s. No action needed from you.'
        ),

        'notification.assignment_submitted.team_email.title': _notification_msgid(
            'Team update: %(assignment_title)s submitted by %(submitter_name)s'
        ),
        'notification.assignment_submitted.team_email.message': _notification_msgid(
            '%(submitter_name)s submitted %(assignment_title)s for your entity team.'
        ),

        'notification.assignment_submitted.admin.title': _notification_msgid(
            '{submitter_name} has submitted {assignment_title}.'
        ),
        'notification.assignment_submitted.admin.message': _notification_msgid(
            'Please review and validate this submission for %(country)s in the Backoffice.'
        ),

        'notification.assignment_approved.title': _notification_msgid(
            'Assignment approved: %(assignment_title)s'
        ),
        'notification.assignment_approved.message': _notification_msgid(
            '%(actor_name)s approved this assignment for %(country)s.'
        ),

        'notification.assignment_reopened.title': _notification_msgid(
            'Assignment reopened: %(assignment_title)s'
        ),
        'notification.assignment_reopened.message': _notification_msgid(
            '%(actor_name)s reopened this assignment for %(country)s.'
        ),

        'notification.assignment_sent_for_review.title': _notification_msgid(
            'Review requested: %(assignment_title)s — %(country)s'
        ),
        'notification.assignment_sent_for_review.message': _notification_msgid(
            '%(submitter_name)s sent this assignment for %(country)s for your review before submission.'
        ),
        'notification.assignment_sent_for_review.admin.title': _notification_msgid(
            'Sent for review: %(assignment_title)s — %(country)s'
        ),
        'notification.assignment_sent_for_review.admin.message': _notification_msgid(
            '%(submitter_name)s escalated this assignment for %(country)s for delegation review.'
        ),

        'notification.assignment_returned_for_revision.title': _notification_msgid(
            'Changes requested: %(assignment_title)s — %(country)s'
        ),
        'notification.assignment_returned_for_revision.message': _notification_msgid(
            '%(actor_name)s returned this assignment for your changes before resubmitting for review.'
        ),

        # Document notifications
        'notification.document_uploaded.title': _notification_msgid('Document uploaded'),
        'notification.document_uploaded.message': _notification_msgid(
            "'%(document)s' (%(document_type)s) was uploaded for %(country)s."
        ),

        'notification.document_uploaded.pending.title': _notification_msgid('Document pending review'),
        'notification.document_uploaded.pending.message': _notification_msgid(
            "'%(document)s' (%(document_type)s) for %(country)s requires approval."
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

        # Form notifications
        'notification.form_updated.title': _notification_msgid('Form updated'),
        'notification.form_updated.message': _notification_msgid('Form data has been updated.'),

        # Deadline notifications
        'notification.deadline_reminder.title': _notification_msgid(
            'Deadline reminder: %(assignment_title)s'
        ),
        'notification.deadline_reminder.message': _notification_msgid(
            '%(country)s — due on %(due_date)s.'
        ),

        # Self-report notifications
        'notification.self_report_created.title': _notification_msgid(
            'Self report created: %(assignment_title)s'
        ),
        'notification.self_report_created.message': _notification_msgid(
            'A new self-report is available for %(country)s.'
        ),

        # Public submission notifications
        'notification.public_submission_received.title': _notification_msgid('Public submission received'),
        'notification.public_submission_received.message': _notification_msgid(
            "From %(submitter)s (%(country)s) for %(assignment_title)s."
        ),

        # Admin message notifications (these use custom messages, so we handle them specially)
        'notification.admin_message.title': _notification_msgid('Admin Message'),
        'notification.admin_message.message': _notification_msgid('You have received an admin message'),

        # Account welcome (title/message from email template metadata when provided)
        'notification.account_welcome.title': _notification_msgid('Welcome to the %(org_name)s!'),
        'notification.account_welcome.message': _notification_msgid(
            "Welcome to the %(org_name)s! Your account has been created. Open your dashboard to get started, "
            "review assignments, and use Documentation from the main navigation for guides."
        ),

        'notification.email_digest.title': _notification_msgid('%(frequency)s Notification Digest'),
        'notification.email_digest.message': _notification_msgid(
            '%(frequency)s email digest delivered with %(count)s notification(s).'
        ),

        # Validation questions (data quality checks)
        'notification.validation_questions.title': _notification_msgid(
            'Validation questions: %(assignment_title)s'
        ),
        'notification.validation_questions.message': _notification_msgid(
            '%(count)s data validation question(s) for %(entity)s require your response.'
        ),
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
                if translation_key == 'notification.account_welcome.title' and 'custom_title' in params:
                    return str(params['custom_title'])[:255]
                if translation_key == 'notification.account_welcome.message' and 'message' in params:
                    return str(params['message'])[:MAX_NOTIFICATION_MESSAGE_LENGTH]
                if translation_key == 'notification.email_digest.title' and 'custom_title' in params:
                    return str(params['custom_title'])[:255]
                if translation_key == 'notification.email_digest.message' and 'message' in params:
                    return str(params['message'])[:MAX_NOTIFICATION_MESSAGE_LENGTH]

            # Translate at runtime using the current locale
            # Use force_locale if a specific locale is provided, otherwise use canonical session/request language
            from flask_babel import force_locale
            from app.utils.form_localization import get_translation_key

            locale_to_use = locale or get_translation_key()

            # Normalize and validate locale
            if locale_to_use:
                from config import Config as _Cfg
                supported_langs = current_app.config.get('SUPPORTED_LANGUAGES', _Cfg.LANGUAGES)
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
                # Re-resolve org_name fresh for the viewer's locale so locale-specific org names
                # work correctly and the name isn't stale from notification creation time.
                if 'org_name' in format_params:
                    try:
                        from app.utils.organization_helpers import get_org_name as _get_org_name
                        format_params['org_name'] = _get_org_name(locale=locale_to_use or 'en')
                    except Exception:
                        pass  # keep the stored value as fallback
                if format_params:
                    try:
                        # Prefer .format() for {name} placeholders (avoids gettext % escaping issues)
                        if '{' in str(translated):
                            result = translated.format(**format_params)
                        else:
                            result = translated % format_params
                        locale_key = get_translation_key(locale_to_use)
                        if locale_key in {'ar', 'fa', 'he', 'ur'}:
                            from app.utils.form_localization import normalize_arabic_lam_definite_assimilation
                            result = normalize_arabic_lam_definite_assimilation(result)
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
        from app.services.organization.entity_service import EntityService

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




def _notification_retention_days(days: Optional[int] = None) -> int:
    """Resolve archived-notification retention from explicit arg or app config."""
    if days is not None:
        try:
            return max(1, int(days))
        except (TypeError, ValueError):
            pass
    try:
        return max(1, int(current_app.config.get('NOTIFICATION_CLEANUP_RETENTION_DAYS', 90)))
    except (TypeError, ValueError):
        return 90


def _email_delivery_log_retention_days() -> int:
    """Retention for email_delivery_log rows (defaults to notification cleanup retention)."""
    raw = current_app.config.get(
        'NOTIFICATION_EMAIL_LOG_RETENTION_DAYS',
        current_app.config.get('NOTIFICATION_CLEANUP_RETENTION_DAYS', 90),
    )
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 90


def cleanup_old_email_delivery_logs(days: Optional[int] = None) -> int:
    """
    Delete email delivery log rows older than the retention window.
    Includes digest rows with notification_id=NULL.
    """
    try:
        retention_days = days if days is not None else _email_delivery_log_retention_days()
        cutoff = utcnow() - timedelta(days=retention_days)
        return EmailDeliveryLog.query.filter(
            EmailDeliveryLog.created_at < cutoff,
        ).delete(synchronize_session=False)
    except Exception as e:
        current_app.logger.error(f"Error cleaning up email delivery logs: {e}", exc_info=True)
        return 0


def cleanup_old_notifications(days: Optional[int] = None) -> Dict[str, int]:
    """
    Delete archived notifications older than specified days.
    Also deletes expired notifications (regardless of archived status).

    Args:
        days (int): Number of days to keep archived notifications

    Returns:
        dict: Statistics about cleanup (archived_deleted, expired_deleted,
              email_logs_deleted, total_deleted)
    """
    try:
        now = utcnow()
        retention_days = _notification_retention_days(days)
        cutoff = now - timedelta(days=retention_days)

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

        email_logs_deleted = cleanup_old_email_delivery_logs()

        try:
            db.session.commit()
        except Exception as commit_error:
            current_app.logger.error(f"Error committing notification cleanup: {str(commit_error)}", exc_info=True)
            db.session.rollback()
            return {
                'archived_deleted': 0,
                'expired_deleted': 0,
                'email_logs_deleted': 0,
                'total_deleted': 0
            }

        total_deleted = expired_deleted + archived_deleted

        if total_deleted > 0 or email_logs_deleted > 0:
            current_app.logger.info(
                f"Cleaned up {total_deleted} old notifications "
                f"({expired_deleted} expired, {archived_deleted} archived), "
                f"{email_logs_deleted} email delivery log(s)"
            )

        return {
            'archived_deleted': archived_deleted,
            'expired_deleted': expired_deleted,
            'email_logs_deleted': email_logs_deleted,
            'total_deleted': total_deleted
        }
    except Exception as e:
        current_app.logger.error(f"Error cleaning up notifications: {str(e)}", exc_info=True)
        db.session.rollback()
        return {
            'archived_deleted': 0,
            'expired_deleted': 0,
            'email_logs_deleted': 0,
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
        if not audience_bucket_enabled(notification_type, "focal_points"):
            return []

        exclude_set = set()
        if exclude_user_id is not None:
            exclude_set.add(exclude_user_id)
        if exclude_user_ids:
            exclude_set.update(exclude_user_ids)

        focal_point_ids = get_assignment_editor_submitter_user_ids_for_entity(
            entity_type,
            entity_id,
            exclude_user_ids=list(exclude_set) if exclude_set else None,
        )

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
        NotificationType.assignment_sent_for_review: 'fas fa-user-check',
        NotificationType.assignment_returned_for_revision: 'fas fa-undo-alt',
        NotificationType.assignment_approved: 'fas fa-check-circle',
        NotificationType.assignment_reopened: 'fas fa-undo',
        NotificationType.public_submission_received: 'fas fa-inbox',
        NotificationType.form_updated: 'fas fa-pen',
        NotificationType.document_uploaded: 'fas fa-file-upload',
        NotificationType.user_added_to_country: 'fas fa-user-plus',
        NotificationType.self_report_created: 'fas fa-clipboard-list',
        NotificationType.deadline_reminder: 'fas fa-clock',
        NotificationType.access_request_received: 'fas fa-user-plus',
        NotificationType.validation_questions: 'fas fa-clipboard-question',
        NotificationType.account_welcome: 'fas fa-user-check',
        NotificationType.email_digest: 'fas fa-envelope-open-text',
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

# ---------------------------------------------------------------------------
# Re-exports from notifier modules (preserve import paths)
# ---------------------------------------------------------------------------
from app.services.notification.notifiers.assignment import (
    notify_assignment_created,
    notify_assignment_submitted,
    notify_assignment_sent_for_review,
    notify_assignment_returned_for_revision,
    notify_assignment_approved,
    notify_assignment_reopened,
    notify_self_report_created,
    notify_form_data_updated,
)
from app.services.notification.notifiers.documents import (
    notify_document_uploaded,
    notify_standalone_document_uploaded,
)
from app.services.notification.notifiers.digest import (
    notify_user_added_to_country,
    notify_public_submission_received,
)

from app.services.notification.validators import (
    validate_notification_url,
    validate_action_button_endpoint,
    validate_and_sanitize_action_buttons,
)
from app.services.notification.dedup import (
    generate_notification_hash,
    check_duplicate_notification,
    calculate_notification_expiration,
    generate_group_id,
)
from app.services.notification.creation import (
    create_notification,
    is_notification_type_enabled_for_user,
    get_user_preferences_batch,
    IN_APP_ONLY_NOTIFICATION_TYPES,
)

