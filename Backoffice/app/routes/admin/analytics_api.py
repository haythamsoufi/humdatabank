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
    User, Country, FormTemplate, IndicatorBank, PublicSubmission,
    UserLoginLog, UserActivityLog, SecurityEvent, UserSessionLog,
)
from app.routes.admin.shared import admin_required, permission_required
from app.utils.api_responses import json_ok, json_server_error, json_not_found, json_bad_request
from app.utils.transactions import request_transaction_rollback
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE
from app.utils.api_pagination import validate_pagination_params
from sqlalchemy import func, desc, and_, or_, inspect, text
from datetime import datetime, timedelta
from app.services.organization.authorization_service import AuthorizationService
from app.services.platform.user_analytics_query_service import (
    execute_end_session,
    get_admin_dashboard_stats,
    get_session_log_page_view_paths,
    login_logs_filters_from_request_args,
    paginate_login_logs,
    paginate_session_logs,
    session_logs_filters_from_request_args,
)

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

@bp.route("/analytics/login-logs", methods=["GET"])
@permission_required('admin.analytics.view')
def login_logs_list_api():
    """Paginated login logs (same filters as /admin/analytics/login-logs HTML)."""
    page, per_page = validate_pagination_params(
        request.args, default_per_page=50, max_per_page=100
    )
    data = paginate_login_logs(
        page,
        per_page,
        login_logs_filters_from_request_args(request.args),
        variant='admin',
    )
    return json_ok(data=data)


@bp.route("/analytics/session-logs", methods=["GET"])
@permission_required('admin.analytics.view')
def session_logs_list_api():
    """Paginated user session logs (same filters as /admin/analytics/sessions HTML)."""
    page, per_page = validate_pagination_params(
        request.args, default_per_page=50, max_per_page=100
    )
    data = paginate_session_logs(
        page,
        per_page,
        session_logs_filters_from_request_args(request.args),
        variant='admin',
    )
    return json_ok(data=data)


@bp.route("/analytics/session-logs/<session_id>/page-view-paths", methods=["GET"])
@permission_required('admin.analytics.view')
def session_log_page_view_paths_api(session_id):
    """Lazy-load page view path histogram for one session (session logs grid modal)."""
    payload = get_session_log_page_view_paths(session_id)
    if payload is None:
        return json_not_found('Session not found.')
    return json_ok(data=payload)


@bp.route("/analytics/end-session/<session_id>", methods=["POST"])
@csrf.exempt  # Mobile app POSTs without a Referer header; auth/permission checks below are sufficient
@permission_required('admin.analytics.view')
def end_session_api(session_id):
    """End a user session and blacklist it (JSON for admin clients)."""
    from app.services.platform.user_analytics_service import log_admin_action
    from flask import session as flask_session
    from flask_login import logout_user

    try:
        result = execute_end_session(
            session_id,
            actor_user=current_user,
            flask_session=flask_session,
        )
        if result.error == 'not_found':
            return json_not_found('Session not found.')
        if result.error == 'already_ended':
            return json_bad_request('Session is already ended.')

        session_log = result.session_log
        user_email = result.user_email

        if result.logged_out_self:
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
        return json_ok(
            status='success',
            data=get_admin_dashboard_stats(),
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
