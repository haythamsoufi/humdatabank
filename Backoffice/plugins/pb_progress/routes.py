"""HTTP routes for the P&B Progress module."""

from __future__ import annotations

import logging

from flask import render_template, request, url_for
from werkzeug.exceptions import NotFound

from flask_login import current_user

from plugins.pb_progress import bp
from plugins.pb_progress.db_source import (
    DbSourceError,
    import_config_from_excel,
    sync_mapping_from_indicator_bank,
    validate_mapping_config,
)
from plugins.pb_progress.plugin_data_store import PBProgressDataStore
from plugins.pb_progress.service import PBProgressService
from plugins.pb_progress.versions import DEFAULT_VERSION, REPORT_VERSIONS, VERSION_ORDER, validate_version
from app.routes.admin.shared import permission_required, system_manager_required
from app.services.authorization_service import AuthorizationService
from app.utils.api_responses import json_bad_request, json_ok, json_server_error

logger = logging.getLogger(__name__)

_ADMIN_SUBTABS = frozenset({"build", "mapping", "translations", "section-order"})


@bp.route("/pb-progress/manage", methods=["GET"])
@permission_required("admin.data_explore.pb_progress")
@system_manager_required
def manage_page():
    initial_subtab = (request.args.get("tab") or "build").strip().lower()
    if initial_subtab not in _ADMIN_SUBTABS:
        initial_subtab = "build"
    initial_data_source = PBProgressDataStore.get_data_source(DEFAULT_VERSION)
    if initial_subtab != "build" and initial_data_source != "system":
        initial_subtab = "build"
    explore_report_url = url_for("data_exploration.explore_data", tab="pb-progress")
    return render_template(
        "plugins/pb_progress/pb_progress/manage.html",
        pb_report_versions=REPORT_VERSIONS,
        pb_report_version_order=VERSION_ORDER,
        pb_default_version=DEFAULT_VERSION,
        pb_initial_subtab=initial_subtab,
        pb_initial_data_source=initial_data_source,
        explore_report_url=explore_report_url,
    )


@bp.route("/pb-progress/<version>/upload", methods=["POST"])
@permission_required("admin.data_explore.pb_progress")
@system_manager_required
def upload_excel(version: str):
    try:
        version_key = validate_version(version)
    except ValueError as exc:
        return json_bad_request(str(exc))
    file = request.files.get("excel")
    if not file or not file.filename:
        return json_bad_request("No Excel file provided.")
    try:
        upload_result = PBProgressService.store_excel(version_key, file)
        return json_ok(version=version_key, **upload_result)
    except ValueError as exc:
        return json_bad_request(str(exc))
    except Exception as exc:
        logger.exception("P&B progress Excel upload failed")
        return json_server_error(str(exc))


@bp.route("/pb-progress/<version>/excel-info", methods=["GET"])
@permission_required("admin.data_explore.pb_progress")
@system_manager_required
def excel_info(version: str):
    try:
        version_key = validate_version(version)
    except ValueError as exc:
        return json_bad_request(str(exc))
    return json_ok(excel=PBProgressService.get_excel_info(version_key), version=version_key)


@bp.route("/pb-progress/<version>/generate", methods=["POST"])
@permission_required("admin.data_explore.pb_progress")
@system_manager_required
def generate(version: str):
    try:
        version_key = validate_version(version)
    except ValueError as exc:
        return json_bad_request(str(exc))
    payload = request.get_json(silent=True) or {}
    language = (payload.get("language") or "all").strip() or "all"
    try:
        job_id = PBProgressService.start_generation(version_key, language=language)
        return json_ok(
            job_id=job_id,
            version=version_key,
            status=PBProgressService.get_status(version_key),
        )
    except RuntimeError as exc:
        logger.warning("P&B progress generation blocked: %s", exc)
        return json_bad_request(str(exc))
    except Exception as exc:
        logger.exception("P&B progress generation start failed")
        return json_server_error(str(exc))


@bp.route("/pb-progress/<version>/status", methods=["GET"])
@permission_required("admin.data_explore.pb_progress")
def status(version: str):
    try:
        version_key = validate_version(version)
    except ValueError as exc:
        return json_bad_request(str(exc))
    if AuthorizationService.is_system_manager(current_user):
        return json_ok(status=PBProgressService.get_status(version_key))
    return json_ok(status=PBProgressService.get_public_status(version_key))


