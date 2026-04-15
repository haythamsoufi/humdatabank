# Backoffice/app/routes/api/mobile/analytics.py
"""Client-side analytics ingestion for the mobile app."""

import time

from flask import current_app, g, request, session as flask_session
from flask_login import current_user

from app.utils.mobile_auth import mobile_auth_required
from app.utils.mobile_responses import mobile_ok, mobile_bad_request
from app.utils.rate_limiting import mobile_rate_limit
from app.routes.api.mobile import mobile_bp

# Per-user dedup cache: user_id -> (screen_name, timestamp)
_recent_screen_views: dict[int, tuple[str, float]] = {}
_DEDUP_WINDOW_SECONDS = 2.0


def _is_duplicate(user_id: int, screen_name: str) -> bool:
    """Return True if this screen was already logged within the dedup window."""
    entry = _recent_screen_views.get(user_id)
    if entry is None:
        return False
    prev_screen, prev_time = entry
    return prev_screen == screen_name and (time.time() - prev_time) < _DEDUP_WINDOW_SECONDS


@mobile_bp.route('/analytics/screen-view', methods=['POST'])
@mobile_rate_limit(requests_per_minute=60)
@mobile_auth_required
def screen_view():
    """Record a mobile screen view in the audit trail."""
    from app.services.user_analytics_service import (
        log_user_activity_explicit,
        get_client_ip,
    )

    data = request.get_json(silent=True) or {}
    screen_name = (data.get('screen_name') or '').strip()
    if not screen_name:
        return mobile_bad_request('screen_name is required')

    screen_class = (data.get('screen_class') or '').strip() or None
    route_path = (data.get('route_path') or '').strip() or None

    user_id = current_user.id
    if _is_duplicate(user_id, screen_name):
        return mobile_ok()

    _recent_screen_views[user_id] = (screen_name, time.time())

    session_id = (
        flask_session.get('session_id')
        or getattr(g, '_mobile_jwt_sid', None)
    )

    try:
        from app.utils.page_view_paths import mobile_page_view_path_key

        path_key = mobile_page_view_path_key(screen_name, route_path=route_path)
        description = f"Viewed {screen_name} (Mobile)"
        context_data = {
            'page_view_path_key': path_key,
            'method': 'POST',
            'status_code': 200,
            'source': 'mobile_app',
            'screen_name': screen_name,
        }
        if screen_class:
            context_data['screen_class'] = screen_class
        if route_path:
            context_data['route_path'] = route_path

        log_user_activity_explicit(
            user_id=user_id,
            session_id=session_id,
            activity_type='page_view',
            description=description,
            context_data=context_data,
            response_time_ms=None,
            status_code=200,
            endpoint=None,
            http_method='POST',
            url_path=path_key[:500] if path_key else request.path,
            referrer=None,
            ip_address=get_client_ip(),
            user_agent=request.headers.get('User-Agent'),
            page_view_path_key=path_key,
        )
    except Exception as e:
        current_app.logger.warning('mobile screen_view logging failed: %s', e)

    return mobile_ok()
