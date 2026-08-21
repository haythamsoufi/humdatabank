"""Typed notification helpers for admin and user onboarding events."""

from flask import url_for, current_app
from app.models import NotificationType, User, Country
from app.services.notification.audience import collect_entity_admin_audience_recipient_ids
from app.services.notification.creation import create_notification
from app.services.notification.core import log_entity_activity, notify_entity_focal_points

# Safety cap so a very large batch still produces a short, readable message/email
# instead of listing hundreds of country names.
_MAX_COUNTRIES_LISTED_IN_MESSAGE = 15


def _format_country_names_for_message(names):
    """Comma-joined country names, capped with a '(+N more)' suffix for large batches."""
    if len(names) <= _MAX_COUNTRIES_LISTED_IN_MESSAGE:
        return ', '.join(names)
    shown = names[:_MAX_COUNTRIES_LISTED_IN_MESSAGE]
    remaining = len(names) - len(shown)
    return f"{', '.join(shown)} (+{remaining} more)"


def notify_user_added_to_country(user_id, country_id):
    """Notify user when they are added as a focal point to a country."""
    try:
        user = User.query.get(user_id)
        country = Country.query.get(country_id)

        if not user or not country:
            current_app.logger.warning(f"Cannot notify user {user_id} about country {country_id}: user or country not found")
            return []

        # English fallback stored in params; localized at display time via entity_id.
        country_name = country.name

        # Create notification for the user using translation keys
        return create_notification(
            user_ids=[user_id],
            notification_type=NotificationType.user_added_to_country,
            title_key='notification.user_added_to_country.title',
            title_params=None,
            message_key='notification.user_added_to_country.message',
            message_params={
                'country': country_name
            },
        entity_type='country',
        entity_id=country_id,
            related_object_type='country',
            related_object_id=country_id,
            related_url=url_for('main.dashboard'),
            priority='high',  # High priority so email is sent even if user has digest preferences
            icon='fas fa-user-plus'
        )
    except Exception as e:
        current_app.logger.error(f"Error notifying user {user_id} about being added to country {country_id}: {str(e)}", exc_info=True)
        return []


def notify_user_added_to_countries(user_id, country_ids):
    """
    Notify a user once about being added as a focal point to one or more countries.

    Bulk approval flows (e.g. "approve all pending requests") used to call
    notify_user_added_to_country() once per country, which meant one notification
    row AND one instant email per country — a burst of 10+ near-simultaneous emails
    to the same recipient during a single admin action (see the 2026-08-11 incident
    where a 10-country bulk approval produced 10 failed instant-email sends).
    This combines an entire batch into a single notification/email.

    Falls back to the exact single-country message when only one id is given, so
    callers can use this unconditionally regardless of batch size.
    """
    try:
        unique_country_ids = list(dict.fromkeys(
            int(cid) for cid in (country_ids or []) if cid is not None
        ))
        if not unique_country_ids:
            return []

        user = User.query.get(user_id)
        if not user:
            current_app.logger.warning(
                f"Cannot notify user {user_id} about countries {unique_country_ids}: user not found"
            )
            return []

        countries = Country.query.filter(Country.id.in_(unique_country_ids)).all()
        if not countries:
            current_app.logger.warning(
                f"Cannot notify user {user_id} about countries {unique_country_ids}: no matching countries found"
            )
            return []

        if len(countries) == 1:
            return create_notification(
                user_ids=[user_id],
                notification_type=NotificationType.user_added_to_country,
                title_key='notification.user_added_to_country.title',
                title_params=None,
                message_key='notification.user_added_to_country.message',
                message_params={'country': countries[0].name},
                entity_type='country',
                entity_id=countries[0].id,
                related_object_type='country',
                related_object_id=countries[0].id,
                related_url=url_for('main.dashboard'),
                priority='high',
                icon='fas fa-user-plus'
            )

        country_names = sorted(c.name for c in countries)
        return create_notification(
            user_ids=[user_id],
            notification_type=NotificationType.user_added_to_country,
            title_key='notification.user_added_to_country.title_bulk',
            title_params={'country_count': len(country_names)},
            message_key='notification.user_added_to_country.message_bulk',
            message_params={
                'country_count': len(country_names),
                'countries': _format_country_names_for_message(country_names),
            },
            related_url=url_for('main.dashboard'),
            priority='high',  # High priority so one email is still sent even if user has digest preferences
            icon='fas fa-user-plus'
        )
    except Exception as e:
        current_app.logger.error(
            f"Error notifying user {user_id} about being added to countries {country_ids}: {str(e)}",
            exc_info=True
        )
        return []


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
        related_url=url_for('assignments.view_assignment', aes_id=aes.id),
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
        related_url=url_for('assignments.view_assignment', aes_id=aes.id),
        priority='normal'
    )


def notify_public_submission_received(public_submission):
    """Notify org admins and/or system managers when a public submission is received."""
    try:
        country_eid = public_submission.country_id
        if not country_eid:
            current_app.logger.debug("Public submission has no country — skipping admin notifications")
            return []

        admin_user_ids = collect_entity_admin_audience_recipient_ids(
            NotificationType.public_submission_received,
            "country",
            int(country_eid),
        )
        if not admin_user_ids:
            current_app.logger.debug("No recipients for public submission admin notification")
            return []

        from app.models.forms import FormTemplate

        template_name = 'Unknown Template'
        assignment_title = template_name
        country_name = 'Unknown Country'
        if public_submission.assigned_form and public_submission.assigned_form.template_id:
            template = FormTemplate.query.get(public_submission.assigned_form.template_id)
            if template:
                template_name = template.name
            try:
                assignment_title = public_submission.assigned_form.display_name or template_name
            except Exception:
                assignment_title = template_name
        if public_submission.country:
            country_name = public_submission.country.name

        # Create notifications for all admins
        return create_notification(
            user_ids=admin_user_ids,
            notification_type=NotificationType.public_submission_received,
            title_key='notification.public_submission_received.title',
            title_params=None,
            message_key='notification.public_submission_received.message',
            message_params={
                'template': template_name,
                'assignment_title': assignment_title,
                'country': country_name,
                'submitter': public_submission.submitter_name or public_submission.submitter_email or 'Unknown'
            },
        entity_type='country' if public_submission.country_id else None,
        entity_id=public_submission.country_id if public_submission.country_id else None,
            related_object_type='public_submission',
            related_object_id=public_submission.id,
            related_url=url_for('form_builder.manage_templates'),  # Could be enhanced to link to submission review page
            priority='normal',
            icon='fas fa-inbox'
        )
    except Exception as e:
        current_app.logger.error(f"Error notifying admins about public submission {public_submission.id}: {str(e)}", exc_info=True)
        return []

