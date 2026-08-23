"""Server-side payload for audit trail page JSON bootstrap (no Jinja in static JS)."""
from __future__ import annotations

from typing import Any

from app.utils.datetime_helpers import ensure_utc


def _iso_datetime(dt: Any) -> str:
    if not dt:
        return ''
    try:
        dt_utc = ensure_utc(dt)
        if dt_utc:
            return dt_utc.isoformat()
        return dt.isoformat() if hasattr(dt, 'isoformat') else str(dt)
    except Exception:
        return ''


def _humanize_activity_label(value: str) -> str:
    from app.utils.audit_trail_labels import activity_type_display_label

    return activity_type_display_label(value)


def build_audit_trail_grid_rows(entries: list[dict]) -> list[dict]:
    rows = []
    for entry in entries:
        user = entry.get('user')
        rows.append({
            'id': entry.get('id'),
            'timestamp': _iso_datetime(entry.get('timestamp')),
            'user_id': user.id if user else None,
            'user_name': (user.name or user.email) if user else '',
            'user_email': user.email if user else '',
            'user_title': (user.title or '') if user else '',
            'user_active': user.active if user else True,
            'user_profile_color': (user.profile_color or '') if user and user.profile_color else '',
            'entity_type': entry.get('entity_type', '') or '',
            'entity_name': entry.get('entity_name', '') or '',
            'activity_type': entry.get('consolidated_activity_type', '') or '',
            'description': (entry.get('consistent_description') or entry.get('description', '')) or '',
            'details': entry.get('details'),
            'endpoint': entry.get('endpoint', '') or '',
            'http_method': entry.get('http_method', '') or '',
            'risk_level': entry.get('risk_level', '') or '',
            'ip_address': entry.get('ip_address', '') or '',
            'type': entry.get('type', '') or '',
            'action_type': entry.get('action_type') or '',
            'requires_review': bool(entry.get('requires_review', False)),
            'response_status_code': entry.get('response_status_code'),
            'user_session_id': entry.get('user_session_id') or '',
        })
    return rows


def build_audit_trail_multiselect_data(
    *,
    users,
    countries,
    activity_types: list,
    action_types: list | None,
    recent_session_logs,
    filters: dict,
) -> dict:
    user_items = []
    for user in users:
        item = {
            'value': user.email,
            'label': user.name or user.email,
        }
        if user.name:
            item['sublabel'] = user.email
        user_items.append(item)

    country_items = [{'value': str(c.id), 'label': c.name} for c in countries]
    selected_countries = filters.get('country')
    if selected_countries:
        selected_country_values = [str(v) for v in selected_countries]
    else:
        selected_country_values = [str(c.id) for c in countries]

    activity_items = [
        {'value': v, 'label': _humanize_activity_label(v)} for v in activity_types
    ]
    if action_types:
        for v in action_types:
            activity_items.append({'value': v, 'label': _humanize_activity_label(v)})

    seen = set()
    unique_activity = []
    for item in activity_items:
        if not item.get('value') or item['value'] in seen:
            continue
        seen.add(item['value'])
        unique_activity.append(item)

    if filters.get('activity_type'):
        selected_activity = list(filters['activity_type'])
    else:
        from app.services.audit.trail_session_query import (
            AUDIT_TRAIL_DEFAULT_HIDDEN_ACTIVITY_TYPES,
        )

        selected_activity = [
            item['value']
            for item in unique_activity
            if item['value'] not in AUDIT_TRAIL_DEFAULT_HIDDEN_ACTIVITY_TYPES
        ]

    if filters.get('risk_level'):
        selected_risk = list(filters['risk_level'])
    else:
        selected_risk = ['low', 'medium', 'high', 'critical']

    session_items = []
    for s in recent_session_logs:
        email = s.user.email if s.user and s.user.email else '—'
        label = f'#{s.id} — {email}'
        sublabel = _iso_datetime(s.session_start)
        session_items.append({
            'value': str(s.id),
            'label': label,
            'sublabel': sublabel,
        })

    selected_session = []
    if filters.get('session_id'):
        selected_session = [str(filters['session_id'])]

    return {
        'users': user_items,
        'selectedUsers': list(filters.get('user') or []),
        'countries': country_items,
        'selectedCountries': selected_country_values,
        'activityTypes': unique_activity,
        'selectedActivityTypes': selected_activity,
        'selectedRiskLevels': selected_risk,
        'requiresReviewSelected': ['1'] if filters.get('requires_review') else [],
        'sessionLogs': session_items,
        'selectedSessionLogIds': selected_session,
    }
