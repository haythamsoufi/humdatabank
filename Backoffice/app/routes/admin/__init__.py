# File: Backoffice/app/routes/admin/__init__.py
from app.utils.datetime_helpers import utcnow
"""
Admin Module - Centralized registration of all admin blueprints
"""

from flask import Blueprint, render_template, current_app, request, url_for
from werkzeug.routing.exceptions import BuildError
from app.utils.api_responses import json_forbidden, json_not_found, json_ok, json_server_error
from flask_login import current_user
from app import db
from app.models import (
    User, Country, FormTemplate, AssignedForm, IndicatorBank, PublicSubmission,
    UserLoginLog, SecurityEvent, UserActivityLog, UserSessionLog, AssignmentEntityStatus, PublicSubmissionStatus
)
from app.routes.admin.shared import admin_required, admin_permission_required, permission_required, permission_required_any, system_manager_required
from app.utils.request_utils import is_json_request
from datetime import datetime, timedelta
from sqlalchemy import func, and_, or_, inspect, select
from app.services import get_platform_stats

# Import all admin module blueprints
from app.routes.admin.form_builder import bp as form_builder_bp
from app.routes.admin.user_management import bp as user_management_bp
from app.routes.admin.assignment_management import bp as assignment_management_bp
from app.routes.admin.content_management import bp as content_management_bp
from app.routes.admin.system_admin import bp as system_admin_bp
from app.routes.admin.analytics import bp as analytics_bp
from app.routes.admin.analytics_api import bp as analytics_api_bp
from app.routes.admin.utilities import bp as utilities_bp
from app.routes.admin.template_special import bp as template_special_bp
from app.routes.admin.settings import bp as settings_bp
from app.routes.admin.organization import bp as organization_bp
from app.routes.admin.monitoring import bp as monitoring_bp
from app.routes.admin.data_exploration import bp as data_exploration_bp
from app.routes.admin.api_management import bp as api_management_bp
from app.routes.admin.api_key_management import bp as api_key_management_bp
from app.routes.admin.security_dashboard import bp as security_dashboard_bp
from app.routes.admin.notifications import bp as admin_notifications_bp

# Admin documentation / onboarding (file-based markdown under Backoffice/docs)
from app.routes.admin.documentation import bp as admin_docs_bp

# Import plugin management route
from app.routes.admin.plugin_management import plugin_bp, plugin_static_bp, plugin_settings_bp

# Import AI management route
from app.routes.admin.ai_management import bp as ai_management_bp

# Import RBAC management route
from app.routes.admin.rbac_management import bp as rbac_management_bp
from app.routes.admin.governance_dashboard import bp as governance_dashboard_bp

# Create main admin blueprint
bp = Blueprint("admin", __name__, url_prefix="/admin")

