# Backoffice/app/routes/api/mobile/user_dashboard.py
"""User-facing dashboard (assignments + entities) for mobile JWT clients."""

from app.routes.api.mobile import mobile_bp
from app.utils.mobile_auth import mobile_auth_required
from app.routes.api.users import get_dashboard


@mobile_bp.route('/user/dashboard', methods=['GET'])
@mobile_auth_required
def mobile_user_dashboard():
    """
    Focal-point dashboard: same JSON body as ``GET /api/v1/dashboard``
    (``current_assignments``, ``past_assignments``, ``entities``, ``selected_entity``)
    but reachable with ``Authorization: Bearer`` mobile JWT.
    """
    return get_dashboard()
