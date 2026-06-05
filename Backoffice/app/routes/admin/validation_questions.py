"""Admin validation questions management."""

from flask import render_template, request, send_file
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app import db
from app.models import FormTemplate, Country
from app.models.validation import ValidationQuestion
from app.routes.admin import bp
from app.routes.admin.shared import permission_required
from app.services.validation_dashboard_service import (
    global_periods_for_template,
    list_countries_for_period,
    template_options,
)
from app.services.validation_questions_excel_service import (
    build_import_template_workbook,
    export_filename,
    export_questions_workbook,
    import_question_updates,
    query_validation_questions,
)
from app.utils.advanced_validation import validate_upload_extension_and_mime
from app.utils.api_responses import json_bad_request, json_ok, json_server_error
from app.utils.api_helpers import get_json_safe
from app.utils.file_parsing import EXCEL_EXTENSIONS
from flask_wtf import FlaskForm
from app.utils.datetime_helpers import utcnow
from app.utils.request_validation import enforce_csrf_json


@bp.route("/validation-questions", methods=["GET"])
@login_required
@permission_required("admin.data_explore.compliance")
def validation_questions_admin():
    return render_template(
        "admin/validation_questions.html",
        template_options=template_options(),
    )


@bp.route("/validation-questions/api/periods", methods=["GET"])
@login_required
@permission_required("admin.data_explore.compliance")
def validation_questions_periods_api():
    template_id = request.args.get("template_id", type=int)
    if not template_id:
        return json_bad_request("template_id is required")
    return json_ok(periods=global_periods_for_template(template_id))


@bp.route("/validation-questions/api/countries", methods=["GET"])
@login_required
@permission_required("admin.data_explore.compliance")
def validation_questions_countries_api():
    template_id = request.args.get("template_id", type=int)
    period = request.args.get("period", type=str)
    if not template_id or not period:
        return json_bad_request("template_id and period are required")
    return json_ok(countries=list_countries_for_period(template_id, period))


@bp.route("/validation-questions/api/list", methods=["GET"])
@login_required
@permission_required("admin.data_explore.compliance")
def validation_questions_list_api():
    template_id = request.args.get("template_id", type=int)
    period = request.args.get("period", type=str)
    status = request.args.get("status", type=str)
    country_id = request.args.get("country_id", type=int)

    rows = query_validation_questions(
        template_id=template_id,
        period=period,
        status=status,
        country_id=country_id,
        limit=500,
    )
    countries = {c.id: c.name for c in Country.query.all()}
    templates = {t.id: t.name for t in FormTemplate.query.all()}
    return json_ok(
        rows=[
            {
                "id": r.id,
                "template_id": r.template_id,
                "template_name": templates.get(r.template_id, ""),
                "entity_type": r.entity_type,
                "entity_id": r.entity_id,
                "entity_name": countries.get(r.entity_id) if r.entity_type == "country" else f"{r.entity_type}:{r.entity_id}",
                "period_name": r.period_name,
                "rule_code": r.rule_code,
                "severity": r.severity,
                "status": r.status,
                "question_text": r.question_text,
                "definition_text": r.definition_text,
                "answer_text": r.answer_text,
                "answered_at": r.answered_at.isoformat() if r.answered_at else None,
                "sent_at": r.sent_at.isoformat() if r.sent_at else None,
                "source": r.source,
                "form_item_id": r.form_item_id,
            }
            for r in rows
        ]
    )


@bp.route("/validation-questions/api/<int:question_id>/status", methods=["POST"])
@login_required
@permission_required("admin.data_explore.compliance")
def validation_questions_update_status(question_id: int):
    csrf_error = enforce_csrf_json()
    if csrf_error:
        return csrf_error
    data = get_json_safe()
    status = (data.get("status") or "").strip().lower()
    answer_text = (data.get("answer_text") or "").strip()
    if status not in {"open", "answered", "waived", "resolved"}:
        return json_bad_request("Invalid status")

    question = ValidationQuestion.query.get_or_404(question_id)
    question.status = status
    if status == "answered":
        if not answer_text and not (question.answer_text or "").strip():
            return json_bad_request("answer_text is required when status is answered")
        if answer_text:
            question.answer_text = answer_text
        question.answered_at = utcnow()
        question.answered_by_user_id = current_user.id
    elif status == "open":
        question.answer_text = None
        question.answered_at = None
        question.answered_by_user_id = None
    db.session.commit()
    return json_ok(id=question.id, status=question.status)


@bp.route("/validation-questions/export", methods=["GET"])
@login_required
@permission_required("admin.data_explore.compliance")
def validation_questions_export():
    template_id = request.args.get("template_id", type=int)
    period = request.args.get("period", type=str)
    status = request.args.get("status", type=str)
    country_id = request.args.get("country_id", type=int)
    output = export_questions_workbook(
        template_id=template_id,
        period=period,
        status=status,
        country_id=country_id,
    )
    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=export_filename(),
    )


@bp.route("/validation-questions/import-template", methods=["GET"])
@login_required
@permission_required("admin.data_explore.compliance")
def validation_questions_import_template():
    output = build_import_template_workbook()
    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="validation_questions_import_template.xlsx",
    )


@bp.route("/validation-questions/import", methods=["POST"])
@login_required
@permission_required("admin.data_explore.compliance")
def validation_questions_import():
    csrf_form = FlaskForm()
    if not csrf_form.validate_on_submit():
        return json_bad_request("Security validation failed. Please refresh and try again.")

    if "excel_file" not in request.files:
        return json_bad_request("No Excel file provided.")

    file = request.files["excel_file"]
    if not file or file.filename == "":
        return json_bad_request("No Excel file selected.")

    filename = secure_filename(file.filename)
    valid, error_msg, _ext = validate_upload_extension_and_mime(file, EXCEL_EXTENSIONS)
    if not valid:
        return json_bad_request(error_msg or "Invalid file type. Please upload an Excel file (.xlsx or .xls).")

    try:
        result = import_question_updates(
            file,
            filename,
            updated_by_user_id=current_user.id,
        )
    except ValueError as exc:
        return json_bad_request(str(exc))
    except Exception as exc:
        db.session.rollback()
        return json_server_error(str(exc))

    return json_ok(
        updated=result.updated,
        skipped=result.skipped,
        errors=result.errors,
        has_errors=bool(result.errors),
    )


