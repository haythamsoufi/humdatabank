"""Flask before_request and after_request hooks."""

from flask import current_app, redirect, request, session, url_for
from flask_login import current_user

from app.i18n import persist_queued_language_cookie, update_session_activity
from app.utils.activity_logging_skip import should_skip_activity_endpoint, should_skip_activity_path
from app.utils.api_responses import json_ok
from app.utils.datetime_helpers import utcnow
from app.utils.request_utils import (
    is_json_request,
    is_static_asset_request,
    mark_mobile_app_webview_embed_request,
    persist_mobile_app_embed_cookie,
)


def register_request_hooks(app):
    """Register all request lifecycle hooks on the application."""

    @app.before_request
    def serve_root_health_probe_fast_path():
        if request.path != '/' or request.method != 'GET' or current_user.is_authenticated:
            return None

        user_agent = (request.headers.get('User-Agent') or '').strip()
        accept = (request.headers.get('Accept') or '').strip()
        has_cookies = bool((request.headers.get('Cookie') or '').strip())

        if not user_agent and (not accept or accept == '*/*') and not has_cookies:
            return json_ok(
                status='healthy',
                service='backoffice-databank',
                timestamp=utcnow().isoformat(),
                path='/',
            )

        return None

    @app.before_request
    def track_request_memory():
        from app.services.monitoring.memory import log_request_memory
        log_request_memory()

    @app.after_request
    def track_request_memory_end(response):
        from app.services.monitoring.memory import log_request_memory_end
        log_request_memory_end()
        return response

    @app.before_request
    def track_request_performance():
        from app.services.monitoring.system import track_request_performance as _track
        _track()

    @app.after_request
    def track_request_performance_end(response):
        from app.services.monitoring.system import log_request_performance_end
        log_request_performance_end()
        return response

    @app.before_request
    def track_request_pressure():
        from app.utils.request_utils import is_static_asset_request as _is_static
        if _is_static():
            return
        from app.services.monitoring.request_pressure import record_traffic, track_pressure_start
        record_traffic()
        track_pressure_start()

    @app.before_request
    def track_slow_request_start():
        from app.services.monitoring.slow_requests import track_slow_request_start as _track
        _track()

    @app.after_request
    def track_request_pressure_end(response):
        from app.services.monitoring.request_pressure import track_pressure_end
        track_pressure_end()
        return response

    @app.after_request
    def track_slow_request_end(response):
        from app.services.monitoring.slow_requests import track_slow_request_end as _track_end
        _track_end()
        return response

    @app.teardown_request
    def track_request_pressure_teardown(exc):
        from app.services.monitoring.request_pressure import track_pressure_end
        track_pressure_end()

    @app.teardown_request
    def track_slow_request_teardown(exc):
        from app.services.monitoring.slow_requests import track_slow_request_teardown
        track_slow_request_teardown(exc)

    @app.after_request
    def clear_flashes_for_xhr(response):
        try:
            if is_json_request():
                session.pop('_flashes', None)
        except Exception as e:
            current_app.logger.debug("Failed to clear flashes for XHR: %s", e)
        return response

    @app.before_request
    def _mark_mobile_app_webview_embed():
        if is_static_asset_request():
            return None
        try:
            mark_mobile_app_webview_embed_request()
        except Exception as e:
            current_app.logger.debug("mark_mobile_app_webview_embed_request failed: %s", e)
        return None

    @app.after_request
    def _persist_mobile_app_embed_cookie(response):
        try:
            return persist_mobile_app_embed_cookie(response)
        except Exception as e:
            current_app.logger.debug("persist_mobile_app_embed_cookie failed: %s", e)
            return response

    @app.after_request
    def _persist_ui_language_cookie(response):
        return persist_queued_language_cookie(response)

    @app.before_request
    def _jwt_auth_from_bearer():
        from app.utils.request_utils import is_static_asset_request as _is_static
        if _is_static():
            return
        if not current_user.is_authenticated:
            from app.utils.mobile_auth import _try_jwt_auth
            _try_jwt_auth()

    @app.before_request
    def update_activity():
        if is_static_asset_request():
            return
        # Background polls (heartbeats, presence, CSRF refresh, notifications,
        # settings checks, etc.) must NOT reset the inactivity timer — they run
        # silently while the user may be away.  Only genuine user-facing page
        # navigations and form submissions should count as activity.
        if should_skip_activity_path(request.path):
            return
        if should_skip_activity_endpoint(request.endpoint):
            return
        if current_user.is_authenticated:
            update_session_activity()

    from app.middleware.api_tracker import track_api_request, track_api_response

    @app.before_request
    def _api_track_before_request():
        track_api_request()

    @app.after_request
    def _api_track_after_request(response):
        return track_api_response(response)
