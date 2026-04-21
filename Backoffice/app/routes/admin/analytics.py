from app.utils.transactions import request_transaction_rollback
from app.utils.datetime_helpers import utcnow, ensure_utc
from app.utils.sql_utils import safe_ilike_pattern
"""
Analytics Routes for Admin Dashboard

Provides routes for viewing user activity analytics, login logs,
session analytics, and security events.
"""


import logging

from flask import Blueprint, render_template, request, flash, redirect, url_for, Response
from flask_babel import gettext as _

logger = logging.getLogger(__name__)
from flask_login import current_user
from app import db
from app.routes.admin.shared import admin_permission_required, permission_required
from app.utils.request_utils import is_json_request
from app.models import (
    UserLoginLog, UserActivityLog, UserSessionLog, AdminActionLog,
    SecurityEvent, User, Country
)
from app.services.user_analytics_service import (
    get_user_login_analytics, get_user_activity_analytics,
    get_security_events_summary, get_session_analytics, get_active_sessions_count,
    log_admin_action,
    aggregate_page_view_path_histogram,
    format_page_path_histogram_csv,
    effective_session_active_duration_minutes,
)
from app.middleware.activity_middleware import track_admin_action
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE
from app.utils.api_pagination import validate_pagination_params
from app.utils.api_responses import json_ok
from app.services.audit_details_service import format_admin_action_details
from app.services.audit_trail_session_query import (
    apply_audit_trail_user_activity_noise_filters,
    count_audit_visible_entries_for_session,
)
from app.services.audit_trail_display_service import (
    build_form_context_lookups_from_activity_logs,
    consolidate_activity_type,
    create_consistent_description,
    extract_entity_info,
    refine_activity_row_consolidated_type,
)
from sqlalchemy import func, desc, and_, or_, cast, String
from sqlalchemy.orm import joinedload, load_only
from datetime import datetime, timedelta
from urllib.parse import urlencode
import csv
import io
import json

bp = Blueprint('analytics', __name__, url_prefix='/admin/analytics')

@bp.route('/dashboard')
@permission_required('admin.analytics.view')
def analytics_dashboard():
    """Main analytics dashboard with overview statistics."""
    # Get date range from query params (default to last 30 days)
    days = request.args.get('days', 30, type=int)

    # Get overview statistics
    login_analytics = get_user_login_analytics(days=days)
    activity_analytics = get_user_activity_analytics(days=days)
    security_summary = get_security_events_summary(days=days)

    # Get top active users
    top_users = get_top_active_users(days)

    # Get recent security events
    recent_security_events = SecurityEvent.query.filter(
        SecurityEvent.timestamp > utcnow() - timedelta(days=7)
    ).order_by(desc(SecurityEvent.timestamp)).limit(10).all()

    # Get session statistics
    session_stats = get_session_statistics(days)

    # Device distribution: sorted rows + totals for dashboard infographic / chart order
    _device_bd = login_analytics.get('device_breakdown') or {}
    _device_sorted = sorted(_device_bd.items(), key=lambda x: x[1], reverse=True)
    _device_total = sum(c for _, c in _device_sorted)
    device_dist_rows = []
    for name, cnt in _device_sorted:
        pct = round(100.0 * cnt / _device_total, 1) if _device_total else 0.0
        device_dist_rows.append({'device': name, 'count': cnt, 'pct': pct})
    # Avoid 99.9% / 100.1% display totals from rounding (confusing next to the bar)
    if device_dist_rows:
        _psum = sum(r['pct'] for r in device_dist_rows)
        _pdiff = round(100.0 - _psum, 1)
        if abs(_pdiff) >= 0.05:
            device_dist_rows[-1]['pct'] = round(device_dist_rows[-1]['pct'] + _pdiff, 1)

    return render_template(
        'admin/analytics/dashboard.html',
        login_analytics=login_analytics,
        activity_analytics=activity_analytics,
        security_summary=security_summary,
        top_users=top_users,
        recent_security_events=recent_security_events,
        session_stats=session_stats,
        device_dist_rows=device_dist_rows,
        device_dist_total=_device_total,
        selected_days=days
    )


