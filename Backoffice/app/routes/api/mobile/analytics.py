# Backoffice/app/routes/api/mobile/analytics.py
"""Client-side analytics ingestion for the mobile app."""

import time

from flask import current_app, g, request, session as flask_session
from flask_login import current_user

from app.utils.api.api_helpers import get_json_safe
from app.utils.mobile.mobile_auth import mobile_auth_required
from app.utils.mobile.mobile_responses import mobile_ok, mobile_bad_request
from app.utils.security.rate_limiting import mobile_rate_limit
from app.routes.api.mobile import mobile_bp

# Per-process dedup cache: key -> (screen_name, route_path, timestamp).
# The key is (user_id, session_id) so two devices of one user do not suppress each
# other's page views; entries older than the window are pruned once the cache grows.
_recent_screen_views: dict = {}
_DEDUP_WINDOW_SECONDS = 2.0
_DEDUP_CACHE_MAX_ENTRIES = 2000


def _prune_recent_screen_views(now: float) -> None:
    if len(_recent_screen_views) < _DEDUP_CACHE_MAX_ENTRIES:
        return
    stale = [
        key for key, (_s, _r, ts) in _recent_screen_views.items()
        if now - ts >= _DEDUP_WINDOW_SECONDS
    ]
    for key in stale:
        _recent_screen_views.pop(key, None)
    if len(_recent_screen_views) >= _DEDUP_CACHE_MAX_ENTRIES:
        _recent_screen_views.clear()


def _is_duplicate(user_id, screen_name: str, route_path: str | None) -> bool:
    """Return True if this screen was already logged within the dedup window.

    ``user_id`` is any hashable cache key (the route passes ``(user_id, session_id)``).
    """
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
    from app.services.platform.user_analytics_service import (
        increment_session_page_views_without_activity_log_deferred,
    )

    data = get_json_safe()
    screen_name = (data.get('screen_name') or '').strip()
    if not screen_name:
        return mobile_bad_request('screen_name is required')

    route_path = (data.get('route_path') or '').strip() or None
    route_key = (route_path or "").strip()

    user_id = current_user.id
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

    cache_key = (user_id, session_id)
    if _is_duplicate(cache_key, screen_name, route_path):
        return mobile_ok()

    now = time.time()
    _prune_recent_screen_views(now)
    _recent_screen_views[cache_key] = (screen_name, route_key, now)

    try:
        from app.utils.activity.page_view_paths import mobile_page_view_path_key

        path_key = mobile_page_view_path_key(screen_name, route_path=route_path)
        increment_session_page_views_without_activity_log_deferred(
            session_id, page_view_path_key=path_key
        )
    except Exception as e:
        current_app.logger.warning('mobile screen_view logging failed: %s', e)

    return mobile_ok()
