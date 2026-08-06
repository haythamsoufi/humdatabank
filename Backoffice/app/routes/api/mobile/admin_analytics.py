# Backoffice/app/routes/api/mobile/admin_analytics.py
"""Admin analytics routes: dashboard stats, activity, login/session logs, audit trail."""

from datetime import datetime, timedelta

from flask import request, current_app, session
from flask_login import current_user, logout_user
from sqlalchemy import desc, inspect
from sqlalchemy.orm import joinedload, contains_eager

from app import db
from app.utils.api_helpers import get_json_safe
from app.utils.api_pagination import validate_pagination_params
from app.utils.mobile_auth import mobile_auth_required
from app.utils.mobile_responses import (
    mobile_ok, mobile_bad_request, mobile_not_found,
    mobile_server_error, mobile_paginated,
)
from app.utils.rate_limiting import mobile_rate_limit
from app.utils.sql_utils import safe_ilike_pattern
from app.utils.datetime_helpers import utcnow
from app.routes.api.mobile import mobile_bp
from app.services.audit.trail_display_service import create_consistent_description
from app.services.notification.push import PushNotificationService
from app.services.platform.user_analytics_query_service import (
    execute_end_session,
    get_admin_dashboard_stats,
    login_logs_filters_from_request_args,
    paginate_login_logs,
    paginate_session_logs,
    session_logs_filters_from_request_args,
)
from app.services.platform.user_analytics_service import log_admin_action


@mobile_bp.route('/admin/analytics/dashboard-stats', methods=['GET'])
@mobile_auth_required(permission='admin.analytics.view')
def dashboard_stats():
    """Platform-wide dashboard statistics."""
    try:
        data = get_admin_dashboard_stats()
        data.pop('unresolved_security_events', None)
        return mobile_ok(data=data)
    except Exception as e:
        current_app.logger.error("dashboard_stats: %s", e, exc_info=True)
        return mobile_server_error()


@mobile_bp.route('/admin/analytics/dashboard-activity', methods=['GET'])
@mobile_auth_required(permission='admin.analytics.view')
def dashboard_activity():
    """Recent activity feed for the admin dashboard."""
    from app.models import UserActivityLog, UserLoginLog, SecurityEvent
    from app.services.platform.user_analytics_query_service import has_table

    try:
        recent_activity = []
        if has_table(UserActivityLog.__tablename__):
            for log in UserActivityLog.query.order_by(UserActivityLog.timestamp.desc()).limit(50).all():
                recent_activity.append({
                    'id': log.id,
                    'user_id': log.user_id,
                    'user_name': log.user.name if log.user else 'Unknown',
                    'action': getattr(log, 'activity_type', None),
                    'details': getattr(log, 'activity_description', None),
                    'timestamp': log.timestamp.isoformat(),
                    'ip_address': getattr(log, 'ip_address', None),
                })

        recent_logins = []
        if has_table(UserLoginLog.__tablename__):
            for log in UserLoginLog.query.order_by(UserLoginLog.timestamp.desc()).limit(20).all():
                recent_logins.append({
                    'id': log.id,
                    'user_id': log.user_id,
                    'user_name': log.user.name if log.user else 'Unknown',
                    'login_time': log.timestamp.isoformat(),
                    'ip_address': getattr(log, 'ip_address', None),
                    'success': getattr(log, 'success', True),
                })

        recent_security = []
        if has_table(SecurityEvent.__tablename__):
            for event in SecurityEvent.query.order_by(SecurityEvent.timestamp.desc()).limit(20).all():
                recent_security.append({
                    'id': event.id,
                    'event_type': event.event_type,
                    'description': event.description,
                    'user_id': getattr(event, 'user_id', None),
                    'ip_address': getattr(event, 'ip_address', None),
                    'occurred_at': event.timestamp.isoformat(),
                })

        return mobile_ok(data={
            'recent_activity': recent_activity,
            'recent_logins': recent_logins,
            'recent_security_events': recent_security,
        })
    except Exception as e:
        current_app.logger.error("dashboard_activity: %s", e, exc_info=True)
        return mobile_server_error()


@mobile_bp.route('/admin/analytics/login-logs', methods=['GET'])
@mobile_auth_required(permission='admin.analytics.view')
def login_logs():
    """Paginated login logs."""
    try:
        page, per_page = validate_pagination_params(
            request.args, default_per_page=50, max_per_page=100
        )
        data = paginate_login_logs(
            page,
            per_page,
            login_logs_filters_from_request_args(request.args),
            variant='mobile',
        )
        return mobile_paginated(
            items=data['items'],
            total=data['total'],
            page=data['page'],
            per_page=data['per_page'],
        )
    except Exception as e:
        current_app.logger.error("login_logs: %s", e, exc_info=True)
        return mobile_server_error()


@mobile_bp.route('/admin/analytics/session-logs', methods=['GET'])
@mobile_auth_required(permission='admin.analytics.view')
def session_logs():
    """Paginated user session logs."""
    try:
        page, per_page = validate_pagination_params(
            request.args, default_per_page=50, max_per_page=100
        )
        data = paginate_session_logs(
            page,
            per_page,
            session_logs_filters_from_request_args(request.args),
            variant='mobile',
        )
        return mobile_paginated(
            items=data['items'],
            total=data['total'],
            page=data['page'],
            per_page=data['per_page'],
        )
    except Exception as e:
        current_app.logger.error("session_logs: %s", e, exc_info=True)
        return mobile_server_error()


