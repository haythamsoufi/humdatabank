# Backoffice/app/routes/api/mobile/admin_analytics.py
"""Admin analytics routes: dashboard stats, activity, login/session logs, audit trail."""

from datetime import datetime, timedelta

from flask import request, current_app, session
from flask_login import current_user, logout_user
from sqlalchemy import func, desc, and_, or_, inspect
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
from app.utils.page_view_paths import distinct_page_view_path_count
from app.services.audit_trail_display_service import create_consistent_description


def _has_table(table_name):
    try:
        return inspect(db.engine).has_table(table_name)
    except Exception:
        return False


@mobile_bp.route('/admin/analytics/dashboard-stats', methods=['GET'])
@mobile_auth_required(permission='admin.analytics.view')
def dashboard_stats():
    """Platform-wide dashboard statistics."""
    from app.models import (
        User, AssignedForm, PublicSubmission, UserLoginLog,
        SecurityEvent, AssignmentEntityStatus, PublicSubmissionStatus,
    )
    from app.services import get_platform_stats
    from contextlib import suppress

    try:
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
            if _has_table(UserLoginLog.__tablename__):
                recent_logins = UserLoginLog.query.filter(
                    and_(UserLoginLog.timestamp >= week_ago, UserLoginLog.event_type == 'login_success')
                ).count()

        recent_submissions = 0
        with suppress(Exception):
            recent_submissions = PublicSubmission.query.filter(PublicSubmission.submitted_at >= week_ago).count()

        month_ago = utcnow() - timedelta(days=30)
        active_users = stats.get('total_users', 0)
        with suppress(Exception):
            if _has_table(UserLoginLog.__tablename__):
                active_users = db.session.query(User.id).join(
                    UserLoginLog, User.id == UserLoginLog.user_id
                ).filter(UserLoginLog.timestamp >= month_ago).distinct().count()

        day_ago = utcnow() - timedelta(days=1)
        failed_logins_24h = 0
        with suppress(Exception):
            if _has_table(SecurityEvent.__tablename__):
                failed_logins_24h = SecurityEvent.query.filter(
                    and_(SecurityEvent.event_type == 'failed_login', SecurityEvent.occurred_at >= day_ago)
                ).count()

        today_start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_logins = 0
        with suppress(Exception):
            if _has_table(UserLoginLog.__tablename__):
                today_logins = UserLoginLog.query.filter(
                    and_(UserLoginLog.timestamp >= today_start, UserLoginLog.event_type == 'login_success')
                ).count()

        admin_count = 0
        focal_point_count = 0
        with suppress(Exception):
            from app.models.rbac import RbacUserRole, RbacRole
            admin_role_ids = db.session.query(RbacRole.id).filter(
                or_(RbacRole.code == "system_manager", RbacRole.code == "admin_core",
                    RbacRole.code.like("admin\\_%", escape="\\"))
            ).subquery()
            admin_count = db.session.query(User.id).join(
                RbacUserRole, User.id == RbacUserRole.user_id
            ).filter(RbacUserRole.role_id.in_(admin_role_ids)).distinct().count()
            focal_role_id = db.session.query(RbacRole.id).filter(
                RbacRole.code == "assignment_editor_submitter"
            ).subquery()
            focal_point_count = db.session.query(User.id).join(
                RbacUserRole, User.id == RbacUserRole.user_id
            ).filter(RbacUserRole.role_id.in_(focal_role_id)).distinct().count()

        overdue_assignments = 0
        with suppress(Exception):
            overdue_assignments = AssignmentEntityStatus.query.filter(
                and_(
                    AssignmentEntityStatus.entity_type == 'country',
                    AssignmentEntityStatus.due_date.isnot(None),
                    AssignmentEntityStatus.due_date < utcnow(),
                    AssignmentEntityStatus.status.in_(['Assigned', 'In Progress']),
                )
            ).count()

        pending_public = 0
        with suppress(Exception):
            pending_public = PublicSubmission.query.filter(
                PublicSubmission.status == PublicSubmissionStatus.pending
            ).count()

        return mobile_ok(data={
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
            'overdue_assignments': overdue_assignments,
            'pending_public_submissions_count': pending_public,
        })
    except Exception as e:
        current_app.logger.error("dashboard_stats: %s", e, exc_info=True)
        return mobile_server_error()


