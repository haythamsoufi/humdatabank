"""Typed notification helpers for assignment workflow events."""

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

from app.services.notification.core import (
    log_entity_activity,
    notify_entity_focal_points,
)

def notify_assignment_created(assignment_entity_status):
    """Notify focal points (and optionally entity-scoped admins) when a new assignment is created."""
    aes = assignment_entity_status
    entity_type = aes.entity_type
    entity_id = aes.entity_id

    from app.services.organization.entity_service import EntityService
    from app.models.forms import FormTemplate

    # Get template directly via template_id to avoid stale relationship data
    assigned_form = aes.assigned_form
    template = FormTemplate.query.get(assigned_form.template_id) if assigned_form and assigned_form.template_id else None
    template_name = template.name if template else "Unknown Template"

    # Suppress all notifications and emails for load-test assignments so that
    # automated runs do not spam focal points or admins.
    if assigned_form and (assigned_form.period_name or "").startswith("[LOADTEST]"):
        current_app.logger.debug(
            "[NOTIFY] Suppressing notify_assignment_created for [LOADTEST] assignment "
            "(period=%r, aes_id=%s)", assigned_form.period_name, aes.id
        )
        return []

    # Debug: Log template lookup to help diagnose any issues
    if assigned_form and template:
        current_app.logger.debug(
            f"[NOTIFY_ASSIGNMENT_CREATED] Template lookup for AES {aes.id}: "
            f"AssignedForm {assigned_form.id}, template_id={assigned_form.template_id}, "
            f"template_name='{template_name}'"
        )

    # Log activity for the entity
    log_entity_activity(
        entity_type=entity_type,
        entity_id=entity_id,
        activity_type='assignment_created',
        activity_description=f"New assignment '{template_name}' for period '{assigned_form.period_name}' was created",
        summary_key='activity.assignment_created',
        summary_params={'template': template_name},
        related_object_type='assignment',
        related_object_id=aes.id,
        assignment_id=aes.id,
        related_url=url_for('forms.view_edit_form', form_type='assignment', form_id=aes.id),
        activity_category='admin',
        icon=None,
        user_id=None
    )

    # Create notifications for focal points using translation keys
    # Use assigned_form_id instead of AES ID for related_object_id to ensure proper deduplication
    # across multiple entities in the same assignment
    due_date_str = aes.due_date.strftime('%Y-%m-%d') if aes.due_date else _('No deadline set')

    notifications = notify_entity_focal_points(
        entity_type=entity_type,
        entity_id=entity_id,
        notification_type=NotificationType.assignment_created,
        title_key='notification.assignment_created.title',
        title_params=None,
        message_key='notification.assignment_created.message',
        message_params={
            'template': template_name,
            'period': assigned_form.period_name,
            'due_date': due_date_str,
            '_entity_type': entity_type,  # Store entity info for label (prefixed with _ to avoid translation)
            '_entity_id': entity_id
        },
        related_object_type='assignment',
        related_object_id=aes.assigned_form_id,
        related_url=url_for('forms.view_edit_form', form_type='assignment', form_id=aes.id),
        priority='normal'
    ) or []

    # Optional admin channels (org admins vs system managers are separate settings buckets).
    admin_notifications = []
    secondary_recipients = collect_entity_admin_audience_recipient_ids(
        NotificationType.assignment_created,
        entity_type,
        entity_id,
    )
    if secondary_recipients:
        focal_cover = set(
            get_assignment_editor_submitter_user_ids_for_entity(entity_type, entity_id)
        )
        admin_only = [uid for uid in secondary_recipients if uid not in focal_cover]
        if admin_only:
            admin_notifications = create_notification(
                user_ids=admin_only,
                notification_type=NotificationType.assignment_created,
                title_key='notification.assignment_created.title',
                title_params=None,
                message_key='notification.assignment_created.message',
                message_params={
                    'template': template_name,
                    'period': assigned_form.period_name,
                    'due_date': due_date_str,
                    '_entity_type': entity_type,
                    '_entity_id': entity_id,
                },
                related_object_type='assignment',
                related_object_id=aes.assigned_form_id,
                related_url=url_for('forms.view_edit_form', form_type='assignment', form_id=aes.id),
                entity_type=entity_type,
                entity_id=entity_id,
                priority='normal',
            ) or []

    return list(notifications) + list(admin_notifications)

