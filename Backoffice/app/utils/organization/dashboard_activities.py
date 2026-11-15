"""Recent-activity payload for the dashboard API.

The web dashboard renders the same country feed in
``core/dashboard/_admin_panel.html``. This module turns those activity rows
into the JSON the mobile dashboard shows: who changed what, on which
assignment, with the same summaries the back office already localizes.
"""

from __future__ import annotations

import re
from html import unescape

from flask import current_app

from app.utils.common.datetime_helpers import ensure_utc

# Same first page as ``main.dashboard`` (then "Load more").
DASHBOARD_RECENT_ACTIVITIES_PAGE_SIZE = 10
DASHBOARD_RECENT_ACTIVITIES_MAX_PAGE_SIZE = 50

_BR_RE = re.compile(r'(?i)<br\s*/?>')
_TAG_RE = re.compile(r'<[^>]+>')


def load_dashboard_recent_activities(entity_type, entity_id, *, offset=0, limit=None):
    """Activities for the country an entity belongs to.

    Returns ``(page, has_more)``. ``page`` is a list of JSON-ready dicts.
    An entity with no country, or a failed lookup, yields an empty page.
    """
    from app.routes.main.helpers import (
        enrich_dashboard_recent_activities,
        filter_dashboard_assignment_activities,
    )
    from app.services.notification.core import get_country_recent_activities
    from app.services.organization.entity_service import EntityService

    try:
        offset = max(0, int(offset or 0))
    except (TypeError, ValueError):
        offset = 0
    try:
        limit = int(limit if limit is not None else DASHBOARD_RECENT_ACTIVITIES_PAGE_SIZE)
    except (TypeError, ValueError):
        limit = DASHBOARD_RECENT_ACTIVITIES_PAGE_SIZE
    limit = max(1, min(limit, DASHBOARD_RECENT_ACTIVITIES_MAX_PAGE_SIZE))

    country = EntityService.get_country_for_entity(entity_type, entity_id)
    if country is None:
        return [], False

    # One extra row so a full page can tell the client there is more,
    # matching ``load_more_activities`` on the web dashboard.
    fetch_limit = offset + limit + 1
    activities = filter_dashboard_assignment_activities(
        get_country_recent_activities(
            country_id=country.id,
            days=None,
            limit=fetch_limit,
        )
    )
    try:
        enrich_dashboard_recent_activities(activities)
    except Exception as exc:
        current_app.logger.debug(
            "Could not enrich dashboard activities for %s:%s: %s",
            entity_type,
            entity_id,
            exc,
        )

    page = activities[offset:offset + limit] if offset < len(activities) else []
    has_more = len(activities) >= fetch_limit
    return [serialize_dashboard_activity(activity) for activity in page], has_more


def serialize_dashboard_activity(activity) -> dict:
    """One activity card: user, assignment, localized summary, and field lines."""
    params = getattr(activity, 'summary_params', None)
    if not isinstance(params, dict):
        params = {}

    summary_key = getattr(activity, 'summary_key', None)
    assignment_id = getattr(activity, 'assignment_id', None)
    title = _first_text(
        params.get('assignment_title'),
        params.get('template'),
        params.get('template_period'),
    )
    template_period = _first_text(params.get('template_period'), title)

    changes = []
    if summary_key == 'activity.form_data_updated.multiple':
        for change in params.get('changes') or []:
            if not isinstance(change, dict):
                continue
            text = _format_field_change(change, assignment_id)
            if not text:
                continue
            changes.append({
                'change_type': _change_type(change.get('change_type')),
                'text': text,
            })
        summary = _summary_text(activity)
    elif summary_key == 'activity.form_data_updated.single':
        summary = '' if params.get('_suppress_matrix_display') else _format_field_change(
            params, assignment_id,
        )
    else:
        summary = _summary_text(activity)

    timestamp = ensure_utc(getattr(activity, 'timestamp', None))
    return {
        'id': getattr(activity, 'id', None),
        'timestamp': timestamp.isoformat() if timestamp is not None else None,
        'user': _user_payload(getattr(activity, 'user', None)),
        'assignment_id': assignment_id,
        'assignment_title': title,
        'template_period': template_period,
        'summary_key': summary_key,
        'change_type': _change_type(params.get('change_type')) if summary_key == 'activity.form_data_updated.single' else None,
        'change_count': _change_count(params) if summary_key == 'activity.form_data_updated.multiple' else None,
        'summary': summary,
        'changes': changes,
    }


def _summary_text(activity) -> str:
    from app.routes.main.helpers import render_activity_summary

    try:
        return _html_to_text(render_activity_summary(activity))
    except Exception as exc:
        current_app.logger.debug(
            "Could not render activity summary %s: %s",
            getattr(activity, 'id', None),
            exc,
        )
        return ''


def _format_field_change(change, assignment_id) -> str:
    """Plain-text field line, including matrix diffs the web draws as HTML."""
    from app.routes.main.helpers import (
        format_activity_value,
        localized_field_name,
        render_matrix_change,
    )
    from app.utils.forms.matrix_activity import is_matrix_activity_payload

    if not isinstance(change, dict):
        return ''

    field_id = change.get('field_id')
    try:
        label = localized_field_name(
            field_id,
            fallback_name=change.get('field'),
            field_id_kind=change.get('field_id_kind'),
            assignment_id=assignment_id,
        )
    except Exception as exc:
        current_app.logger.debug("Activity field label failed: %s", exc)
        label = change.get('field') or ''

    old_val = change.get('old')
    new_val = change.get('new')
    change_type = _change_type(change.get('change_type'))
    if is_matrix_activity_payload(old_val, new_val):
        try:
            return _html_to_text(render_matrix_change(
                label,
                old_val if isinstance(old_val, dict) else {},
                new_val if isinstance(new_val, dict) else {},
                field_id,
            ))
        except Exception as exc:
            current_app.logger.debug("Activity matrix summary failed: %s", exc)
            return ''

    old_s = _html_to_text(format_activity_value(old_val, field_id))
    new_s = _html_to_text(format_activity_value(new_val, field_id))
    if change_type == 'added':
        body = new_s
    elif change_type == 'removed':
        body = old_s
    else:
        body = f'{old_s} → {new_s}' if (old_s or new_s) else ''

    label = str(label or '').strip()
    if label and body:
        return f'{label}: {body}'
    return label or body


def _user_payload(user):
    if user is None:
        return None
    name = _first_text(getattr(user, 'name', None))
    title = _first_text(getattr(user, 'title', None))
    email = getattr(user, 'email', None) or ''
    return {
        'id': getattr(user, 'id', None),
        'name': name,
        'email': email,
        'title': title,
    }


def _change_type(value) -> str:
    text = str(value or 'updated').strip().lower()
    if text in ('added', 'removed', 'updated'):
        return text
    return 'updated'


def _change_count(params):
    try:
        return int(params.get('count'))
    except (TypeError, ValueError):
        return None


def _first_text(*values):
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _html_to_text(value) -> str:
    """Drop the tags ``render_matrix_change`` emits and keep the words."""
    text = '' if value is None else str(value)
    text = text.replace('&rarr;', '→').replace('&nbsp;', ' ')
    text = _BR_RE.sub('\n', text)
    text = _TAG_RE.sub('', text)
    lines = [unescape(line).strip() for line in text.splitlines()]
    return '\n'.join(line for line in lines if line).strip()