@bp.route('/page-paths')
@permission_required('admin.analytics.view')
def page_path_analytics():
    """
    Aggregate page_view_path_counts across sessions (session-tracked routes, not audit trail).
    Query: days, user_id, user (email), path_prefix, export=csv
    """
    days = request.args.get('days', 30, type=int) or 30
    path_prefix = (request.args.get('path_prefix') or '').strip() or None
    user_id = request.args.get('user_id', type=int)
    user_email = (request.args.get('user') or '').strip() or None

    resolved_user = None
    if user_id is not None:
        resolved_user = User.query.get(user_id)
    elif user_email:
        resolved_user = User.query.filter(
            User.email.ilike(safe_ilike_pattern(user_email))
        ).first()
        if resolved_user:
            user_id = resolved_user.id
        else:
            flash(_('No user found for that email. Showing all users.'), 'warning')
            user_id = None

    data = aggregate_page_view_path_histogram(
        user_id=user_id,
        days=days,
        path_prefix=path_prefix,
    )

    if request.args.get('export') == 'csv':
        csv_text = format_page_path_histogram_csv(data['paths'])
        filename = f'page_path_analytics_{days}d.csv'
        return Response(
            csv_text,
            mimetype='text/csv; charset=utf-8',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
            },
        )

    paths_full = data['paths']
    limit = int(data.get('display_limit') or 500)
    paths_display = paths_full[:limit]
    paths_truncated = len(paths_full) > limit

    filter_user_display = (user_email or '').strip()
    if resolved_user and not filter_user_display:
        filter_user_display = (resolved_user.email or '').strip()

    users = User.query.order_by(User.email).all()
    ppa_users = []
    emails_in_list = set()
    for u in users:
        emails_in_list.add((u.email or '').strip())
        item = {'value': u.email, 'label': u.name or u.email}
        if u.name and str(u.name).strip():
            item['sublabel'] = u.email
        ppa_users.append(item)
    if filter_user_display and filter_user_display not in emails_in_list:
        ppa_users.insert(
            0,
            {
                'value': filter_user_display,
                'label': filter_user_display,
                'sublabel': _('Not in directory (from URL)'),
            },
        )

    csv_args = {'export': 'csv', 'days': days}
    if filter_user_display:
        csv_args['user'] = filter_user_display
    elif user_id is not None:
        csv_args['user_id'] = user_id
    if path_prefix:
        csv_args['path_prefix'] = path_prefix
    export_csv_url = url_for('analytics.page_path_analytics') + '?' + urlencode(csv_args)

    return render_template(
        'admin/analytics/page_path_analytics.html',
        histogram_data=data,
        paths_display=paths_display,
        paths_truncated=paths_truncated,
        paths_total_count=len(paths_full),
        filters={
            'days': days,
            'user': filter_user_display,
            'path_prefix': path_prefix or '',
        },
        ppa_users=ppa_users,
        export_csv_url=export_csv_url,
    )


@bp.route('/login-logs')
@permission_required('admin.analytics.view')
def login_logs():
    """View detailed login logs (rows loaded via /admin/api/analytics/login-logs + AG Grid)."""
    user_filter = request.args.get('user')
    event_type = request.args.get('event_type')
    ip_filter = request.args.get('ip')
    suspicious_only = request.args.get('suspicious_only', type=bool)
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')

    return render_template(
        'admin/analytics/login_logs.html',
        filters={
            'user': user_filter,
            'event_type': event_type,
            'ip': ip_filter,
            'suspicious_only': suspicious_only,
            'date_from': date_from,
            'date_to': date_to,
        },
    )


@bp.route('/activity-logs')
@permission_required('admin.analytics.view')
def activity_logs():
    """View detailed user activity logs."""
    page, per_page = validate_pagination_params(request.args, default_per_page=50, max_per_page=100)

    # Filters
    user_filter = request.args.get('user')
    activity_type = request.args.get('activity_type')
    endpoint_filter = request.args.get('endpoint')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')

    # Build query
    query = UserActivityLog.query.join(User)

    if user_filter:
        query = query.filter(User.email.ilike(safe_ilike_pattern(user_filter)))

    if activity_type:
        query = query.filter(UserActivityLog.activity_type == activity_type)

    if endpoint_filter:
        query = query.filter(UserActivityLog.endpoint.ilike(safe_ilike_pattern(endpoint_filter)))

    if date_from:
        try:
            date_from_dt = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(UserActivityLog.timestamp >= date_from_dt)
        except ValueError:
            flash(f"Invalid date format for 'from' date: {date_from}. Expected YYYY-MM-DD", "warning")

    if date_to:
        try:
            date_to_dt = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(UserActivityLog.timestamp < date_to_dt)
        except ValueError:
            flash(f"Invalid date format for 'to' date: {date_to}. Expected YYYY-MM-DD", "warning")

    # Order by most recent first
    query = query.order_by(desc(UserActivityLog.timestamp))

    # Paginate
    logs = query.paginate(
        page=page, per_page=per_page, error_out=False
    )

    # Get unique activity types for filter dropdown
    activity_types = UserActivityLog.query.with_entities(
        func.distinct(UserActivityLog.activity_type)
    ).all()
    activity_types = [t[0] for t in activity_types if t[0]]

    return render_template(
        'admin/analytics/activity_logs.html',
        logs=logs,
        activity_types=activity_types,
        filters={
            'user': user_filter,
            'activity_type': activity_type,
            'endpoint': endpoint_filter,
            'date_from': date_from,
            'date_to': date_to
        }
    )


@bp.route('/sessions')
@permission_required('admin.analytics.view')
def session_logs():
    """View user session logs (data loaded via /admin/api/analytics/session-logs + AG Grid)."""
    user_filter = request.args.get('user')
    active_only = request.args.get('active_only', type=bool)
    min_duration = request.args.get('min_duration', type=int)
    session_id_filter = (request.args.get('session_id') or '').strip() or None

    return render_template(
        'admin/analytics/sessions.html',
        filters={
            'user': user_filter,
            'active_only': active_only,
            'min_duration': min_duration,
            'session_id': session_id_filter,
        },
    )