def notify_assignment_submitted(assignment_entity_status):
    """Notify focal points and admins when an assignment is submitted for any entity type."""
    aes = assignment_entity_status
    entity_type = aes.entity_type
    entity_id = aes.entity_id

    from app.services.organization.entity_service import EntityService
    from app.models.forms import FormTemplate

    # Get template directly via template_id to avoid stale relationship data
    assigned_form = aes.assigned_form
    template = FormTemplate.query.get(assigned_form.template_id) if assigned_form and assigned_form.template_id else None
    template_name = template.name if template else "Unknown Template"

    # Suppress all notifications and emails for load-test assignments so that
    # automated runs do not spam focal points or admins.
    if assigned_form and (assigned_form.period_name or "").startswith("[LOADTEST]"):
        current_app.logger.debug(
            "[NOTIFY] Suppressing notify_assignment_submitted for [LOADTEST] assignment "
            "(period=%r, aes_id=%s)", assigned_form.period_name, aes.id
        )
        return []

    # Log activity for the entity
    log_entity_activity(
        entity_type=entity_type,
        entity_id=entity_id,
        activity_type='assignment_submitted',
        activity_description=f"Assignment '{template_name}' for period '{assigned_form.period_name}' was submitted",
        summary_key='activity.assignment_submitted',
        summary_params={'template': template_name},
        related_object_type='assignment',
        related_object_id=aes.id,
        assignment_id=aes.id,
        related_url=url_for('forms.view_edit_form', form_type='assignment', form_id=aes.id),
        activity_category='form',
        icon=None,
        user_id=None
    )

    # Identify entity-scoped admins for dedupe + optional admin broadcast (never global admin blast).
    secondary_recipients = collect_entity_admin_audience_recipient_ids(
        NotificationType.assignment_submitted,
        entity_type,
        entity_id,
    )

    # Exclude users who already receive the admin/SM copy below (avoid duplicate in-app notifications).
    exclude_from_focal = set(secondary_recipients)

    # Notify focal points (assignment_editor/submitter), including the submitter when they hold that role.
    notifications = notify_entity_focal_points(
        entity_type=entity_type,
        entity_id=entity_id,
        notification_type=NotificationType.assignment_submitted,
        title_key='notification.assignment_submitted.title',
        title_params={'template': template_name, 'period': assigned_form.period_name},
        message_key='notification.assignment_submitted.message',
        message_params={
            'template': template_name,
            'period': assigned_form.period_name,
            '_entity_type': entity_type,
            '_entity_id': entity_id
        },
        related_object_type='assignment',
        related_object_id=aes.id,
        related_url=url_for('forms.view_edit_form', form_type='assignment', form_id=aes.id),
        priority='normal',
        exclude_user_ids=list(exclude_from_focal) if exclude_from_focal else None,
    )

    # Get entity name for the notification message
    from app.services.organization.entity_service import EntityService
    entity_name = EntityService.get_localized_entity_name(entity_type, entity_id, include_hierarchy=True)
    if not entity_name or entity_name.startswith('Unknown'):
        # Fallback to entity type if name not found
        entity_name = entity_type.replace('_', ' ').title()

    submitter_name = current_user.name if (current_user and current_user.is_authenticated) else "A focal point"

    if secondary_recipients:
        admin_notifications = create_notification(
            user_ids=secondary_recipients,
            notification_type=NotificationType.assignment_submitted,
            title_key='notification.assignment_submitted.admin.title',
            title_params={
                'submitter_name': submitter_name,
                'period': assigned_form.period_name,
            },
            message_key='notification.assignment_submitted.admin.message',
            message_params={
                'template': template_name,
                'country': entity_name,
                'period': assigned_form.period_name,
                'submitter_name': submitter_name,
                '_entity_type': entity_type,
                '_entity_id': entity_id
            },
            entity_type=entity_type,
            entity_id=entity_id,
            related_object_type='assignment',
            related_object_id=aes.id,
            related_url=url_for('forms.view_edit_form', form_type='assignment', form_id=aes.id),
            priority='high',
            override_email_preferences=True  # Always email admins for action-required review
        )
    else:
        admin_notifications = []

    return notifications + (admin_notifications or [])


def _focal_point_ids_by_org_domain(entity_type, entity_id, *, org_only: bool, exclude_user_ids=None):
    """Assignment editor/submitter IDs filtered by organization email domain."""
    from app.models import User
    from app.utils.organization_helpers import is_org_email

    exclude_set = set(exclude_user_ids or [])
    focal_point_ids = get_assignment_editor_submitter_user_ids_for_entity(
        entity_type,
        entity_id,
        exclude_user_ids=list(exclude_set) if exclude_set else None,
    )
    if not focal_point_ids:
        return []
    users = User.query.filter(User.id.in_(focal_point_ids)).all()
    if org_only:
        return [u.id for u in users if is_org_email(getattr(u, 'email', ''))]
    return [u.id for u in users if not is_org_email(getattr(u, 'email', ''))]

