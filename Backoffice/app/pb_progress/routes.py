"""HTTP routes for the P&B Progress module."""

from __future__ import annotations

import logging

from flask import request
from werkzeug.exceptions import NotFound

from flask_login import current_user

from app.pb_progress import bp
from app.pb_progress.service import PBProgressService
from app.routes.admin.shared import permission_required, system_manager_required
from app.services.authorization_service import AuthorizationService
from app.utils.api_responses import json_bad_request, json_ok, json_server_error

logger = logging.getLogger(__name__)


@bp.route("/pb-progress/upload", methods=["POST"])
@permission_required("admin.data_explore.pb_progress")
@system_manager_required
def upload_excel():
    file = request.files.get("excel")
    if not file or not file.filename:
        return json_bad_request("No Excel file provided.")
    try:
        excel_info = PBProgressService.store_excel(file)
        return json_ok(excel=excel_info)
    except ValueError as exc:
        return json_bad_request(str(exc))
    except Exception as exc:
        logger.exception("P&B progress Excel upload failed")
        return json_server_error(str(exc))


@bp.route("/pb-progress/excel-info", methods=["GET"])
@permission_required("admin.data_explore.pb_progress")
@system_manager_required
def excel_info():
    return json_ok(excel=PBProgressService.get_excel_info())


@bp.route("/pb-progress/generate", methods=["POST"])
@permission_required("admin.data_explore.pb_progress")
@system_manager_required
def generate():
    payload = request.get_json(silent=True) or {}
    language = (payload.get("language") or "all").strip() or "all"
    try:
        job_id = PBProgressService.start_generation(language=language)
        return json_ok(job_id=job_id, status=PBProgressService.get_status())
    except RuntimeError as exc:
        logger.warning("P&B progress generation blocked: %s", exc)
        return json_bad_request(str(exc))
    except Exception as exc:
        logger.exception("P&B progress generation start failed")
        return json_server_error(str(exc))


@bp.route("/pb-progress/status", methods=["GET"])
@permission_required("admin.data_explore.pb_progress")
def status():
    if AuthorizationService.is_system_manager(current_user):
        return json_ok(status=PBProgressService.get_status())
    return json_ok(status=PBProgressService.get_public_status())


@bp.route("/pb-progress/output/<path:filename>", methods=["GET"])
@permission_required("admin.data_explore.pb_progress")
def serve_output(filename: str):
    try:
        return PBProgressService.serve_output(filename)
    except NotFound:
        raise
    except ValueError as exc:
        return json_bad_request(str(exc))
    except Exception as exc:
        logger.exception("P&B progress output serve failed")
        return json_server_error(str(exc))