@bp.route('/admin-actions')
@permission_required('admin.analytics.view')
def admin_actions():
    """View admin action logs."""
    page, per_page = validate_pagination_params(request.args, default_per_page=50, max_per_page=100)

    # Filters
    admin_filter = request.args.get('admin')
    action_type = request.args.get('action_type')
    risk_level = request.args.getlist('risk_level')  # Changed to getlist for multi-select
    requires_review = request.args.get('requires_review', type=bool)

    # Build query
    query = AdminActionLog.query.join(User)

    if admin_filter:
        query = query.filter(User.email.ilike(safe_ilike_pattern(admin_filter)))

    if action_type:
        query = query.filter(AdminActionLog.action_type == action_type)

    if risk_level:
        # Handle multiple risk level selections
        risk_level_conditions = []
        for level in risk_level:
            risk_level_conditions.append(AdminActionLog.risk_level == level)
        if risk_level_conditions:
            query = query.filter(or_(*risk_level_conditions))

    if requires_review:
        query = query.filter(AdminActionLog.requires_review == True)

    # Order by most recent first
    query = query.order_by(desc(AdminActionLog.timestamp))

    # Paginate
    actions = query.paginate(
        page=page, per_page=per_page, error_out=False
    )

    # Get unique action types for filter dropdown
    action_types = AdminActionLog.query.with_entities(
        func.distinct(AdminActionLog.action_type)
    ).all()
    action_types = [t[0] for t in action_types if t[0]]

    return render_template(
        'admin/analytics/admin_actions.html',
        actions=actions,
        action_types=action_types,
        filters={
            'admin': admin_filter,
            'action_type': action_type,
            'risk_level': risk_level,
            'requires_review': requires_review
        }
    )


@bp.route('/security-events')
@permission_required('admin.analytics.view')
def security_events():
    """View security events."""
    page, per_page = validate_pagination_params(request.args, default_per_page=25, max_per_page=100)

    # Filters
    severity = request.args.get('severity')
    event_type = request.args.get('event_type')
    unresolved_only = request.args.get('unresolved_only', type=bool)

    # Build query
    query = SecurityEvent.query

    if severity:
        query = query.filter(SecurityEvent.severity == severity)

    if event_type:
        query = query.filter(SecurityEvent.event_type == event_type)

    if unresolved_only:
        query = query.filter(SecurityEvent.is_resolved == False)

    # Order by most recent first
    query = query.order_by(desc(SecurityEvent.timestamp))

    # Paginate
    events = query.paginate(
        page=page, per_page=per_page, error_out=False
    )

    return render_template(
        'admin/analytics/security_events.html',
        events=events,
        filters={
            'severity': severity,
            'event_type': event_type,
            'unresolved_only': unresolved_only
        }
    )


@bp.route('/security-events/<int:event_id>/resolve', methods=['POST'])
@permission_required('admin.analytics.view')
def resolve_security_event(event_id):
    """Resolve a security event."""
    event = SecurityEvent.query.get_or_404(event_id)
    resolution_notes = request.form.get('resolution_notes', '')

    # Store old values for tracking
    old_values = {
        'is_resolved': event.is_resolved,
        'resolved_by_user_id': event.resolved_by_user_id,
        'resolved_at': event.resolved_at.isoformat() if event.resolved_at else None,
        'resolution_notes': event.resolution_notes
    }

    event.is_resolved = True
    event.resolved_by_user_id = current_user.id
    event.resolved_at = utcnow()
    event.resolution_notes = resolution_notes

    # Store new values for tracking
    new_values = {
        'is_resolved': event.is_resolved,
        'resolved_by_user_id': event.resolved_by_user_id,
        'resolved_at': event.resolved_at.isoformat(),
        'resolution_notes': event.resolution_notes
    }

    db.session.flush()

    # Log admin action with proper target tracking
    log_admin_action(
        action_type='resolve_security_event',
        description=f'Resolved security event #{event.id}',
        target_type='security_event',
        target_id=event.id,
        target_description=f'{event.event_type} - {event.severity}',
        old_values=old_values,
        new_values=new_values,
        risk_level='medium'
    )

    flash(f'Security event #{event.id} has been resolved.', 'success')
    return redirect(url_for('analytics.security_events'))