def notify_assignment_sent_for_review(assignment_entity_status):
    """Notify org-email delegation focal points (and, if enabled, entity-scoped org admins) when NS sends an assignment for review."""
    aes = assignment_entity_status
    entity_type = aes.entity_type
    entity_id = aes.entity_id
    assigned_form = aes.assigned_form
    from app.models.forms import FormTemplate
    from app.services.organization.entity_service import EntityService

    template = FormTemplate.query.get(assigned_form.template_id) if assigned_form and assigned_form.template_id else None
    template_name = template.name if template else "Unknown Template"

    if assigned_form and (assigned_form.period_name or "").startswith("[LOADTEST]"):
        return []

    entity_name = EntityService.get_localized_entity_name(entity_type, entity_id, include_hierarchy=True)
    if not entity_name or entity_name.startswith('Unknown'):
        entity_name = entity_type.replace('_', ' ').title()

    submitter_name = (
        current_user.name
        if (current_user and current_user.is_authenticated and current_user.name)
        else "A National Society focal point"
    )

    log_entity_activity(
        entity_type=entity_type,
        entity_id=entity_id,
        activity_type='assignment_sent_for_review',
        activity_description=(
            f"Assignment '{template_name}' for {entity_name} (period '{assigned_form.period_name}') was sent for review"
        ),
        summary_key='activity.assignment_sent_for_review',
        summary_params={'template': template_name, 'country': entity_name},
        related_object_type='assignment',
        related_object_id=aes.id,
        assignment_id=aes.id,
        related_url=url_for('forms.view_edit_form', form_type='assignment', form_id=aes.id),
        activity_category='form',
        icon=None,
        user_id=None,
    )

    exclude = [current_user.id] if current_user and current_user.is_authenticated else None
    org_focal_ids = _focal_point_ids_by_org_domain(
        entity_type, entity_id, org_only=True, exclude_user_ids=exclude
    )

    notifications = []
    if org_focal_ids and audience_bucket_enabled(NotificationType.assignment_sent_for_review, "focal_points"):
        notifications = create_notification(
            user_ids=org_focal_ids,
            notification_type=NotificationType.assignment_sent_for_review,
            title_key='notification.assignment_sent_for_review.title',
            title_params={
                'template': template_name,
                'period': assigned_form.period_name,
                'country': entity_name,
            },
            message_key='notification.assignment_sent_for_review.message',
            message_params={
                'template': template_name,
                'period': assigned_form.period_name,
                'country': entity_name,
                'submitter_name': submitter_name,
                '_entity_type': entity_type,
                '_entity_id': entity_id,
            },
            entity_type=entity_type,
            entity_id=entity_id,
            related_object_type='assignment',
            related_object_id=aes.id,
            related_url=url_for('forms.view_edit_form', form_type='assignment', form_id=aes.id),
            priority='high',
            override_email_preferences=True,
        ) or []

    # Optional admin channel (org admins only — system managers stay off for this type).
    admin_notifications = []
    secondary_recipients = collect_entity_admin_audience_recipient_ids(
        NotificationType.assignment_sent_for_review,
        entity_type,
        entity_id,
        exclude_user_ids=exclude,
    )
    admin_only = [uid for uid in secondary_recipients if uid not in set(org_focal_ids)]
    if admin_only:
        admin_notifications = create_notification(
            user_ids=admin_only,
            notification_type=NotificationType.assignment_sent_for_review,
            title_key='notification.assignment_sent_for_review.admin.title',
            title_params={
                'template': template_name,
                'period': assigned_form.period_name,
                'country': entity_name,
            },
            message_key='notification.assignment_sent_for_review.admin.message',
            message_params={
                'template': template_name,
                'period': assigned_form.period_name,
                'country': entity_name,
                'submitter_name': submitter_name,
                '_entity_type': entity_type,
                '_entity_id': entity_id,
            },
            entity_type=entity_type,
            entity_id=entity_id,
            related_object_type='assignment',
            related_object_id=aes.id,
            related_url=url_for('forms.view_edit_form', form_type='assignment', form_id=aes.id),
            priority='high',
            override_email_preferences=True,
        ) or []

    return list(notifications) + list(admin_notifications)


