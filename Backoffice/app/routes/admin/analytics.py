from app.utils.transactions import request_transaction_rollback
from app.utils.datetime_helpers import utcnow
from app.utils.sql_utils import safe_ilike_pattern
"""
Analytics Routes for Admin Dashboard

Provides routes for viewing user activity analytics, login logs,
session analytics, and security events.
"""

from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import current_user
from app import db
from app.routes.admin.shared import admin_permission_required, permission_required
from app.utils.request_utils import is_json_request
from app.models import (
    UserLoginLog, UserActivityLog, UserSessionLog, AdminActionLog,
    SecurityEvent, User, Country
)
from app.utils.user_analytics import (
    get_user_login_analytics, get_user_activity_analytics,
    get_security_events_summary, get_session_analytics, get_active_sessions_count,
    log_admin_action
)
from app.utils.activity_middleware import track_admin_action
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE
from app.utils.api_pagination import validate_pagination_params
from app.utils.api_responses import json_ok
from app.utils.activity_types import normalize_activity_type
from sqlalchemy import func, desc, and_, or_, cast, String
from datetime import datetime, timedelta
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

    return render_template(
        'admin/analytics/dashboard.html',
        login_analytics=login_analytics,
        activity_analytics=activity_analytics,
        security_summary=security_summary,
        top_users=top_users,
        recent_security_events=recent_security_events,
        session_stats=session_stats,
        selected_days=days
    )


