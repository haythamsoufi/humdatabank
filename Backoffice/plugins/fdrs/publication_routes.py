"""Admin routes for the FDRS "Manage Publication" tool.

Lets a system manager preview what publishing an FDRS assignment (one reporting
period, all countries) would change in the public feed, highlight those changes,
and run the publish for the whole assignment or a chosen subset of countries.
See ``plugins/fdrs/services/fdrs_publication_service.py`` for the actual diff /
copy logic, and ``plugins/fdrs/public_api_routes.py`` for the external endpoint
that serves the published snapshot this tool writes.
"""

from __future__ import annotations

from flask import render_template
from flask_login import current_user
from werkzeug.exceptions import HTTPException

from app.routes.admin.shared import (
    admin_permission_required,
    admin_required,
    check_template_access,
    system_manager_required,
)
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE, get_json_safe
from app.utils.api_responses import json_bad_request, json_forbidden, json_ok
from app.utils.data_quality_constants import FDRS_TEMPLATE_ID
from app.utils.error_handling import handle_json_view_exception
from plugins.fdrs import bp
from plugins.fdrs.services.fdrs_publication_service import (
    get_assignment_publication_summary,
    get_country_change_detail,
    list_fdrs_assignments,
    publish_assignment,
)


def _fdrs_template_access_denied():
    """Shared guard beyond the route decorators: real per-template RBAC (owner /
    shared-with / system manager), mirrors the check ``run_data_sync`` performs.
    Returns a JSON 403 Response, or None when access is fine."""
    if not check_template_access(FDRS_TEMPLATE_ID, current_user.id):
        return json_forbidden("Access denied")
    return None


@bp.route("/admin/plugins/fdrs/publication", methods=["GET"])
@admin_required
@system_manager_required
def publication_page():
    return render_template(
        "plugins/fdrs/admin/fdrs_publication.html",
        assignments=list_fdrs_assignments(),
    )


@bp.route("/admin/plugins/fdrs/publication/<int:assigned_form_id>/summary", methods=["GET"])
@admin_permission_required("admin.templates.view")
def publication_summary(assigned_form_id: int):
    denied = _fdrs_template_access_denied()
    if denied is not None:
        return denied
    try:
        summary = get_assignment_publication_summary(assigned_form_id)
        return json_ok(success=True, **summary)
    except HTTPException:
        raise
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route(
    "/admin/plugins/fdrs/publication/<int:assigned_form_id>/countries/<int:assignment_entity_status_id>/detail",
    methods=["GET"],
)
@admin_permission_required("admin.templates.view")
def publication_country_detail(assigned_form_id: int, assignment_entity_status_id: int):
    denied = _fdrs_template_access_denied()
    if denied is not None:
        return denied
    try:
        detail = get_country_change_detail(assigned_form_id, assignment_entity_status_id)
        return json_ok(success=True, **detail)
    except HTTPException:
        raise
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/admin/plugins/fdrs/publication/<int:assigned_form_id>/publish", methods=["POST"])
@admin_permission_required("admin.templates.edit")
@system_manager_required
def publication_publish(assigned_form_id: int):
    denied = _fdrs_template_access_denied()
    if denied is not None:
        return denied
    try:
        data = get_json_safe()
        raw_ids = data.get("assignment_entity_status_ids")
        aes_ids = None
        if raw_ids is not None:
            if not isinstance(raw_ids, (list, tuple)):
                return json_bad_request("assignment_entity_status_ids must be a list")
            try:
                aes_ids = [int(x) for x in raw_ids]
            except (TypeError, ValueError):
                return json_bad_request("assignment_entity_status_ids must be a list of integers")

        stats = publish_assignment(
            assigned_form_id,
            assignment_entity_status_ids=aes_ids,
            user_id=int(getattr(current_user, "id", 0) or 0) or None,
        )
        return json_ok(success=True, **stats)
    except HTTPException:
        raise
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)
