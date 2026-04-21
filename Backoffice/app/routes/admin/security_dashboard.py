# Security Dashboard Routes
from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import current_user
from app.routes.admin.shared import admin_required, permission_required
from app.services.security.monitoring import get_security_metrics, log_security_event
from app.models import SecurityEvent, AdminActionLog
from app import db
from datetime import datetime, timedelta
from sqlalchemy import desc
from app.utils.datetime_helpers import utcnow
from app.utils.api_responses import json_ok

bp = Blueprint('security', __name__, url_prefix='/admin')

@bp.route('/security/dashboard')
@permission_required('admin.security.view')
def security_dashboard():
    """Security dashboard for administrators."""
    # Get security metrics for the last 7 days
    metrics = get_security_metrics(days=7)

    # Get recent security events
    recent_events = SecurityEvent.query.filter(
        SecurityEvent.severity.in_(['high', 'critical'])
    ).order_by(desc(SecurityEvent.timestamp)).limit(10).all()

    # Get recent admin actions
    recent_admin_actions = AdminActionLog.query.filter(
        AdminActionLog.risk_level.in_(['high', 'critical'])
    ).order_by(desc(AdminActionLog.timestamp)).limit(10).all()

    return render_template('admin/security/dashboard.html',
                         metrics=metrics,
                         recent_events=recent_events,
                         recent_admin_actions=recent_admin_actions)

@bp.route('/security/events')
@permission_required('admin.security.view')
def security_events():
    """View all security events."""
    from app.utils.api_pagination import validate_pagination_params
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

    # Use the existing security_events.html template from analytics
    return render_template('admin/analytics/security_events.html',
                         events=events,
                         filters={
                             'severity': severity,
                             'event_type': event_type,
                             'unresolved_only': unresolved_only
                         })

@bp.route('/security/events/<int:event_id>/resolve', methods=['POST'])
@permission_required('admin.security.respond')
def resolve_security_event(event_id):
    """Resolve a security event."""
    event = SecurityEvent.query.get_or_404(event_id)

    if event.is_resolved:
        flash('This security event is already resolved.', 'info')
        return redirect(url_for('security.security_events'))

    # Mark as resolved
    event.is_resolved = True
    event.resolved_by_user_id = current_user.id
    event.resolved_at = utcnow()
    event.resolution_notes = request.form.get('resolution_notes', '')

    db.session.flush()

    flash(f'Security event {event_id} has been resolved.', 'success')
    return redirect(url_for('security.security_events'))

@bp.route('/security/events/<int:event_id>')
@permission_required('admin.security.view')
def security_event_detail(event_id):
    """View details of a specific security event."""
    event = SecurityEvent.query.get_or_404(event_id)

    # Get related events (same IP, similar type, etc.)
    related_events = SecurityEvent.query.filter(
        SecurityEvent.id != event_id,
        SecurityEvent.ip_address == event.ip_address,
        SecurityEvent.timestamp >= event.timestamp - timedelta(days=7)
    ).order_by(desc(SecurityEvent.timestamp)).limit(5).all()

    return render_template('admin/security/event_detail.html',
                         event=event,
                         related_events=related_events)

@bp.route('/security/alerts')
@permission_required('admin.security.view')
def security_alerts():
    """View active security alerts."""
    # Get unresolved high/critical severity events
    alerts = SecurityEvent.query.filter(
        SecurityEvent.severity.in_(['high', 'critical']),
        SecurityEvent.is_resolved == False
    ).order_by(desc(SecurityEvent.timestamp)).all()

    return render_template('admin/security/alerts.html', alerts=alerts)

@bp.route('/security/settings')
@permission_required('admin.security.view')
def security_settings():
    """Security configuration settings."""
    return render_template('admin/security/settings.html')

@bp.route('/security/test-alert', methods=['POST'])
@permission_required('admin.security.respond')
def test_security_alert():
    """Test security alerting system."""
    try:
        log_security_event(
            event_type='test_alert',
            severity='medium',
            description='Test security alert triggered by administrator',
            context_data={
                'triggered_by': current_user.email,
                'timestamp': utcnow().isoformat()
            },
            user_id=current_user.id
        )

        flash('Test security alert sent successfully.', 'success')
    except Exception as e:
        flash("An error occurred. Please try again.", "danger")

    return redirect(url_for('security.security_dashboard'))

@bp.route('/api/security/metrics')
@permission_required('admin.security.view')
def api_security_metrics():
    """API endpoint for security metrics."""
    days = request.args.get('days', 7, type=int)
    metrics = get_security_metrics(days=days)
    return json_ok(**metrics) if isinstance(metrics, dict) else json_ok(data=metrics)