def notify_assignment_returned_for_revision(assignment_entity_status):
    """Notify non-org NS focal points when delegation returns work for changes."""
    aes = assignment_entity_status
    entity_type = aes.entity_type
    entity_id = aes.entity_id
    assigned_form = aes.assigned_form
    from app.models.forms import FormTemplate

    template = FormTemplate.query.get(assigned_form.template_id) if assigned_form and assigned_form.template_id else None
    template_name = template.name if template else "Unknown Template"

    if assigned_form and (assigned_form.period_name or "").startswith("[LOADTEST]"):
        return []

    log_entity_activity(
        entity_type=entity_type,
        entity_id=entity_id,
        activity_type='assignment_returned_for_revision',
        activity_description=(
            f"Assignment '{template_name}' for period '{assigned_form.period_name}' was returned for revision"
        ),
        summary_key='activity.assignment_returned_for_revision',
        summary_params={'template': template_name},
        related_object_type='assignment',
        related_object_id=aes.id,
        assignment_id=aes.id,
        related_url=url_for('forms.view_edit_form', form_type='assignment', form_id=aes.id),
        activity_category='form',
        icon=None,
        user_id=None,
    )

    exclude = [current_user.id] if current_user and current_user.is_authenticated else None
    ns_focal_ids = _focal_point_ids_by_org_domain(
        entity_type, entity_id, org_only=False, exclude_user_ids=exclude
    )
    if not ns_focal_ids:
        return []

    if not audience_bucket_enabled(NotificationType.assignment_returned_for_revision, "focal_points"):
        return []

    return create_notification(
        user_ids=ns_focal_ids,
        notification_type=NotificationType.assignment_returned_for_revision,
        title_key='notification.assignment_returned_for_revision.title',
        title_params={'template': template_name, 'period': assigned_form.period_name},
        message_key='notification.assignment_returned_for_revision.message',
        message_params={
            'template': template_name,
            'period': assigned_form.period_name,
            '_entity_type': entity_type,
            '_entity_id': entity_id,
        },
        entity_type=entity_type,
        entity_id=entity_id,
        related_object_type='assignment',
        related_object_id=aes.id,
        related_url=url_for('forms.view_edit_form', form_type='assignment', form_id=aes.id),
        priority='high',
        override_email_preferences=True,
    )

def notify_assignment_approved(assignment_entity_status):
    """Notify focal points when an assignment is approved for any entity type."""
    aes = assignment_entity_status
    entity_type = aes.entity_type
    entity_id = aes.entity_id

    from app.services.organization.entity_service import EntityService
    from app.models.forms import FormTemplate

    # Get template directly via template_id to avoid stale relationship data
    assigned_form = aes.assigned_form
    template = FormTemplate.query.get(assigned_form.template_id) if assigned_form and assigned_form.template_id else None
    template_name = template.name if template else "Unknown Template"

    # Log activity for the entity
    log_entity_activity(
        entity_type=entity_type,
        entity_id=entity_id,
        activity_type='assignment_approved',
        activity_description=f"Assignment '{template_name}' for period '{assigned_form.period_name}' was approved",
        summary_key='activity.assignment_approved',
        summary_params={'template': template_name},
        related_object_type='assignment',
        related_object_id=aes.id,
        assignment_id=aes.id,
        related_url=url_for('forms.view_edit_form', form_type='assignment', form_id=aes.id),
        activity_category='admin',
        icon=None,
        user_id=None
    )

    # Create notifications for focal points using translation keys
    return notify_entity_focal_points(
        entity_type=entity_type,
        entity_id=entity_id,
        notification_type=NotificationType.assignment_approved,
        title_key='notification.assignment_approved.title',
        title_params=None,
        message_key='notification.assignment_approved.message',
        message_params={
            'template': template_name,
            '_entity_type': entity_type,
            '_entity_id': entity_id
        },
        related_object_type='assignment',
        related_object_id=aes.id,
        related_url=url_for('forms.view_edit_form', form_type='assignment', form_id=aes.id),
        priority='normal'
    )


def notify_assignment_reopened(assignment_entity_status):
    """Notify focal points when an assignment is reopened for any entity type."""
    aes = assignment_entity_status
    entity_type = aes.entity_type
    entity_id = aes.entity_id

    from app.services.organization.entity_service import EntityService
    from app.models.forms import FormTemplate

    # Get template directly via template_id to avoid stale relationship data
    assigned_form = aes.assigned_form
    template = FormTemplate.query.get(assigned_form.template_id) if assigned_form and assigned_form.template_id else None
    template_name = template.name if template else "Unknown Template"

    # Log activity for the entity
    log_entity_activity(
        entity_type=entity_type,
        entity_id=entity_id,
        activity_type='assignment_reopened',
        activity_description=f"Assignment '{template_name}' for period '{assigned_form.period_name}' was reopened",
        summary_key='activity.assignment_reopened',
        summary_params={'template': template_name},
        related_object_type='assignment',
        related_object_id=aes.id,
        assignment_id=aes.id,
        related_url=url_for('forms.view_edit_form', form_type='assignment', form_id=aes.id),
        activity_category='admin',
        icon=None,
        user_id=None
    )

    # Create notifications for focal points using translation keys
    notifications = notify_entity_focal_points(
        entity_type=entity_type,
        entity_id=entity_id,
        notification_type=NotificationType.assignment_reopened,
        title_key='notification.assignment_reopened.title',
        title_params=None,
        message_key='notification.assignment_reopened.message',
        message_params={
            'template': template_name,
            '_entity_type': entity_type,
            '_entity_id': entity_id
        },
        related_object_type='assignment',
        related_object_id=aes.id,
        related_url=url_for('forms.view_edit_form', form_type='assignment', form_id=aes.id),
        priority='normal'
    )
    return notifications

