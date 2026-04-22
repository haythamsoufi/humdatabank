"""
Helpers to align session-list “activity” counts with the default audit-trail drill-down.

The legacy ``UserSessionLog.actions_performed`` counter can diverge (e.g. historical
mobile per-request increments). For admin session grids we count
``UserActivityLog`` + ``AdminActionLog`` rows using the same exclusions and session
window as ``/admin/analytics/audit-trail?session_id=…`` (default view: no page_view).
Login and logout rows are omitted from this count only; they remain in the audit trail.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import and_, or_

from app.models import AdminActionLog, User, UserActivityLog, UserSessionLog
from app.utils.datetime_helpers import ensure_utc, utcnow


def apply_audit_trail_user_activity_noise_filters(activity_query):
    """
    Endpoint / type exclusions shared by audit trail UserActivityLog queries.
    Keep in sync with ``analytics.audit_trail``.
    """
    return (
        activity_query.filter(
            ~(
                (UserActivityLog.activity_type == 'presence_heartbeat')
                | (UserActivityLog.endpoint == 'forms_api.api_presence_heartbeat')
                | (
                    UserActivityLog.endpoint.in_(
                        (
                            'mobile_api.device_heartbeat',
                            'notifications.device_heartbeat',
                            'admin_analytics_api.session_logs_list_api',
                            'admin_analytics_api.login_logs_list_api',
                            'user_management.api_users_profile_summary',
                            'main.api_users_profile_summary',
                            'forms_api.api_presence_active_users',
                            'utilities.refresh_csrf_token',
                            'utilities.refresh_csrf_token_get',
                            'forms_api.api_search_indicator_bank',
                            'forms_api.get_lookup_list_options',
                            'forms_api.get_lookup_list_config_ui',
                            'forms_api.api_render_dynamic_indicator',
                            'user_management.get_user_entities',
                            'user_management.get_ns_hierarchy',
                            'user_management.get_secretariat_hierarchy',
                            'user_management.get_secretariat_regions_hierarchy',
                            'ai_v2.chat',
                            'ai_v2.issue_token',
                            'ai_documents.list_ifrc_api_documents',
                            'ai_documents.list_ifrc_api_types',
                            'ai_ws',
                            'ai_management.list_system_documents',
                            'settings.api_check_updates',
                            'utilities.api_translation_services',
                        )
                    )
                )
            )
        )
        .filter(~(UserActivityLog.activity_type == 'api_usage'))
        .filter(
            ~(
                (UserActivityLog.endpoint.ilike('/api/ai/documents/workflows%'))
                | (UserActivityLog.url_path.ilike('/api/ai/documents/workflows%'))
            )
        )
        .filter(
            ~(
                (UserActivityLog.endpoint.ilike('/api/forms/lookup-lists/reporting_currency/options%'))
                | (UserActivityLog.url_path.ilike('/api/forms/lookup-lists/reporting_currency/options%'))
            )
        )
        .filter(~(UserActivityLog.endpoint == 'forms.search_matrix_rows'))
        .filter(
            ~(
                (UserActivityLog.endpoint == 'notifications.mark_notifications_read')
                | (UserActivityLog.endpoint == 'main.mark_notifications_read')
            )
        )
    )


def count_audit_visible_entries_for_session(session_log: UserSessionLog) -> int:
    """
    Rows that match audit trail default session scope (excludes ``page_view`` at SQL),
    same window and noise rules as opening audit from session logs. Unlike the audit
    grid, ``login`` and ``logout`` activity types are not counted so session “activities”
    reflect post-auth work only.

    Admin actions are included when ``admin_user_id`` matches the session user and
    timestamps fall in the session window (same as audit merge).
    """
    if session_log is None:
        return 0
    session_id_param = (session_log.session_id or '').strip()
    if not session_id_param or session_log.session_start is None:
        return int(session_log.actions_performed or 0)

    session_start_for_filter = ensure_utc(session_log.session_start)
    session_end_for_filter = (
        ensure_utc(session_log.session_end) if session_log.session_end else utcnow()
    )
    if session_end_for_filter < session_start_for_filter:
        session_end_for_filter = utcnow()

    date_from_dt = session_start_for_filter - timedelta(seconds=1)

    activity_query = (
        UserActivityLog.query.join(User)
        .filter(UserActivityLog.timestamp >= date_from_dt)
        .filter(UserActivityLog.timestamp <= session_end_for_filter)
        .filter(
            or_(
                UserActivityLog.user_session_id == session_id_param,
                and_(
                    UserActivityLog.user_session_id.is_(None),
                    UserActivityLog.user_id == session_log.user_id,
                    UserActivityLog.timestamp >= session_start_for_filter,
                    UserActivityLog.timestamp <= session_end_for_filter,
                ),
            )
        )
    )
    activity_query = apply_audit_trail_user_activity_noise_filters(activity_query)
    activity_query = activity_query.filter(UserActivityLog.activity_type != 'page_view')
    activity_query = activity_query.filter(
        ~UserActivityLog.activity_type.in_(('login', 'logout'))
    )

    n_activity = activity_query.count()

    admin_query = (
        AdminActionLog.query.join(User)
        .filter(AdminActionLog.timestamp >= date_from_dt)
        .filter(AdminActionLog.timestamp <= session_end_for_filter)
        .filter(AdminActionLog.admin_user_id == session_log.user_id)
    )
    n_admin = admin_query.count()

    return int(n_activity + n_admin)
