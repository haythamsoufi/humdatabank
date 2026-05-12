"""
Centralized service for notification management.
Extracted from utils/notifications.py and routes/main.py for better organization.

This service handles:
- Retrieving user notifications with filtering and pagination
- Marking notifications as read/unread
- Archiving notifications
- Deleting notifications
- Getting notification preferences
- Updating notification preferences
"""
# ========== Notification Service ==========
from app.utils.datetime_helpers import utcnow, ensure_utc

from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime, timedelta
from flask import current_app
from flask_babel import gettext as _
from app.models import db, Notification, NotificationPreferences, User, CountryAccessRequest, NotificationType, EmailDeliveryLog
from sqlalchemy import and_, or_ as sa_or_, func, cast, String
from app.services.notification.core import get_default_icon_for_notification_type, validate_and_sanitize_action_buttons
import logging

logger = logging.getLogger(__name__)

# Message body is the main headline; title is the shorter category line (translated type headline).
MESSAGE_PRIMARY_NOTIFICATION_TYPES = frozenset({
    'access_request_received',
    'assignment_submitted',
    'assignment_approved',
    'assignment_reopened',
    'assignment_created',
    'document_uploaded',
    'user_added_to_country',
    'public_submission_received',
    'form_updated',
    'template_updated',
    'self_report_created',
    'deadline_reminder',
})

# Font Awesome icon suffix for the small badge on the actor avatar (e.g. fa-key).
ACTOR_BADGE_ICON_BY_TYPE = {
    'access_request_received': 'fa-key',
    'assignment_submitted': 'fa-paper-plane',
    'assignment_approved': 'fa-check',
    'assignment_reopened': 'fa-undo',
    'assignment_created': 'fa-plus-circle',
    'document_uploaded': 'fa-file-upload',
    'user_added_to_country': 'fa-user-check',
    'public_submission_received': 'fa-inbox',
    'form_updated': 'fa-pen',
    'template_updated': 'fa-file-alt',
    'self_report_created': 'fa-clipboard-list',
    'deadline_reminder': 'fa-clock',
}


