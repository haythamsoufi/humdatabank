# File: Backoffice/app/routes/admin/analytics.py
from app.utils.datetime_helpers import utcnow
"""
Analytics Module - Dashboard APIs and Reporting
"""

from flask import Blueprint, request, current_app
from flask_login import current_user
from app import db
from app.extensions import csrf
from app.models import (
    User, Country, FormTemplate, AssignedForm, IndicatorBank, PublicSubmission,
    UserLoginLog, UserActivityLog, SecurityEvent, UserSessionLog,
    AssignmentEntityStatus, PublicSubmissionStatus
)
from contextlib import suppress
from app.routes.admin.shared import admin_required, permission_required
from app.utils.api_responses import json_ok, json_server_error, json_not_found, json_bad_request
from app.utils.transactions import request_transaction_rollback
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE
from app.utils.api_pagination import validate_pagination_params
from app.utils.sql_utils import safe_ilike_pattern
from sqlalchemy import func, desc, and_, or_, inspect, text
from sqlalchemy.orm import joinedload
from datetime import datetime, timedelta
import json
from app.services import get_platform_stats
from app.services.authorization_service import AuthorizationService
from app.services.user_analytics_service import (
    bot_user_agent_explanation,
    effective_session_active_duration_minutes,
    effective_session_duration_minutes,
    session_log_device_icon_classes,
    user_session_log_active_duration_minutes_sql,
)
from app.services.audit_trail_session_query import count_audit_visible_entries_for_session
from app.utils.page_view_paths import distinct_page_view_path_count


def _login_log_risk_json(log: UserLoginLog):
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

bp = Blueprint("admin_analytics_api", __name__, url_prefix="/admin/api")
PROCESS_START_TIME = utcnow()


def _format_uptime(delta: timedelta) -> str:
    seconds = int(delta.total_seconds())
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)

    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)

def _has_table(table_name):
    """Safely check if a table exists in the database"""
    try:
        return inspect(db.engine).has_table(table_name)
    except Exception as e:
        current_app.logger.debug("has_table(%s) failed: %s", table_name, e)
        return False

@bp.route("/analytics/login-logs", methods=["GET"])
@permission_required('admin.analytics.view')
def login_logs_list_api():
    """Paginated login logs (same filters as /admin/analytics/login-logs HTML)."""
    if not _has_table(UserLoginLog.__tablename__):
        return json_ok(
            data={
                'items': [],
                'total': 0,
                'page': 1,
                'per_page': 50,
                'pages': 0,
            }
        )

    page, per_page = validate_pagination_params(
        request.args, default_per_page=50, max_per_page=100
    )
    user_filter = request.args.get('user')
    event_type = request.args.get('event_type')
    ip_filter = request.args.get('ip')
    suspicious_only = request.args.get('suspicious_only', type=bool)
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')

    query = UserLoginLog.query.options(joinedload(UserLoginLog.user))

    if user_filter:
        query = query.filter(
            UserLoginLog.email_attempted.ilike(safe_ilike_pattern(user_filter))
        )
    if event_type:
        query = query.filter(UserLoginLog.event_type == event_type)
    if ip_filter:
        query = query.filter(UserLoginLog.ip_address == ip_filter)
    if suspicious_only:
        query = query.filter(UserLoginLog.is_suspicious == True)

    if date_from:
        try:
            date_from_dt = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(UserLoginLog.timestamp >= date_from_dt)
        except ValueError:
            pass
    if date_to:
        try:
            date_to_dt = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(UserLoginLog.timestamp < date_to_dt)
        except ValueError:
            pass

    query = query.order_by(desc(UserLoginLog.timestamp))
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    items = []
    for log in paginated.items:
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
        items.append({
            'id': log.id,
            'timestamp': log.timestamp.isoformat(),
            'event_type': log.event_type,
            'email_attempted': log.email_attempted,
            'user': user_payload,
            'ip_address': log.ip_address,
            'location': log.location,
            'browser': log.browser,
            'browser_name': log.browser_name,
            'browser_version': log.browser_version,
            'device_type': log.device_type,
            'device_name': log.device_name,
            'operating_system': log.operating_system,
            'user_agent': ua,
            'referrer_url': log.referrer_url,
            'is_suspicious': bool(log.is_suspicious),
            'is_bot_detected': bool(log.is_bot_detected),
            'bot_detection_detail': bot_user_agent_explanation(log.user_agent)
            if log.is_bot_detected
            else None,
            'failure_reason': log.failure_reason,
            'failure_reason_display': log.failure_reason_display,
            'failed_attempts_count': log.failed_attempts_count,
            'risk': _login_log_risk_json(log),
            'device_icon_classes': session_log_device_icon_classes(
                log.user_agent, log.device_type, log.operating_system
            ),
        })

    return json_ok(
        data={
            'items': items,
            'total': paginated.total,
            'page': paginated.page,
            'per_page': paginated.per_page,
            'pages': paginated.pages or 0,
        }
    )


