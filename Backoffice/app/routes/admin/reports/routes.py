"""Admin report builder routes."""

from __future__ import annotations

from flask import Blueprint, render_template, request, send_file
from flask_login import current_user, login_required
import io

from app.models import FormItem, FormTemplate, IndicatorBank
from app import db
from app.routes.admin.shared import permission_required
from app.services.data_quality.helpers import list_exploration_period_names
from app.services.organization.authorization_service import AuthorizationService
from app.services.reports.build_service import ReportBuildService
from app.services.reports.data_service import ReportDataService
from app.services.reports.definition_service import (
    REPORTS_EDIT,
    REPORTS_VIEW,
    ReportDefinitionError,
    ReportDefinitionService,
    resolve_user_scope,
    user_can_edit_report,
)
from app.services.reports.export_service import ReportExportService
from app.services.reports.schema import default_definition
from app.utils.api_helpers import get_json_safe
from app.utils.api_responses import json_bad_request, json_forbidden, json_not_found, json_ok, json_server_error
from app.utils.request_validation import enforce_csrf_json

bp = Blueprint("reports", __name__, url_prefix="/admin/reports")


def _forbidden_if_no_view():
    if not (
        AuthorizationService.is_system_manager(current_user)
        or AuthorizationService.has_rbac_permission(current_user, REPORTS_VIEW)
        or AuthorizationService.has_rbac_permission(current_user, REPORTS_EDIT)
    ):
        return json_forbidden("Access denied")
    return None


@bp.route("", methods=["GET"])
@login_required
def reports_list():
    denied = _forbidden_if_no_view()
    if denied:
        return denied
    reports = ReportDefinitionService.list_reports(current_user)
    return render_template(
        "admin/reports/list.html",
        reports=reports,
        can_edit=AuthorizationService.has_rbac_permission(current_user, REPORTS_EDIT)
        or AuthorizationService.is_system_manager(current_user),
    )


@bp.route("/new", methods=["GET"])
@login_required
@permission_required(REPORTS_EDIT)
def reports_new():
    return render_template(
        "admin/reports/builder.html",
        report=None,
        definition=default_definition(),
        is_new=True,
    )


@bp.route("/<int:report_id>", methods=["GET"])
@login_required
def reports_view(report_id: int):
    denied = _forbidden_if_no_view()
    if denied:
        return denied
    try:
        report = ReportDefinitionService.get_report(report_id, current_user)
    except ReportDefinitionError:
        return json_not_found("Report not found"), 404
    return render_template(
        "admin/reports/view.html",
        report=report,
        can_edit=user_can_edit_report(current_user, report),
    )


@bp.route("/<int:report_id>/edit", methods=["GET"])
@login_required
@permission_required(REPORTS_EDIT)
def reports_edit(report_id: int):
    try:
        report = ReportDefinitionService.get_report(report_id, current_user)
    except ReportDefinitionError:
        return json_not_found("Report not found"), 404
    if not user_can_edit_report(current_user, report):
        return json_forbidden("Access denied")
    return render_template(
        "admin/reports/builder.html",
        report=report,
        definition=report.definition_json or default_definition(),
        is_new=False,
    )


def _csrf_guard():
    csrf_error = enforce_csrf_json()
    if csrf_error:
        return csrf_error
    return None


@bp.route("/api", methods=["POST"])
@login_required
@permission_required(REPORTS_EDIT)
def api_create_report():
    csrf_error = _csrf_guard()
    if csrf_error:
        return csrf_error
    payload = get_json_safe() or {}
    try:
        report = ReportDefinitionService.create_report(
            current_user,
            title=payload.get("title") or "Untitled report",
            description=payload.get("description"),
            definition=payload.get("definition"),
            scope_json=payload.get("scope"),
        )
        return json_ok(report=ReportDefinitionService.serialize(report))
    except ValueError as exc:
        return json_bad_request(str(exc))
    except ReportDefinitionError as exc:
        return json_forbidden(str(exc))


@bp.route("/api/<int:report_id>", methods=["GET"])
@login_required
def api_get_report(report_id: int):
    denied = _forbidden_if_no_view()
    if denied:
        return denied
    try:
        report = ReportDefinitionService.get_report(report_id, current_user)
        return json_ok(report=ReportDefinitionService.serialize(report))
    except ReportDefinitionError:
        return json_not_found("Report not found")


@bp.route("/api/<int:report_id>", methods=["PUT"])
@login_required
@permission_required(REPORTS_EDIT)
def api_update_report(report_id: int):
    csrf_error = _csrf_guard()
    if csrf_error:
        return csrf_error
    payload = get_json_safe() or {}
    try:
        report = ReportDefinitionService.update_report(
            report_id,
            current_user,
            title=payload.get("title"),
            description=payload.get("description"),
            definition=payload.get("definition"),
            scope_json=payload.get("scope"),
            status=payload.get("status"),
        )
        return json_ok(report=ReportDefinitionService.serialize(report))
    except ValueError as exc:
        return json_bad_request(str(exc))
    except ReportDefinitionError as exc:
        return json_forbidden(str(exc))


