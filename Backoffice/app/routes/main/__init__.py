from flask import Blueprint
from flask import current_app
from flask_login import current_user

bp = Blueprint("main", __name__)


@bp.app_context_processor
def inject_rbac_helpers():
    """Inject RBAC helper functions into all templates"""
    from app.services.authorization_service import AuthorizationService

    def has_permission(permission_code, scope=None):
        """Check if current user has a specific RBAC permission"""
        try:
            return AuthorizationService.has_rbac_permission(current_user, permission_code, scope=scope)
        except Exception as e:
            current_app.logger.debug("has_rbac_permission failed: %s", e)
            return False

    def can_approve_assignment(aes):
        """Check if current user can approve an assignment"""
        try:
            return AuthorizationService.can_approve_assignment(aes, current_user)
        except Exception as e:
            current_app.logger.debug("can_approve_assignment failed: %s", e)
            return False

    def can_reopen_assignment(aes):
        """Check if current user can reopen an assignment"""
        try:
            return AuthorizationService.can_reopen_assignment(aes, current_user)
        except Exception as e:
            current_app.logger.debug("can_reopen_assignment failed: %s", e)
            return False

    def can_reopen_closed_assignment(assignment):
        """Check if current user can reopen a closed assignment (admin only)."""
        if not assignment:
            return False
        try:
            if AuthorizationService.is_system_manager(current_user):
                return True
            return AuthorizationService.has_rbac_permission(current_user, "admin.assignments.edit")
        except Exception as e:
            current_app.logger.debug("can_reopen_closed_assignment failed: %s", e)
            return False

    return dict(
        has_permission=has_permission,
        can_approve_assignment=can_approve_assignment,
        can_reopen_assignment=can_reopen_assignment,
        can_reopen_closed_assignment=can_reopen_closed_assignment
    )


# Import submodules to register routes on the blueprint.
# Each submodule imports `bp` from this package and decorates its routes.
from app.routes.main import helpers  # noqa: F401,E402
from app.routes.main import dashboard  # noqa: F401,E402
from app.routes.main import documents  # noqa: F401,E402
from app.routes.main import api  # noqa: F401,E402
from app.routes.main import assignments  # noqa: F401,E402
from app.routes.main import views  # noqa: F401,E402
