from flask import flash, redirect, url_for, render_template
from flask_babel import _
from app import db
from app.models import UserSessionLog
from app.routes.admin.shared import permission_required
from app.utils.common.error_handling import handle_view_exception
from sqlalchemy import inspect

from app.routes.admin.utilities import bp


# === Session Management Routes ===
@bp.route("/utilities/sessions/cleanup", methods=["POST"])
@permission_required('admin.system.maintain')
def cleanup_sessions():
    """Cleanup expired sessions"""
    try:
        if inspect(db.engine).has_table(UserSessionLog.__tablename__):
            # Same routine as the scheduled job: closes rows completely (is_active,
            # session_end, ended_by, duration) using the configured timeouts. The
            # previous inline version stamped only session_end/ended_by, leaving rows
            # that were "Active" yet already ended, with no duration.
            from app.services.platform.user_analytics_service import cleanup_inactive_sessions

            count = cleanup_inactive_sessions()
            flash(_("Cleaned up %(count)d expired sessions.", count=count), "success")
        else:
            flash(_("Session tracking is not configured."), "warning")

    except Exception as e:
        return handle_view_exception(e, _("Error during session cleanup."), redirect_endpoint="admin.admin_dashboard")

    return redirect(url_for("admin.admin_dashboard"))

@bp.route("/utilities/sessions/show_all", methods=["GET"])
@permission_required('admin.analytics.view')
def show_all_sessions():
    """Show all active sessions"""
    try:
        sessions = []

        if inspect(db.engine).has_table(UserSessionLog.__tablename__):
            active_sessions = UserSessionLog.query.filter(
                UserSessionLog.is_active.is_(True)
            ).order_by(UserSessionLog.last_activity.desc()).all()

            for session in active_sessions:
                sessions.append({
                    'id': session.id,
                    'user_id': session.user_id,
                    'user_name': session.user.name if session.user else 'Unknown',
                    'started_at': session.session_start,
                    'last_activity': session.last_activity,
                    'ip_address': getattr(session, 'ip_address', None),
                    'user_agent': getattr(session, 'user_agent', None)
                })

        return render_template("admin/utilities/all_sessions.html",
                             sessions=sessions,
                             title="All Active Sessions")

    except Exception as e:
        return handle_view_exception(e, _("Error retrieving session data."), redirect_endpoint="admin.admin_dashboard")