@bp.route('/user/<int:user_id>')
@permission_required('admin.analytics.view')
def user_analytics(user_id):
    """View analytics for a specific user."""
    user = User.query.get_or_404(user_id)
    days = request.args.get('days', 30, type=int)

    # Get user-specific analytics
    login_analytics = get_user_login_analytics(user_id=user_id, days=days)
    activity_analytics = get_user_activity_analytics(user_id=user_id, days=days)

    # Get recent sessions for the selected time period
    from_date = utcnow() - timedelta(days=days)
    recent_sessions = UserSessionLog.query.filter(
        UserSessionLog.user_id == user_id,
        UserSessionLog.session_start >= from_date
    ).order_by(
        desc(UserSessionLog.session_start)
    ).limit(10).all()

    for _sess in recent_sessions:
        _sess.audit_visible_activity_count = count_audit_visible_entries_for_session(_sess)

    total_sessions_count = UserSessionLog.query.filter(
        UserSessionLog.user_id == user_id,
        UserSessionLog.session_start >= from_date
    ).count()

    # Total active time = sum of per-session active minutes (session_start →
    # last_activity), same rule as ``effective_session_active_duration_minutes`` /
    # session logs "Active time". Excludes idle after last activity until close.
    period_sessions_for_active_total = UserSessionLog.query.filter(
        UserSessionLog.user_id == user_id,
        UserSessionLog.session_start >= from_date,
    ).options(
        load_only(
            UserSessionLog.id,
            UserSessionLog.session_start,
            UserSessionLog.last_activity,
        )
    ).all()

    total_active_time_minutes = 0
    for _s in period_sessions_for_active_total:
        m = effective_session_active_duration_minutes(_s)
        if m is not None:
            total_active_time_minutes += m

    total_page_views_row = db.session.query(
        func.coalesce(func.sum(UserSessionLog.page_views), 0)
    ).filter(
        UserSessionLog.user_id == user_id,
        UserSessionLog.session_start >= from_date,
    ).scalar()
    total_page_views = int(total_page_views_row or 0)

    # Get recent login attempts
    recent_logins = UserLoginLog.query.filter_by(user_id=user_id).order_by(
        desc(UserLoginLog.timestamp)
    ).limit(20).all()

    partial = request.args.get('partial', '0') == '1'
    template = 'admin/analytics/_user_detail_partial.html' if partial else 'admin/analytics/user_detail.html'
    return render_template(
        template,
        user=user,
        login_analytics=login_analytics,
        activity_analytics=activity_analytics,
        recent_sessions=recent_sessions,
        total_sessions_count=total_sessions_count,
        total_active_time_minutes=total_active_time_minutes,
        total_page_views=total_page_views,
        recent_logins=recent_logins,
        selected_days=days
    )


@bp.route('/api/charts/login-activity')
@permission_required('admin.analytics.view')
def chart_login_activity():
    """API endpoint for login activity chart data."""
    days = request.args.get('days', 30, type=int)
    analytics = get_user_login_analytics(days=days)

    return json_ok(
        daily_activity=analytics['daily_activity'],
        device_breakdown=analytics['device_breakdown'],
        browser_breakdown=analytics['browser_breakdown']
    )


@bp.route('/api/charts/user-activity')
@permission_required('admin.analytics.view')
def chart_user_activity():
    """API endpoint for user activity chart data."""
    days = request.args.get('days', 30, type=int)
    analytics = get_user_activity_analytics(days=days)

    return json_ok(
        daily_activity=analytics['daily_activity'],
        activity_breakdown=analytics['activity_breakdown'],
        popular_pages=analytics['popular_pages']
    )


# Helper functions

def get_top_active_users(days=30):
    """Get the most active users by activity count."""
    from_date = utcnow() - timedelta(days=days)

    active_users = UserActivityLog.query.join(User).filter(
        UserActivityLog.timestamp > from_date
    ).group_by(User.id).with_entities(
        User.id,
        User.email,
        User.name,
        func.count(UserActivityLog.id).label('activity_count')
    ).order_by(desc('activity_count')).limit(10).all()

    return active_users


def get_session_statistics(days=30):
    """Get session statistics."""
    return get_session_analytics(days)


@bp.route('/cleanup-sessions', methods=['POST'])
@permission_required('admin.analytics.view')
def cleanup_sessions():
    """Manual cleanup of inactive sessions."""
    from app.services.user_analytics_service import cleanup_inactive_sessions

    try:
        count = cleanup_inactive_sessions()

        # Log admin action with proper details
        log_admin_action(
            action_type='cleanup_sessions',
            description=f'Manual session cleanup removed {count} inactive sessions',
            target_type='user_session',
            target_description=f'{count} inactive sessions',
            new_values={'sessions_cleaned': count, 'cleanup_time': utcnow().isoformat()},
            risk_level='medium'
        )

        flash(f'Successfully cleaned up {count} inactive sessions.', 'success')
    except Exception as e:
        # Log failed cleanup attempt
        log_admin_action(
            action_type='cleanup_sessions',
            description='Failed session cleanup attempt.',
            target_type='user_session',
            new_values={'error': GENERIC_ERROR_MESSAGE, 'cleanup_time': utcnow().isoformat()},
            risk_level='medium'
        )
        flash('Error occurred during session cleanup.', 'danger')

    return redirect(url_for('analytics.session_logs'))


