"""Data quality API endpoints."""

from flask import request
from flask_login import login_required, current_user

from app.routes.api import api_bp
from app.services.data_quality.service import compute_data_quality, list_data_quality_templates_for_entity
from app.utils.api_helpers import json_response, api_error
from app.utils.data_quality_constants import is_data_quality_dashboard_enabled


def _user_can_access_entity(entity_type: str, entity_id: int) -> bool:
    return current_user.has_entity_access(entity_type, entity_id)


@api_bp.route("/dashboard/data-quality/templates", methods=["GET"])
@login_required
def get_data_quality_templates():
    if not is_data_quality_dashboard_enabled():
        return json_response({"enabled": False, "templates": []})

    entity_type = request.args.get("entity_type", type=str)
    entity_id = request.args.get("entity_id", type=int)
    if not entity_type or entity_id is None:
        return api_error("entity_type and entity_id are required", 400)
    if not _user_can_access_entity(entity_type, entity_id):
        return api_error("Access denied for this entity", 403)

    templates = list_data_quality_templates_for_entity(entity_type, entity_id)
    return json_response({"enabled": True, "templates": templates})


@api_bp.route("/dashboard/data-quality", methods=["GET"])
@login_required
def get_data_quality_score():
    if not is_data_quality_dashboard_enabled():
        return json_response({"enabled": False})

    entity_type = request.args.get("entity_type", type=str)
    entity_id = request.args.get("entity_id", type=int)
    template_id = request.args.get("template_id", type=int)
    period = request.args.get("period", type=str)

    if not all([entity_type, entity_id is not None, template_id, period]):
        return api_error("entity_type, entity_id, template_id, and period are required", 400)
    if not _user_can_access_entity(entity_type, entity_id):
        return api_error("Access denied for this entity", 403)

    try:
        result = compute_data_quality(
            template_id=template_id,
            entity_type=entity_type,
            entity_id=entity_id,
            period_name=period,
        )
        payload = result.to_dict()
        payload["enabled"] = True
        return json_response(payload)
    except ValueError as exc:
        return api_error(str(exc), 400)
    except Exception as exc:
        from flask import current_app

        current_app.logger.exception("Data quality score failed for template %s period %s", template_id, period)
        return api_error("Failed to compute data quality score", 500, debug_message=str(exc))