@bp.route("/pb-progress/<version>/output/<path:filename>", methods=["GET"])
@permission_required("admin.data_explore.pb_progress")
def serve_output(version: str, filename: str):
    try:
        version_key = validate_version(version)
    except ValueError as exc:
        return json_bad_request(str(exc))
    try:
        return PBProgressService.serve_output(version_key, filename)
    except NotFound:
        raise
    except ValueError as exc:
        return json_bad_request(str(exc))
    except Exception as exc:
        logger.exception("P&B progress output serve failed")
        return json_server_error(str(exc))


@bp.route("/pb-progress/<version>/mapping", methods=["GET", "PUT"])
@permission_required("admin.data_explore.pb_progress")
@system_manager_required
def mapping(version: str):
    try:
        version_key = validate_version(version)
    except ValueError as exc:
        return json_bad_request(str(exc))

    if request.method == "GET":
        rows = PBProgressDataStore.get_mapping_config(version_key)
        return json_ok(
            version=version_key,
            mapping=validate_mapping_config(rows),
        )

    payload = request.get_json(silent=True) or {}
    rows = payload.get("mapping")
    if not isinstance(rows, list):
        return json_bad_request("Expected a mapping array.")
    rows = validate_mapping_config(rows)
    PBProgressDataStore.save_mapping_config(version_key, rows)
    return json_ok(version=version_key, mapping=rows)


@bp.route("/pb-progress/<version>/mapping/sync-from-indicator-bank", methods=["POST"])
@permission_required("admin.data_explore.pb_progress")
@system_manager_required
def mapping_sync(version: str):
    try:
        version_key = validate_version(version)
        summary = sync_mapping_from_indicator_bank(version_key)
        return json_ok(version=version_key, summary=summary, mapping=validate_mapping_config(PBProgressDataStore.get_mapping_config(version_key)))
    except ValueError as exc:
        return json_bad_request(str(exc))
    except DbSourceError as exc:
        return json_bad_request(str(exc))
    except Exception as exc:
        logger.exception("P&B progress mapping sync failed")
        return json_server_error(str(exc))


@bp.route("/pb-progress/<version>/translations", methods=["GET", "PUT"])
@permission_required("admin.data_explore.pb_progress")
@system_manager_required
def translations(version: str):
    try:
        version_key = validate_version(version)
    except ValueError as exc:
        return json_bad_request(str(exc))

    if request.method == "GET":
        return json_ok(
            version=version_key,
            translations=PBProgressDataStore.get_translations_config(version_key),
        )

    payload = request.get_json(silent=True) or {}
    rows = payload.get("translations")
    if not isinstance(rows, list):
        return json_bad_request("Expected a translations array.")
    PBProgressDataStore.save_translations_config(version_key, rows)
    return json_ok(
        version=version_key,
        translations=PBProgressDataStore.get_translations_config(version_key),
    )


@bp.route("/pb-progress/<version>/section-order", methods=["GET", "PUT"])
@permission_required("admin.data_explore.pb_progress")
@system_manager_required
def section_order(version: str):
    try:
        version_key = validate_version(version)
    except ValueError as exc:
        return json_bad_request(str(exc))

    if request.method == "GET":
        return json_ok(
            version=version_key,
            section_order=PBProgressDataStore.get_section_order_config(version_key),
        )

    payload = request.get_json(silent=True) or {}
    rows = payload.get("section_order")
    if not isinstance(rows, list):
        return json_bad_request("Expected a section_order array.")
    PBProgressDataStore.save_section_order_config(version_key, rows)
    return json_ok(
        version=version_key,
        section_order=PBProgressDataStore.get_section_order_config(version_key),
    )


@bp.route("/pb-progress/<version>/config/import-from-excel", methods=["POST"])
@permission_required("admin.data_explore.pb_progress")
@system_manager_required
def config_import_from_excel(version: str):
    try:
        version_key = validate_version(version)
        summary = import_config_from_excel(version_key)
        return json_ok(
            version=version_key,
            summary=summary,
            mapping=PBProgressDataStore.get_mapping_config(version_key),
            translations=PBProgressDataStore.get_translations_config(version_key),
            section_order=PBProgressDataStore.get_section_order_config(version_key),
        )
    except ValueError as exc:
        return json_bad_request(str(exc))
    except DbSourceError as exc:
        return json_bad_request(str(exc))
    except Exception as exc:
        logger.exception("P&B progress config import failed")
        return json_server_error(str(exc))