@bp.route('/end-session/<session_id>', methods=['POST'])
@permission_required('admin.analytics.view')
def end_session(session_id):
    """End a specific user session manually and force logout the user."""
    from app.services.user_analytics_service import end_user_session
    from flask import session as flask_session
    from flask_login import logout_user
    import os

    try:
        # Get the session to find user info for logging
        session_log = UserSessionLog.query.filter_by(session_id=session_id).first()
        if not session_log:
            flash('Session not found.', 'danger')
            return redirect(url_for('analytics.session_logs'))

        if not session_log.is_active:
            flash('Session is already ended.', 'info')
            return redirect(url_for('analytics.session_logs'))

        # Get user info for logging
        user_email = session_log.user.email if session_log.user else 'Unknown'
        target_user = session_log.user

        # End the analytics session log
        end_user_session(session_id, ended_by='admin_action')

        # Force logout: Add the session to a blacklist for immediate termination
        # We'll store force-logout sessions in a simple way that the before_request handler can check
        from app.services.user_analytics_service import add_session_to_blacklist
        add_session_to_blacklist(session_id)

        # If this is the current user's own session, log them out immediately
        if (current_user.is_authenticated and
            target_user and
            current_user.id == target_user.id and
            flask_session.get('session_id') == session_id):

            # Clear their current Flask session
            flask_session.clear()
            logout_user()

            # Commit the session changes
            db.session.flush()

            # Log admin action
            log_admin_action(
                action_type='end_user_session',
                description=f'Manually ended own session (forced logout)',
                target_type='user_session',
                target_id=session_log.id,
                target_description=f'Session {session_id} for {user_email}',
                new_values={
                    'session_id': session_id,
                    'ended_by': 'admin_action',
                    'end_time': utcnow().isoformat(),
                    'user_email': user_email,
                    'forced_logout': True
                },
                risk_level='medium'
            )

            flash(f'Successfully ended your own session. You have been logged out.', 'success')
            return redirect(url_for('auth.login'))

        # Commit the session changes
        db.session.flush()

        # Log admin action
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
                'forced_logout': True
            },
            risk_level='medium'
        )

        flash(f'Successfully ended session for user {user_email}. They will be logged out on their next request.', 'success')
    except Exception as e:
        request_transaction_rollback()
        # Log failed attempt
        log_admin_action(
            action_type='end_user_session',
            description='Failed to end session.',
            target_type='user_session',
            new_values={'error': GENERIC_ERROR_MESSAGE, 'session_id': session_id},
            risk_level='medium'
        )
        flash('Error occurred while ending session.', 'danger')

    return redirect(url_for('analytics.session_logs'))