@bp.route("/analytics/session-logs", methods=["GET"])
@permission_required('admin.analytics.view')
def session_logs_list_api():
    """Paginated user session logs (same filters as /admin/analytics/sessions HTML)."""
    if not _has_table(UserSessionLog.__tablename__):
        return json_ok(
            data={
                'items': [],
                'total': 0,
                'page': 1,
                'per_page': 50,
                'pages': 0,
            }
        )

    page, per_page = validate_pagination_params(
        request.args, default_per_page=50, max_per_page=100
    )
    user_filter = request.args.get('user')
    active_only = request.args.get('active_only', type=bool)
    min_duration = request.args.get('min_duration', type=int)
    session_id_exact = (request.args.get('session_id') or '').strip()

    query = UserSessionLog.query.options(joinedload(UserSessionLog.user)).join(User)

    if session_id_exact:
        query = query.filter(UserSessionLog.session_id == session_id_exact)

    if user_filter:
        query = query.filter(User.email.ilike(safe_ilike_pattern(user_filter)))

    if active_only:
        query = query.filter(UserSessionLog.is_active == True)

    if min_duration is not None and min_duration > 0:
        cutoff = utcnow() - timedelta(minutes=min_duration)
        active_min_sql = user_session_log_active_duration_minutes_sql()
        min_parts = [
            UserSessionLog.duration_minutes >= min_duration,
            and_(
                UserSessionLog.is_active == True,
                UserSessionLog.session_start.isnot(None),
                UserSessionLog.session_start <= cutoff,
            ),
        ]
        if active_min_sql is not None:
            min_parts.append(active_min_sql >= min_duration)
        query = query.filter(or_(*min_parts))

    query = query.order_by(desc(UserSessionLog.session_start))
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    items = []
    for s in paginated.items:
        u = s.user
        user_payload = None
        if u is not None:
            user_payload = {
                'id': u.id,
                'name': u.name,
                'email': u.email,
            }
        ua = s.user_agent
        if ua and len(ua) > 400:
            ua = ua[:400] + '…'

        pvc = s.page_view_path_counts if isinstance(s.page_view_path_counts, dict) else {}
        items.append({
            'session_log_id': s.id,
            'session_id': s.session_id,
            'session_start': s.session_start.isoformat() if s.session_start else None,
            'session_end': s.session_end.isoformat() if s.session_end else None,
            'last_activity': s.last_activity.isoformat() if s.last_activity else None,
            'duration_minutes': effective_session_duration_minutes(s),
            'active_duration_minutes': effective_session_active_duration_minutes(s),
            'page_views': s.page_views or 0,
            'distinct_page_view_paths': distinct_page_view_path_count(s),
            'page_view_path_counts': pvc,
            'activity_count': count_audit_visible_entries_for_session(s),
            'is_active': bool(s.is_active),
            'device_type': s.device_type,
            'browser': s.browser,
            'operating_system': s.operating_system,
            'ip_address': s.ip_address,
            'user_agent': ua,
            'user': user_payload,
            'device_icon_classes': session_log_device_icon_classes(
                s.user_agent, s.device_type, s.operating_system
            ),
        })

    return json_ok(
        data={
            'items': items,
            'total': paginated.total,
            'page': paginated.page,
            'per_page': paginated.per_page,
            'pages': paginated.pages or 0,
        }
    )


