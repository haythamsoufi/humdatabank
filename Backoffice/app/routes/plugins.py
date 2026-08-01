from flask import Blueprint, current_app, request
from flask_login import login_required, current_user
import json

from app.models.assignments import AssignmentEntityStatus
from app.services.organization.authorization_service import AuthorizationService
from app.utils.form_authorization import redirect_if_assignment_entry_blocked


bp = Blueprint("plugins_api", __name__, url_prefix="/api/plugins")


def _plugin_render_access_denied(message: str):
    return (
        f"<p class='text-red-500'>{message}</p>",
        403,
        {"Content-Type": "text/html"},
    )


def _check_plugin_field_render_access():
    """
    Ensure the caller may render a plugin entry template for the current form context.

    Admins with template view permission may render without an assignment id.
    Entry-form users must pass assignment_entity_status_id (or aes_id) and have
    assignment access for that entity.
    """
    if AuthorizationService.has_rbac_permission(current_user, "admin.templates.view"):
        return None

    aes_id = request.args.get("assignment_entity_status_id", type=int) or request.args.get("aes_id", type=int)
    if not aes_id:
        return _plugin_render_access_denied("Assignment context is required to render this field.")

    aes = AssignmentEntityStatus.query.get(aes_id)
    if aes is None:
        return (
            "<p class='text-red-500'>Assignment not found.</p>",
            404,
            {"Content-Type": "text/html"},
        )

    assigned_form = getattr(aes, "assigned_form", None)
    blocked = redirect_if_assignment_entry_blocked(
        assigned_form,
        inactive_message="This assignment is currently inactive and cannot be accessed.",
    )
    if blocked is not None:
        return (
            "<p class='text-red-500'>This assignment is currently inactive and cannot be accessed.</p>",
            403,
            {"Content-Type": "text/html"},
        )

    if not AuthorizationService.can_access_assignment(aes, current_user):
        return _plugin_render_access_denied("You are not authorized to access this assignment.")

    return None


@bp.route("/field-types/<field_type_id>/render-entry", methods=["GET"])
@login_required
def render_plugin_field_entry_public(field_type_id):
    """
    Generic (non-admin) endpoint to render a plugin entry template.

    This is used by the generic PluginFieldLoader on entry forms to fetch and inject
    a plugin's HTML structure before initializing its JS module.

    Requires authentication and assignment/form access (or admin template view).
    """
    access_error = _check_plugin_field_render_access()
    if access_error is not None:
        return access_error

    try:
        if not hasattr(current_app, "form_integration") or current_app.form_integration is None:
            return (
                "<p class='text-red-500'>Form integration is not available.</p>",
                500,
                {"Content-Type": "text/html"},
            )

        # Field configuration and existing data are passed as JSON strings in query params
        # IMPORTANT: plugins typically key DOM ids off `field_name`. Entry forms use numeric ids
        # (e.g. 153), so we inject `field_name = field_id` to keep DOM ids consistent with the
        # JS initializer (which is constructed with `fieldId`).
        field_id = request.args.get("field_id")
        field_config_raw = request.args.get("field_config")
        existing_data_raw = request.args.get("existing_data")

        try:
            field_config = json.loads(field_config_raw) if field_config_raw else {}
        except (TypeError, json.JSONDecodeError):
            field_config = {}

        if field_id:
            # Force a deterministic per-field name for DOM ids.
            field_config = dict(field_config or {})
            field_config["field_name"] = str(field_id)

        try:
            existing_data = json.loads(existing_data_raw) if existing_data_raw else {}
        except (TypeError, json.JSONDecodeError):
            existing_data = {}

        # NOTE: form_integration will pass through dict/list values as-is.
        field_value = existing_data if isinstance(existing_data, (dict, list)) else existing_data.get("value")

        html = current_app.form_integration.render_custom_field_entry_form(
            field_type=field_type_id,
            field_config=field_config,
            field_value=field_value,
        )

        return (html or "", 200, {"Content-Type": "text/html"})
    except Exception as e:
        current_app.logger.error(f"Error rendering entry template for {field_type_id}: {e}", exc_info=True)
        return ("<p class='text-red-500'>An error occurred while rendering this field.</p>", 500, {"Content-Type": "text/html"})
