"""Admin UI for validation rule registry, thresholds, and check types."""

from flask import render_template, request
from flask_login import login_required

from app import db
from app.routes.admin import bp
from app.routes.admin.shared import VALIDATION_RULES_PERMISSION, permission_required
from app.services.validation.dashboard_service import template_options
from app.services.validation.registry_service import (
    delete_check_type,
    delete_threshold,
    list_check_type_rows,
    list_countries_for_picker,
    list_question_template_rows,
    list_rule_catalog,
    list_threshold_rows,
    registry_bootstrap,
    update_question_template,
    upsert_check_type,
    upsert_threshold,
)
from app.utils.api_helpers import get_json_safe
from app.utils.api_responses import json_bad_request, json_ok, json_server_error
from app.utils.request_validation import enforce_csrf_json


@bp.route("/validation-rules", methods=["GET"])
@login_required
@permission_required(VALIDATION_RULES_PERMISSION)
def validation_rules_admin():
    bootstrap = registry_bootstrap()
    return render_template(
        "admin/validation_rules.html",
        template_options=template_options(),
        rule_packs=bootstrap["rule_packs"],
        check_type_options=bootstrap["check_type_options"],
        kpi_codes=bootstrap["kpi_codes"],
        rule_catalog=list_rule_catalog(),
        countries=list_countries_for_picker(),
    )


@bp.route("/validation-rules/api/catalog", methods=["GET"])
@login_required
@permission_required(VALIDATION_RULES_PERMISSION)
def validation_rules_catalog_api():
    rule_pack = request.args.get("rule_pack", type=str)
    return json_ok(rules=list_rule_catalog(rule_pack=rule_pack))


@bp.route("/validation-rules/api/thresholds", methods=["GET"])
@login_required
@permission_required(VALIDATION_RULES_PERMISSION)
def validation_rules_thresholds_list_api():
    template_id = request.args.get("template_id", type=int)
    return json_ok(rows=list_threshold_rows(template_id=template_id))


@bp.route("/validation-rules/api/thresholds", methods=["POST"])
@login_required
@permission_required(VALIDATION_RULES_PERMISSION)
def validation_rules_thresholds_upsert_api():
    csrf_error = enforce_csrf_json()
    if csrf_error:
        return csrf_error
    data = get_json_safe() or {}
    try:
        row = upsert_threshold(
            row_id=data.get("id"),
            country_id=int(data["country_id"]),
            kpi_code=data.get("kpi_code", ""),
            threshold_fraction=float(data["threshold_fraction"]),
            template_id=data.get("template_id"),
        )
        return json_ok(row=row)
    except (KeyError, TypeError, ValueError) as exc:
        return json_bad_request(str(exc))
    except Exception as exc:
        db.session.rollback()
        return json_server_error(str(exc))


@bp.route("/validation-rules/api/thresholds/<int:row_id>", methods=["DELETE"])
@login_required
@permission_required(VALIDATION_RULES_PERMISSION)
def validation_rules_thresholds_delete_api(row_id: int):
    csrf_error = enforce_csrf_json()
    if csrf_error:
        return csrf_error
    try:
        delete_threshold(row_id)
        return json_ok(deleted=True)
    except Exception as exc:
        db.session.rollback()
        return json_server_error(str(exc))


@bp.route("/validation-rules/api/check-types", methods=["GET"])
@login_required
@permission_required(VALIDATION_RULES_PERMISSION)
def validation_rules_check_types_list_api():
    template_id = request.args.get("template_id", type=int)
    return json_ok(rows=list_check_type_rows(template_id=template_id))


@bp.route("/validation-rules/api/check-types", methods=["POST"])
@login_required
@permission_required(VALIDATION_RULES_PERMISSION)
def validation_rules_check_types_upsert_api():
    csrf_error = enforce_csrf_json()
    if csrf_error:
        return csrf_error
    data = get_json_safe() or {}
    try:
        row = upsert_check_type(
            row_id=data.get("id"),
            kpi_code=data.get("kpi_code", ""),
            check_type=data.get("check_type", ""),
            template_id=data.get("template_id"),
        )
        return json_ok(row=row)
    except (KeyError, TypeError, ValueError) as exc:
        return json_bad_request(str(exc))
    except Exception as exc:
        db.session.rollback()
        return json_server_error(str(exc))


@bp.route("/validation-rules/api/check-types/<int:row_id>", methods=["DELETE"])
@login_required
@permission_required(VALIDATION_RULES_PERMISSION)
def validation_rules_check_types_delete_api(row_id: int):
    csrf_error = enforce_csrf_json()
    if csrf_error:
        return csrf_error
    try:
        delete_check_type(row_id)
        return json_ok(deleted=True)
    except Exception as exc:
        db.session.rollback()
        return json_server_error(str(exc))


@bp.route("/validation-rules/api/question-templates", methods=["GET"])
@login_required
@permission_required(VALIDATION_RULES_PERMISSION)
def validation_rules_question_templates_list_api():
    rule_pack = request.args.get("rule_pack", type=str)
    language = request.args.get("language", type=str)
    return json_ok(rows=list_question_template_rows(rule_pack=rule_pack, language=language))


@bp.route("/validation-rules/api/question-templates/<int:row_id>", methods=["POST"])
@login_required
@permission_required(VALIDATION_RULES_PERMISSION)
def validation_rules_question_templates_update_api(row_id: int):
    csrf_error = enforce_csrf_json()
    if csrf_error:
        return csrf_error
    data = get_json_safe() or {}
    try:
        row = update_question_template(
            row_id,
            template_text=data.get("template_text", ""),
            needs_ending_value=data.get("needs_ending_value"),
        )
        return json_ok(row=row)
    except ValueError as exc:
        return json_bad_request(str(exc))
    except Exception as exc:
        db.session.rollback()
        return json_server_error(str(exc))