@bp.route("/analytics/end-session/<session_id>", methods=["POST"])
@csrf.exempt  # Mobile app POSTs without a Referer header; auth/permission checks below are sufficient
@permission_required('admin.analytics.view')
def end_session_api(session_id):
    """End a user session and blacklist it (JSON for admin clients)."""

    from app.services.user_analytics_service import (
        add_session_to_blacklist,
        end_user_session,
        log_admin_action,
    )
    from flask import session as flask_session
    from flask_login import logout_user

    try:
        session_log = UserSessionLog.query.filter_by(session_id=session_id).first()
        if not session_log:
            return json_not_found('Session not found.')

        if not session_log.is_active:
            return json_bad_request('Session is already ended.')

        user_email = session_log.user.email if session_log.user else 'Unknown'
        target_user = session_log.user

        end_user_session(session_id, ended_by='admin_action')
        add_session_to_blacklist(session_id)

        if (current_user.is_authenticated and target_user and
                current_user.id == target_user.id and
                flask_session.get('session_id') == session_id):
            flask_session.clear()
            logout_user()
            log_admin_action(
                action_type='end_user_session',
                description='Manually ended own session (forced logout)',
                target_type='user_session',
                target_id=session_log.id,
                target_description=f'Session {session_id} for {user_email}',
                new_values={
                    'session_id': session_id,
                    'ended_by': 'admin_action',
                    'end_time': utcnow().isoformat(),
                    'user_email': user_email,
                    'forced_logout': True,
                },
                risk_level='medium',
            )
            db.session.flush()
            return json_ok(
                message='Your session was ended. You have been logged out.',
                logged_out_self=True,
            )

        db.session.flush()

        from app.services.user_analytics_service import log_admin_action
        log_admin_action(
            action_type='end_user_session',
            description=f'Manually ended session for user {user_email} (forced logout)',
            target_type='user_session',
            target_id=session_log.id,
            target_description=f'Session {session_id} for {user_email}',
            new_values={
                'session_id': session_id,
                'ended_by': 'admin_action',
                'end_time': utcnow().isoformat(),
                'user_email': user_email,
                'forced_logout': True,
            },
            risk_level='medium',
        )

        return json_ok(
            message=f'Session ended for {user_email}. They will be logged out on their next request.',
            logged_out_self=False,
        )
    except Exception:
        request_transaction_rollback()
        log_admin_action(
            action_type='end_user_session',
            description='Failed to end session.',
            target_type='user_session',
            new_values={'error': GENERIC_ERROR_MESSAGE, 'session_id': session_id},
            risk_level='medium',
        )
        return json_server_error('Error occurred while ending session.')


