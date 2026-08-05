"""Typed notification helpers for assignment workflow events."""

from flask import url_for, current_app
from flask_login import current_user
from flask_babel import gettext as _
from sqlalchemy import or_, select

from app.models import NotificationType, User
from app.services.platform.app_settings_service import audience_bucket_enabled
from app.services.notification.audience import (
    collect_entity_admin_audience_recipient_ids,
    get_assignment_editor_submitter_user_ids_for_entity,
)
from app.services.notification.assignment_review_recipient import (
    resolve_submission_review_recipient_user_ids,
)
from app.services.notification.creation import create_notification

from app.services.notification.core import (
    log_entity_activity,
    notify_entity_focal_points,
)


def _resolve_entity_name(entity_type, entity_id) -> str:
    from app.services.organization.entity_service import EntityService

    entity_name = EntityService.get_localized_entity_name(
        entity_type, entity_id, include_hierarchy=True
    )
    if not entity_name or entity_name.startswith('Unknown'):
        return entity_type.replace('_', ' ').title()
    return entity_name


def _resolve_current_actor_name(*, fallback: str = "An administrator") -> str:
    if current_user and current_user.is_authenticated and current_user.name:
        return current_user.name
    return fallback


def _resolve_current_actor_user_id():
    if current_user and current_user.is_authenticated:
        return current_user.id
    return None


def _resolve_approved_by_name(assignment_entity_status) -> str:
    approver_id = getattr(assignment_entity_status, 'approved_by_user_id', None)
    if approver_id:
        approver = User.query.get(int(approver_id))
        if approver and approver.name:
            return approver.name
    return _resolve_current_actor_name(fallback="An administrator")


def _build_assignment_notification_params(
    aes,
    assigned_form,
    template_name: str,
    *,
    actor_name: str | None = None,
    actor_user_id=None,
    due_date_str: str | None = None,
) -> dict:
    """Shared message params: display title, entity, and optional actor."""
    params = {
        'assignment_title': _resolve_assignment_display_title(assigned_form, template_name),
        'template': template_name,
        'period': assigned_form.period_name if assigned_form else '',
        'country': _resolve_entity_name(aes.entity_type, aes.entity_id),
        '_entity_type': aes.entity_type,
        '_entity_id': aes.entity_id,
    }
    if due_date_str is not None:
        params['due_date'] = due_date_str
    if actor_name is not None:
        params['actor_name'] = actor_name
    if actor_user_id is not None:
        params['_actor_user_id'] = actor_user_id
    return params


def notify_assignment_created(assignment_entity_status):
    """Notify focal points (and optionally entity-scoped admins) when a new assignment is created."""
    aes = assignment_entity_status
    entity_type = aes.entity_type
    entity_id = aes.entity_id

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
    message_params = _build_assignment_notification_params(
        aes, assigned_form, template_name, due_date_str=due_date_str
    )
    title_params = {
        'assignment_title': message_params['assignment_title'],
        'country': message_params['country'],
    }

    notifications = notify_entity_focal_points(
        entity_type=entity_type,
        entity_id=entity_id,
        notification_type=NotificationType.assignment_created,
        title_key='notification.assignment_created.title',
        title_params=title_params,
        message_key='notification.assignment_created.message',
        message_params=message_params,
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
                title_params=title_params,
                message_key='notification.assignment_created.message',
                message_params=dict(message_params),
                related_object_type='assignment',
                related_object_id=aes.assigned_form_id,
                related_url=url_for('forms.view_edit_form', form_type='assignment', form_id=aes.id),
                entity_type=entity_type,
                entity_id=entity_id,
                priority='normal',
            ) or []

    return list(notifications) + list(admin_notifications)

def _resolve_assignment_submitter_name(assignment_entity_status) -> str:
    """Display name for whoever submitted the assignment (persisted id first, then current user)."""
    submitter_id = getattr(assignment_entity_status, 'submitted_by_user_id', None)
    if submitter_id:
        submitter = User.query.get(int(submitter_id))
        if submitter and submitter.name:
            return submitter.name
    if current_user and current_user.is_authenticated and current_user.name:
        return current_user.name
    return "A focal point"