@bp.route("/pb-progress/<version>/years", methods=["GET", "PUT"])
@permission_required("admin.data_explore.pb_progress")
@system_manager_required
def report_years(version: str):
    from plugins.pb_progress.db_source import list_available_years

    try:
        version_key = validate_version(version)
    except ValueError as exc:
        return json_bad_request(str(exc))

    if request.method == "GET":
        available = list_available_years(version_key)
        selected = PBProgressDataStore.get_selected_years(version_key)
        effective = selected if selected else available
        return json_ok(
            version=version_key,
            available_years=available,
            selected_years=selected,
            effective_years=effective,
        )

    payload = request.get_json(silent=True) or {}
    years = payload.get("years")
    if not isinstance(years, list):
        return json_bad_request("Expected a years array.")
    cleaned = sorted({str(year).strip() for year in years if str(year).strip()})
    if not cleaned:
        return json_bad_request("Select at least one year.")
    available = set(list_available_years(version_key))
    invalid = [year for year in cleaned if year not in available]
    if invalid:
        return json_bad_request(f"Unknown years: {', '.join(invalid)}")
    PBProgressDataStore.save_selected_years(version_key, cleaned)
    return json_ok(
        version=version_key,
        available_years=sorted(available),
        selected_years=cleaned,
        effective_years=cleaned,
    )


@bp.route("/pb-progress/<version>/data-source", methods=["POST"])
@permission_required("admin.data_explore.pb_progress")
@system_manager_required
def data_source(version: str):
    try:
        version_key = validate_version(version)
    except ValueError as exc:
        return json_bad_request(str(exc))
    payload = request.get_json(silent=True) or {}
    source = (payload.get("data_source") or "").strip().lower()
    if source not in {"excel", "system"}:
        return json_bad_request("data_source must be 'excel' or 'system'.")
    try:
        saved = PBProgressService.set_data_source(version_key, source)
        return json_ok(version=version_key, data_source=saved)
    except ValueError as exc:
        return json_bad_request(str(exc))
    except Exception as exc:
        logger.exception("P&B progress data source update failed")
        return json_server_error(str(exc))


@bp.route("/pb-progress/<version>/generate-system-dataset", methods=["POST"])
@permission_required("admin.data_explore.pb_progress")
@system_manager_required
def generate_system_dataset(version: str):
    try:
        version_key = validate_version(version)
        summary = PBProgressService.generate_system_dataset(version_key)
        return json_ok(version=version_key, summary=summary)
    except ValueError as exc:
        return json_bad_request(str(exc))
    except DbSourceError as exc:
        return json_bad_request(str(exc))
    except Exception as exc:
        logger.exception("P&B progress system dataset generation failed")
        return json_server_error(str(exc))


@bp.route("/pb-progress/<version>/system-dataset/download", methods=["GET"])
@permission_required("admin.data_explore.pb_progress")
@system_manager_required
def download_system_dataset(version: str):
    try:
        version_key = validate_version(version)
    except ValueError as exc:
        return json_bad_request(str(exc))
    try:
        return PBProgressService.serve_system_dataset(version_key)
    except NotFound:
        raise
    except Exception as exc:
        logger.exception("P&B progress system dataset download failed")
        return json_server_error(str(exc))


@bp.route("/pb-progress/<version>/compare-system-dataset", methods=["GET"])
@permission_required("admin.data_explore.pb_progress")
@system_manager_required
def compare_system_dataset(version: str):
    try:
        version_key = validate_version(version)
        comparison = PBProgressService.compare_system_dataset(version_key)
        return json_ok(version=version_key, comparison=comparison)
    except ValueError as exc:
        return json_bad_request(str(exc))
    except DbSourceError as exc:
        return json_bad_request(str(exc))
    except Exception as exc:
        logger.exception("P&B progress dataset comparison failed")
        return json_server_error(str(exc))