@bp.route("/dashboard/stats", methods=["GET"])
@permission_required('admin.analytics.view')
def dashboard_stats_api():
    """Get dashboard statistics for admin overview"""
    try:
        # Use service for platform statistics
        stats = get_platform_stats(user_scoped=False)  # Admin sees all stats

        # Additional counts not in the service
        try:
            assignment_count = AssignedForm.query.count()
        except Exception as e:
            current_app.logger.debug("assignment_count query failed: %s", e)
            assignment_count = 0

        try:
            public_submission_count = PublicSubmission.query.count()
        except Exception as e:
            current_app.logger.debug("public_submission_count query failed: %s", e)
            public_submission_count = 0

        # Recent activity counts (last 7 days)
        week_ago = utcnow() - timedelta(days=7)

        recent_logins = 0
        try:
            if _has_table(UserLoginLog.__tablename__):
                recent_logins = UserLoginLog.query.filter(
                    and_(
                        UserLoginLog.timestamp >= week_ago,
                        UserLoginLog.event_type == 'login_success'
                    )
                ).count()
        except Exception as e:
            current_app.logger.debug("recent_logins query failed: %s", e)
            recent_logins = 0

        recent_submissions = 0
        try:
            recent_submissions = PublicSubmission.query.filter(
                PublicSubmission.submitted_at >= week_ago
            ).count()
        except Exception as e:
            current_app.logger.debug("recent_submissions query failed: %s", e)
            recent_submissions = 0

        # Active users (logged in last 30 days)
        month_ago = utcnow() - timedelta(days=30)
        active_users = stats.get('total_users', 0)
        try:
            if _has_table(UserLoginLog.__tablename__):
                active_users = db.session.query(User.id).join(
                    UserLoginLog, User.id == UserLoginLog.user_id
                ).filter(
                    UserLoginLog.timestamp >= month_ago
                ).distinct().count()
        except Exception as e:
            current_app.logger.debug("active_users query failed: %s", e)
            active_users = stats.get('total_users', 0)

        # Failed login attempts (last 24 hours)
        day_ago = utcnow() - timedelta(days=1)
        failed_logins_24h = 0
        try:
            if _has_table(SecurityEvent.__tablename__):
                failed_logins_24h = SecurityEvent.query.filter(
                    and_(
                        SecurityEvent.event_type == 'failed_login',
                        SecurityEvent.occurred_at >= day_ago
                    )
                ).count()
        except Exception as e:
            current_app.logger.debug("failed_logins_24h query failed: %s", e)
            failed_logins_24h = 0

        # Today's logins
        today_start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_logins = 0
        try:
            if _has_table(UserLoginLog.__tablename__):
                today_logins = UserLoginLog.query.filter(
                    and_(
                        UserLoginLog.timestamp >= today_start,
                        UserLoginLog.event_type == 'login_success'
                    )
                ).count()
        except Exception as e:
            current_app.logger.debug("today_logins query failed: %s", e)
            today_logins = 0

        # Role stats
        admin_count = 0
        focal_point_count = 0
        with suppress(Exception):
            from app.models.rbac import RbacUserRole, RbacRole

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

        # Unresolved security events
        unresolved_security_events = 0
        try:
            if _has_table(SecurityEvent.__tablename__):
                unresolved_security_events = SecurityEvent.query.filter_by(is_resolved=False).count()
        except Exception as e:
            current_app.logger.debug("unresolved_security_events query failed: %s", e)
            unresolved_security_events = 0

        # Overdue assignments (country-level AES)
        overdue_assignments = 0
        try:
            overdue_assignments = AssignmentEntityStatus.query.filter(
                and_(
                    AssignmentEntityStatus.entity_type == 'country',
                    AssignmentEntityStatus.due_date.isnot(None),
                    AssignmentEntityStatus.due_date < utcnow(),
                    AssignmentEntityStatus.status.in_(['Assigned', 'In Progress'])
                )
            ).count()
        except Exception as e:
            current_app.logger.debug("overdue_assignments query failed: %s", e)
            overdue_assignments = 0

        # Pending public submissions
        pending_public_submissions_count = 0
        try:
            pending_public_submissions_count = PublicSubmission.query.filter(
                PublicSubmission.status == PublicSubmissionStatus.pending
            ).count()
        except Exception as e:
            current_app.logger.debug("pending_public_submissions_count query failed: %s", e)
            pending_public_submissions_count = 0

        return json_ok(
            status='success',
            data={
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
                'pending_public_submissions_count': pending_public_submissions_count
            }
        )

    except Exception as e:
        current_app.logger.error(f"Error getting dashboard stats: {e}", exc_info=True)
        return json_server_error(
            'An internal error occurred.',
            status='error',
            message='An internal error occurred.'
        )

