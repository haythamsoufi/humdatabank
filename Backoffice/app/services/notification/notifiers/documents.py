"""Typed notification helpers for document upload events."""

from flask import url_for, current_app
from flask_login import current_user
from flask_babel import gettext as _
from sqlalchemy import or_, select

from app.models import NotificationType, User, Country
from app.services.platform.app_settings_service import audience_bucket_enabled
from app.services.notification.audience import (
    collect_entity_admin_audience_recipient_ids,
    get_assignment_editor_submitter_user_ids_for_entity,
)
from app.services.notification.creation import create_notification

from app.services.notification.core import log_entity_activity, notify_entity_focal_points

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
        # 1. If status is "pending": Only notify admins/system managers (for approval)
        # 2. If status is "approved": Notify focal points (they should know about approved documents)
        # 3. Never notify the uploader
        # 4. Users who are both admins and focal points only get one notification (admin takes priority)

        if document.status == 'pending':
            current_app.logger.info(
                f"[DOCUMENT_NOTIFICATION] Document status is 'pending' - will notify admins/system managers only"
            )

            xs_uploader = [uploader_id] if uploader_id else []
            admin_user_ids = collect_entity_admin_audience_recipient_ids(
                NotificationType.document_uploaded,
                "country",
                int(country_id),
                exclude_user_ids=xs_uploader,
            )

            if not admin_user_ids:
                current_app.logger.info(
                    "[DOCUMENT_NOTIFICATION] Pending document: no org-admin/system-manager recipients (settings or empty)"
                )
            else:

                current_app.logger.info(
                    f"[DOCUMENT_NOTIFICATION] Found admin-capable users to notify: {len(admin_user_ids)}"
                )

                excluded_admin_ids = xs_uploader if xs_uploader else []

                if excluded_admin_ids:
                    current_app.logger.info(
                        f"[DOCUMENT_NOTIFICATION] Excluding uploader (admin/system manager) from notifications: {excluded_admin_ids}"
                    )

                current_app.logger.info(
                    f"[DOCUMENT_NOTIFICATION] Will notify {len(admin_user_ids)} admins/system managers: {admin_user_ids}"
                )

                # Get user emails for logging (batch load; stale IDs are skipped)
                admin_users_by_id = {
                    u.id: u for u in User.query.filter(User.id.in_(admin_user_ids)).all()
                }
                admin_emails = [
                    admin_users_by_id[uid].email
                    for uid in admin_user_ids
                    if admin_users_by_id.get(uid) is not None
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

                if focal_point_ids and audience_bucket_enabled(
                    NotificationType.document_uploaded, "focal_points"
                ):
                    focal_users_by_id = {
                        u.id: u for u in User.query.filter(User.id.in_(focal_point_ids)).all()
                    }
                    focal_point_emails = [
                        focal_users_by_id[uid].email
                        for uid in focal_point_ids
                        if focal_users_by_id.get(uid) is not None
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
                elif focal_point_ids:
                    current_app.logger.info(
                        "[DOCUMENT_NOTIFICATION] Audience rule: focal_points disabled for document_uploaded — skipping focal notifications"
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