@bp.route("/api/<int:report_id>", methods=["DELETE"])
@login_required
@permission_required(REPORTS_EDIT)
def api_delete_report(report_id: int):
    csrf_error = _csrf_guard()
    if csrf_error:
        return csrf_error
    try:
        ReportDefinitionService.delete_report(report_id, current_user)
        return json_ok(deleted=True)
    except ReportDefinitionError as exc:
        return json_forbidden(str(exc))


@bp.route("/api/<int:report_id>/clone", methods=["POST"])
@login_required
@permission_required(REPORTS_EDIT)
def api_clone_report(report_id: int):
    csrf_error = _csrf_guard()
    if csrf_error:
        return csrf_error
    try:
        report = ReportDefinitionService.clone_report(report_id, current_user)
        return json_ok(report=ReportDefinitionService.serialize(report))
    except ReportDefinitionError as exc:
        return json_forbidden(str(exc))


@bp.route("/api/<int:report_id>/run", methods=["POST"])
@login_required
def api_run_report(report_id: int):
    csrf_error = _csrf_guard()
    if csrf_error:
        return csrf_error
    denied = _forbidden_if_no_view()
    if denied:
        return denied
    payload = get_json_safe() or {}
    try:
        result = ReportDataService.execute_report(
            report_id,
            current_user,
            runtime_overrides=payload.get("filters"),
        )
        return json_ok(**result)
    except ReportDefinitionError:
        return json_not_found("Report not found")


@bp.route("/api/<int:report_id>/widgets/<widget_id>/run", methods=["POST"])
@login_required
def api_run_widget(report_id: int, widget_id: str):
    csrf_error = _csrf_guard()
    if csrf_error:
        return csrf_error
    denied = _forbidden_if_no_view()
    if denied:
        return denied
    payload = get_json_safe() or {}
    try:
        result = ReportDataService.execute_widget_by_id(
            report_id,
            widget_id,
            current_user,
            runtime_overrides=payload.get("filters"),
        )
        return json_ok(widget=result)
    except ReportDefinitionError:
        return json_not_found("Report not found")


@bp.route("/api/<int:report_id>/export", methods=["POST"])
@login_required
def api_export_report(report_id: int):
    csrf_error = _csrf_guard()
    if csrf_error:
        return csrf_error
    denied = _forbidden_if_no_view()
    if denied:
        return denied
    payload = get_json_safe() or {}
    fmt = (payload.get("format") or "excel").strip().lower()
    try:
        report = ReportDefinitionService.get_report(report_id, current_user)
        result = ReportDataService.execute_report(
            report_id,
            current_user,
            runtime_overrides=payload.get("filters"),
        )
        if fmt == "pdf":
            chart_images = payload.get("chart_images") or {}
            pdf_bytes = ReportExportService.export_pdf(report, result, chart_images=chart_images)
            return send_file(
                io.BytesIO(pdf_bytes),
                mimetype="application/pdf",
                as_attachment=True,
                download_name=f"{report.slug}.pdf",
            )
        xlsx_bytes = ReportExportService.export_excel(report, result)
        return send_file(
            io.BytesIO(xlsx_bytes),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"{report.slug}.xlsx",
        )
    except ReportDefinitionError:
        return json_not_found("Report not found")
    except Exception as exc:
        return json_server_error(str(exc))


@bp.route("/api/<int:report_id>/publish", methods=["POST"])
@login_required
@permission_required(REPORTS_EDIT)
def api_publish_report(report_id: int):
    csrf_error = _csrf_guard()
    if csrf_error:
        return csrf_error
    try:
        ReportDefinitionService.update_report(report_id, current_user, status="published")
        run = ReportBuildService.start_publish(report_id, current_user)
        return json_ok(run=ReportBuildService.serialize_run(run))
    except ReportDefinitionError as exc:
        return json_forbidden(str(exc))


@bp.route("/api/runs/<run_id>", methods=["GET"])
@login_required
def api_get_run(run_id: str):
    denied = _forbidden_if_no_view()
    if denied:
        return denied
    run = ReportBuildService.get_run(run_id)
    if not run:
        return json_not_found("Run not found")
    return json_ok(run=ReportBuildService.serialize_run(run))


@bp.route("/api/metadata/templates", methods=["GET"])
@login_required
def api_metadata_templates():
    denied = _forbidden_if_no_view()
    if denied:
        return denied
    scope = resolve_user_scope(current_user)
    q = FormTemplate.query
    if scope["template_ids"] is not None:
        q = q.filter(FormTemplate.id.in_(scope["template_ids"]))
    templates_raw = q.all()
    templates_raw.sort(key=lambda t: (t.name or "").lower())
    templates = [{"id": t.id, "name": t.name or f"Template {t.id}"} for t in templates_raw]
    return json_ok(templates=templates)