@bp.route("/dashboard/activity", methods=["GET"])
@permission_required('admin.analytics.view')
def dashboard_activity_api():
    """Get recent activity data for dashboard"""
    try:
        # Get recent user activity (last 50 events)
        recent_activity = []

        if inspect(db.engine).has_table(UserActivityLog.__tablename__):
            activity_logs = UserActivityLog.query.order_by(
                UserActivityLog.timestamp.desc()
            ).limit(50).all()

            for log in activity_logs:
                recent_activity.append({
                    'id': log.id,
                    'user_id': log.user_id,
                    'user_name': log.user.name if log.user else 'Unknown',
                    'action': log.action,
                    'details': log.details,
                    'timestamp': log.timestamp.isoformat(),
                    'ip_address': getattr(log, 'ip_address', None)
                })

        # Get recent logins (last 20)
        recent_logins = []

        if inspect(db.engine).has_table(UserLoginLog.__tablename__):
            login_logs = UserLoginLog.query.order_by(
                UserLoginLog.timestamp.desc()
            ).limit(20).all()

            for log in login_logs:
                recent_logins.append({
                    'id': log.id,
                    'user_id': log.user_id,
                    'user_name': log.user.name if log.user else 'Unknown',
                    'login_time': log.timestamp.isoformat(),
                    'ip_address': getattr(log, 'ip_address', None),
                    'user_agent': getattr(log, 'user_agent', None),
                    'success': getattr(log, 'success', True)
                })

        # Get recent security events (last 20)
        recent_security_events = []

        if inspect(db.engine).has_table(SecurityEvent.__tablename__):
            security_events = SecurityEvent.query.order_by(
                SecurityEvent.occurred_at.desc()
            ).limit(20).all()

            for event in security_events:
                recent_security_events.append({
                    'id': event.id,
                    'event_type': event.event_type,
                    'description': event.description,
                    'user_id': getattr(event, 'user_id', None),
                    'ip_address': getattr(event, 'ip_address', None),
                    'occurred_at': event.occurred_at.isoformat()
                })

        return json_ok(
            status='success',
            data={
                'recent_activity': recent_activity,
                'recent_logins': recent_logins,
                'recent_security_events': recent_security_events
            }
        )

    except Exception as e:
        current_app.logger.error(f"Error getting dashboard activity: {e}", exc_info=True)
        return json_server_error(
            'Error retrieving dashboard activity',
            status='error',
            message='Error retrieving dashboard activity'
        )

@bp.route("/dashboard/trends", methods=["GET"])
@permission_required('admin.analytics.view')
def dashboard_trends_api():
    """Get trend data for dashboard charts"""
    try:
        days = request.args.get('days', 30, type=int)
        end_date = utcnow().date()
        start_date = end_date - timedelta(days=days-1)

        # Daily login trends
        login_trends = []
        if inspect(db.engine).has_table(UserLoginLog.__tablename__):
            login_data = db.session.query(
                func.date(UserLoginLog.timestamp).label('date'),
                func.count(UserLoginLog.id).label('count')
            ).filter(
                func.date(UserLoginLog.timestamp).between(start_date, end_date)
            ).group_by(
                func.date(UserLoginLog.timestamp)
            ).order_by('date').all()

            login_trends = [
                {'date': row.date.isoformat(), 'count': row.count}
                for row in login_data
            ]

        # Daily submission trends
        submission_trends = []
        submission_data = db.session.query(
            func.date(PublicSubmission.submitted_at).label('date'),
            func.count(PublicSubmission.id).label('count')
        ).filter(
            func.date(PublicSubmission.submitted_at).between(start_date, end_date)
        ).group_by(
            func.date(PublicSubmission.submitted_at)
        ).order_by('date').all()

        submission_trends = [
            {'date': row.date.isoformat(), 'count': row.count}
            for row in submission_data
        ]

        # User registration trends (if user creation date is tracked)
        registration_trends = []
        if hasattr(User, 'created_at'):
            registration_data = db.session.query(
                func.date(User.created_at).label('date'),
                func.count(User.id).label('count')
            ).filter(
                func.date(User.created_at).between(start_date, end_date)
            ).group_by(
                func.date(User.created_at)
            ).order_by('date').all()

            registration_trends = [
                {'date': row.date.isoformat(), 'count': row.count}
                for row in registration_data
            ]

        return json_ok(
            status='success',
            data={
                'login_trends': login_trends,
                'submission_trends': submission_trends,
                'registration_trends': registration_trends,
                'period': {
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat(),
                    'days': days
                }
            }
        )

    except Exception as e:
        current_app.logger.error(f"Error getting dashboard trends: {e}", exc_info=True)
        return json_server_error(
            'Error retrieving dashboard trends',
            status='error',
            message='Error retrieving dashboard trends'
        )

