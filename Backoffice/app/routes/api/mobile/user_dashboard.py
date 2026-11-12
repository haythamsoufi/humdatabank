# Backoffice/app/routes/api/mobile/user_dashboard.py
"""User-facing dashboard (assignments + entities) for mobile JWT clients."""

import json as _json

from flask import Response
from app.routes.api.mobile import mobile_bp
from app.utils.mobile.mobile_auth import mobile_auth_required
from app.utils.mobile.mobile_responses import mobile_ok, mobile_server_error
from app.routes.api.users import get_dashboard, get_dashboard_offline_entities


def _wrap_inner(inner, error_fallback):
    """Turn a ``/api/v1`` JSON view result into the mobile envelope."""
    if isinstance(inner, tuple):
        resp_obj, status = inner[0], inner[1]
    else:
        resp_obj, status = inner, 200

    if isinstance(resp_obj, Response):
        data = _json.loads(resp_obj.get_data(as_text=True))
    else:
        data = resp_obj

    if status != 200:
        from app.utils.mobile.mobile_responses import mobile_error
        return mobile_error(data.get('error', error_fallback), int(status))

    return mobile_ok(data=data)


@mobile_bp.route('/user/dashboard', methods=['GET'])
@mobile_auth_required
def mobile_user_dashboard():
    """
    Focal-point dashboard: same payload as ``GET /api/v1/dashboard``
    (``current_assignments``, ``past_assignments``, ``entities``, ``selected_entity``)
    but reachable with ``Authorization: Bearer`` mobile JWT and wrapped in the
    standard ``{success: true, data: {...}}`` mobile envelope.
    """
    try:
        return _wrap_inner(get_dashboard(), 'Dashboard unavailable.')
    except Exception as e:
        from flask import current_app
        current_app.logger.error("mobile_user_dashboard: %s", e, exc_info=True)
        return mobile_server_error()


@mobile_bp.route('/user/dashboard/offline-entities', methods=['GET'])
@mobile_auth_required
def mobile_user_dashboard_offline_entities():
    """
    Assignments and contacts of every entity the user can select (optionally only
    of the given ``template_ids``), so the app can keep all of them available offline
    after downloading a form template once. See ``get_dashboard_offline_entities``.
    """
    try:
        return _wrap_inner(
            get_dashboard_offline_entities(), 'Offline dashboards unavailable.'
        )
    except Exception as e:
        from flask import current_app
        current_app.logger.error("mobile_user_dashboard_offline_entities: %s", e, exc_info=True)
        return mobile_server_error()