@bp.route('/audit-trail')
@admin_permission_required('admin.audit.view')
def audit_trail():
    """View unified audit trail combining activity logs and admin actions."""
    # Higher limits than typical admin lists: merged audit data is already capped in DB queries;
    # the HTML grid had no client pagination, so users were stuck at the first page only.
    logger.info(
        "[audit_trail] raw args — page=%r per_page=%r",
        request.args.get('page'), request.args.get('per_page'),
    )
    page, per_page = validate_pagination_params(
        request.args, default_per_page=100, max_per_page=500
    )
    logger.info("[audit_trail] resolved page=%d per_page=%d", page, per_page)

    # Filters
    user_filter = request.args.getlist('user')  # Changed to getlist for multi-select
    activity_type = request.args.getlist('activity_type')  # Changed to getlist for multi-select
    risk_level = request.args.getlist('risk_level')  # Changed to getlist for multi-select
    country_filter = request.args.getlist('country')  # Changed to getlist for multi-select
    endpoint_filter = request.args.get('endpoint')
    description_filter = request.args.get('description')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    requires_review = request.args.get('requires_review', type=bool)

    session_id_param = (request.args.get('session_id') or '').strip()
    session_row = None
    session_end_for_filter = None
    session_start_for_filter = None
    filters_session_id = None
    session_token = None  # UserSessionLog.session_id (long token) for activity log filters

    if session_id_param:
        q = UserSessionLog.query.options(joinedload(UserSessionLog.user))
        if session_id_param.isdigit():
            sid_int = int(session_id_param)
            if sid_int > 0:
                session_row = q.filter_by(id=sid_int).first()
        if session_row is None:
            session_row = q.filter_by(session_id=session_id_param).first()
        if not session_row:
            flash(_('Session not found. Audit is not scoped to a session.'), 'warning')
            session_id_param = ''
        else:
            session_token = session_row.session_id
            filters_session_id = str(session_row.id)
            session_start_for_filter = ensure_utc(session_row.session_start)
            session_end_for_filter = (
                ensure_utc(session_row.session_end) if session_row.session_end else utcnow()
            )
            if session_end_for_filter < session_start_for_filter:
                session_end_for_filter = utcnow()
            if session_row.user and session_row.user.email:
                user_filter = [session_row.user.email]

    # Limit date range to prevent loading excessive data (default to last 90 days if no date filter)
    # This prevents memory issues with very large datasets
    if session_row and session_start_for_filter is not None:
        date_from_dt = session_start_for_filter - timedelta(seconds=1)
    elif not date_from:
        default_date_from = utcnow() - timedelta(days=90)
        date_from_dt = default_date_from
    else:
        try:
            date_from_dt = datetime.strptime(date_from, '%Y-%m-%d')
        except ValueError:
            date_from_dt = utcnow() - timedelta(days=90)
            flash(f"Invalid date format for 'from' date: {date_from}. Using default 90 days", "warning")

    # Get all entries without duplicates
    entries = []
    processed_ids = set()  # Track processed entries to prevent duplicates

    # Treat "all countries selected" as no country filter.
    # Many activity/admin entries do not carry country_id metadata; applying a country
    # filter in that case would unintentionally hide valid results.
    all_country_ids = {str(country_id) for (country_id,) in Country.query.with_entities(Country.id).all()}
    selected_country_ids = {str(country_id) for country_id in country_filter if str(country_id).strip()}
    apply_country_filter = bool(selected_country_ids) and selected_country_ids != all_country_ids

    # Build single activity query with all conditions
    activity_query = UserActivityLog.query.join(User).filter(
        UserActivityLog.timestamp >= date_from_dt
    )

    activity_query = apply_audit_trail_user_activity_noise_filters(activity_query)

    if session_row and session_end_for_filter is not None:
        activity_query = activity_query.filter(
            UserActivityLog.timestamp <= session_end_for_filter
        )
        activity_query = activity_query.filter(
            or_(
                UserActivityLog.user_session_id == session_token,
                and_(
                    UserActivityLog.user_session_id.is_(None),
                    UserActivityLog.user_id == session_row.user_id,
                    UserActivityLog.timestamp >= session_start_for_filter,
                    UserActivityLog.timestamp <= session_end_for_filter,
                ),
            )
        )

    # Omit page_view at SQL when the UI will not show them (default + filtered views
    # that exclude page_view), to avoid loading thousands of low-value rows.
    # Same rule for session-scoped and global audit: driven by Activity Type (activity_type).
    _need_page_views_in_results = bool(activity_type) and 'page_view' in activity_type
    if not _need_page_views_in_results:
        activity_query = activity_query.filter(UserActivityLog.activity_type != 'page_view')

    if user_filter:
        # Handle multiple user selections
        user_conditions = []
        for user_email in user_filter:
            user_conditions.append(User.email == user_email)
        if user_conditions:
            activity_query = activity_query.filter(or_(*user_conditions))

    if endpoint_filter:
        activity_query = activity_query.filter(UserActivityLog.endpoint.ilike(safe_ilike_pattern(endpoint_filter)))

    if description_filter:
        activity_query = activity_query.filter(UserActivityLog.activity_description.ilike(safe_ilike_pattern(description_filter)))

    if apply_country_filter:
        # Match on entity_id (new field for all entity types) or legacy country_id
        country_conditions = []
        for cid in selected_country_ids:
            country_conditions.append(cast(UserActivityLog.context_data['entity_id'], String) == str(cid))
            country_conditions.append(cast(UserActivityLog.context_data['country_id'], String) == str(cid))
        if country_conditions:
            activity_query = activity_query.filter(or_(*country_conditions))

    if date_from:
        try:
            date_from_dt = datetime.strptime(date_from, '%Y-%m-%d')
            activity_query = activity_query.filter(UserActivityLog.timestamp >= date_from_dt)
        except ValueError:
            flash(f"Invalid date format for 'from' date: {date_from}. Expected YYYY-MM-DD", "warning")

    if date_to:
        try:
            date_to_dt = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
            activity_query = activity_query.filter(UserActivityLog.timestamp < date_to_dt)
        except ValueError:
            flash(f"Invalid date format for 'to' date: {date_to}. Expected YYYY-MM-DD", "warning")

    MAX_ACTIVITY_ROWS = 5000
    activity_logs = activity_query.order_by(UserActivityLog.timestamp.desc()).limit(MAX_ACTIVITY_ROWS).all()
    form_lookups = build_form_context_lookups_from_activity_logs(activity_logs)

    for log in activity_logs:
        log_id = f'activity_{log.id}'
        if log_id not in processed_ids:
            processed_ids.add(log_id)

            consolidated_type = refine_activity_row_consolidated_type(
                log.activity_type,
                log.activity_description,
                log.endpoint,
                getattr(log, "http_method", None),
            )

            # Enhance context_data with url_path if available
            enhanced_context = log.context_data.copy() if log.context_data else {}
            if log.url_path and 'url_path' not in enhanced_context:
                enhanced_context['url_path'] = log.url_path

            consistent_desc = create_consistent_description(
                'activity',
                log.activity_type,
                None,
                log.activity_description,
                log.endpoint,
                enhanced_context,
                form_lookups=form_lookups,
                http_method=getattr(log, "http_method", None),
            )

            entity_type, entity_id, entity_name = extract_entity_info('activity', enhanced_context)

            entries.append({
                'id': log_id,
                'type': 'activity',
                'timestamp': log.timestamp,
                'user': log.user,
                'user_email': log.user.email if log.user else None,
                'activity_type': log.activity_type,
                'consolidated_activity_type': consolidated_type,
                'description': log.activity_description,
                'consistent_description': consistent_desc,
                'endpoint': log.endpoint,
                'http_method': log.http_method,
                'ip_address': log.ip_address,
                'response_status_code': log.response_status_code,
                'risk_level': 'low',
                'requires_review': False,
                'context_data': log.context_data,
                'entity_type': entity_type,
                'entity_id': entity_id,
                'entity_name': entity_name,
                'user_session_id': getattr(log, 'user_session_id', None),
            })

    # Build single admin query with all conditions
    # Apply date filter to prevent loading excessive data
    admin_query = AdminActionLog.query.join(User).filter(
        AdminActionLog.timestamp >= date_from_dt
    )

    if session_row and session_end_for_filter is not None:
        admin_query = admin_query.filter(
            AdminActionLog.timestamp <= session_end_for_filter
        )
        admin_query = admin_query.filter(
            AdminActionLog.admin_user_id == session_row.user_id
        )

    if user_filter:
        # Handle multiple user selections
        user_conditions = []
        for user_email in user_filter:
            user_conditions.append(User.email == user_email)
        if user_conditions:
            admin_query = admin_query.filter(or_(*user_conditions))

    if risk_level:
        # Handle multiple risk level selections
        risk_level_conditions = []
        for level in risk_level:
            risk_level_conditions.append(AdminActionLog.risk_level == level)
        if risk_level_conditions:
            admin_query = admin_query.filter(or_(*risk_level_conditions))

    if requires_review:
        admin_query = admin_query.filter(AdminActionLog.requires_review == True)

    if description_filter:
        admin_query = admin_query.filter(AdminActionLog.action_description.ilike(safe_ilike_pattern(description_filter)))

    if apply_country_filter:
        # Handle multiple country selections
        country_conditions = []
        for country_id in selected_country_ids:
            country_conditions.extend([
                cast(AdminActionLog.new_values['country_id'], String) == str(country_id),
                cast(AdminActionLog.old_values['country_id'], String) == str(country_id)
            ])
        # Only include entries matching the selected countries (exclude entries with no country)
        if country_conditions:
            admin_query = admin_query.filter(or_(*country_conditions))

    if date_from:
        try:
            date_from_dt = datetime.strptime(date_from, '%Y-%m-%d')
            admin_query = admin_query.filter(AdminActionLog.timestamp >= date_from_dt)
        except ValueError:
            flash(f"Invalid date format for 'from' date: {date_from}. Expected YYYY-MM-DD", "warning")

    if date_to:
        try:
            date_to_dt = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
            admin_query = admin_query.filter(AdminActionLog.timestamp < date_to_dt)
        except ValueError:
            flash(f"Invalid date format for 'to' date: {date_to}. Expected YYYY-MM-DD", "warning")

    MAX_ADMIN_ROWS = 5000
    # Page-view-only view has no admin_action rows with consolidated type page_view
    if session_row and activity_type and set(activity_type) == {'page_view'}:
        admin_actions = []
    else:
        admin_actions = admin_query.order_by(AdminActionLog.timestamp.desc()).limit(MAX_ADMIN_ROWS).all()
    for action in admin_actions:
        action_id = f'admin_{action.id}'
        if action_id not in processed_ids:
            processed_ids.add(action_id)

            # Consolidate and create consistent data immediately
            consolidated_type = consolidate_activity_type(None, action.action_type)
            consistent_desc = create_consistent_description(
                'admin_action',
                None,
                action.action_type,
                action.action_description,
                action.endpoint,
                action.new_values or action.old_values,
            )

            entity_type, entity_id, entity_name = extract_entity_info('admin_action', action.new_values or action.old_values, admin_action=action)

            details_payload = format_admin_action_details(
                action.action_type, action.old_values, action.new_values
            )
            if details_payload is None:
                details_payload = action.old_values or action.new_values

            entries.append({
                'id': action_id,
                'type': 'admin_action',
                'timestamp': action.timestamp,
                'user': action.admin_user,
                'user_email': action.admin_user.email if action.admin_user else None,
                'action_type': action.action_type,
                'consolidated_activity_type': consolidated_type,
                'description': action.action_description,
                'consistent_description': consistent_desc,
                'endpoint': action.endpoint,
                'ip_address': action.ip_address,
                'risk_level': action.risk_level,
                'requires_review': action.requires_review,
                'target_type': action.target_type,
                'target_description': action.target_description,
                'details': details_payload,
                'entity_type': entity_type,
                'entity_id': entity_id,
                'entity_name': entity_name,
                'user_session_id': None,
            })

    # Apply activity type filter after consolidation (same logic with or without session_id)
    if activity_type:
        entries = [entry for entry in entries if entry['consolidated_activity_type'] in activity_type]
    else:
        entries = [entry for entry in entries if entry['consolidated_activity_type'] != 'page_view']

    # Sort all entries by timestamp (most recent first)
    entries.sort(key=lambda x: x['timestamp'], reverse=True)

    total_entries = len(entries)
    logger.info("[audit_trail] total=%d entries passed to AG-Grid", total_entries)

    # Get filter options - create consolidated activity types directly
    activity_types_query = UserActivityLog.query.with_entities(
        func.distinct(UserActivityLog.activity_type)
    ).all()
    raw_activity_types = [t[0] for t in activity_types_query if t[0]]

    action_types_query = AdminActionLog.query.with_entities(
        func.distinct(AdminActionLog.action_type)
    ).all()
    raw_action_types = [t[0] for t in action_types_query if t[0]]

    # Create consolidated activity types for dropdown
    consolidated_types = set()
    for activity_type_val in raw_activity_types:
        consolidated_types.add(consolidate_activity_type(activity_type_val))
    for action_type_val in raw_action_types:
        consolidated_types.add(consolidate_activity_type(None, action_type_val))

    # Convert to sorted list
    activity_types = sorted(list(consolidated_types))
    action_types = []  # We're consolidating everything into activity_types

    # Get all countries for dropdown
    countries = Country.query.order_by(Country.name).all()

    # Return JSON for API requests (mobile app) — paginated server-side
    if is_json_request():
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_entries = entries[start_idx:end_idx]
        total_pages = (total_entries + per_page - 1) // per_page if per_page else 1
        entries_data = []
        for entry in paginated_entries:
            entries_data.append({
                'id': entry.get('id'),
                'type': entry.get('type'),
                'timestamp': entry['timestamp'].isoformat() if entry.get('timestamp') else None,
                'user_email': entry.get('user_email'),
                'user_name': entry.get('user', {}).name if hasattr(entry.get('user'), 'name') else None,
                'activity_type': entry.get('consolidated_activity_type'),
                'description': entry.get('consistent_description'),
                'endpoint': entry.get('endpoint'),
                'ip_address': entry.get('ip_address'),
                'risk_level': entry.get('risk_level'),
                'requires_review': entry.get('requires_review', False),
                'entity_type': entry.get('entity_type'),
                'entity_id': entry.get('entity_id'),
                'entity_name': entry.get('entity_name'),
                'details': entry.get('details'),
                'user_session_id': entry.get('user_session_id'),
            })
        return json_ok(
            success=True,
            entries=entries_data,
            count=len(entries_data),
            total=total_entries,
            page=page,
            pages=total_pages,
            activity_types=activity_types,
        )

    users = User.query.order_by(User.email).all()

    AUDIT_TRAIL_SESSION_CHOICE_LIMIT = 750
    recent_session_logs = (
        UserSessionLog.query.options(joinedload(UserSessionLog.user))
        .order_by(desc(UserSessionLog.session_start))
        .limit(AUDIT_TRAIL_SESSION_CHOICE_LIMIT)
        .all()
    )
    if filters_session_id:
        try:
            fid = int(str(filters_session_id).strip())
            ids_present = {s.id for s in recent_session_logs}
            if fid > 0 and fid not in ids_present:
                extra = (
                    UserSessionLog.query.options(joinedload(UserSessionLog.user))
                    .filter_by(id=fid)
                    .first()
                )
                if extra:
                    recent_session_logs = [extra] + [
                        s for s in recent_session_logs if s.id != extra.id
                    ]
                    recent_session_logs = recent_session_logs[:AUDIT_TRAIL_SESSION_CHOICE_LIMIT]
        except (ValueError, TypeError):
            pass

    return render_template(
        'admin/analytics/audit_trail.html',
        entries=entries,
        activity_types=activity_types,
        action_types=action_types,
        countries=countries,
        users=users,
        recent_session_logs=recent_session_logs,
        filters={
            'user': user_filter,
            'activity_type': activity_type,
            'risk_level': risk_level,
            'country': country_filter,
            'endpoint': endpoint_filter,
            'description': description_filter,
            'date_from': date_from,
            'date_to': date_to,
            'requires_review': requires_review,
            'session_id': filters_session_id,
        }
    )


