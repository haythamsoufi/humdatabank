# Backoffice/app/routes/api/mobile/__init__.py
"""
Dedicated mobile API surface — ``/api/mobile/v1/``.

All endpoints use JWT Bearer authentication via ``@mobile_auth_required``.
Responses use the standardized mobile envelope from ``app.utils.mobile_responses``.
"""

from flask import Blueprint, current_app, request

mobile_bp = Blueprint('mobile_api', __name__, url_prefix='/api/mobile/v1')


# ---------------------------------------------------------------------------
# Minimum app version enforcement
# ---------------------------------------------------------------------------

def _parse_version(version_str):
    """Parse a semver-like version string into a tuple for comparison."""
    try:
        return tuple(int(p) for p in version_str.strip().split('.'))
    except (ValueError, AttributeError):
        return ()


@mobile_bp.before_request
def _check_minimum_app_version():
    try:
        from app.services.app_settings_service import get_mobile_min_app_version

        min_version = get_mobile_min_app_version()
    except Exception:
        min_version = current_app.config.get("MOBILE_MIN_APP_VERSION")
    if not min_version:
        return None
    client_version = request.headers.get('X-App-Version', '')
    if not client_version:
        return None
    client_tuple = _parse_version(client_version)
    min_tuple = _parse_version(min_version)
    if client_tuple and min_tuple and client_tuple < min_tuple:
        from app.utils.mobile_responses import mobile_error
        return mobile_error(
            'This version of the app is no longer supported. Please update.',
            426,
            error_code='APP_UPDATE_REQUIRED',
        )
    return None


# Import sub-modules so their @mobile_bp.route decorators register with the blueprint.
from app.routes.api.mobile import (  # noqa: F401, E402
    analytics,
    auth,
    notifications,
    devices,
    admin_users,
    admin_requests,
    admin_analytics,
    admin_content,
    admin_org,
    public_data,
    user_dashboard,
)
