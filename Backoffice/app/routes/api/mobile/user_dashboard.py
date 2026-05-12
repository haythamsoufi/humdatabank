# Backoffice/app/routes/api/mobile/user_dashboard.py
"""User-facing dashboard (assignments + entities) for mobile JWT clients."""

import json as _json

from flask import Response
from app.routes.api.mobile import mobile_bp
from app.utils.mobile_auth import mobile_auth_required
from app.utils.mobile_responses import mobile_ok, mobile_server_error
from app.routes.api.users import get_dashboard


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
        inner = get_dashboard()
        if isinstance(inner, tuple):
            resp_obj, status = inner[0], inner[1]
        else:
            resp_obj, status = inner, 200

        if isinstance(resp_obj, Response):
            data = _json.loads(resp_obj.get_data(as_text=True))
        else:
            data = resp_obj

        if status != 200:
            from app.utils.mobile_responses import mobile_error
            return mobile_error(
                data.get('error', 'Dashboard unavailable.'),
                int(status),
            )

        return mobile_ok(data=data)
    except Exception as e:
        from flask import current_app
        current_app.logger.error("mobile_user_dashboard: %s", e, exc_info=True)
        return mobile_server_error()
