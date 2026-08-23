"""
Helpers to align session-list “activity” counts with the default audit-trail drill-down.

The legacy ``UserSessionLog.actions_performed`` counter can diverge (e.g. historical
mobile per-request increments). For admin session grids we count
``UserActivityLog`` + ``AdminActionLog`` rows using the same exclusions and session
window as ``/admin/analytics/audit-trail?session_id=…`` (default view: no page_view).
Login and logout are recorded for ``/admin/analytics/login-logs`` but omitted from the
audit trail and session activity counts.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import and_, or_

from app.models import AdminActionLog, User, UserActivityLog, UserSessionLog
from app.utils.activity_logging_skip import (
    SKIP_ACTIVITY_ENDPOINTS,
    SKIP_ACTIVITY_ENDPOINT_SUFFIXES,
    SKIP_AUTOMATIC_ACTIVITY_ENDPOINTS,
)
from app.utils.datetime_helpers import ensure_utc, utcnow


def _session_audit_scope(session_log: UserSessionLog) -> dict[str, Any] | None:
    """Window and identifiers for audit-trail-aligned counts, or None to use actions_performed."""
    session_id_param = (session_log.session_id or '').strip()
    if not session_id_param or session_log.session_start is None:
        return None

    session_start_for_filter = ensure_utc(session_log.session_start)
    session_end_for_filter = (
        ensure_utc(session_log.session_end) if session_log.session_end else utcnow()
    )
    if session_end_for_filter < session_start_for_filter:
        session_end_for_filter = utcnow()

    return {
        'session_log_id': session_log.id,
        'session_id': session_id_param,
        'user_id': session_log.user_id,
        'date_from': session_start_for_filter - timedelta(seconds=1),
        'session_start': session_start_for_filter,
        'session_end': session_end_for_filter,
    }


def _activity_row_matches_scope(row, scope: dict[str, Any]) -> bool:
    ts = ensure_utc(row.timestamp)
    if ts < scope['date_from'] or ts > scope['session_end']:
        return False
    if row.user_session_id == scope['session_id']:
        return True
    if row.user_session_id is None and row.user_id == scope['user_id']:
        return scope['session_start'] <= ts <= scope['session_end']
    return False


def _admin_row_matches_scope(row, scope: dict[str, Any]) -> bool:
    if row.admin_user_id != scope['user_id']:
        return False
    ts = ensure_utc(row.timestamp)
    return scope['date_from'] <= ts <= scope['session_end']

# Auth events live on Login Logs; do not surface them in the unified audit trail.
AUDIT_TRAIL_EXCLUDED_ACTIVITY_TYPES = ('login', 'logout')

# Hidden unless the reviewer explicitly filters for them (same idea as page_view).
AUDIT_TRAIL_DEFAULT_HIDDEN_ACTIVITY_TYPES = ('page_view', 'form_saved', 'form_save')


def apply_audit_trail_user_activity_noise_filters(activity_query):
    """
    Endpoint / type exclusions shared by audit trail UserActivityLog queries.
    Keep in sync with ``analytics.audit_trail``.
    """
    suffix_noise = or_(
        *[
            UserActivityLog.endpoint.like(
                f"%.{suffix.replace('_', r'\_')}",
                escape="\\",
            )
            for suffix in sorted(SKIP_ACTIVITY_ENDPOINT_SUFFIXES)
        ]
    )
    return (
        activity_query.filter(
            ~UserActivityLog.activity_type.in_(AUDIT_TRAIL_EXCLUDED_ACTIVITY_TYPES)
        )
        .filter(
            ~(
                (UserActivityLog.activity_type == 'presence_heartbeat')
                | UserActivityLog.endpoint.in_(tuple(SKIP_ACTIVITY_ENDPOINTS))
                | (
                    UserActivityLog.endpoint.in_(tuple(SKIP_AUTOMATIC_ACTIVITY_ENDPOINTS))
                    & (UserActivityLog.activity_type != "profile_update")
                )
                | suffix_noise
            )
        )
        .filter(~(UserActivityLog.activity_type == 'api_usage'))
        .filter(
            ~(
                (UserActivityLog.endpoint.ilike('/api/ai/documents/workflows%'))
                | (
                    UserActivityLog.url_path.isnot(None)
                    & UserActivityLog.url_path.ilike('/api/ai/documents/workflows%')
                )
            )
        )
        .filter(
            ~(
                (UserActivityLog.endpoint.ilike('/api/forms/lookup-lists/reporting_currency/options%'))
                | (
                    UserActivityLog.url_path.isnot(None)
                    & UserActivityLog.url_path.ilike('/api/forms/lookup-lists/reporting_currency/options%')
                )
            )
        )
    )


def count_audit_visible_entries_for_sessions(
    session_logs: list[UserSessionLog],
) -> dict[int, int]:
    """
    Batch audit-trail-aligned activity counts keyed by ``UserSessionLog.id``.

    Uses two queries per page instead of two per session. Matching rules mirror
    ``count_audit_visible_entries_for_session``.
    """
    counts: dict[int, int] = {}
    scopes: list[dict[str, Any]] = []

    for session_log in session_logs:
        if session_log is None:
            continue
        session_log_id = session_log.id
        scope = _session_audit_scope(session_log)
        if scope is None:
            counts[session_log_id] = int(session_log.actions_performed or 0)
            continue
        scopes.append(scope)
        counts[session_log_id] = 0

    if not scopes:
        return counts

    global_min = min(scope['date_from'] for scope in scopes)
    global_max = max(scope['session_end'] for scope in scopes)
    session_ids = [scope['session_id'] for scope in scopes]
    user_ids = list({scope['user_id'] for scope in scopes})

    activity_query = (
        UserActivityLog.query.filter(UserActivityLog.timestamp >= global_min)
        .filter(UserActivityLog.timestamp <= global_max)
        .filter(~UserActivityLog.activity_type.in_(AUDIT_TRAIL_DEFAULT_HIDDEN_ACTIVITY_TYPES))
        .filter(
            or_(
                UserActivityLog.user_session_id.in_(session_ids),
                and_(
                    UserActivityLog.user_session_id.is_(None),
                    UserActivityLog.user_id.in_(user_ids),
                ),
            )
        )
    )
    activity_query = apply_audit_trail_user_activity_noise_filters(activity_query)
    activity_rows = activity_query.with_entities(
        UserActivityLog.user_session_id,
        UserActivityLog.user_id,
        UserActivityLog.timestamp,
    ).all()

    admin_rows = (
        AdminActionLog.query.filter(AdminActionLog.timestamp >= global_min)
        .filter(AdminActionLog.timestamp <= global_max)
        .filter(AdminActionLog.admin_user_id.in_(user_ids))
        .with_entities(
            AdminActionLog.admin_user_id,
            AdminActionLog.timestamp,
        )
        .all()
    )

    for row in activity_rows:
        for scope in scopes:
            if _activity_row_matches_scope(row, scope):
                counts[scope['session_log_id']] += 1

    for row in admin_rows:
        for scope in scopes:
            if _admin_row_matches_scope(row, scope):
                counts[scope['session_log_id']] += 1

    return counts


def count_audit_visible_entries_for_session(session_log: UserSessionLog) -> int:
    """
    Rows that match audit trail default session scope (excludes ``page_view`` and
    login/logout at SQL), same window and noise rules as opening audit from session logs.

    Admin actions are included when ``admin_user_id`` matches the session user and
    timestamps fall in the session window (same as audit merge).
    """
    if session_log is None:
        return 0
    scope = _session_audit_scope(session_log)
    if scope is None:
        return int(session_log.actions_performed or 0)
    return count_audit_visible_entries_for_sessions([session_log]).get(
        session_log.id,
        int(session_log.actions_performed or 0),
    )