@mobile_bp.route('/admin/analytics/sessions/<session_id>/end', methods=['POST'])
@mobile_auth_required(permission='admin.analytics.manage')
def end_session(session_id):
    """End a user session and blacklist it (admin)."""
    from app.utils.transactions import request_transaction_rollback

    try:
        result = execute_end_session(
            session_id,
            actor_user=current_user,
            flask_session=session,
        )
        if result.error == 'not_found':
            return mobile_not_found('Session not found.')
        if result.error == 'already_ended':
            return mobile_bad_request('Session is already ended.')

        if result.logged_out_self:
            logout_user()

        log_admin_action(
            action_type='end_user_session',
            description=f'Ended session for {result.user_email} via mobile admin API',
            target_type='user_session',
            target_id=result.session_log.id,
            target_description=f'Session {session_id} for {result.user_email}',
            new_values={
                'session_id': session_id,
                'ended_by': 'admin_action',
                'end_time': utcnow().isoformat(),
            },
            risk_level='medium',
        )
        db.session.flush()
        return mobile_ok(
            message='Session ended and blacklisted.',
            logged_out_self=result.logged_out_self,
        )
    except Exception as e:
        current_app.logger.error("end_session: %s", e, exc_info=True)
        request_transaction_rollback()
        return mobile_server_error()


@mobile_bp.route('/admin/analytics/audit-trail', methods=['GET'])
@mobile_auth_required(permission='admin.audit.view')
def audit_trail():
    """Paginated audit trail (user activity logs with endpoint noise filtered out)."""
    from app.models import UserActivityLog
    from app.services.audit.trail_session_query import apply_audit_trail_user_activity_noise_filters
    from app.services.platform.user_analytics_query_service import has_table

    page, per_page = validate_pagination_params(request.args, default_per_page=50, max_per_page=200)
    activity_type_filter = request.args.get('activity_type')
    user_filter = request.args.get('user')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')

    try:
        entries = []

        if has_table(UserActivityLog.__tablename__):
            q = UserActivityLog.query
            if user_filter:
                from app.models import User
                q = (
                    q.join(User, UserActivityLog.user_id == User.id)
                    .filter(User.email.ilike(safe_ilike_pattern(user_filter)))
                    .options(contains_eager(UserActivityLog.user))
                )
            else:
                q = q.options(joinedload(UserActivityLog.user))
            if activity_type_filter:
                q = q.filter(UserActivityLog.activity_type == activity_type_filter)
            if date_from:
                try:
                    q = q.filter(UserActivityLog.timestamp >= datetime.strptime(date_from, '%Y-%m-%d'))
                except ValueError:
                    pass
            if date_to:
                try:
                    q = q.filter(UserActivityLog.timestamp < datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1))
                except ValueError:
                    pass

            q = apply_audit_trail_user_activity_noise_filters(q)

            q = q.order_by(desc(UserActivityLog.timestamp))
            paginated = q.paginate(page=page, per_page=per_page, error_out=False)

            for log in paginated.items:
                ctx = log.context_data if isinstance(log.context_data, dict) else {}
                consistent_desc = create_consistent_description(
                    "activity",
                    log.activity_type,
                    None,
                    log.activity_description,
                    log.endpoint,
                    ctx,
                    http_method=getattr(log, "http_method", None),
                )
                entries.append({
                    'id': log.id,
                    'type': 'activity',
                    'timestamp': log.timestamp.isoformat() if log.timestamp else None,
                    'user_email': log.user.email if log.user else None,
                    'user_name': log.user.name if log.user else None,
                    'activity_type': log.activity_type,
                    'description': log.activity_description,
                    'consistent_description': consistent_desc,
                    'endpoint': log.endpoint,
                    'http_method': getattr(log, "http_method", None),
                    'ip_address': log.ip_address,
                    'details': log.context_data,
                })

            return mobile_paginated(
                items=entries,
                total=paginated.total,
                page=paginated.page,
                per_page=paginated.per_page,
            )

        return mobile_paginated(items=[], total=0, page=page, per_page=per_page)
    except Exception as e:
        current_app.logger.error("audit_trail: %s", e, exc_info=True)
        return mobile_server_error()


@mobile_bp.route('/admin/notifications/send', methods=['POST'])
@mobile_rate_limit(requests_per_minute=5)
@mobile_auth_required(permission='admin.communication.manage')
def admin_send_notification():
    """Send push/email notification to selected users (admin)."""
    from app.utils.notification_push import (
        is_notifications_push_enabled,
        PUSH_NOT_ENABLED_CODE,
    )

    if not is_notifications_push_enabled():
        return mobile_bad_request(
            'Push notifications are not enabled on this deployment.',
            error_code=PUSH_NOT_ENABLED_CODE,
        )

    data = get_json_safe()

    title = data.get('title', '').strip()
    body = data.get('body', '').strip()
    user_ids = data.get('user_ids', [])

    if not title or not body:
        return mobile_bad_request('title and body are required')
    if not user_ids:
        return mobile_bad_request('user_ids is required')

    try:
        result = PushNotificationService.send_bulk_push_notifications(
            user_ids=user_ids, title=title, body=body, data=data.get('data'),
        )
        return mobile_ok(data=result)
    except Exception as e:
        current_app.logger.error("admin_send_notification: %s", e, exc_info=True)
        return mobile_server_error()