@bp.route("/api/metadata/periods", methods=["GET"])
@login_required
def api_metadata_periods():
    denied = _forbidden_if_no_view()
    if denied:
        return denied
    template_id = request.args.get("template_id", type=int)
    periods = list_exploration_period_names(template_id=template_id)
    return json_ok(periods=periods)


@bp.route("/api/metadata/indicators", methods=["GET"])
@login_required
def api_metadata_indicators():
    denied = _forbidden_if_no_view()
    if denied:
        return denied
    q_text = (request.args.get("q") or "").strip()
    template_id = request.args.get("template_id", type=int)
    extra_ids_raw = (request.args.get("ids") or "").strip()
    extra_ids = [int(part) for part in extra_ids_raw.split(",") if part.strip().isdigit()]

    indicators_map: dict[int, dict] = {}

    def _serialize_indicator(ib: IndicatorBank, *, label: str | None = None) -> dict:
        name = ib.name or f"Indicator {ib.id}"
        display = name
        if label and label.strip() and label.strip() != name:
            display = f"{label.strip()} — {name}"
        return {
            "id": ib.id,
            "name": name,
            "label": label,
            "type": ib.type,
            "unit": ib.unit,
            "display": display,
        }

    if template_id:
        scope = resolve_user_scope(current_user)
        allowed = scope["template_ids"]
        if allowed is not None and template_id not in allowed:
            return json_forbidden("Template not in scope")
        rows = (
            db.session.query(FormItem, IndicatorBank)
            .join(IndicatorBank, FormItem.indicator_bank_id == IndicatorBank.id)
            .filter(
                FormItem.template_id == template_id,
                FormItem.indicator_bank_id.isnot(None),
                IndicatorBank.archived.isnot(True),
            )
            .order_by(FormItem.label.asc(), IndicatorBank.name.asc())
            .limit(500)
            .all()
        )
        for item, ib in rows:
            if ib.id not in indicators_map:
                indicators_map[ib.id] = _serialize_indicator(ib, label=item.label)
    else:
        q = IndicatorBank.query.filter(IndicatorBank.archived.isnot(True))
        if q_text:
            like = f"%{q_text}%"
            q = q.filter(IndicatorBank.name.ilike(like))
        for ib in q.order_by(IndicatorBank.name.asc()).limit(100).all():
            indicators_map[ib.id] = _serialize_indicator(ib)

    if extra_ids:
        missing = [i for i in extra_ids if i not in indicators_map]
        if missing:
            for ib in IndicatorBank.query.filter(IndicatorBank.id.in_(missing)).all():
                indicators_map[ib.id] = _serialize_indicator(ib)

    results = list(indicators_map.values())
    if q_text and template_id:
        needle = q_text.lower()
        results = [
            row
            for row in results
            if needle in (row.get("display") or "").lower()
            or needle in (row.get("name") or "").lower()
            or needle in (row.get("label") or "").lower()
        ]
    results.sort(key=lambda row: (row.get("display") or "").lower())
    return json_ok(indicators=results)


@bp.route("/api/metadata/form-items", methods=["GET"])
@login_required
def api_metadata_form_items():
    denied = _forbidden_if_no_view()
    if denied:
        return denied
    template_id = request.args.get("template_id", type=int)
    if not template_id:
        return json_bad_request("template_id is required")
    scope = resolve_user_scope(current_user)
    allowed = scope["template_ids"]
    if allowed is not None and template_id not in allowed:
        return json_forbidden("Template not in scope")
    from app.models import FormItem

    items = (
        FormItem.query.filter(
            FormItem.template_id == template_id,
            FormItem.indicator_bank_id.isnot(None),
        )
        .order_by(FormItem.label.asc())
        .limit(500)
        .all()
    )
    return json_ok(
        form_items=[
            {
                "id": it.id,
                "label": it.label,
                "indicator_bank_id": it.indicator_bank_id,
                "item_type": it.item_type,
            }
            for it in items
        ]
    )


@bp.route("/api/metadata/indicator-rule/fields", methods=["GET"])
@login_required
def api_metadata_indicator_rule_fields():
    denied = _forbidden_if_no_view()
    if denied:
        return denied
    from app.services.reports.indicator_rule_service import list_distinct_related_programmes, list_distinct_tags

    return json_ok(
        related_programmes=list_distinct_related_programmes(),
        tags=list_distinct_tags(),
    )


@bp.route("/api/metadata/indicator-rule/preview", methods=["POST"])
@login_required
def api_metadata_indicator_rule_preview():
    denied = _forbidden_if_no_view()
    if denied:
        return denied
    csrf_error = enforce_csrf_json()
    if csrf_error:
        return csrf_error
    from app.services.reports.indicator_rule_service import preview_indicator_rule

    payload = get_json_safe() or {}
    rule = payload.get("rule") or payload
    full_list = bool(payload.get("full_list"))
    sample_limit = int(payload.get("sample_limit") or 8)
    return json_ok(preview=preview_indicator_rule(rule, sample_limit=sample_limit, full_list=full_list))