def _resolve_assignment_display_title(assigned_form, template_name: str | None = None) -> str:
    """Assignment label: custom name when set, otherwise template name and period."""
    if assigned_form is not None:
        try:
            title = assigned_form.display_name
            if title and str(title).strip():
                return str(title).strip()
        except Exception:
            pass
    if template_name:
        period_name = getattr(assigned_form, 'period_name', None) if assigned_form else None
        if period_name:
            return f"{template_name} \u2013 {period_name}"
        return template_name
    return "this assignment"


def notify_assignment_submitted(assignment_entity_status):
    """Notify focal points and admins when an assignment is submitted for any entity type."""
    aes = assignment_entity_status
    entity_type = aes.entity_type
    entity_id = aes.entity_id

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

    submitter_name = _resolve_assignment_submitter_name(aes)
    submitter_user_id = getattr(aes, 'submitted_by_user_id', None)
    if submitter_user_id is None and current_user and current_user.is_authenticated:
        submitter_user_id = current_user.id

    assignment_title = _resolve_assignment_display_title(assigned_form, template_name)
    entity_name = _resolve_entity_name(entity_type, entity_id)
    related_url = url_for('forms.view_edit_form', form_type='assignment', form_id=aes.id)

    focal_notifications = []
    if audience_bucket_enabled(NotificationType.assignment_submitted, "focal_points"):
        focal_point_ids = get_assignment_editor_submitter_user_ids_for_entity(entity_type, entity_id)
        if focal_point_ids:
            common_notification_kwargs = {
                'entity_type': entity_type,
                'entity_id': entity_id,
                'notification_type': NotificationType.assignment_submitted,
                'related_object_type': 'assignment',
                'related_object_id': aes.id,
                'related_url': related_url,
                'priority': 'normal',
                'send_email_notifications': False,
            }
            stored_params = {
                'assignment_title': assignment_title,
                'submitter_name': submitter_name,
                'country': entity_name,
                'template': template_name,
                'period': assigned_form.period_name,
                '_entity_type': entity_type,
                '_entity_id': entity_id,
            }

            if submitter_user_id and submitter_user_id in focal_point_ids:
                focal_notifications.extend(create_notification(
                    user_ids=[submitter_user_id],
                    title_key='notification.assignment_submitted.submitter.title',
                    title_params={'assignment_title': assignment_title},
                    message_key='notification.assignment_submitted.submitter.message',
                    message_params=dict(stored_params),
                    **common_notification_kwargs,
                ) or [])

            peer_ids = [uid for uid in focal_point_ids if uid != submitter_user_id]
            if peer_ids:
                focal_notifications.extend(create_notification(
                    user_ids=peer_ids,
                    title_key='notification.assignment_submitted.title',
                    title_params={'assignment_title': assignment_title},
                    message_key='notification.assignment_submitted.message',
                    message_params=dict(stored_params),
                    **common_notification_kwargs,
                ) or [])

            from app.services.notification.emails import send_assignment_submitted_team_email

            notification_by_user_id = {n.user_id: n for n in focal_notifications}
            send_assignment_submitted_team_email(
                user_ids=focal_point_ids,
                assignment_title=assignment_title,
                submitter_name=submitter_name,
                related_url=related_url,
                notification_by_user_id=notification_by_user_id,
            )


    secondary_recipients = resolve_submission_review_recipient_user_ids(
        aes,
        exclude_user_ids=[submitter_user_id] if submitter_user_id else None,
    )
    if secondary_recipients and not audience_bucket_enabled(
        NotificationType.assignment_submitted, "admin_users"
    ):
        secondary_recipients = []

    if secondary_recipients:
        admin_notifications = create_notification(
            user_ids=secondary_recipients,
            notification_type=NotificationType.assignment_submitted,
            title_key='notification.assignment_submitted.admin.title',
            title_params={
                'submitter_name': submitter_name,
                'assignment_title': assignment_title,
                'period': assigned_form.period_name,
            },
            message_key='notification.assignment_submitted.admin.message',
            message_params={
                'template': template_name,
                'assignment_title': assignment_title,
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
            related_url=related_url,
            priority='high',
            override_email_preferences=True  # Always email admins for action-required review
        )
    else:
        admin_notifications = []

    return focal_notifications + (admin_notifications or [])


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

    template = FormTemplate.query.get(assigned_form.template_id) if assigned_form and assigned_form.template_id else None
    template_name = template.name if template else "Unknown Template"

    if assigned_form and (assigned_form.period_name or "").startswith("[LOADTEST]"):
        return []

    entity_name = _resolve_entity_name(entity_type, entity_id)
    assignment_title = _resolve_assignment_display_title(assigned_form, template_name)

    submitter_name = (
        current_user.name
        if (current_user and current_user.is_authenticated and current_user.name)
        else "A National Society focal point"
    )
    submitter_user_id = getattr(aes, 'submitted_by_user_id', None)
    if submitter_user_id is None and current_user and current_user.is_authenticated:
        submitter_user_id = current_user.id

    message_params = _build_assignment_notification_params(
        aes, assigned_form, template_name
    )
    message_params['submitter_name'] = submitter_name
    if submitter_user_id is not None:
        message_params['_actor_user_id'] = submitter_user_id
    title_params = {
        'assignment_title': assignment_title,
        'country': entity_name,
    }

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
            title_params=title_params,
            message_key='notification.assignment_sent_for_review.message',
            message_params=dict(message_params),
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
            title_params=title_params,
            message_key='notification.assignment_sent_for_review.admin.message',
            message_params=dict(message_params),
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

    actor_name = _resolve_current_actor_name(fallback="Delegation reviewer")
    actor_user_id = _resolve_current_actor_user_id()
    message_params = _build_assignment_notification_params(
        aes,
        assigned_form,
        template_name,
        actor_name=actor_name,
        actor_user_id=actor_user_id,
    )
    title_params = {
        'assignment_title': message_params['assignment_title'],
        'country': message_params['country'],
    }

    return create_notification(
        user_ids=ns_focal_ids,
        notification_type=NotificationType.assignment_returned_for_revision,
        title_key='notification.assignment_returned_for_revision.title',
        title_params=title_params,
        message_key='notification.assignment_returned_for_revision.message',
        message_params=message_params,
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

    actor_name = _resolve_approved_by_name(aes)
    actor_user_id = getattr(aes, 'approved_by_user_id', None) or _resolve_current_actor_user_id()
    message_params = _build_assignment_notification_params(
        aes,
        assigned_form,
        template_name,
        actor_name=actor_name,
        actor_user_id=actor_user_id,
    )
    title_params = {'assignment_title': message_params['assignment_title']}

    # Create notifications for focal points using translation keys
    return notify_entity_focal_points(
        entity_type=entity_type,
        entity_id=entity_id,
        notification_type=NotificationType.assignment_approved,
        title_key='notification.assignment_approved.title',
        title_params=title_params,
        message_key='notification.assignment_approved.message',
        message_params=message_params,
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

    actor_name = _resolve_current_actor_name(fallback="An administrator")
    actor_user_id = _resolve_current_actor_user_id()
    message_params = _build_assignment_notification_params(
        aes,
        assigned_form,
        template_name,
        actor_name=actor_name,
        actor_user_id=actor_user_id,
    )
    title_params = {'assignment_title': message_params['assignment_title']}

    # Create notifications for focal points using translation keys
    notifications = notify_entity_focal_points(
        entity_type=entity_type,
        entity_id=entity_id,
        notification_type=NotificationType.assignment_reopened,
        title_key='notification.assignment_reopened.title',
        title_params=title_params,
        message_key='notification.assignment_reopened.message',
        message_params=message_params,
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

    message_params = _build_assignment_notification_params(aes, assigned_form, template_name)
    title_params = {'assignment_title': message_params['assignment_title']}

    # Create notifications for focal points using translation keys
    return notify_entity_focal_points(
        entity_type=entity_type,
        entity_id=entity_id,
        notification_type=NotificationType.self_report_created,
        title_key='notification.self_report_created.title',
        title_params=title_params,
        message_key='notification.self_report_created.message',
        message_params=message_params,
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