def notify_self_report_created(assignment_entity_status):
    """Notify focal points when a self-report is created for any entity type."""
    aes = assignment_entity_status
    entity_type = aes.entity_type
    entity_id = aes.entity_id

    from app.services.organization.entity_service import EntityService
    from app.models.forms import FormTemplate

    # Get template directly via template_id to avoid stale relationship data
    assigned_form = aes.assigned_form
    template = FormTemplate.query.get(assigned_form.template_id) if assigned_form and assigned_form.template_id else None
    template_name = template.name if template else "Unknown Template"

    # Log activity for the entity
    log_entity_activity(
        entity_type=entity_type,
        entity_id=entity_id,
        activity_type='self_report_created',
        activity_description=f"Self-report '{template_name}' for period '{assigned_form.period_name}' was created",
        summary_key='activity.self_report_created',
        summary_params={'template': template_name},
        related_object_type='assignment',
        related_object_id=aes.id,
        assignment_id=aes.id,
        related_url=url_for('forms.view_edit_form', form_type='assignment', form_id=aes.id),
        activity_category='admin',
        icon=None,
        user_id=None
    )

    # Create notifications for focal points using translation keys
    return notify_entity_focal_points(
        entity_type=entity_type,
        entity_id=entity_id,
        notification_type=NotificationType.self_report_created,
        title_key='notification.self_report_created.title',
        title_params=None,
        message_key='notification.self_report_created.message',
        message_params={
            'template': template_name,
            '_entity_type': entity_type,
            '_entity_id': entity_id
        },
        related_object_type='assignment',
        related_object_id=aes.id,
        related_url=url_for('forms.view_edit_form', form_type='assignment', form_id=aes.id),
        priority='normal'
    )

def notify_form_data_updated(assignment_entity_status, completion_percentage=None, field_changes=None):
    """Notify focal points when form data is updated with detailed field change information for any entity type."""
    aes = assignment_entity_status
    entity_type = aes.entity_type
    entity_id = aes.entity_id

    from app.models.forms import FormTemplate

    # Get template directly via template_id to avoid stale relationship data
    assigned_form = aes.assigned_form
    template = FormTemplate.query.get(assigned_form.template_id) if assigned_form and assigned_form.template_id else None
    template_name = template.name if template else "Unknown Template"

    # Create activity summary based on field changes
    activity_description = f"Form data updated for assignment '{template_name}'"

    # Enhance summary and description with field changes
    summary_key = 'activity.form_data_updated.multiple'
    summary_params = {'count': 0, 'template': template_name}
    if field_changes:
        change_count = len(field_changes)
        if change_count == 1:
            change = field_changes[0]
            activity_description = f"Updated field '{change['field_name']}' from '{change.get('old_value') or ''}' to '{change.get('new_value') or ''}'"
            summary_key = 'activity.form_data_updated.single'
            summary_params = {'field': change['field_name'], 'old': change.get('old_value') or '', 'new': change.get('new_value') or ''}
        else:
            activity_description = f"Updated {change_count} fields in assignment '{template_name}'"
            summary_key = 'activity.form_data_updated.multiple'
            summary_params = {'count': change_count, 'template': template_name}

    # Add completion percentage to summary
    completion_text = f" (now {completion_percentage:.1f}% complete)" if completion_percentage else ""
    activity_description += completion_text

    # Log activity with detailed field changes for the entity
    log_entity_activity(
        entity_type=entity_type,
        entity_id=entity_id,
        activity_type='form_data_updated',
        activity_description=activity_description,
        summary_key=summary_key,
        summary_params=summary_params,
        related_object_type='assignment',
        related_object_id=aes.id,
        assignment_id=aes.id,
        related_url=url_for('forms.view_edit_form', form_type='assignment', form_id=aes.id),
        activity_category='form',
        icon=None,
        user_id=None
    )