@bp.route("/users/activity/<int:user_id>", methods=["GET"])
@permission_required('admin.audit.view')
def user_activity_api(user_id):
    """Get activity data for a specific user"""
    try:
        user = User.query.get_or_404(user_id)

        # Get user's activity logs
        activity_logs = []
        if inspect(db.engine).has_table(UserActivityLog.__tablename__):
            logs = UserActivityLog.query.filter_by(user_id=user_id).order_by(
                UserActivityLog.timestamp.desc()
            ).limit(100).all()

            activity_logs = [
                {
                    'id': log.id,
                    'action': log.action,
                    'details': log.details,
                    'timestamp': log.timestamp.isoformat(),
                    'ip_address': getattr(log, 'ip_address', None)
                }
                for log in logs
            ]

        # Get user's login history
        login_history = []
        if inspect(db.engine).has_table(UserLoginLog.__tablename__):
            logins = UserLoginLog.query.filter_by(user_id=user_id).order_by(
                UserLoginLog.timestamp.desc()
            ).limit(50).all()

            login_history = [
                {
                    'id': log.id,
                    'login_time': log.timestamp.isoformat(),
                    'ip_address': getattr(log, 'ip_address', None),
                    'user_agent': getattr(log, 'user_agent', None),
                    'success': getattr(log, 'success', True)
                }
                for log in logins
            ]

        return json_ok(
            status='success',
            data={
                'user': {
                    'id': user.id,
                    'name': user.name,
                    'email': user.email,
                    'role': (
                        'system_manager'
                        if AuthorizationService.is_system_manager(user)
                        else 'admin'
                        if AuthorizationService.is_admin(user)
                        else 'focal_point'
                        if AuthorizationService.has_role(user, "assignment_editor_submitter")
                        else 'user'
                    )
                },
                'activity_logs': activity_logs,
                'login_history': login_history
            }
        )

    except Exception as e:
        current_app.logger.error(f"Error getting user activity: {e}", exc_info=True)
        return json_server_error(
            'Error retrieving user activity',
            status='error',
            message='Error retrieving user activity'
        )

@bp.route("/submissions/statistics", methods=["GET"])
@permission_required('admin.analytics.view')
def submission_statistics_api():
    """Get submission statistics"""
    try:
        # Overall statistics
        total_submissions = PublicSubmission.query.count()

        # Status breakdown
        status_breakdown = db.session.query(
            PublicSubmission.status,
            func.count(PublicSubmission.id).label('count')
        ).group_by(PublicSubmission.status).all()

        status_stats = {
            str(row.status): row.count for row in status_breakdown
        }

        # Country breakdown
        country_breakdown = db.session.query(
            Country.name,
            func.count(PublicSubmission.id).label('count')
        ).join(
            PublicSubmission, PublicSubmission.country_id == Country.id
        ).group_by(Country.name).order_by(desc('count')).limit(20).all()

        country_stats = [
            {'country': row.name, 'count': row.count}
            for row in country_breakdown
        ]

        # Monthly trends (last 12 months)
        twelve_months_ago = utcnow() - timedelta(days=365)
        monthly_trends = db.session.query(
            func.date_trunc('month', PublicSubmission.submitted_at).label('month'),
            func.count(PublicSubmission.id).label('count')
        ).filter(
            PublicSubmission.submitted_at >= twelve_months_ago
        ).group_by(
            func.date_trunc('month', PublicSubmission.submitted_at)
        ).order_by('month').all()

        monthly_stats = [
            {
                'month': row.month.strftime('%Y-%m') if row.month else None,
                'count': row.count
            }
            for row in monthly_trends
        ]

        return json_ok(
            status='success',
            data={
                'total_submissions': total_submissions,
                'status_breakdown': status_stats,
                'country_breakdown': country_stats,
                'monthly_trends': monthly_stats
            }
        )

    except Exception as e:
        current_app.logger.error(f"Error getting submission statistics: {e}", exc_info=True)
        return json_server_error(
            'Error retrieving submission statistics',
            status='error',
            message='Error retrieving submission statistics'
        )

