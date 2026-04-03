from flask import Blueprint, current_app, request
from flask_login import login_required
import json


bp = Blueprint("plugins_api", __name__, url_prefix="/api/plugins")


@bp.route("/field-types/<field_type_id>/render-entry", methods=["GET"])
def render_plugin_field_entry_public(field_type_id):
    """
    Generic (non-admin) endpoint to render a plugin entry template.

    This is used by the generic PluginFieldLoader on entry forms to fetch and inject
    a plugin's HTML structure before initializing its JS module.

    It intentionally mirrors the admin endpoint but without requiring admin permissions.
    """
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
        return (f"<p class='text-red-500'>Error rendering plugin field: {e}</p>", 500, {"Content-Type": "text/html"})
