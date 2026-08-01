"""
Shared query/serialization logic for admin and mobile analytics APIs.

Route modules should stay thin: call these helpers and wrap results with
json_ok / mobile_ok / mobile_paginated.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from contextlib import suppress
from flask import current_app
from sqlalchemy import and_, desc, inspect, or_
from sqlalchemy.orm import Query, joinedload

from app import db
from app.models import (
    AssignedForm,
    AssignmentEntityStatus,
    PublicSubmission,
    PublicSubmissionStatus,
    SecurityEvent,
    User,
    UserLoginLog,
    UserSessionLog,
)
from app.services import get_platform_stats
from app.services.audit.trail_session_query import (
    count_audit_visible_entries_for_session,
    count_audit_visible_entries_for_sessions,
)
from app.services.platform.user_analytics_service import (
    add_session_to_blacklist,
    bot_user_agent_explanation,
    effective_session_active_duration_minutes,
    effective_session_duration_minutes,
    end_user_session,
    session_log_device_icon_classes,
    user_session_log_active_duration_minutes_sql,
)
from app.utils.datetime_helpers import utcnow
from app.utils.page_view_paths import distinct_page_view_path_count
from app.utils.sql_utils import safe_ilike_pattern


def has_table(table_name: str) -> bool:
    """Safely check if a table exists in the database."""
    try:
        return inspect(db.engine).has_table(table_name)
    except Exception as e:
        current_app.logger.debug("has_table(%s) failed: %s", table_name, e)
        return False


def empty_pagination_payload(page: int = 1, per_page: int = 50) -> Dict[str, Any]:
    return {
        'items': [],
        'total': 0,
        'page': page,
        'per_page': per_page,
        'pages': 0,
    }


def parse_date_from(date_from: Optional[str]) -> Optional[datetime]:
    if not date_from:
        return None
    try:
        return datetime.strptime(date_from, '%Y-%m-%d')
    except ValueError:
        return None


def parse_date_to_exclusive(date_to: Optional[str]) -> Optional[datetime]:
    if not date_to:
        return None
    try:
        return datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
    except ValueError:
        return None


def login_log_risk_json(log: UserLoginLog) -> Optional[Dict[str, Any]]:
    """Serialize risk badge for failed logins (mirrors UserLoginLog.risk_level_display)."""
    if log.event_type != 'login_failed':
        return None
    rd = log.risk_level_display
    if not rd:
        return None
    return {
        'text': rd.text,
        'icon': rd.icon,
        'badge_class': getattr(rd, 'class', None) or 'bg-gray-100 text-gray-800',
    }


@dataclass(frozen=True)
class LoginLogsFilters:
    user: Optional[str] = None
    event_type: Optional[str] = None
    ip: Optional[str] = None
    suspicious_only: Optional[bool] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None


def build_login_logs_query(filters: LoginLogsFilters) -> Query:
    query = UserLoginLog.query.options(joinedload(UserLoginLog.user))

    if filters.user:
        query = query.filter(
            UserLoginLog.email_attempted.ilike(safe_ilike_pattern(filters.user))
        )
    if filters.event_type:
        query = query.filter(UserLoginLog.event_type == filters.event_type)
    if filters.ip:
        query = query.filter(UserLoginLog.ip_address == filters.ip)
    if filters.suspicious_only:
        query = query.filter(UserLoginLog.is_suspicious == True)  # noqa: E712

    date_from_dt = parse_date_from(filters.date_from)
    if date_from_dt is not None:
        query = query.filter(UserLoginLog.timestamp >= date_from_dt)

    date_to_dt = parse_date_to_exclusive(filters.date_to)
    if date_to_dt is not None:
        query = query.filter(UserLoginLog.timestamp < date_to_dt)

    return query.order_by(desc(UserLoginLog.timestamp))


def serialize_login_log(log: UserLoginLog, *, variant: str = 'admin') -> Dict[str, Any]:
    u = log.user
    user_payload = None
    if u is not None:
        user_payload = {
            'id': u.id,
            'name': u.name,
            'email': u.email,
        }

    ua = log.user_agent
    if ua and len(ua) > 500:
        ua = ua[:500] + '…'

    item: Dict[str, Any] = {
        'id': log.id,
        'timestamp': log.timestamp.isoformat(),
        'event_type': log.event_type,
        'email_attempted': log.email_attempted,
        'user': user_payload,
        'ip_address': log.ip_address,
        'location': log.location,
        'device_type': log.device_type,
        'operating_system': log.operating_system,
        'is_suspicious': bool(log.is_suspicious),
        'is_bot_detected': bool(log.is_bot_detected),
        'bot_detection_detail': bot_user_agent_explanation(log.user_agent)
        if log.is_bot_detected
        else None,
        'failure_reason': log.failure_reason,
        'failure_reason_display': log.failure_reason_display,
        'device_icon_classes': session_log_device_icon_classes(
            log.user_agent, log.device_type, log.operating_system
        ),
    }

    if variant == 'admin':
        item.update({
            'browser': log.browser,
            'browser_name': log.browser_name,
            'browser_version': log.browser_version,
            'device_name': log.device_name,
            'user_agent': ua,
            'referrer_url': log.referrer_url,
            'failed_attempts_count': log.failed_attempts_count,
            'risk': login_log_risk_json(log),
        })
    else:
        item['browser_name'] = log.browser_name

    return item


def paginate_login_logs(
    page: int,
    per_page: int,
    filters: LoginLogsFilters,
    *,
    variant: str = 'admin',
) -> Dict[str, Any]:
    if not has_table(UserLoginLog.__tablename__):
        return empty_pagination_payload(page=page, per_page=per_page)

    paginated = build_login_logs_query(filters).paginate(
        page=page, per_page=per_page, error_out=False
    )
    items = [serialize_login_log(log, variant=variant) for log in paginated.items]
    return {
        'items': items,
        'total': paginated.total,
        'page': paginated.page,
        'per_page': paginated.per_page,
        'pages': paginated.pages or 0,
    }


@dataclass(frozen=True)
class SessionLogsFilters:
    user: Optional[str] = None
    active_only: Optional[bool] = None
    min_duration: Optional[int] = None
    session_id: Optional[str] = None


def build_session_logs_query(filters: SessionLogsFilters) -> Query:
    """Shared filters for session log list APIs (HTML grid + mobile)."""
    session_id_exact = (filters.session_id or '').strip()

    query = UserSessionLog.query.options(joinedload(UserSessionLog.user)).join(User)

    if session_id_exact:
        query = query.filter(UserSessionLog.session_id == session_id_exact)

    if filters.user:
        query = query.filter(User.email.ilike(safe_ilike_pattern(filters.user)))

    if filters.active_only:
        query = query.filter(UserSessionLog.is_active == True)  # noqa: E712

    min_duration = filters.min_duration
    if min_duration is not None and min_duration > 0:
        cutoff = utcnow() - timedelta(minutes=min_duration)
        active_min_sql = user_session_log_active_duration_minutes_sql()
        min_parts = [
            UserSessionLog.duration_minutes >= min_duration,
            and_(
                UserSessionLog.is_active == True,  # noqa: E712
                UserSessionLog.session_start.isnot(None),
                UserSessionLog.session_start <= cutoff,
            ),
        ]
        if active_min_sql is not None:
            min_parts.append(active_min_sql >= min_duration)
        query = query.filter(or_(*min_parts))

    return query.order_by(desc(UserSessionLog.is_active), desc(UserSessionLog.session_start))


def serialize_session_log_list_item(
    session_log: UserSessionLog,
    activity_count: int,
    *,
    variant: str = 'admin',
) -> Dict[str, Any]:
    """JSON payload for one session row."""
    user = session_log.user
    user_payload = None
    if user is not None:
        user_payload = {
            'id': user.id,
            'name': user.name,
            'email': user.email,
        }

    page_views = session_log.page_views or 0
    distinct_paths = distinct_page_view_path_count(session_log)

    item: Dict[str, Any] = {
        'session_id': session_log.session_id,
        'session_start': session_log.session_start.isoformat() if session_log.session_start else None,
        'session_end': session_log.session_end.isoformat() if session_log.session_end else None,
        'last_activity': session_log.last_activity.isoformat() if session_log.last_activity else None,
        'duration_minutes': effective_session_duration_minutes(session_log),
        'active_duration_minutes': effective_session_active_duration_minutes(session_log),
        'page_views': page_views,
        'distinct_page_view_paths': distinct_paths,
        'activity_count': activity_count,
        'is_active': bool(session_log.is_active),
        'device_type': session_log.device_type,
        'browser': session_log.browser,
        'operating_system': session_log.operating_system,
        'ip_address': session_log.ip_address,
        'user': user_payload,
        'device_icon_classes': session_log_device_icon_classes(
            session_log.user_agent,
            session_log.device_type,
            session_log.operating_system,
        ),
    }

    if variant == 'admin':
        user_agent = session_log.user_agent
        if user_agent and len(user_agent) > 400:
            user_agent = user_agent[:400] + '…'
        item.update({
            'session_log_id': session_log.id,
            'has_path_breakdown': page_views > 0 or distinct_paths > 0,
            'user_agent': user_agent,
        })
    else:
        pvc = (
            session_log.page_view_path_counts
            if isinstance(session_log.page_view_path_counts, dict)
            else {}
        )
        item['page_view_path_counts'] = pvc

    return item


def paginate_session_logs(
    page: int,
    per_page: int,
    filters: SessionLogsFilters,
    *,
    variant: str = 'admin',
) -> Dict[str, Any]:
    if not has_table(UserSessionLog.__tablename__):
        return empty_pagination_payload(page=page, per_page=per_page)

    paginated = build_session_logs_query(filters).paginate(
        page=page, per_page=per_page, error_out=False
    )
    activity_counts = count_audit_visible_entries_for_sessions(paginated.items)
    items = [
        serialize_session_log_list_item(
            s,
            activity_counts.get(
                s.id,
                count_audit_visible_entries_for_session(s),
            ),
            variant=variant,
        )
        for s in paginated.items
    ]
    return {
        'items': items,
        'total': paginated.total,
        'page': paginated.page,
        'per_page': paginated.per_page,
        'pages': paginated.pages or 0,
    }


def get_session_log_page_view_paths(session_id: str) -> Optional[Dict[str, Any]]:
    if not has_table(UserSessionLog.__tablename__):
        return None

    session_log = UserSessionLog.query.filter_by(session_id=session_id).first()
    if not session_log:
        return None

    pvc = (
        session_log.page_view_path_counts
        if isinstance(session_log.page_view_path_counts, dict)
        else {}
    )
    return {
        'session_id': session_log.session_id,
        'page_views': session_log.page_views or 0,
        'page_view_path_counts': pvc,
    }


def get_admin_dashboard_stats() -> Dict[str, Any]:
    """Platform-wide dashboard statistics shared by admin web and mobile APIs."""
    stats = get_platform_stats(user_scoped=False)

    assignment_count = 0
    with suppress(Exception):
        assignment_count = AssignedForm.query.count()

    public_submission_count = 0
    with suppress(Exception):
        public_submission_count = PublicSubmission.query.count()

    week_ago = utcnow() - timedelta(days=7)

    recent_logins = 0
    with suppress(Exception):
        if has_table(UserLoginLog.__tablename__):
            recent_logins = UserLoginLog.query.filter(
                and_(
                    UserLoginLog.timestamp >= week_ago,
                    UserLoginLog.event_type == 'login_success',
                )
            ).count()

    recent_submissions = 0
    with suppress(Exception):
        recent_submissions = PublicSubmission.query.filter(
            PublicSubmission.submitted_at >= week_ago
        ).count()

    month_ago = utcnow() - timedelta(days=30)
    active_users = stats.get('total_users', 0)
    with suppress(Exception):
        if has_table(UserLoginLog.__tablename__):
            active_users = db.session.query(User.id).join(
                UserLoginLog, User.id == UserLoginLog.user_id
            ).filter(
                UserLoginLog.timestamp >= month_ago
            ).distinct().count()

    day_ago = utcnow() - timedelta(days=1)
    failed_logins_24h = 0
    with suppress(Exception):
        if has_table(SecurityEvent.__tablename__):
            failed_logins_24h = SecurityEvent.query.filter(
                and_(
                    SecurityEvent.event_type == 'failed_login',
                    SecurityEvent.occurred_at >= day_ago,
                )
            ).count()

    today_start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_logins = 0
    with suppress(Exception):
        if has_table(UserLoginLog.__tablename__):
            today_logins = UserLoginLog.query.filter(
                and_(
                    UserLoginLog.timestamp >= today_start,
                    UserLoginLog.event_type == 'login_success',
                )
            ).count()

    admin_count = 0
    focal_point_count = 0
    with suppress(Exception):
        from app.models.rbac import RbacRole, RbacUserRole

        admin_role_ids = (
            db.session.query(RbacRole.id)
            .filter(
                or_(
                    RbacRole.code == "system_manager",
                    RbacRole.code == "admin_core",
                    RbacRole.code.like("admin\\_%", escape="\\"),
                )
            )
            .subquery()
        )
        admin_count = (
            db.session.query(User.id)
            .join(RbacUserRole, User.id == RbacUserRole.user_id)
            .filter(RbacUserRole.role_id.in_(admin_role_ids))
            .distinct()
            .count()
        )

        focal_role_id = (
            db.session.query(RbacRole.id)
            .filter(RbacRole.code == "assignment_editor_submitter")
            .subquery()
        )
        focal_point_count = (
            db.session.query(User.id)
            .join(RbacUserRole, User.id == RbacUserRole.user_id)
            .filter(RbacUserRole.role_id.in_(focal_role_id))
            .distinct()
            .count()
        )

    unresolved_security_events = 0
    with suppress(Exception):
        if has_table(SecurityEvent.__tablename__):
            unresolved_security_events = SecurityEvent.query.filter_by(is_resolved=False).count()

    overdue_assignments = 0
    with suppress(Exception):
        overdue_assignments = AssignmentEntityStatus.query.filter(
            and_(
                AssignmentEntityStatus.entity_type == 'country',
                AssignmentEntityStatus.due_date.isnot(None),
                AssignmentEntityStatus.due_date < utcnow(),
                AssignmentEntityStatus.status.in_(['pending', 'in_progress']),
            )
        ).count()

    pending_public_submissions_count = 0
    with suppress(Exception):
        pending_public_submissions_count = PublicSubmission.query.filter(
            PublicSubmission.status == PublicSubmissionStatus.pending
        ).count()

    return {
        'user_count': stats.get('total_users', 0),
        'country_count': stats.get('total_countries', 0),
        'template_count': stats.get('total_templates', 0),
        'assignment_count': assignment_count,
        'indicator_bank_count': stats.get('total_indicators', 0),
        'public_submission_count': public_submission_count,
        'recent_logins': recent_logins,
        'recent_submissions': recent_submissions,
        'active_users': active_users,
        'failed_logins_24h': failed_logins_24h,
        'today_logins': today_logins,
        'admin_count': admin_count,
        'focal_point_count': focal_point_count,
        'unresolved_security_events': unresolved_security_events,
        'overdue_assignments': overdue_assignments,
        'pending_public_submissions_count': pending_public_submissions_count,
    }


@dataclass
class EndSessionResult:
    ok: bool
    error: Optional[str] = None
    session_log: Optional[UserSessionLog] = None
    user_email: Optional[str] = None
    target_user: Optional[User] = None
    logged_out_self: bool = False


def execute_end_session(
    session_id: str,
    *,
    actor_user,
    flask_session,
) -> EndSessionResult:
    """
    End a user session and blacklist it.

    Returns EndSessionResult; route layers handle audit logging and HTTP responses.
    """
    session_log = UserSessionLog.query.filter_by(session_id=session_id).first()
    if not session_log:
        return EndSessionResult(ok=False, error='not_found')

    if not session_log.is_active:
        return EndSessionResult(ok=False, error='already_ended')

    user_email = session_log.user.email if session_log.user else 'Unknown'
    target_user = session_log.user

    end_user_session(session_id, ended_by='admin_action')
    add_session_to_blacklist(session_id)

    logged_out_self = False
    if (
        actor_user.is_authenticated
        and target_user
        and actor_user.id == target_user.id
        and flask_session.get('session_id') == session_id
    ):
        flask_session.clear()
        logged_out_self = True

    return EndSessionResult(
        ok=True,
        session_log=session_log,
        user_email=user_email,
        target_user=target_user,
        logged_out_self=logged_out_self,
    )


def login_logs_filters_from_request_args(args) -> LoginLogsFilters:
    return LoginLogsFilters(
        user=args.get('user'),
        event_type=args.get('event_type'),
        ip=args.get('ip'),
        suspicious_only=args.get('suspicious_only', type=bool),
        date_from=args.get('date_from'),
        date_to=args.get('date_to'),
    )


def session_logs_filters_from_request_args(args) -> SessionLogsFilters:
    return SessionLogsFilters(
        user=args.get('user'),
        active_only=args.get('active_only', type=bool),
        min_duration=args.get('min_duration', type=int),
        session_id=args.get('session_id'),
    )
