# Backoffice/app/routes/api/mobile/analytics.py
"""Client-side analytics ingestion for the mobile app."""

import time

from flask import current_app, g, request, session as flask_session
from flask_login import current_user

from app.utils.mobile_auth import mobile_auth_required
from app.utils.mobile_responses import mobile_ok, mobile_bad_request
from app.utils.rate_limiting import mobile_rate_limit
from app.routes.api.mobile import mobile_bp

# Per-user dedup cache: user_id -> (screen_name, route_path, timestamp)
_recent_screen_views: dict[int, tuple[str, str, float]] = {}
_DEDUP_WINDOW_SECONDS = 2.0


def _is_duplicate(user_id: int, screen_name: str, route_path: str | None) -> bool:
    """Return True if this screen was already logged within the dedup window."""
    entry = _recent_screen_views.get(user_id)
    if entry is None:
        return False
    prev_screen, prev_route, prev_time = entry
    rp = (route_path or "").strip()
    if prev_screen != screen_name or prev_route != rp:
        return False
    return (time.time() - prev_time) < _DEDUP_WINDOW_SECONDS


@mobile_bp.route('/analytics/screen-view', methods=['POST'])
@mobile_rate_limit(requests_per_minute=60)
@mobile_auth_required
def screen_view():
    """Update session page-view histogram for a mobile screen (no UserActivityLog row)."""
    from app.services.user_analytics_service import (
        increment_session_page_views_without_activity_log_deferred,
    )

    data = request.get_json(silent=True) or {}
    screen_name = (data.get('screen_name') or '').strip()
    if not screen_name:
        return mobile_bad_request('screen_name is required')

    route_path = (data.get('route_path') or '').strip() or None
    route_key = (route_path or "").strip()

    user_id = current_user.id
    if _is_duplicate(user_id, screen_name, route_path):
        return mobile_ok()

    _recent_screen_views[user_id] = (screen_name, route_key, time.time())

    session_id = (
        flask_session.get('session_id')
        or getattr(g, '_mobile_jwt_sid', None)
    )
    # JWT may omit `sid` on some token pairs; still attach histogram to an active row.
    if not session_id:
        from app.models import UserSessionLog

        row = (
            UserSessionLog.query.filter_by(
                user_id=user_id,
                is_active=True,
            )
            .order_by(UserSessionLog.last_activity.desc())
            .first()
        )
        if row:
            session_id = row.session_id

    try:
        from app.utils.page_view_paths import mobile_page_view_path_key

        path_key = mobile_page_view_path_key(screen_name, route_path=route_path)
        increment_session_page_views_without_activity_log_deferred(
            session_id, page_view_path_key=path_key
        )
    except Exception as e:
        current_app.logger.warning('mobile screen_view logging failed: %s', e)

    return mobile_ok()