@bp.route("/activity-endpoint-catalog")
@permission_required("admin.analytics.view")
def activity_endpoint_catalog():
    """
    Read-only browser for ENDPOINT_ACTIVITY_SPECS (automatic UserActivityLog descriptions).
    GET routes are omitted from the catalog; session page_views are tracked separately.

    Description text uses ``catalog_display_description`` so wording tracks
    ``defaults.py`` without requiring a server restart after regenerating partials.
    """
    from app.utils.activity_endpoint_catalog import ENDPOINT_ACTIVITY_SPECS
    from app.utils.activity_endpoint_catalog.defaults import catalog_display_description

    q = (request.args.get("q") or "").strip().lower()

    rows = []
    for (method, endpoint), spec in sorted(
        ENDPOINT_ACTIVITY_SPECS.items(),
        key=lambda item: (item[0][1].lower(), item[0][0]),
    ):
        desc = catalog_display_description(method, endpoint) or (spec.description or "")
        at = spec.activity_type or ""
        if q:
            hay = " ".join((method, endpoint, desc, at)).lower()
            if q not in hay:
                continue
        rows.append(
            {
                "method": method,
                "endpoint": endpoint,
                "description": desc,
                "activity_type": at,
            }
        )

    if request.args.get("export") == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                _("Method"),
                _("Endpoint"),
                _("Description"),
                _("Activity type"),
            ]
        )
        for r in rows:
            writer.writerow(
                [r["method"], r["endpoint"], r["description"], r["activity_type"]]
            )
        data = buf.getvalue()
        return Response(
            "\ufeff" + data,
            mimetype="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": "attachment; filename=activity_endpoint_catalog.csv"
            },
        )

    return render_template(
        "admin/analytics/activity_endpoint_catalog.html",
        rows=rows,
        total_catalog=len(ENDPOINT_ACTIVITY_SPECS),
        filtered_count=len(rows),
        q=request.args.get("q") or "",
    )