@mobile_bp.route('/admin/analytics/dashboard-activity', methods=['GET'])
@mobile_auth_required(permission='admin.analytics.view')
def dashboard_activity():
    """Recent activity feed for the admin dashboard."""
    from app.models import UserActivityLog, UserLoginLog, SecurityEvent

    try:
        recent_activity = []
        if _has_table(UserActivityLog.__tablename__):
            for log in UserActivityLog.query.order_by(UserActivityLog.timestamp.desc()).limit(50).all():
                recent_activity.append({
                    'id': log.id,
                    'user_id': log.user_id,
                    'user_name': log.user.name if log.user else 'Unknown',
                    'action': log.action,
                    'details': log.details,
                    'timestamp': log.timestamp.isoformat(),
                    'ip_address': getattr(log, 'ip_address', None),
                })

        recent_logins = []
        if _has_table(UserLoginLog.__tablename__):
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
        if _has_table(SecurityEvent.__tablename__):
            for event in SecurityEvent.query.order_by(SecurityEvent.occurred_at.desc()).limit(20).all():
                recent_security.append({
                    'id': event.id,
                    'event_type': event.event_type,
                    'description': event.description,
                    'user_id': getattr(event, 'user_id', None),
                    'ip_address': getattr(event, 'ip_address', None),
                    'occurred_at': event.occurred_at.isoformat(),
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
    from app.models import UserLoginLog
    from app.services.user_analytics_service import (
        bot_user_agent_explanation, session_log_device_icon_classes,
    )

    if not _has_table(UserLoginLog.__tablename__):
        return mobile_paginated(items=[], total=0, page=1, per_page=50)

    page, per_page = validate_pagination_params(request.args, default_per_page=50, max_per_page=100)
    user_filter = request.args.get('user')
    event_type = request.args.get('event_type')
    ip_filter = request.args.get('ip')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')

    query = UserLoginLog.query.options(joinedload(UserLoginLog.user))

    if user_filter:
        query = query.filter(UserLoginLog.email_attempted.ilike(safe_ilike_pattern(user_filter)))
    if event_type:
        query = query.filter(UserLoginLog.event_type == event_type)
    if ip_filter:
        query = query.filter(UserLoginLog.ip_address == ip_filter)
    if date_from:
        try:
            query = query.filter(UserLoginLog.timestamp >= datetime.strptime(date_from, '%Y-%m-%d'))
        except ValueError:
            pass
    if date_to:
        try:
            query = query.filter(UserLoginLog.timestamp < datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1))
        except ValueError:
            pass

    query = query.order_by(desc(UserLoginLog.timestamp))
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    items = []
    for log in paginated.items:
        u = log.user
        ua = log.user_agent
        if ua and len(ua) > 500:
            ua = ua[:500] + '…'
        items.append({
            'id': log.id,
            'timestamp': log.timestamp.isoformat(),
            'event_type': log.event_type,
            'email_attempted': log.email_attempted,
            'user': {'id': u.id, 'name': u.name, 'email': u.email} if u else None,
            'ip_address': log.ip_address,
            'location': log.location,
            'browser_name': log.browser_name,
            'device_type': log.device_type,
            'operating_system': log.operating_system,
            'is_suspicious': bool(log.is_suspicious),
            'is_bot_detected': bool(log.is_bot_detected),
            'bot_detection_detail': bot_user_agent_explanation(log.user_agent) if log.is_bot_detected else None,
            'failure_reason': log.failure_reason,
            'failure_reason_display': log.failure_reason_display,
            'device_icon_classes': session_log_device_icon_classes(
                log.user_agent, log.device_type, log.operating_system
            ),
        })

    return mobile_paginated(items=items, total=paginated.total, page=paginated.page, per_page=paginated.per_page)


@mobile_bp.route('/admin/analytics/session-logs', methods=['GET'])
@mobile_auth_required(permission='admin.analytics.view')
def session_logs():
    """Paginated user session logs."""
    from app.models import User, UserSessionLog
    from app.services.user_analytics_service import (
        effective_session_active_duration_minutes,
        effective_session_duration_minutes,
        session_log_device_icon_classes,
        user_session_log_active_duration_minutes_sql,
    )
    from app.services.audit_trail_session_query import count_audit_visible_entries_for_session

    if not _has_table(UserSessionLog.__tablename__):
        return mobile_paginated(items=[], total=0, page=1, per_page=50)

    page, per_page = validate_pagination_params(request.args, default_per_page=50, max_per_page=100)
    user_filter = request.args.get('user')
    active_only = request.args.get('active_only', type=bool)
    min_duration = request.args.get('min_duration', type=int)

    query = UserSessionLog.query.options(joinedload(UserSessionLog.user)).join(User)

    if user_filter:
        query = query.filter(User.email.ilike(safe_ilike_pattern(user_filter)))
    if active_only:
        query = query.filter(UserSessionLog.is_active == True)  # noqa: E712
    if min_duration and min_duration > 0:
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

    query = query.order_by(desc(UserSessionLog.session_start))
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    items = []
    for s in paginated.items:
        u = s.user
        ua = s.user_agent
        if ua and len(ua) > 400:
            ua = ua[:400] + '…'
        pvc = s.page_view_path_counts if isinstance(s.page_view_path_counts, dict) else {}
        items.append({
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
            'user': {'id': u.id, 'name': u.name, 'email': u.email} if u else None,
            'device_icon_classes': session_log_device_icon_classes(
                s.user_agent, s.device_type, s.operating_system
            ),
        })

    return mobile_paginated(items=items, total=paginated.total, page=paginated.page, per_page=paginated.per_page)


@mobile_bp.route('/admin/analytics/sessions/<session_id>/end', methods=['POST'])
@mobile_auth_required(permission='admin.analytics.view')
def end_session(session_id):
    """End a user session and blacklist it (admin)."""
    from flask import g
    from app.models.core import UserSessionLog
    from app.services.user_analytics_service import (
        add_session_to_blacklist, end_user_session, log_admin_action,
    )

    try:
        session_log = UserSessionLog.query.filter_by(session_id=session_id).first()
        if not session_log:
            return mobile_not_found('Session not found.')
        if not session_log.is_active:
            return mobile_bad_request('Session is already ended.')

        user_email = session_log.user.email if session_log.user else 'Unknown'
        target_user = session_log.user

        end_user_session(session_id, ended_by='admin_action')
        add_session_to_blacklist(session_id)

        logged_out_self = False
        if (current_user.is_authenticated and target_user and
                current_user.id == target_user.id and
                session.get('session_id') == session_id):
            session.clear()
            logout_user()
            logged_out_self = True

        log_admin_action(
            action_type='end_user_session',
            description=f'Ended session for {user_email} via mobile admin API',
            target_type='user_session',
            target_id=session_log.id,
            target_description=f'Session {session_id} for {user_email}',
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
            logged_out_self=logged_out_self,
        )
    except Exception as e:
        current_app.logger.error("end_session: %s", e, exc_info=True)
        from app.utils.transactions import request_transaction_rollback
        request_transaction_rollback()
        return mobile_server_error()


@mobile_bp.route('/admin/analytics/audit-trail', methods=['GET'])
@mobile_auth_required(permission='admin.audit.view')
def audit_trail():
    """Paginated audit trail (merged activity + admin action logs)."""
    from app.models import UserActivityLog
    from app.utils.api_pagination import validate_pagination_params

    page, per_page = validate_pagination_params(request.args, default_per_page=50, max_per_page=200)
    activity_type_filter = request.args.get('activity_type')
    user_filter = request.args.get('user')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')

    try:
        entries = []

        if _has_table(UserActivityLog.__tablename__):
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

            q = q.filter(
                UserActivityLog.endpoint.notin_((
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
                ))
            )

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
@mobile_auth_required(permission='admin.notifications.manage')
def admin_send_notification():
    """Send push/email notification to selected users (admin)."""
    from app.services.notification.push import PushNotificationService
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