@bp.route("/indicators/usage", methods=["GET"])
@permission_required('admin.analytics.view')
def indicator_usage_api():
    """Get indicator usage statistics"""
    try:
        # Most used indicators (from form items)
        # This would need to be adapted based on your FormItem structure

        # Total indicators by type
        type_breakdown = db.session.query(
            IndicatorBank.type,
            func.count(IndicatorBank.id).label('count')
        ).group_by(IndicatorBank.type).all()

        type_stats = {
            row.type or 'Unknown': row.count for row in type_breakdown
        }

        # Emergency vs non-emergency indicators
        emergency_breakdown = db.session.query(
            IndicatorBank.emergency,
            func.count(IndicatorBank.id).label('count')
        ).group_by(IndicatorBank.emergency).all()

        emergency_stats = {
            ('Emergency' if row.emergency else 'Regular'): row.count
            for row in emergency_breakdown
        }

        # Recently added indicators (last 30 days)
        thirty_days_ago = utcnow() - timedelta(days=30)
        recent_indicators = IndicatorBank.query.filter(
            IndicatorBank.created_at >= thirty_days_ago
        ).count() if hasattr(IndicatorBank, 'created_at') else 0

        # Archived indicators
        archived_count = IndicatorBank.query.filter_by(archived=True).count()

        return json_ok(
            status='success',
            data={
                'total_indicators': IndicatorBank.query.count(),
                'type_breakdown': type_stats,
                'emergency_breakdown': emergency_stats,
                'recent_indicators': recent_indicators,
                'archived_count': archived_count
            }
        )

    except Exception as e:
        current_app.logger.error(f"Error getting indicator usage: {e}", exc_info=True)
        return json_server_error(
            'Error retrieving indicator usage statistics',
            status='error',
            message='Error retrieving indicator usage statistics'
        )

@bp.route("/system/health", methods=["GET"])
@permission_required('admin.analytics.view')
def system_health_api():
    """Get system health indicators"""
    try:
        # Database connection test
        db_healthy = True
        try:
            db.session.execute(text('SELECT 1'))
        except Exception as e:
            current_app.logger.debug("DB health check failed: %s", e)
            db_healthy = False

        # Active sessions (if session tracking is implemented)
        active_sessions = 0
        if inspect(db.engine).has_table(UserSessionLog.__tablename__):
            active_sessions = UserSessionLog.query.filter(
                # `UserSessionLog` tracks session_end (not ended_at)
                UserSessionLog.session_end.is_(None)
            ).count()

        # Recent errors (if error logging is implemented)
        recent_errors = 0

        uptime_delta = utcnow() - PROCESS_START_TIME
        uptime = _format_uptime(uptime_delta)

        return json_ok(
            status='success',
            data={
                'database_healthy': db_healthy,
                'active_sessions': active_sessions,
                'recent_errors': recent_errors,
                'uptime': uptime,
                'timestamp': utcnow().isoformat()
            }
        )

    except Exception as e:
        current_app.logger.error(f"Error getting system health: {e}", exc_info=True)
        return json_server_error(
            'Error retrieving system health',
            status='error',
            message='Error retrieving system health'
        )