class NotificationService:
    """Service for managing user notifications"""

    @classmethod
    def _get_translated_notification_type_label(cls, notification_type_value: str) -> str:
        """
        Get a translated label for a notification type.

        Args:
            notification_type_value: The notification type enum value (e.g., 'assignment_created')

        Returns:
            Translated label string (e.g., 'Assignment Created')
        """
        # Map notification types to English source strings
        # These must match the msgid strings in the translation files (.po files)
        # These will be translated at request time using the current locale
        type_source_map = {
            'assignment_created': 'New Assignment Created',  # Matches translation file
            'assignment_submitted': 'Assignment Submitted',
            'assignment_approved': 'Assignment Approved',
            'assignment_reopened': 'Assignment Reopened',
            'public_submission_received': 'Public Submission Received',
            'form_updated': 'Form Updated',
            'document_uploaded': 'Document Uploaded',
            'user_added_to_country': 'User Added to Country',
            'template_updated': 'Template Updated',
            'self_report_created': 'Self Report Created',
            'deadline_reminder': 'Deadline Reminder',
            'admin_message': 'Admin Message',
            'access_request_received': 'Country Access Request Received',  # Matches translation file
        }

        # Get the source string and translate it at request time
        if notification_type_value in type_source_map:
            source_string = type_source_map[notification_type_value]
            # Use the same locale handling as _translate_notification_content
            # to ensure we use the session locale
            try:
                from flask_babel import force_locale
                from app.utils.form_localization import get_translation_key

                locale_to_use = get_translation_key()
                if locale_to_use:
                    # Force locale for translation
                    from flask_babel import gettext
                    with force_locale(locale_to_use):
                        return gettext(source_string)
                else:
                    # Use current Babel locale
                    from flask_babel import gettext
                    return gettext(source_string)
            except Exception as e:
                logger.warning(f"Error translating notification type label '{notification_type_value}': {e}")
                # Fallback to English
                return source_string
        else:
            # Fallback: format the type value (replace underscores with spaces and title case)
            return notification_type_value.replace('_', ' ').title()

    @staticmethod
    def _serialize_actor_user(user: User) -> Dict[str, Any]:
        """Build JSON-safe actor payload for notification UIs (initials + colour)."""
        from app.utils.profile_utils import generate_color_from_email, display_initials
        name = (user.name or user.email or '').strip()
        initials = display_initials(name=user.name, email=user.email)
        color = user.profile_color if user.profile_color and user.profile_color != '#3B82F6' else None
        if not color:
            color = generate_color_from_email(user.email or '')
        return {
            'id': user.id,
            'name': name,
            'initials': initials,
            'profile_color': color,
        }

    @classmethod
    def _resolve_actor_user_id_for_notification(
        cls,
        n: Notification,
        nt_val: str,
        car_id_to_user_id: Dict[int, int],
        assignment_status_cache: Dict[Any, Any],
    ) -> Optional[int]:
        """
        Return the user id to show as the notification actor (avatar), if any.

        user_added_to_country is intentionally excluded (recipient is the subject, not a second party).
        """
        if nt_val == 'user_added_to_country':
            return None
        if nt_val == 'access_request_received' and n.related_object_type == 'country_access_request' and n.related_object_id:
            return car_id_to_user_id.get(int(n.related_object_id))
        if n.related_object_type != 'assignment' or not n.related_object_id:
            return None
        aes = assignment_status_cache.get(n.related_object_id)
        if not aes:
            return None
        if nt_val == 'assignment_submitted':
            return getattr(aes, 'submitted_by_user_id', None)
        if nt_val == 'assignment_approved':
            return getattr(aes, 'approved_by_user_id', None)
        return None

    @classmethod
    def _build_assignment_caches_for_notifications(
        cls, notifications: List[Notification]
    ) -> Tuple[Dict[Any, Any], Dict[int, Any]]:
        """
        Batch-load AssignmentEntityStatus / AssignedForm rows referenced by notifications.
        Returns (assignment_status_cache, assigned_form_cache) matching get_user_notifications.
        """
        assignment_status_ids: List[int] = []
        assigned_form_ids: List[int] = []
        for n in notifications:
            if n.related_object_type == 'assignment' and n.related_object_id:
                assignment_status_ids.append(n.related_object_id)
                assigned_form_ids.append(n.related_object_id)

        assignment_status_cache: Dict[Any, Any] = {}
        assigned_form_cache: Dict[int, Any] = {}
        if not assignment_status_ids and not assigned_form_ids:
            return assignment_status_cache, assigned_form_cache

        try:
            from app.models.assignments import AssignmentEntityStatus, AssignedForm

            if assignment_status_ids:
                aes_records = AssignmentEntityStatus.query.filter(
                    AssignmentEntityStatus.id.in_(assignment_status_ids)
                ).all()
                for aes in aes_records:
                    assignment_status_cache[aes.id] = aes

            if assigned_form_ids:
                form_records = AssignedForm.query.filter(
                    AssignedForm.id.in_(assigned_form_ids)
                ).all()
                assigned_form_cache = {form.id: form for form in form_records}

                if form_records:
                    form_ids = [f.id for f in form_records]
                    aes_for_forms = AssignmentEntityStatus.query.filter(
                        AssignmentEntityStatus.assigned_form_id.in_(form_ids)
                    ).all()
                    for aes in aes_for_forms:
                        cache_key = (aes.assigned_form_id, aes.entity_type, aes.entity_id)
                        assignment_status_cache[cache_key] = aes
                        if aes.id not in assignment_status_cache:
                            assignment_status_cache[aes.id] = aes

        except Exception as e:
            logger.warning(f"Error batch-loading AssignmentEntityStatus records: {e}", exc_info=True)

        return assignment_status_cache, assigned_form_cache

    @classmethod
    def build_actor_display_fields_map(
        cls,
        notifications: List[Notification],
        assignment_status_cache: Dict[Any, Any],
    ) -> Dict[int, Dict[str, Any]]:
        """
        Per-notification actor avatar data and primary_is_message flag.
        Used by get_user_notifications and admin notifications grid.
        """
        car_id_to_user_id: Dict[int, int] = {}
        car_ids_for_actor: List[int] = []
        for n in notifications:
            nt0 = n.notification_type.value if hasattr(n.notification_type, 'value') else n.notification_type
            if nt0 == 'access_request_received' and n.related_object_type == 'country_access_request' and n.related_object_id:
                car_ids_for_actor.append(int(n.related_object_id))
        if car_ids_for_actor:
            try:
                cars = CountryAccessRequest.query.filter(CountryAccessRequest.id.in_(car_ids_for_actor)).all()
                car_id_to_user_id = {c.id: c.user_id for c in cars}
            except Exception as e:
                logger.warning(f"Error batch-loading CountryAccessRequest for actors: {e}", exc_info=True)

        actor_user_ids: set = set()
        for n in notifications:
            nt0 = n.notification_type.value if hasattr(n.notification_type, 'value') else n.notification_type
            aid = cls._resolve_actor_user_id_for_notification(
                n, nt0, car_id_to_user_id, assignment_status_cache
            )
            if aid:
                actor_user_ids.add(int(aid))

        users_by_id: Dict[int, User] = {}
        if actor_user_ids:
            try:
                actor_users = User.query.filter(User.id.in_(actor_user_ids)).all()
                users_by_id = {u.id: u for u in actor_users}
            except Exception as e:
                logger.warning(f"Error batch-loading actor users: {e}", exc_info=True)

        out: Dict[int, Dict[str, Any]] = {}
        for n in notifications:
            nt_val = n.notification_type.value if hasattr(n.notification_type, 'value') else n.notification_type
            actor_uid = cls._resolve_actor_user_id_for_notification(
                n, nt_val, car_id_to_user_id, assignment_status_cache
            )
            actor_payload = None
            actor_badge_icon = ACTOR_BADGE_ICON_BY_TYPE.get(nt_val)
            recipient_id = getattr(n, 'user_id', None)
            # Do not show the recipient's own initials as the "actor" (e.g. self-submitted assignment).
            is_self_actor = (
                actor_uid is not None
                and recipient_id is not None
                and int(actor_uid) == int(recipient_id)
            )
            if actor_uid and not is_self_actor and actor_uid in users_by_id:
                actor_payload = cls._serialize_actor_user(users_by_id[actor_uid])
            primary_is_message = nt_val in MESSAGE_PRIMARY_NOTIFICATION_TYPES
            out[n.id] = {
                'actor': actor_payload,
                'actor_action_icon': actor_badge_icon,
                'primary_is_message': primary_is_message,
            }
        return out

    @classmethod
    def _translate_notification_content(cls, notification: Notification) -> Tuple[Optional[str], Optional[str]]:
        """
        Translate notification title and message from translation keys.

        Args:
            notification: Notification object

        Returns:
            Tuple of (translated_message, translated_title) or (None, None) if no translation keys
        """
        title_key = getattr(notification, 'title_key', None)
        title_params = getattr(notification, 'title_params', None)
        message_key = getattr(notification, 'message_key', None)
        message_params = getattr(notification, 'message_params', None)

        translated_title = None
        translated_message = None

        if not title_key and not message_key:
            return None, None

        try:
            from app.services.notification.core import translate_notification_message
            from app.utils.form_localization import get_translation_key

            locale_to_use = get_translation_key()

            # Translate from keys if available
            if title_key:
                try:
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
                    translated_title = translate_notification_message(title_key, tp, locale=locale_to_use)
                except Exception as e:
                    logger.warning(f"Error translating title_key '{title_key}' for notification {notification.id}: {e}", exc_info=True)
                    translated_title = None

            if message_key:
                try:
                    # Ensure message_params is a dict (it might be None or a string)
                    if message_params is None:
                        message_params = {}
                    elif not isinstance(message_params, dict):
                        # Try to parse if it's a JSON string
                        try:
                            import json
                            message_params = json.loads(message_params) if isinstance(message_params, str) else {}
                        except Exception as e:
                            logger.debug("Could not parse message_params JSON: %s", e)
                            message_params = {}

                    # Make a copy to avoid modifying the original (which might be stored in DB)
                    message_params = message_params.copy() if message_params else {}

                    # Add missing 'country' parameter only when the message template requires it.
                    # This prevents noisy warnings for notifications that don't use %(country)s.
                    keys_requiring_country = {
                        'notification.public_submission_received.message',
                        'notification.user_added_to_country.message',
                    }
                    if message_key in keys_requiring_country and 'country' not in message_params:
                        # Check if we have entity info to get country name
                        # First try from message_params, then from notification object as fallback
                        entity_type = message_params.get('_entity_type') or getattr(notification, 'entity_type', None)
                        entity_id = message_params.get('_entity_id') or getattr(notification, 'entity_id', None)
                        if entity_type and entity_id:
                            try:
                                from app.services.entity_service import EntityService
                                entity_name = EntityService.get_localized_entity_name(
                                    entity_type,
                                    entity_id,
                                    include_hierarchy=True
                                )
                                if entity_name and not entity_name.startswith('Unknown'):
                                    message_params['country'] = entity_name
                            except Exception as e:
                                logger.warning(f"[NOTIFICATION_SERVICE] Error getting entity name for country parameter: {e}", exc_info=True)
                        else:
                            # Important only when the message requires %(country)s, otherwise it's noise.
                            logger.warning(
                                f"[NOTIFICATION_SERVICE] Notification {notification.id}: missing entity info for required country param "
                                f"(message_key='{message_key}', entity_type='{entity_type}', entity_id={entity_id})"
                            )

                    # Add missing submitter_name/period for assignment_submitted.admin (older notifications may lack them)
                    if message_key == 'notification.assignment_submitted.admin.message':
                        if 'submitter_name' not in message_params:
                            message_params['submitter_name'] = 'A focal point'
                        if 'period' not in message_params:
                            message_params['period'] = '—'

                    # Localize template names in params if they exist
                    # This needs to happen at display time to respect user's current language
                    if message_params and 'template' in message_params:
                        try:
                            from app.models import AssignedForm, FormTemplate, PublicSubmission
                            from app.utils.form_localization import get_localized_template_name

                            template = None

                            # Try to get template from related object based on notification type
                            if notification.related_object_type == 'assignment' and notification.related_object_id:
                                # NOTE: related_object_id can be either:
                                # 1. AssignmentEntityStatus.id (aes.id) - for some older notifications
                                # 2. AssignedForm.id - for newer notifications (as set in notify_assignment_created)
                                # Get template via: AssignedForm -> FormTemplate
                                try:
                                    from app.models import AssignmentEntityStatus

                                    assigned_form = None
                                    # First try as AssignedForm ID (newer notifications)
                                    assigned_form = AssignedForm.query.get(notification.related_object_id)
                                    if not assigned_form:
                                        # Fallback: try as AssignmentEntityStatus ID (older notifications)
                                        assignment_status = AssignmentEntityStatus.query.get(notification.related_object_id)
                                        if assignment_status:
                                            if assignment_status.assigned_form:
                                                assigned_form = assignment_status.assigned_form
                                            else:
                                                logger.warning(
                                                    f"[NOTIFICATION_SERVICE] Notification {notification.id}: "
                                                    f"AssignmentEntityStatus {notification.related_object_id} found but has no assigned_form. "
                                                    f"AssignedForm may have been deleted."
                                                )
                                        else:
                                            # Both lookups failed - check if either exists in database
                                            from app import db
                                            from sqlalchemy import text
                                            af_exists = db.session.execute(
                                                text("SELECT id FROM assigned_form WHERE id = :id"),
                                                {"id": notification.related_object_id}
                                            ).first()
                                            aes_exists = db.session.execute(
                                                text("SELECT id FROM assignment_entity_status WHERE id = :id"),
                                                {"id": notification.related_object_id}
                                            ).first()

                                            if not af_exists and not aes_exists:
                                                logger.warning(
                                                    f"[NOTIFICATION_SERVICE] Notification {notification.id}: "
                                                    f"Could not find AssignedForm or AssignmentEntityStatus with ID {notification.related_object_id}. "
                                                    f"Notification may reference deleted data."
                                                )
                                            elif af_exists:
                                                logger.warning(
                                                    f"[NOTIFICATION_SERVICE] Notification {notification.id}: "
                                                    f"AssignedForm {notification.related_object_id} exists in DB but query failed. "
                                                    f"This may indicate a session/caching issue."
                                                )
                                            elif aes_exists:
                                                logger.warning(
                                                    f"[NOTIFICATION_SERVICE] Notification {notification.id}: "
                                                    f"AssignmentEntityStatus {notification.related_object_id} exists in DB but query failed. "
                                                    f"This may indicate a session/caching issue."
                                                )

                                    if assigned_form:
                                        # Get template_id directly from the database row to avoid any caching
                                        # Query the template_id column directly using raw SQL or fresh query
                                        from app import db
                                        from sqlalchemy import text

                                        # Get fresh template_id directly from database to bypass SQLAlchemy caching
                                        result = db.session.execute(
                                            text("SELECT template_id FROM assigned_form WHERE id = :id"),
                                            {"id": assigned_form.id}
                                        ).first()

                                        if result and result[0]:
                                            template_id = result[0]
                                            # Also check what the object attribute says for comparison
                                            object_template_id = getattr(assigned_form, 'template_id', None)
                                            if object_template_id != template_id:
                                                logger.warning(
                                                    f"[NOTIFICATION_SERVICE] Notification {notification.id}: "
                                                    f"Template ID mismatch! DB has {template_id}, object has {object_template_id}"
                                                )

                                            # Query template fresh by ID
                                            template = FormTemplate.query.get(template_id)

                                            if template:
                                                # Get template name directly from DB to verify
                                                name_result = db.session.execute(
                                                    text("""
                                                        SELECT ftv.name
                                                        FROM form_template ft
                                                        LEFT JOIN form_template_version ftv ON ft.published_version_id = ftv.id
                                                        WHERE ft.id = :id
                                                        LIMIT 1
                                                    """),
                                                    {"id": template_id}
                                                ).first()

                                                db_template_name = name_result[0] if name_result else None
                                                object_template_name = template.name if template else None

                                                if db_template_name and object_template_name and db_template_name != object_template_name:
                                                    logger.error(
                                                        f"[NOTIFICATION_SERVICE] Notification {notification.id}: "
                                                        f"CRITICAL: Template name mismatch! DB has '{db_template_name}', "
                                                        f"object has '{object_template_name}' (template_id={template_id})"
                                                    )

                                            if not template:
                                                logger.warning(
                                                    f"[NOTIFICATION_SERVICE] Notification {notification.id}: "
                                                    f"AssignedForm {assigned_form.id} has template_id {template_id} but template not found"
                                                )
                                        elif hasattr(assigned_form, 'template_id') and assigned_form.template_id:
                                            # Fallback to attribute if raw query fails
                                            template_id = assigned_form.template_id
                                            template = FormTemplate.query.get(template_id)

                                            if not template:
                                                logger.warning(
                                                    f"[NOTIFICATION_SERVICE] Notification {notification.id}: "
                                                    f"AssignedForm {assigned_form.id} has template_id {template_id} but template not found"
                                                )
                                        # Fallback: try template relationship (shouldn't normally be needed)
                                        elif hasattr(assigned_form, 'template') and assigned_form.template:
                                            template = assigned_form.template
                                            # Expire to get fresh data
                                            try:
                                                db.session.expire(template)
                                                db.session.refresh(template)
                                            except Exception:
                                                pass
                                        else:
                                            template = None
                                            logger.warning(
                                                f"[NOTIFICATION_SERVICE] Notification {notification.id}: "
                                                f"AssignedForm {assigned_form.id} found but has no template_id or template relationship"
                                            )
                                except Exception as e:
                                    logger.error(
                                        f"[NOTIFICATION_SERVICE] Error querying template for notification {notification.id} "
                                        f"(related_object_id={notification.related_object_id}): {e}",
                                        exc_info=True
                                    )

                            elif notification.related_object_type == 'public_submission' and notification.related_object_id:
                                # For public submissions, get template from assigned_form
                                public_submission = PublicSubmission.query.get(notification.related_object_id)
                                if public_submission and public_submission.assigned_form and public_submission.assigned_form.template:
                                    template = public_submission.assigned_form.template

                            elif notification.related_object_type == 'template' and notification.related_object_id:
                                # Direct template reference (e.g., template_updated notifications)
                                template = FormTemplate.query.get(notification.related_object_id)

                            # Always use fresh template lookup - never trust stored template name
                            if template:
                                # Get locale from session to ensure correct translation
                                from flask import session
                                current_locale = session.get('language')
                                if not current_locale:
                                    from flask_babel import get_locale
                                    current_locale = str(get_locale()) if get_locale() else None

                                message_params = message_params.copy()
                                original_template_name = message_params.get('template', 'N/A')

                                # Always use the fresh template we found - don't query again to avoid issues
                                # The template was already queried fresh from the database
                                try:
                                    localized_template_name = get_localized_template_name(template, locale=current_locale)
                                    message_params['template'] = localized_template_name

                                    # Warn if stored name doesn't match template name (indicates a bug)
                                    if original_template_name != template.name and original_template_name != localized_template_name:
                                        logger.warning(
                                            f"[NOTIFICATION_SERVICE] Notification {notification.id}: "
                                            f"Template name mismatch! Stored name '{original_template_name}' != "
                                            f"Fresh template name '{template.name}' (ID {template.id}). "
                                            f"Using fresh name '{localized_template_name}'."
                                        )
                                except Exception as localize_e:
                                    logger.error(
                                        f"[NOTIFICATION_SERVICE] Error localizing template for notification {notification.id}: {localize_e}",
                                        exc_info=True
                                    )
                                    # Fallback to template name without localization
                                    message_params['template'] = template.name
                            else:
                                # Template lookup failed - try to get template_id from stored message_params if available
                                # This can happen if the AssignedForm was deleted or related_object_id is wrong
                                stored_name = message_params.get('template', 'Unknown Template') if message_params else 'Unknown Template'

                                # Try one more time: check if we can find the template by querying all AssignedForms
                                # that might match this notification's context
                                logger.warning(
                                    f"[NOTIFICATION_SERVICE] Notification {notification.id}: "
                                    f"Template lookup failed (related_object_type='{notification.related_object_type}', "
                                    f"related_object_id={notification.related_object_id}). "
                                    f"Stored name was '{stored_name}'. "
                                    f"Will use stored name as fallback."
                                )

                        except Exception as e:
                            logger.error(f"Error localizing template name for notification {notification.id}: {e}", exc_info=True)

                    # Special handling for access_request_received to get dynamic data
                    nt_val = notification.notification_type.value if hasattr(notification.notification_type, 'value') else str(notification.notification_type)
                    if nt_val == 'access_request_received' and notification.related_object_type == 'country_access_request' and notification.related_object_id:
                        # Fetch fresh data for access request notifications
                        try:
                            access_request = CountryAccessRequest.query.get(notification.related_object_id)
                            if access_request:
                                requesting_user = User.query.get(access_request.user_id)
                                user_name = requesting_user.name if requesting_user and requesting_user.name else (
                                    requesting_user.email if requesting_user else _('Unknown User')
                                )

                                country = access_request.country if access_request.country else None
                                if country:
                                    country_name = country.name  # Default to base name
                                    try:
                                        from app.utils.form_localization import get_localized_country_name
                                        country_name = get_localized_country_name(country)
                                    except (ImportError, AttributeError):
                                        country_name = country.name
                                else:
                                    country_name = _('Unknown Country')

                                # Update params with fresh data
                                if message_params is None:
                                    message_params = {}
                                message_params = message_params.copy()
                                message_params['user_name'] = user_name
                                message_params['country_name'] = country_name
                        except Exception as e:
                            logger.warning(f"Error fetching access request data for notification {notification.id}: {e}")

                    translated_message = translate_notification_message(message_key, message_params, locale=locale_to_use)
                except Exception as e:
                    logger.warning(f"Error translating message_key '{message_key}' for notification {notification.id}: {e}", exc_info=True)
                    translated_message = None

            # Return translated messages if available, otherwise fall back to stored
            final_message = translated_message if translated_message else notification.message
            final_title = translated_title if translated_title else None  # None means use stored title

            # All notifications should have translation keys
            # If keys are missing, log error and use stored title/message
            if not title_key or not message_key:
                logger.warning(
                    f"Notification {notification.id} missing translation keys (title_key={title_key}, message_key={message_key}). "
                    f"Using stored title/message as fallback."
                )
                return notification.message, notification.title

            return final_message, final_title

        except Exception as e:
            logger.error(f"Error in _translate_notification_content for notification {notification.id}: {e}", exc_info=True)
            # Fallback to stored message on any error
            return notification.message, None

    @classmethod
    def _validate_action_buttons_for_serialization(cls, action_buttons: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
        """
        Validate and sanitize action buttons when serializing for API responses.
        This provides defense-in-depth validation when action buttons are retrieved from the database.

        Args:
            action_buttons: List of action button dictionaries from database

        Returns:
            Validated and sanitized list of action buttons, or None if invalid/empty
        """
        return validate_and_sanitize_action_buttons(action_buttons)

    @classmethod
    def get_notifications(
        cls,
        user_id: int,
        page: int = 1,
        per_page: int = 20,
        unread_only: bool = False,
        notification_type: Optional[str] = None,
        priority: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Page-based wrapper around get_user_notifications for the mobile API.

        Converts page/per_page to limit/offset and returns a JSON-safe dict.
        """
        offset = (page - 1) * per_page
        notifications, total = cls.get_user_notifications(
            user_id=user_id,
            unread_only=unread_only,
            notification_type=notification_type,
            priority=priority,
            limit=per_page,
            offset=offset,
        )
        return {
            'notifications': notifications,
            'total': total,
            'page': page,
            'per_page': per_page,
            'total_pages': (total + per_page - 1) // per_page if per_page > 0 else 1,
        }

    @classmethod
    def get_user_notifications(
        cls,
        user_id: int,
        unread_only: bool = False,
        notification_type: Optional[str] = None,
        priority: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        include_archived: bool = False,
        archived_only: bool = False,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 20,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Get notifications for a user with filtering and pagination.

        Args:
            user_id: ID of the user
            country_ids: List of country IDs the user has access to
            unread_only: Only return unread notifications
            notification_type: Filter by notification type
            priority: Filter by ``normal``, ``high``, or ``urgent``
            date_from: Filter notifications from this date
            date_to: Filter notifications until this date
            include_archived: Include archived notifications (shows both archived and non-archived)
            archived_only: Only return archived notifications (overrides include_archived)
            limit: Maximum number of notifications to return
            offset: Number of notifications to skip (for pagination)

        Returns:
            Tuple of (list of notification dicts, total count)
        """
        try:
            now = utcnow()

            # Build query - use with_entities to avoid selecting columns that may not exist
            # We'll access them via getattr later which is safe
            # IMPORTANT: Notifications should only be shown to the specific user they were created for
            # Only show notifications where user_id matches the current user
            query = Notification.query.filter(
                Notification.user_id == user_id
            )

            # Filter out expired notifications
            query = query.filter(
                sa_or_(
                    Notification.expires_at.is_(None),
                    Notification.expires_at > now
                )
            )

            # Apply filters
            if unread_only:
                query = query.filter(Notification.is_read == False)

            # Handle archived filtering
            if archived_only:
                # Only show archived notifications
                query = query.filter(Notification.is_archived == True)
            elif not include_archived:
                # Exclude archived notifications (default)
                query = query.filter(Notification.is_archived == False)
            # If include_archived is True and archived_only is False, show both (no filter)

            if notification_type:
                # Normalize filter for Enum-backed column: accept Enum or string
                try:
                    from app.models.enums import NotificationType as _NT
                    if isinstance(notification_type, _NT):
                        nt_value = notification_type.value
                    else:
                        nt_value = str(notification_type)
                except Exception as e:
                    logger.debug("Could not normalize notification_type: %s", e)
                    nt_value = str(notification_type)
                query = query.filter(cast(Notification.notification_type, String) == nt_value)

            if priority:
                p = str(priority).strip().lower()
                if p in ('normal', 'high', 'urgent'):
                    query = query.filter(Notification.priority == p)

            if date_from:
                query = query.filter(Notification.created_at >= date_from)

            if date_to:
                query = query.filter(Notification.created_at <= date_to)

            # Phase 4: Category and tag filtering
            if category:
                query = query.filter(Notification.category == category)

            if tags:
                # Filter by tags — match any of the specified tags (OR semantics).
                # Build filters first so the fallback path can reuse them with the same OR logic.
                try:
                    tag_filters = [
                        Notification.tags.contains([tag])
                        for tag in tags
                        if tag
                    ]
                    if tag_filters:
                        query = query.filter(sa_or_(*tag_filters))
                except Exception as e:
                    logger.warning(
                        f"Falling back to per-tag OR filtering due to error building tag filter: {e}",
                        exc_info=True
                    )
                    # Fallback must also use OR, not chained AND (filter() chaining is AND).
                    fallback_filters = [
                        Notification.tags.contains([tag])
                        for tag in tags
                        if tag
                    ]
                    if fallback_filters:
                        query = query.filter(sa_or_(*fallback_filters))

            # Get total count before pagination - use with_entities to avoid missing columns
            total_count = query.with_entities(Notification.id).count()

            # Apply pagination and ordering
            notifications = query.order_by(
                Notification.created_at.desc()
            ).offset(offset).limit(limit).all()

            # Title fallback
            def _title_for(n):
                if getattr(n, 'title', None):
                    return n.title
                nt = n.notification_type.value if hasattr(n.notification_type, 'value') else n.notification_type
                try:
                    return (nt or 'notification').replace('_', ' ').title()
                except Exception as e:
                    logger.debug("_title_for fallback: %s", e)
                    return 'Notification'

            # Icon mapping
            def _icon_for(nt: str) -> str:
                try:
                    # Try to map via Enum to the centralized icon map
                    return get_default_icon_for_notification_type(NotificationType(nt))
                except Exception as e:
                    logger.debug("_icon_for fallback: %s", e)
                    return 'fa-bell'

            # Time ago (created_at may be naive from SQLite — normalize before subtracting aware utcnow())
            def _time_ago(ts):
                try:
                    if not ts:
                        return ''
                    ts_utc = ensure_utc(ts)
                    delta = utcnow() - ts_utc
                    s = int(delta.total_seconds())
                    if s < 60:
                        return f"{s}s ago"
                    m = s // 60
                    if m < 60:
                        return f"{m}m ago"
                    h = m // 60
                    if h < 24:
                        return f"{h}h ago"
                    d = h // 24
                    return f"{d}d ago"
                except Exception as e:
                    logger.debug("_time_ago failed: %s", e)
                    return ''

            # OPTIMIZATION: Batch entity lookups to avoid N+1 queries
            # Collect all entity lookups first
            entity_lookups = {}  # {(entity_type, entity_id): [notification_ids]}
            notification_entity_map = {}  # {notification_id: (entity_type, entity_id)}

            # Also collect all AssignmentEntityStatus IDs and AssignedForm IDs for batch loading
            assignment_status_ids = []
            assigned_form_ids = []

            for n in notifications:
                entity_key = None
                # First, try to get entity info from message_params
                if n.message_params and isinstance(n.message_params, dict):
                    entity_type_from_params = n.message_params.get('_entity_type')
                    entity_id_from_params = n.message_params.get('_entity_id')

                    if entity_type_from_params and entity_id_from_params:
                        entity_key = (entity_type_from_params, entity_id_from_params)
                        notification_entity_map[n.id] = entity_key
                        if entity_key not in entity_lookups:
                            entity_lookups[entity_key] = []
                        entity_lookups[entity_key].append(n.id)

                # Collect IDs for batch loading AssignmentEntityStatus records
                if n.related_object_type == 'assignment' and n.related_object_id:
                    assignment_status_ids.append(n.related_object_id)
                    assigned_form_ids.append(n.related_object_id)  # Might be AssignedForm ID

            assignment_status_cache, assigned_form_cache = cls._build_assignment_caches_for_notifications(notifications)

            # Batch lookup all entities from message_params
            entity_cache = {}  # {(entity_type, entity_id): entity_name}
            if entity_lookups:
                try:
                    from app.services.entity_service import EntityService
                    for (entity_type, entity_id), notif_ids in entity_lookups.items():
                        try:
                            entity_name = EntityService.get_localized_entity_name(
                                entity_type,
                                entity_id,
                                include_hierarchy=True
                            )
                            if entity_name and not entity_name.startswith('Unknown'):
                                entity_cache[(entity_type, entity_id)] = entity_name
                            else:
                                entity_cache[(entity_type, entity_id)] = None
                        except Exception as e:
                            logger.warning(f"Error batch-loading entity {entity_type}:{entity_id}: {e}")
                            entity_cache[(entity_type, entity_id)] = None
                except Exception as e:
                    logger.error(f"Error in batch entity lookup: {e}", exc_info=True)

            actor_fields_by_id = cls.build_actor_display_fields_map(notifications, assignment_status_cache)

            # Format notifications
            notifications_data = []
            for n in notifications:
                nt_val = n.notification_type.value if hasattr(n.notification_type, 'value') else n.notification_type

                # Translate message and title from stored keys at display time
                message, dynamic_title = cls._translate_notification_content(n)
                if message is None:
                    message = n.message

                # Use dynamically constructed title if available, otherwise use stored title
                title = dynamic_title if dynamic_title is not None else _title_for(n)

                # Get translated notification type label
                notification_type_label = cls._get_translated_notification_type_label(nt_val)

                # Get localized entity name from cache (optimized batch lookup)
                entity_name = None
                entity_type = None

                if n.id in notification_entity_map:
                    entity_key = notification_entity_map[n.id]
                    entity_name = entity_cache.get(entity_key)
                    if entity_name:
                        entity_type = entity_key[0]

                # Track if we found a non-country entity to prevent wrong country fallback
                found_non_country_entity = False

                # Fallback: Try to get entity info from related AssignmentEntityStatus if available
                # This helps with older notifications that might not have entity info in message_params
                # NOTE: related_object_id might be either:
                #   - AssignmentEntityStatus.id (for most notification types)
                #   - AssignedForm.id (for notify_assignment_created)
                # OPTIMIZED: Uses batch-loaded cache instead of individual queries
                if not entity_name and n.related_object_type == 'assignment' and n.related_object_id:
                    try:
                        from app.models.assignments import AssignmentEntityStatus, AssignedForm
                        from app.services.entity_service import EntityService
                        from app.models.enums import EntityType

                        # First, try direct lookup from cache (batch-loaded)
                        aes = None
                        if n.related_object_id in assignment_status_cache:
                            aes = assignment_status_cache[n.related_object_id]

                        # If that didn't work, it might be an AssignedForm ID - try to find AES via AssignedForm cache
                        if not aes or not aes.entity_type or not aes.entity_id:
                            aes = None

                            # Try to get entity info from message_params first to narrow down which AES to use
                            entity_type_from_params = None
                            entity_id_from_params = None
                            if n.message_params and isinstance(n.message_params, dict):
                                entity_type_from_params = n.message_params.get('_entity_type')
                                entity_id_from_params = n.message_params.get('_entity_id')

                            # Try to find AES via AssignedForm (from cache)
                            assigned_form = assigned_form_cache.get(n.related_object_id)
                            if assigned_form:
                                # Find the AES for this form + entity (from cache)
                                if entity_type_from_params and entity_id_from_params:
                                    cache_key = (n.related_object_id, entity_type_from_params, entity_id_from_params)
                                    aes = assignment_status_cache.get(cache_key)
                                else:
                                    # If no entity info in params, try to find the correct AES from cache
                                    # Strategy: Use country_id as a hint if available, otherwise prioritize non-country entities
                                    # Get all AES for this form from cache
                                    # Look for tuple keys (assigned_form_id, entity_type, entity_id)
                                    all_aes = []
                                    for key, aes in assignment_status_cache.items():
                                        if isinstance(key, tuple) and len(key) == 3 and key[0] == n.related_object_id:
                                            all_aes.append(aes)
                                        # Also check if it's an ID match and the assigned_form_id matches
                                        elif isinstance(key, int) and isinstance(aes, AssignmentEntityStatus):
                                            if aes.assigned_form_id == n.related_object_id:
                                                all_aes.append(aes)

                                    # If notification has a country_id, prefer the AES that matches that country
                                    if n.country_id:
                                        # Try to find country AES that matches the country_id
                                        # For country entities, entity_id IS the country_id
                                        for a in all_aes:
                                            if a.entity_type == EntityType.country.value and a.entity_id == n.country_id:
                                                aes = a
                                                break

                                    # If no country_id or no matching country AES, use prioritization strategy
                                    if not aes:
                                        non_country_aes = [a for a in all_aes if a.entity_type != EntityType.country.value]
                                        country_aes = [a for a in all_aes if a.entity_type == EntityType.country.value]

                                        # If no country_id is set, this is likely a non-country notification
                                        if not n.country_id and non_country_aes:
                                            # Use the first non-country entity (departments, NS branches, etc.)
                                            aes = non_country_aes[0]
                                            found_non_country_entity = True
                                        elif country_aes:
                                            # Use country AES if available
                                            aes = country_aes[0]
                                        elif non_country_aes:
                                            # Fallback to non-country if no country AES
                                            aes = non_country_aes[0]
                                            found_non_country_entity = True
                                        else:
                                            aes = None

                        if aes and aes.entity_type and aes.entity_id:
                            # Track if this is a non-country entity
                            from app.models.enums import EntityType
                            if aes.entity_type != EntityType.country.value:
                                found_non_country_entity = True

                            entity_name = EntityService.get_localized_entity_name(
                                aes.entity_type,
                                aes.entity_id,
                                include_hierarchy=True
                            )
                            entity_type = aes.entity_type

                            if entity_name and not entity_name.startswith('Unknown'):
                                pass  # entity_name is valid
                            else:
                                entity_name = None
                                entity_type = None
                        # else: aes had no entity_type/entity_id — nothing to resolve
                    except Exception:
                        pass

                # If a non-country entity was implied but could not be resolved, leave entity_name
                # as None rather than falling through to a potentially wrong country name.

                ad = actor_fields_by_id.get(n.id, {})
                actor_payload = ad.get('actor')
                actor_badge_icon = ad.get('actor_action_icon')
                primary_is_message = ad.get('primary_is_message', False)

                notifications_data.append({
                    'id': n.id,
                    'title': title,
                    'message': message,
                    'notification_type': nt_val,
                    'notification_type_label': notification_type_label,  # Translated label for display
                    'primary_is_message': primary_is_message,
                    'actor': actor_payload,
                    'actor_action_icon': actor_badge_icon,
                    'is_read': n.is_read,
                    'is_archived': n.is_archived,
                    'timestamp': n.created_at.isoformat() if n.created_at else None,
                    'created_at': n.created_at.isoformat() if n.created_at else None,
                    'time_ago': _time_ago(n.created_at),
                    'entity_name': entity_name,  # Localized entity name
                    'entity_type': entity_type,  # Entity type ('country', 'ns_branch', etc.)
                    'related_id': getattr(n, 'related_object_id', None),
                    'related_type': getattr(n, 'related_object_type', None),
                    'related_url': getattr(n, 'related_url', None),
                    'priority': getattr(n, 'priority', 'normal') or 'normal',
                    'priority_class': 'text-gray-500',
                    'icon': getattr(n, 'icon', None) or _icon_for(nt_val),
                    'group_id': getattr(n, 'group_id', None),  # Phase 2: Add group_id
                    # Phase 3: Action buttons - validate when serializing for defense-in-depth
                    'action_buttons': cls._validate_action_buttons_for_serialization(getattr(n, 'action_buttons', None)),
                    'action_taken': getattr(n, 'action_taken', None),
                    'action_taken_at': n.action_taken_at.isoformat() if getattr(n, 'action_taken_at', None) else None,
                    # Phase 4: User Experience Enhancements
                    'viewed_at': n.viewed_at.isoformat() if getattr(n, 'viewed_at', None) else None,
                    'category': getattr(n, 'category', None),
                    'tags': getattr(n, 'tags', None)
                })

            # Phase 4.3: Grouping disabled - all notifications shown individually
            final_notifications = list(notifications_data)

            # Sort by timestamp (most recent first)
            final_notifications.sort(key=lambda x: x.get('created_at', ''), reverse=True)

            return final_notifications, total_count

        except Exception as e:
            logger.error(f"Error getting user notifications: {e}", exc_info=True)
            return [], 0

    @classmethod
    def get_unread_count(cls, user_id: int) -> int:
        """
        Get count of unread, non-archived, non-expired notifications for a user.

        Args:
            user_id: ID of the user
            country_ids: List of country IDs the user has access to

        Returns:
            Count of unread notifications
        """
        try:
            now = utcnow()
            # Use with_entities to only select id to avoid issues with missing columns
            return Notification.query.with_entities(Notification.id).filter(
                and_(
                    Notification.user_id == user_id,
                    Notification.is_read == False,
                    Notification.is_archived == False,
                    # Filter out expired notifications
                    sa_or_(
                        Notification.expires_at.is_(None),
                        Notification.expires_at > now
                    ),
                )
            ).count()
        except Exception as e:
            logger.error(f"Error getting unread notification count: {e}", exc_info=True)
            return 0

    @classmethod
    def get_archived_count(cls, user_id: int) -> int:
        """
        Get count of archived, non-expired notifications for a user.

        Args:
            user_id: ID of the user
            country_ids: List of country IDs the user has access to

        Returns:
            Count of archived notifications
        """
        try:
            now = utcnow()
            return Notification.query.with_entities(Notification.id).filter(
                and_(
                    Notification.user_id == user_id,
                    Notification.is_archived == True,
                    # Filter out expired notifications
                    sa_or_(
                        Notification.expires_at.is_(None),
                        Notification.expires_at > now
                    ),
                )
            ).count()
        except Exception as e:
            logger.error(f"Error getting archived notification count: {e}", exc_info=True)
            return 0

    @classmethod
    def get_all_count(cls, user_id: int) -> int:
        """
        Get count of all non-archived, non-expired notifications for a user.

        Args:
            user_id: ID of the user
            country_ids: List of country IDs the user has access to

        Returns:
            Count of all notifications (excluding archived)
        """
        try:
            now = utcnow()
            return Notification.query.with_entities(Notification.id).filter(
                and_(
                    Notification.user_id == user_id,
                    Notification.is_archived == False,
                    # Filter out expired notifications
                    sa_or_(
                        Notification.expires_at.is_(None),
                        Notification.expires_at > now
                    ),
                )
            ).count()
        except Exception as e:
            logger.error(f"Error getting all notification count: {e}", exc_info=True)
            return 0

    @classmethod
    def mark_all_as_read(cls, user_id: int) -> bool:
        """
        Bulk-mark all unread, non-archived notifications as read for a user.
        """
        try:
            Notification.query.filter(
                and_(
                    Notification.user_id == user_id,
                    Notification.is_read == False,
                    Notification.is_archived == False,
                )
            ).update({'is_read': True, 'read_at': utcnow()}, synchronize_session='fetch')
            db.session.commit()
            return True
        except Exception as e:
            logger.error(f"Error marking all notifications as read for user {user_id}: {e}", exc_info=True)
            db.session.rollback()
            return False

    @classmethod
    def mark_as_read(cls, notification_ids: List[int], user_id: int) -> bool:
        """
        Mark notifications as read.

        Args:
            notification_ids: List of notification IDs to mark as read
            user_id: ID of the user (for ownership verification)

        Returns:
            True if successful, False otherwise
        """
        try:
            # The user_id filter guarantees all returned rows belong to this user.
            # A count mismatch means some IDs were already deleted or never existed —
            # that is safe to proceed with; we operate on whatever was found.
            notifications = Notification.query.filter(
                and_(
                    Notification.id.in_(notification_ids),
                    Notification.user_id == user_id
                )
            ).all()

            if len(notifications) != len(notification_ids):
                missing = set(notification_ids) - {n.id for n in notifications}
                logger.debug(
                    f"mark_as_read: {len(missing)} requested ID(s) not found for user {user_id} "
                    f"(deleted or unauthorized): {missing}"
                )

            if not notifications:
                return True  # Nothing to do

            for notification in notifications:
                notification.is_read = True
                notification.read_at = utcnow()

            db.session.commit()
            return True

        except Exception as e:
            logger.error(f"Error marking notifications as read: {e}", exc_info=True)
            db.session.rollback()
            return False

    @classmethod
    def mark_as_unread(cls, notification_ids: List[int], user_id: int) -> bool:
        """
        Mark notifications as unread.

        Args:
            notification_ids: List of notification IDs to mark as unread
            user_id: ID of the user (for ownership verification)

        Returns:
            True if successful, False otherwise
        """
        try:
            notifications = Notification.query.filter(
                and_(
                    Notification.id.in_(notification_ids),
                    Notification.user_id == user_id
                )
            ).all()

            if len(notifications) != len(notification_ids):
                missing = set(notification_ids) - {n.id for n in notifications}
                logger.debug(
                    f"mark_as_unread: {len(missing)} requested ID(s) not found for user {user_id} "
                    f"(deleted or unauthorized): {missing}"
                )

            if not notifications:
                return True

            for notification in notifications:
                notification.is_read = False
                notification.read_at = None

            db.session.commit()
            return True

        except Exception as e:
            logger.error(f"Error marking notifications as unread: {e}", exc_info=True)
            db.session.rollback()
            return False

    @classmethod
    def archive_notifications(cls, notification_ids: List[int], user_id: int) -> bool:
        """
        Archive notifications.

        Args:
            notification_ids: List of notification IDs to archive
            user_id: ID of the user (for ownership verification)

        Returns:
            True if successful, False otherwise
        """
        try:
            notifications = Notification.query.filter(
                and_(
                    Notification.id.in_(notification_ids),
                    Notification.user_id == user_id
                )
            ).all()

            if len(notifications) != len(notification_ids):
                missing = set(notification_ids) - {n.id for n in notifications}
                logger.debug(
                    f"archive_notifications: {len(missing)} requested ID(s) not found for user {user_id} "
                    f"(deleted or unauthorized): {missing}"
                )

            if not notifications:
                return True

            for notification in notifications:
                notification.is_archived = True
                notification.archived_at = utcnow()

            db.session.commit()
            return True

        except Exception as e:
            logger.error(f"Error archiving notifications: {e}", exc_info=True)
            db.session.rollback()
            return False

    @classmethod
    def delete_notifications(cls, notification_ids: List[int], user_id: int) -> bool:
        """
        Delete notifications.

        Args:
            notification_ids: List of notification IDs to delete
            user_id: ID of the user (for ownership verification)

        Returns:
            True if successful, False otherwise
        """
        try:
            # The user_id filter in the query guarantees only this user's notifications
            # are touched. Count mismatches mean some IDs were already deleted — that is
            # safe to proceed with; we delete whatever we find.
            query = Notification.query.filter(
                and_(
                    Notification.id.in_(notification_ids),
                    Notification.user_id == user_id
                )
            )

            found_count = query.count()
            if found_count == 0:
                return True  # Nothing to delete

            if found_count != len(notification_ids):
                missing_count = len(notification_ids) - found_count
                logger.debug(
                    f"delete_notifications: {missing_count} of {len(notification_ids)} requested ID(s) "
                    f"not found for user {user_id} (already deleted or unauthorized)"
                )

            # Delete dependent email_delivery_log rows first to satisfy FK constraint
            EmailDeliveryLog.query.filter(
                EmailDeliveryLog.notification_id.in_(notification_ids),
                EmailDeliveryLog.user_id == user_id,
            ).delete(synchronize_session='fetch')

            query.delete(synchronize_session='fetch')
            db.session.commit()
            return True

        except Exception as e:
            logger.error(f"Error deleting notifications: {e}", exc_info=True)
            db.session.rollback()
            return False

    @classmethod
    def get_notification_preferences(cls, user_id: int) -> NotificationPreferences:
        """
        Get notification preferences for a user.
        Creates default preferences if they don't exist.

        Args:
            user_id: ID of the user

        Returns:
            NotificationPreferences object
        """
        preferences = NotificationPreferences.query.filter_by(user_id=user_id).first()

        if not preferences:
            # Create default preferences (empty list => all enabled in UI)
            preferences = NotificationPreferences(
                user_id=user_id,
                email_notifications=True,
                notification_types_enabled=[],
                notification_frequency='instant',
                sound_enabled=True,
                push_notifications=True,
                push_notification_types_enabled=[]
            )
            db.session.add(preferences)
            db.session.commit()

        return preferences

    @classmethod
    def update_notification_preferences(
        cls,
        user_id: int,
        email_notifications: Optional[bool] = None,
        notification_types_enabled: Optional[Dict[str, bool]] = None,
        notification_frequency: Optional[str] = None,
        sound_enabled: Optional[bool] = None,
        push_notifications: Optional[bool] = None,
        push_notification_types_enabled: Optional[List[str]] = None,
        digest_day: Optional[str] = None,
        digest_time: Optional[str] = None,
        timezone: Optional[str] = None
    ) -> Optional[NotificationPreferences]:
        """
        Update notification preferences for a user.

        Args:
            user_id: ID of the user
            email_notifications: Enable/disable email notifications
            notification_types_enabled: Dict of notification types and their enabled status
            notification_frequency: Notification frequency ('instant', 'daily', 'weekly')
            sound_enabled: Enable/disable sound notifications
            push_notifications: Enable/disable push notifications
            push_notification_types_enabled: List of notification types enabled for push

        Returns:
            Updated NotificationPreferences object or None if error
        """
        try:
            preferences = cls.get_notification_preferences(user_id)

            if email_notifications is not None:
                preferences.email_notifications = email_notifications

            if notification_types_enabled is not None:
                # Accept dict or list; normalize to list of enabled types
                if isinstance(notification_types_enabled, dict):
                    preferences.notification_types_enabled = [k for k, v in notification_types_enabled.items() if v]
                elif isinstance(notification_types_enabled, list):
                    preferences.notification_types_enabled = notification_types_enabled
                else:
                    preferences.notification_types_enabled = []

            if notification_frequency is not None:
                preferences.notification_frequency = notification_frequency

            if sound_enabled is not None:
                preferences.sound_enabled = sound_enabled

            if push_notifications is not None:
                preferences.push_notifications = push_notifications

            if push_notification_types_enabled is not None:
                # Accept list of enabled types
                if isinstance(push_notification_types_enabled, list):
                    preferences.push_notification_types_enabled = push_notification_types_enabled
                else:
                    preferences.push_notification_types_enabled = []

            # Handle digest day and time
            # Update if provided (None means clear the field)
            if digest_day is not None:
                preferences.digest_day = digest_day if digest_day else None
            if digest_time is not None:
                preferences.digest_time = digest_time if digest_time else None

            # Clear digest fields based on frequency (this overrides any values set above)
            if notification_frequency == 'instant':
                preferences.digest_day = None
                preferences.digest_time = None
            elif notification_frequency == 'daily':
                # Clear day for daily digest
                preferences.digest_day = None

            # Update timezone if provided
            if timezone is not None:
                preferences.timezone = timezone if timezone else None

            preferences.updated_at = utcnow()
            db.session.commit()
            return preferences

        except Exception as e:
            logger.error(f"Error updating notification preferences: {e}", exc_info=True)
            db.session.rollback()
            return None
