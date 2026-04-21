from app.utils.datetime_helpers import utcnow
from flask import flash, redirect, url_for, render_template
from flask_babel import _
from app import db
from app.models import UserSessionLog
from app.routes.admin.shared import permission_required
from app.utils.error_handling import handle_view_exception
from sqlalchemy import and_, inspect
from datetime import timedelta

from app.routes.admin.utilities import bp


# === Session Management Routes ===
@bp.route("/utilities/sessions/cleanup", methods=["POST"])
@permission_required('admin.analytics.view')
def cleanup_sessions():
    """Cleanup expired sessions"""
    try:
        timeout_threshold = utcnow() - timedelta(hours=2)

        if inspect(db.engine).has_table(UserSessionLog.__tablename__):
            expired_sessions = UserSessionLog.query.filter(
                and_(
                    UserSessionLog.last_activity < timeout_threshold,
                    UserSessionLog.ended_at.is_(None)
                )
            ).all()

            for session in expired_sessions:
                session.ended_at = utcnow()
                session.end_reason = 'timeout'

            db.session.flush()

            flash(_("Cleaned up %(count)d expired sessions.", count=len(expired_sessions)), "success")
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
                UserSessionLog.ended_at.is_(None)
            ).order_by(UserSessionLog.last_activity.desc()).all()

            for session in active_sessions:
                sessions.append({
                    'id': session.id,
                    'user_id': session.user_id,
                    'user_name': session.user.name if session.user else 'Unknown',
                    'started_at': session.started_at,
                    'last_activity': session.last_activity,
                    'ip_address': getattr(session, 'ip_address', None),
                    'user_agent': getattr(session, 'user_agent', None)
                })

        return render_template("admin/utilities/all_sessions.html",
                             sessions=sessions,
                             title="All Active Sessions")

    except Exception as e:
        return handle_view_exception(e, _("Error retrieving session data."), redirect_endpoint="admin.admin_dashboard")