# Register all sub-blueprints
def register_admin_blueprints(app):
    """Register all admin blueprints with the main application"""
    # Register the main admin blueprint first
    app.register_blueprint(bp)

    # Register sub-blueprints
    app.register_blueprint(form_builder_bp)
    app.register_blueprint(user_management_bp)
    app.register_blueprint(assignment_management_bp)
    app.register_blueprint(content_management_bp)
    app.register_blueprint(system_admin_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(analytics_api_bp)
    app.register_blueprint(utilities_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(template_special_bp)
    app.register_blueprint(organization_bp)
    app.register_blueprint(monitoring_bp)
    app.register_blueprint(data_exploration_bp)
    app.register_blueprint(api_management_bp)
    app.register_blueprint(api_key_management_bp)
    app.register_blueprint(security_dashboard_bp)
    app.register_blueprint(admin_notifications_bp)
    app.register_blueprint(admin_docs_bp)

    # Register plugin management blueprints
    app.register_blueprint(plugin_bp)
    app.register_blueprint(plugin_static_bp)
    app.register_blueprint(plugin_settings_bp)

    # Register AI management blueprint
    app.register_blueprint(ai_management_bp)

    # Register RBAC management blueprint
    app.register_blueprint(rbac_management_bp)

    # Register Governance dashboard blueprint
    app.register_blueprint(governance_dashboard_bp)

# Plugin management route
@bp.route("/plugins", methods=["GET"])
@admin_permission_required('admin.plugins.manage')
def plugin_management():
    """Plugin management dashboard"""
    # Return JSON for API requests (mobile app)
    if is_json_request():
        # Import plugin models if available
        try:
            from app.models.plugins import Plugin
            plugins = Plugin.query.all()
            plugins_data = []
            for plugin in plugins:
                plugins_data.append({
                    'id': plugin.id,
                    'name': plugin.name if hasattr(plugin, 'name') else None,
                    'description': plugin.description if hasattr(plugin, 'description') else None,
                    'is_active': plugin.is_active if hasattr(plugin, 'is_active') else False,
                    'version': plugin.version if hasattr(plugin, 'version') else None,
                })
            return json_ok(plugins=plugins_data, count=len(plugins_data))
        except ImportError:
            # If plugin model doesn't exist, return empty list
            return json_ok(plugins=[], count=0)

    return render_template("admin/plugin_management.html")


def _kobo_data_import_url_for_dashboard():
    """URL for the KoBo data-import wizard, or None if the route is not registered."""
    ep = "form_builder.kobo_data_import"
    if ep not in current_app.view_functions:
        return None
    try:
        return url_for(ep)
    except BuildError:
        return None


# Main admin dashboard route
@bp.route("/", methods=["GET"])
@admin_required
@system_manager_required
def admin_dashboard():
    """Main admin dashboard with overview statistics"""
    kobo_data_import_url = _kobo_data_import_url_for_dashboard()
    try:
        from app.services.authorization_service import AuthorizationService

        can_view_analytics = AuthorizationService.is_system_manager(current_user) or AuthorizationService.has_rbac_permission(current_user, 'admin.analytics.view')
        can_view_assignments = AuthorizationService.is_system_manager(current_user) or AuthorizationService.has_rbac_permission(current_user, 'admin.assignments.view')
        can_manage_public_submissions = AuthorizationService.is_system_manager(current_user) or AuthorizationService.has_rbac_permission(current_user, 'admin.assignments.public_submissions.manage')

        # Use service for platform statistics
        stats = get_platform_stats(user_scoped=False)  # Admin sees all stats

        # Extract counts from stats (note: service returns 'total_*' keys)
        user_count = stats.get('total_users', 0)
        country_count = stats.get('total_countries', 0)
        template_count = stats.get('total_templates', 0)
        indicator_bank_count = stats.get('total_indicators', 0)

        # Additional counts not in the service
        assignment_count = AssignedForm.query.count() if can_view_assignments else 0
        public_submission_count = PublicSubmission.query.count() if can_manage_public_submissions else 0

        # Recent activity (last 7 days)
        week_ago = utcnow() - timedelta(days=7)

        # Recent successful logins (analytics permission only)
        recent_logins = 0
        if can_view_analytics and inspect(db.engine).has_table(UserLoginLog.__tablename__):
            recent_logins = UserLoginLog.query.filter(
                and_(UserLoginLog.timestamp >= week_ago,
                     UserLoginLog.event_type == 'login_success')
            ).count()

        # Recent submissions
        recent_submissions = PublicSubmission.query.filter(
            PublicSubmission.submitted_at >= week_ago
        ).count()

        # Recent activities (last 7 days) (analytics permission only)
        recent_activities = 0
        if can_view_analytics and inspect(db.engine).has_table(UserActivityLog.__tablename__):
            recent_activities = UserActivityLog.query.filter(
                UserActivityLog.timestamp >= week_ago
            ).count()

        # Active users (logged in last 30 days) (analytics permission only)
        month_ago = utcnow() - timedelta(days=30)
        active_users = 0
        if can_view_analytics and inspect(db.engine).has_table(UserLoginLog.__tablename__):
            active_users = db.session.query(User.id).join(UserLoginLog).filter(
                and_(UserLoginLog.timestamp >= month_ago,
                     UserLoginLog.event_type == 'login_success')
            ).distinct().count()

        # Failed login attempts (last 24 hours) (analytics permission only)
        failed_logins_24h = 0
        if can_view_analytics and inspect(db.engine).has_table(SecurityEvent.__tablename__):
            day_ago = utcnow() - timedelta(days=1)
            failed_logins_24h = SecurityEvent.query.filter(
                and_(
                    SecurityEvent.event_type == 'failed_login',
                    SecurityEvent.timestamp >= day_ago
                )
            ).count()

        # Today's logins (analytics permission only)
        today_logins = 0
        if can_view_analytics and inspect(db.engine).has_table(UserLoginLog.__tablename__):
            today_start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            today_logins = UserLoginLog.query.filter(
                and_(UserLoginLog.timestamp >= today_start,
                     UserLoginLog.event_type == 'login_success')
            ).count()

        # Role stats
        role_stats = {'admin': 0, 'focal_point': 0}
        try:
            from app.models.rbac import RbacUserRole, RbacRole

            admin_role_ids = select(RbacRole.id).where(
                or_(
                    RbacRole.code == "system_manager",
                    RbacRole.code == "admin_core",
                    RbacRole.code.like("admin\\_%", escape="\\"),
                )
            )
            role_stats["admin"] = (
                db.session.query(User.id)
                .join(RbacUserRole, User.id == RbacUserRole.user_id)
                .filter(RbacUserRole.role_id.in_(admin_role_ids))
                .distinct()
                .count()
            )

            focal_role_id = select(RbacRole.id).where(
                RbacRole.code == "assignment_editor_submitter"
            )
            role_stats["focal_point"] = (
                db.session.query(User.id)
                .join(RbacUserRole, User.id == RbacUserRole.user_id)
                .filter(RbacUserRole.role_id.in_(focal_role_id))
                .distinct()
                .count()
            )
        except Exception as e:
            current_app.logger.debug("Role stats query failed: %s", e)
            role_stats = {'admin': 0, 'focal_point': 0}

        # Active sessions (analytics permission only)
        active_sessions = 0
        if can_view_analytics and inspect(db.engine).has_table(UserSessionLog.__tablename__):
            active_sessions = UserSessionLog.query.filter(
                or_(UserSessionLog.is_active == True, UserSessionLog.session_end.is_(None))
            ).count()

        # Unresolved security events (analytics permission only)
        unresolved_security_events = 0
        if can_view_analytics and inspect(db.engine).has_table(SecurityEvent.__tablename__):
            unresolved_security_events = SecurityEvent.query.filter_by(is_resolved=False).count()

        # Overdue assignments (country-level AES) (assignment permission only)
        overdue_assignments = 0
        if can_view_assignments:
            overdue_assignments = AssignmentEntityStatus.query.filter(
                and_(
                    AssignmentEntityStatus.entity_type == 'country',
                    AssignmentEntityStatus.due_date.isnot(None),
                    AssignmentEntityStatus.due_date < utcnow(),
                    AssignmentEntityStatus.status.in_(['Assigned', 'In Progress'])
                )
            ).count()

        # Pending public submissions (permission only)
        pending_public_submissions_count = 0
        if can_manage_public_submissions and inspect(db.engine).has_table(PublicSubmission.__tablename__):
            pending_public_submissions_count = PublicSubmission.query.filter(
                PublicSubmission.status == PublicSubmissionStatus.pending
            ).count()

        # Security audit metrics for dashboard widget
        security_audit_widget = {"high_risk_actions_30d": 0, "suspicious_logins_30d": 0, "failed_login_rate_30d": 0.0}
        if can_view_analytics:
            try:
                from app.services.governance_metrics_service import _get_security_audit_metrics
                security_audit_widget = _get_security_audit_metrics()
                db.session.rollback()
            except Exception as e:
                current_app.logger.debug("Security audit metrics failed: %s", e)
                db.session.rollback()

        # Translation coverage metrics for dashboard widget (load once in Python, no SQL JSON functions)
        translation_widget = {"avg_name_pct": 0.0, "avg_def_pct": 0.0, "by_lang": {}}
        try:
            from app.services.governance_metrics_service import _get_translation_metrics
            tr = _get_translation_metrics()
            db.session.rollback()
            if tr:
                avg_name = round(sum(v.get("name_pct", 0) for v in tr.values()) / len(tr), 1)
                avg_def  = round(sum(v.get("def_pct",  0) for v in tr.values()) / len(tr), 1)
                translation_widget = {"avg_name_pct": avg_name, "avg_def_pct": avg_def, "by_lang": tr}
        except Exception as e:
            current_app.logger.debug("Translation metrics failed: %s", e)
            db.session.rollback()

        return render_template("admin/dashboard.html",
                             user_count=user_count,
                             country_count=country_count,
                             template_count=template_count,
                             assignment_count=assignment_count,
                             indicator_bank_count=indicator_bank_count,
                             public_submission_count=public_submission_count,
                             recent_logins=recent_logins,
                             recent_submissions=recent_submissions,
                              recent_activities=recent_activities,
                             active_users=active_users,
                             failed_logins_24h=failed_logins_24h,
                              today_logins=today_logins,
                              role_stats=role_stats,
                              active_sessions=active_sessions,
                              unresolved_security_events=unresolved_security_events,
                             overdue_assignments=overdue_assignments,
                             pending_public_submissions_count=pending_public_submissions_count,
                             security_audit_widget=security_audit_widget,
                             translation_widget=translation_widget,
                             kobo_data_import_url=kobo_data_import_url,
                             title="Admin Dashboard")

    except Exception as e:
        current_app.logger.error(f"Error loading admin dashboard: {e}", exc_info=True)
        return render_template("admin/dashboard.html",
                             user_count=0,
                             country_count=0,
                             template_count=0,
                             assignment_count=0,
                             indicator_bank_count=0,
                             public_submission_count=0,
                              recent_logins=0,
                              recent_submissions=0,
                              recent_activities=0,
                             active_users=0,
                             failed_logins_24h=0,
                             today_logins=0,
                             role_stats={'admin': 0, 'focal_point': 0},
                             active_sessions=0,
                             unresolved_security_events=0,
                             overdue_assignments=0,
                             pending_public_submissions_count=0,
                             security_audit_widget={"high_risk_actions_30d": 0, "suspicious_logins_30d": 0, "failed_login_rate_30d": 0.0},
                             translation_widget={"avg_name_pct": 0.0, "avg_def_pct": 0.0, "by_lang": {}},
                             kobo_data_import_url=kobo_data_import_url,
                             title="Admin Dashboard",
                             dashboard_error="Error loading dashboard statistics")

# Template globals for admin module
@bp.app_template_global()
def user_has_permission(permission_name):
    """Template global for checking permissions"""
    if not current_user.is_authenticated:
        return False
    from app.services.authorization_service import AuthorizationService
    return AuthorizationService.has_rbac_permission(current_user, permission_name)

# Template global for getting localized sector name (from shared module)
@bp.app_template_global()
def get_localized_sector_name(sector):
    """Template global for getting localized sector name."""
    from app.routes.admin.shared import get_localized_sector_name as _get_localized_sector_name
    return _get_localized_sector_name(sector)

@bp.app_template_global()
def get_localized_subsector_name(subsector):
    """Template global for getting localized subsector name."""
    from app.routes.admin.shared import get_localized_subsector_name as _get_localized_subsector_name
    return _get_localized_subsector_name(subsector)

# Error handlers for admin module
@bp.errorhandler(403)
def admin_forbidden(error):
    """Handle 403 errors in admin module"""
    if is_json_request():
        return json_forbidden('Access Forbidden', success=False)
    return render_template("admin/error.html",
                         error_code=403,
                         error_message="Access Forbidden",
                         title="Access Denied"), 403

@bp.errorhandler(404)
def admin_not_found(error):
    """Handle 404 errors in admin module"""
    if is_json_request():
        return json_not_found('Page Not Found', success=False)
    return render_template("admin/error.html",
                         error_code=404,
                         error_message="Page Not Found",
                         title="Page Not Found"), 404

@bp.errorhandler(500)
def admin_internal_error(error):
    """Handle 500 errors in admin module"""
    if is_json_request():
        return json_server_error('Internal Server Error', success=False)
    return render_template("admin/error.html",
                         error_code=500,
                         error_message="Internal Server Error",
                         title="Server Error"), 500