@bp.route('/login-logs')
@permission_required('admin.analytics.view')
def login_logs():
    """View detailed login logs."""
    page, per_page = validate_pagination_params(request.args, default_per_page=50, max_per_page=100)

    # Filters
    user_filter = request.args.get('user')
    event_type = request.args.get('event_type')
    ip_filter = request.args.get('ip')
    suspicious_only = request.args.get('suspicious', type=bool)
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')

    # Build query
    query = UserLoginLog.query

    if user_filter:
        from app.utils.sql_utils import safe_ilike_pattern
        query = query.filter(UserLoginLog.email_attempted.ilike(safe_ilike_pattern(user_filter)))

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
            flash(f"Invalid date format for 'from' date: {date_from}. Expected YYYY-MM-DD", "warning")

    if date_to:
        try:
            date_to_dt = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(UserLoginLog.timestamp < date_to_dt)
        except ValueError:
            flash(f"Invalid date format for 'to' date: {date_to}. Expected YYYY-MM-DD", "warning")

    # Order by most recent first
    query = query.order_by(desc(UserLoginLog.timestamp))

    # Paginate
    logs = query.paginate(
        page=page, per_page=per_page, error_out=False
    )

    return render_template(
        'admin/analytics/login_logs.html',
        logs=logs,
        filters={
            'user': user_filter,
            'event_type': event_type,
            'ip': ip_filter,
            'suspicious_only': suspicious_only,
            'date_from': date_from,
            'date_to': date_to
        }
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
    """View user session logs."""
    page, per_page = validate_pagination_params(request.args, default_per_page=25, max_per_page=100)

    # Filters
    user_filter = request.args.get('user')
    active_only = request.args.get('active_only', type=bool)
    min_duration = request.args.get('min_duration', type=int)

    # Build query
    query = UserSessionLog.query.join(User)

    if user_filter:
        query = query.filter(User.email.ilike(safe_ilike_pattern(user_filter)))

    if active_only:
        query = query.filter(UserSessionLog.is_active == True)

    if min_duration:
        query = query.filter(UserSessionLog.duration_minutes >= min_duration)

    # Order by most recent first
    query = query.order_by(desc(UserSessionLog.session_start))

    # Paginate
    sessions = query.paginate(
        page=page, per_page=per_page, error_out=False
    )

    return render_template(
        'admin/analytics/sessions.html',
        sessions=sessions,
        filters={
            'user': user_filter,
            'active_only': active_only,
            'min_duration': min_duration
        }
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

    # Get recent sessions
    recent_sessions = UserSessionLog.query.filter_by(user_id=user_id).order_by(
        desc(UserSessionLog.session_start)
    ).limit(10).all()

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
    from app.utils.user_analytics import cleanup_inactive_sessions

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
    from app.utils.user_analytics import end_user_session
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
        from app.utils.user_analytics import add_session_to_blacklist
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
    page, per_page = validate_pagination_params(request.args, default_per_page=50, max_per_page=100)

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

    # Function to consolidate activity types (moved to top for reuse)
    def consolidate_activity_type(activity_type, action_type=None):
        """Consolidate activity types into canonical, user-friendly keys.

        New canonical types (produced by the updated middleware):
          form_saved, form_submitted, form_reopened, form_validated,
          data_modified, data_deleted, file_uploaded, page_view,
          login, logout, profile_update, data_export, account_created.

        Legacy types (kept for backward-compat with older DB rows):
          form_save  → form_saved
          form_submit → form_submitted
          data_update → data_modified
          data_delete → data_deleted
          file_upload → file_uploaded
        """
        if activity_type:
            normalized_activity_type = normalize_activity_type(activity_type)
            if normalized_activity_type:
                return normalized_activity_type
            if 'view' in activity_type.lower():
                return 'page_view'
            # Unknown types should be preserved for accurate auditing.
            return activity_type

        elif action_type:
            if 'view' in action_type.lower():
                return 'page_view'
            # Admin action types are passed through as-is (they already have
            # descriptive names like user_create, form_section_update, etc.)
            return action_type

        return 'unknown'

    # Function to create consistent descriptions
    def create_consistent_description(entry_type, activity_type, action_type, original_description, endpoint=None, context_data=None):
        """Create consistent, user-friendly descriptions for audit entries.

        Handles both new canonical activity types (form_saved, form_submitted,
        form_reopened, form_validated, data_modified, data_deleted, file_uploaded)
        and legacy types (form_save, form_submit, data_update, data_delete,
        file_upload) for backward compatibility with older DB rows.
        """

        # ── Helper: resolve template/assignment context from DB ────────────
        def _resolve_form_context(context_data, endpoint):
            """Return (template_name, assignment_name, country_name) from context."""
            template_name = assignment_name = country_name = None
            if not context_data or not isinstance(context_data, dict):
                return template_name, assignment_name, country_name
            try:
                form_data = context_data.get('form_data', {}) or {}
                aes_id = (
                    form_data.get('aes_id') or context_data.get('aes_id') or
                    form_data.get('assignment_id') or context_data.get('assignment_id')
                )
                template_id = form_data.get('template_id') or context_data.get('template_id')

                if not aes_id:
                    url_path = context_data.get('url_path') or context_data.get('endpoint', '')
                    if url_path:
                        import re
                        m = re.search(r'/enter_data/(\d+)', url_path)
                        if m:
                            aes_id = int(m.group(1))

                if aes_id:
                    from app.models import AssignmentEntityStatus
                    aes = AssignmentEntityStatus.query.get(aes_id)
                    if aes:
                        if aes.assigned_form and aes.assigned_form.template:
                            template_name = aes.assigned_form.template.name
                        assignment_name = aes.assigned_form.period_name if aes.assigned_form else None
                        if aes.country:
                            country_name = aes.country.name
                elif template_id:
                    from app.models import FormTemplate
                    tmpl = FormTemplate.query.get(template_id)
                    if tmpl:
                        template_name = tmpl.name
            except Exception as e:
                from flask import current_app
                current_app.logger.warning(f"Error resolving form context for description: {e}")
            return template_name, assignment_name, country_name

        # ── Helper: build form description with optional context ───────────
        def _form_desc(base_verb, context_data, endpoint, suffix=""):
            """'Saved / Submitted / Reopened … form data … for Country'"""
            template_name, assignment_name, country_name = _resolve_form_context(context_data, endpoint)
            parts = []
            if template_name:
                parts.append(f"'{template_name}'")
            if assignment_name:
                parts.append(f"({assignment_name})")
            if country_name:
                parts.append(f"for {country_name}")
            if parts:
                return f"{base_verb} {' '.join(parts)}{suffix}"
            # Fallback based on endpoint
            if endpoint and 'public' in endpoint:
                return f"{base_verb} data via public link{suffix}"
            return f"{base_verb} form data{suffix}"

        # ── Helper: friendly page name from endpoint ────────────────────────
        def _page_name(endpoint):
            if not endpoint:
                return "page"
            # 'analytics.audit_trail' → 'Audit Trail'
            part = endpoint.split('.')[-1] if '.' in endpoint else endpoint
            return part.replace('_', ' ').title()

        # ── Activity log entries ────────────────────────────────────────────
        if entry_type == 'activity':
            t = activity_type or ''

            # Page views
            if t == 'page_view' or 'view' in t.lower():
                # If the stored description is already friendly (from new middleware), use it
                if original_description and original_description.startswith('Viewed '):
                    return original_description
                return f"Viewed {_page_name(endpoint)}"

            # Generic POST / API (canonical type `request` from activity middleware)
            if t == 'request':
                if original_description and original_description.startswith('Performed '):
                    return original_description
                return original_description or "Performed an action"

            # Form saved (new type) or legacy form_save
            if t in ('form_saved', 'form_save'):
                return _form_desc("Saved", context_data, endpoint, " as draft")

            # Form submitted (new type) or legacy form_submit
            if t in ('form_submitted', 'form_submit'):
                return _form_desc("Submitted", context_data, endpoint, " for review")

            # Form approved
            if t == 'form_approved':
                template_name, assignment_name, country_name = _resolve_form_context(context_data, endpoint)
                parts = []
                if template_name:
                    parts.append(f"'{template_name}'")
                if country_name:
                    parts.append(f"for {country_name}")
                suffix = f" ({' '.join(parts)})" if parts else ""
                return f"Approved form submission{suffix}"

            # Form reopened
            if t == 'form_reopened':
                template_name, assignment_name, country_name = _resolve_form_context(context_data, endpoint)
                parts = []
                if template_name:
                    parts.append(f"'{template_name}'")
                if country_name:
                    parts.append(f"for {country_name}")
                suffix = f" ({' '.join(parts)})" if parts else ""
                return f"Reopened form for editing{suffix}"

            # Form validated / approved
            if t == 'form_validated':
                template_name, assignment_name, country_name = _resolve_form_context(context_data, endpoint)
                parts = []
                if template_name:
                    parts.append(f"'{template_name}'")
                if country_name:
                    parts.append(f"for {country_name}")
                suffix = f" ({' '.join(parts)})" if parts else ""
                return f"Validated form data{suffix}"

            # Data modified (new) / legacy data_update
            if t in ('data_modified', 'data_update'):
                return original_description if original_description else "Updated data"

            # Data deleted (new) / legacy data_delete
            if t in ('data_deleted', 'data_delete'):
                return original_description if original_description else "Deleted item"

            # File uploaded (new) / legacy file_upload
            if t in ('file_uploaded', 'file_upload'):
                return "Uploaded a file"

            if t == 'login':
                return "Logged in"
            if t == 'logout':
                return "Logged out"
            if t == 'profile_update':
                return "Updated profile settings"
            if t == 'data_export':
                return "Exported data"
            if t == 'account_created':
                return "Account created"

            return original_description or "User activity"

        # ── Admin action log entries ────────────────────────────────────────
        else:
            if not action_type:
                return original_description or "Admin action"
            if 'view' in action_type.lower():
                base = action_type.replace('_', ' ').replace('view ', '').strip()
                return original_description or f"Viewed {base.title()}"
            # Use stored description when available (admin actions usually have good ones)
            if original_description:
                return original_description
            return action_type.replace('_', ' ').title()

    # Function to extract country information
    def extract_entity_info(entry_type, context_data, details=None, admin_action=None):
        """Extract entity information (country, NS branch, etc.) from log context.

        Returns (entity_type, entity_id, entity_name) for activity logs.
        Falls back to country-only info for admin action logs (which only store country_id).
        All three values may be None if no entity info is present.
        """
        entity_type = None
        entity_id = None
        entity_name = None

        try:
            if entry_type == 'activity' and context_data and isinstance(context_data, dict):
                # New fields written by the updated middleware
                entity_type = context_data.get('entity_type')
                entity_id = context_data.get('entity_id')
                entity_name = context_data.get('entity_name')

                # Fall back to legacy country_* fields (old DB rows or approve/reopen context)
                if not entity_id:
                    cid = context_data.get('country_id')
                    cname = context_data.get('country_name')
                    if not cid:
                        form_data = context_data.get('form_data', {}) or {}
                        cid = form_data.get('country_id')
                        cname = cname or form_data.get('country_name')
                    if cid:
                        entity_type = 'country'
                        entity_id = cid
                        entity_name = cname

                # Resolve name from DB if still missing
                if entity_id and not entity_name and entity_type:
                    try:
                        from app.services.entity_service import EntityService
                        entity_name = EntityService.get_entity_display_name(entity_type, int(entity_id))
                    except Exception:
                        pass

            elif entry_type == 'admin_action':
                # Admin action logs store country_id in new_values / old_values
                cid = None
                cname = None
                if details and isinstance(details, dict):
                    cid = details.get('country_id')
                    cname = details.get('country_name')
                if not cid and admin_action:
                    for vals in [admin_action.new_values, admin_action.old_values]:
                        if vals and isinstance(vals, dict):
                            cid = vals.get('country_id')
                            if cid:
                                cname = vals.get('country_name')
                                break
                            cids = vals.get('country_ids')
                            if cids and isinstance(cids, list) and len(cids) == 1:
                                cid = cids[0]
                                break
                    if not cid and admin_action.target_type == 'country' and admin_action.target_id:
                        cid = admin_action.target_id
                if cid:
                    entity_type = 'country'
                    entity_id = cid
                    if not cname:
                        try:
                            country = Country.query.get(int(cid))
                            cname = country.name if country else None
                        except Exception:
                            pass
                    entity_name = cname

        except Exception as e:
            from flask import current_app
            current_app.logger.warning(f"Error extracting entity info: {str(e)}")

        return entity_type, entity_id, entity_name

    # Limit date range to prevent loading excessive data (default to last 90 days if no date filter)
    # This prevents memory issues with very large datasets
    if not date_from:
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

    # Exclude specific endpoints/activities from audit trail
    # Exclude presence heartbeat activities (by activity type or endpoint name)
    activity_query = activity_query.filter(
        ~(
            (UserActivityLog.activity_type == 'presence_heartbeat') |
            (UserActivityLog.endpoint == 'forms_api.api_presence_heartbeat')
        )
    )

    # Exclude api_usage activities
    activity_query = activity_query.filter(
        ~(UserActivityLog.activity_type == 'api_usage')
    )

    # Exclude AI workflows endpoints (check both endpoint and url_path)
    activity_query = activity_query.filter(
        ~(
            (UserActivityLog.endpoint.ilike('/api/ai/documents/workflows%')) |
            (UserActivityLog.url_path.ilike('/api/ai/documents/workflows%'))
        )
    )

    # Exclude lookup-lists endpoints (check both endpoint and url_path)
    activity_query = activity_query.filter(
        ~(
            (UserActivityLog.endpoint.ilike('/api/forms/lookup-lists/reporting_currency/options%')) |
            (UserActivityLog.url_path.ilike('/api/forms/lookup-lists/reporting_currency/options%'))
        )
    )

    # Exclude forms.search_matrix_rows endpoint
    activity_query = activity_query.filter(
        ~(UserActivityLog.endpoint == 'forms.search_matrix_rows')
    )

    # Exclude notifications.mark_notifications_read endpoints
    activity_query = activity_query.filter(
        ~(
            (UserActivityLog.endpoint == 'notifications.mark_notifications_read') |
            (UserActivityLog.endpoint == 'main.mark_notifications_read')
        )
    )

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
    for log in activity_logs:
        log_id = f'activity_{log.id}'
        if log_id not in processed_ids:
            processed_ids.add(log_id)

            # Consolidate and create consistent data immediately
            consolidated_type = consolidate_activity_type(log.activity_type)

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
                enhanced_context
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
            })

    # Build single admin query with all conditions
    # Apply date filter to prevent loading excessive data
    admin_query = AdminActionLog.query.join(User).filter(
        AdminActionLog.timestamp >= date_from_dt
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
                action.new_values or action.old_values
            )

            entity_type, entity_id, entity_name = extract_entity_info('admin_action', action.new_values or action.old_values, admin_action=action)

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
                'details': action.old_values or action.new_values,
                'entity_type': entity_type,
                'entity_id': entity_id,
                'entity_name': entity_name,
            })

    # Apply activity type filter after consolidation
    if activity_type:
        entries = [entry for entry in entries if entry['consolidated_activity_type'] in activity_type]
    else:
        # Default behavior: exclude page_view activities when no filter is specified
        entries = [entry for entry in entries if entry['consolidated_activity_type'] != 'page_view']

    # Sort all entries by timestamp (most recent first)
    entries.sort(key=lambda x: x['timestamp'], reverse=True)

    # Manual pagination
    total_entries = len(entries)
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_entries = entries[start_idx:end_idx]

    # Create pagination object
    class PaginationObject:
        def __init__(self, items, page, per_page, total):
            self.items = items
            self.page = page
            self.per_page = per_page
            self.total = total
            self.pages = (total + per_page - 1) // per_page
            self.has_prev = page > 1
            self.has_next = page < self.pages
            self.prev_num = page - 1 if self.has_prev else None
            self.next_num = page + 1 if self.has_next else None

        def iter_pages(self, left_edge=2, right_edge=2, left_current=2, right_current=3):
            last = self.pages
            for num in range(1, last + 1):
                if num <= left_edge or \
                   (num > self.page - left_current - 1 and num < self.page + right_current) or \
                   num > last - right_edge:
                    yield num

    audit_entries = PaginationObject(paginated_entries, page, per_page, total_entries)

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

    # Get all users for dropdown (though we're now using text input)
    # Return JSON for API requests (mobile app)
    if is_json_request():
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
            })
        return json_ok(
            success=True,
            entries=entries_data,
            count=len(entries_data),
            total=total_entries,
            page=page,
            pages=audit_entries.pages,
            activity_types=activity_types,
        )

    users = User.query.order_by(User.email).all()

    return render_template(
        'admin/analytics/audit_trail.html',
        entries=audit_entries,
        activity_types=activity_types,
        action_types=action_types,
        countries=countries,
        users=users,
        filters={
            'user': user_filter,
            'activity_type': activity_type,
            'risk_level': risk_level,
            'country': country_filter,
            'endpoint': endpoint_filter,
            'description': description_filter,
            'date_from': date_from,
            'date_to': date_to,
            'requires_review': requires_review
        }
    )
