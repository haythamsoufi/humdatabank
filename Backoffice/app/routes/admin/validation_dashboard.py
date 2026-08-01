"""Validation dashboard — preview flags by country and generate questions."""

from flask import current_app, render_template, request
from flask_login import login_required, current_user

from app import db
from app.routes.admin import bp
from app.routes.admin.shared import (
    VALIDATION_DASHBOARD_PERMISSION,
    VALIDATION_DISPATCH_PERMISSIONS,
    permission_required,
    permission_required_any,
)
from app.routes.admin.validation_scope_api import register_validation_scope_routes
from app.services.validation.check_service import run_validation_checks
from app.services.validation.dispatch_service import preview_dispatch, send_dispatch
from app.services.validation.dashboard_service import (
    preview_country_validation,
    summarize_period,
    template_tab_options,
)
from app.services.validation.tracker_service import build_tracker_data
from app.utils.api_responses import json_bad_request, json_ok, json_server_error
from app.utils.api_helpers import get_json_safe
from app.utils.request_validation import enforce_csrf_json


@bp.route("/validation-dashboard", methods=["GET"])
@login_required
@permission_required(VALIDATION_DASHBOARD_PERMISSION)
def validation_dashboard():
    return render_template(
        "admin/validation_dashboard.html",
        template_options=template_tab_options(),
        mapbox_access_token=current_app.config.get("MAPBOX_ACCESS_TOKEN") or "",
        mapbox_style_id=current_app.config.get("MAPBOX_STYLE_ID") or "go-ifrc/ckrfe16ru4c8718phmckdfjh0",
    )


register_validation_scope_routes(
    bp,
    "/validation-dashboard",
    VALIDATION_DASHBOARD_PERMISSION,
    endpoint_prefix="validation_dashboard",
)


@bp.route("/validation-dashboard/api/tracker", methods=["GET"])
@login_required
@permission_required(VALIDATION_DASHBOARD_PERMISSION)
def validation_dashboard_tracker_api():
    template_id = request.args.get("template_id", type=int)
    period = request.args.get("period", type=str)
    if not template_id or not period:
        return json_bad_request("template_id and period are required")
    return json_ok(**build_tracker_data(template_id, period))


@bp.route("/validation-dashboard/api/summary", methods=["GET"])
@login_required
@permission_required(VALIDATION_DASHBOARD_PERMISSION)
def validation_dashboard_summary_api():
    template_id = request.args.get("template_id", type=int)
    period = request.args.get("period", type=str)
    if not template_id or not period:
        return json_bad_request("template_id and period are required")
    return json_ok(**summarize_period(template_id, period))


@bp.route("/validation-dashboard/api/preview", methods=["GET"])
@login_required
@permission_required(VALIDATION_DASHBOARD_PERMISSION)
def validation_dashboard_preview_api():
    template_id = request.args.get("template_id", type=int)
    period = request.args.get("period", type=str)
    country_id = request.args.get("country_id", type=int)
    if not template_id or not period or not country_id:
        return json_bad_request("template_id, period, and country_id are required")
    try:
        preview = preview_country_validation(template_id, period, country_id)
        return json_ok(preview=preview)
    except ValueError as exc:
        return json_bad_request(str(exc))
    except Exception as exc:
        return json_server_error(str(exc))


@bp.route("/validation-dashboard/run-checks", methods=["POST"])
@login_required
@permission_required(VALIDATION_DASHBOARD_PERMISSION)
def validation_dashboard_run_checks():
    csrf_error = enforce_csrf_json()
    if csrf_error:
        return csrf_error
    data = get_json_safe()
    template_id = data.get("template_id")
    period = data.get("period_name")
    country_id = data.get("country_id")
    country_ids = data.get("country_ids")
    if not template_id or not period:
        return json_bad_request("template_id and period_name are required")

    targets = []
    if country_ids:
        targets = [int(c) for c in country_ids]
    elif country_id is not None:
        targets = [int(country_id)]
    else:
        return json_bad_request("country_id or country_ids is required")

    totals = {"created": 0, "updated": 0, "resolved": 0, "errors": []}
    for cid in targets:
        try:
            result = run_validation_checks(int(template_id), "country", cid, period)
            totals["created"] += result.created
            totals["updated"] += result.updated
            totals["resolved"] += result.resolved
        except ValueError as exc:
            totals["errors"].append(f"Country {cid}: {exc}")
        except Exception as exc:
            db.session.rollback()
            totals["errors"].append(f"Country {cid}: {exc}")

    message = (
        f"Generated questions — created: {totals['created']}, updated: {totals['updated']}, "
        f"resolved: {totals['resolved']}."
    )
    if totals["errors"]:
        message += f" {len(totals['errors'])} country/countries failed."

    return json_ok(**totals, message=message, has_errors=bool(totals["errors"]))


@bp.route("/validation-dashboard/dispatch/send", methods=["POST"])
@login_required
@permission_required_any(*VALIDATION_DISPATCH_PERMISSIONS)
def validation_dashboard_dispatch_send():
    csrf_error = enforce_csrf_json()
    if csrf_error:
        return csrf_error
    data = get_json_safe()
    try:
        batch = send_dispatch(
            int(data["template_id"]),
            data["period_name"],
            created_by_user_id=current_user.id,
            channels=data.get("channels", ["in_app", "email"]),
            entity_type="country" if data.get("country_id") else data.get("entity_type"),
            entity_id=data.get("country_id") or data.get("entity_id"),
            question_ids=data.get("question_ids"),
            intro_message=data.get("intro_message"),
            override_email_preferences=bool(data.get("override_email_preferences")),
        )
        return json_ok(batch_id=batch.id, status=batch.status, summary=batch.summary)
    except Exception as exc:
        db.session.rollback()
        return json_server_error(str(exc))


@bp.route("/validation-dashboard/dispatch/preview", methods=["POST"])
@login_required
@permission_required_any(*VALIDATION_DISPATCH_PERMISSIONS)
def validation_dashboard_dispatch_preview():
    csrf_error = enforce_csrf_json()
    if csrf_error:
        return csrf_error
    data = get_json_safe()
    preview = preview_dispatch(
        int(data["template_id"]),
        data["period_name"],
        entity_type="country" if data.get("country_id") else data.get("entity_type"),
        entity_id=data.get("country_id") or data.get("entity_id"),
        question_ids=data.get("question_ids"),
        channels=data.get("channels", []),
    )
    return json_ok(
        entities=preview.entities,
        questions=preview.questions,
        total_recipients=preview.total_recipients,
    )
