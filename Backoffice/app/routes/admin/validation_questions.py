"""Admin validation questions management."""

from flask import render_template, request, send_file
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app import db
from app.models import FormTemplate, Country
from app.models.validation import ValidationQuestion
from app.routes.admin import bp
from app.routes.admin.shared import VALIDATION_QUESTIONS_PERMISSION, permission_required
from app.services.validation_dashboard_service import (
    global_periods_for_template,
    list_countries_for_period,
    template_options,
)
from app.services.validation_questions_excel_service import (
    apply_manual_question_update,
    build_import_template_workbook,
    export_filename,
    export_questions_workbook,
    form_item_labels_for_questions,
    import_question_updates,
    query_validation_questions,
    serialize_validation_question_grid_row,
)
from app.services.validation_question_follow_up import create_follow_up, parent_ids_with_open_follow_up
from app.services.validation_question_lifecycle import clear_answer_received, clear_review_state, mark_answer_received
from app.utils.advanced_validation import validate_upload_extension_and_mime
from app.utils.api_responses import json_bad_request, json_ok, json_server_error
from app.utils.api_helpers import get_json_safe
from app.utils.file_parsing import EXCEL_EXTENSIONS
from flask_wtf import FlaskForm
from app.utils.request_validation import enforce_csrf_json


@bp.route("/validation-questions", methods=["GET"])
@login_required
@permission_required(VALIDATION_QUESTIONS_PERMISSION)
def validation_questions_admin():
    return render_template(
        "admin/validation_questions.html",
        template_options=template_options(),
    )


@bp.route("/validation-questions/api/periods", methods=["GET"])
@login_required
@permission_required(VALIDATION_QUESTIONS_PERMISSION)
def validation_questions_periods_api():
    template_id = request.args.get("template_id", type=int)
    if not template_id:
        return json_bad_request("template_id is required")
    return json_ok(periods=global_periods_for_template(template_id))


@bp.route("/validation-questions/api/countries", methods=["GET"])
@login_required
@permission_required(VALIDATION_QUESTIONS_PERMISSION)
def validation_questions_countries_api():
    template_id = request.args.get("template_id", type=int)
    period = request.args.get("period", type=str)
    if not template_id or not period:
        return json_bad_request("template_id and period are required")
    return json_ok(countries=list_countries_for_period(template_id, period))


@bp.route("/validation-questions/api/list", methods=["GET"])
@login_required
@permission_required(VALIDATION_QUESTIONS_PERMISSION)
def validation_questions_list_api():
    template_id = request.args.get("template_id", type=int)
    period = request.args.get("period", type=str)
    status = request.args.get("status", type=str)
    country_id = request.args.get("country_id", type=int)

    _LIMIT = 500
    rows = query_validation_questions(
        template_id=template_id,
        period=period,
        status=status,
        country_id=country_id,
        limit=_LIMIT + 1,
    )
    truncated = len(rows) > _LIMIT
    if truncated:
        rows = rows[:_LIMIT]
    countries = {c.id: c.name for c in Country.query.all()}
    templates = {t.id: t.name for t in FormTemplate.query.all()}
    row_ids = [r.id for r in rows]
    blocked_follow_up_parents = parent_ids_with_open_follow_up(row_ids)
    form_item_labels = form_item_labels_for_questions(rows)
    payload_rows = [
        serialize_validation_question_grid_row(
            r,
            countries=countries,
            templates=templates,
            form_item_labels=form_item_labels,
            blocked_follow_up_parents=blocked_follow_up_parents,
        )
        for r in rows
    ]
    response, status_code = json_ok(rows=payload_rows, truncated=truncated)
    response.headers["Cache-Control"] = "no-store"
    return response, status_code


@bp.route("/validation-questions/api/<int:question_id>/follow-up", methods=["POST"])
@login_required
@permission_required(VALIDATION_QUESTIONS_PERMISSION)
def validation_questions_create_follow_up(question_id: int):
    csrf_error = enforce_csrf_json()
    if csrf_error:
        return csrf_error
    data = get_json_safe()
    parent = ValidationQuestion.query.get_or_404(question_id)
    try:
        follow_up = create_follow_up(
            parent,
            question_text=data.get("question_text", ""),
            definition_text=data.get("definition_text", ""),
            severity=data.get("severity"),
        )
    except ValueError as exc:
        return json_bad_request(str(exc))
    except Exception as exc:
        db.session.rollback()
        return json_server_error(str(exc))

    db.session.commit()
    return json_ok(
        id=follow_up.id,
        parent_question_id=follow_up.parent_question_id,
        follow_up_round=follow_up.follow_up_round,
        status=follow_up.status,
        question_text=follow_up.question_text,
    )


@bp.route("/validation-questions/api/<int:question_id>", methods=["POST"])
@login_required
@permission_required(VALIDATION_QUESTIONS_PERMISSION)
def validation_questions_update(question_id: int):
    csrf_error = enforce_csrf_json()
    if csrf_error:
        return csrf_error
    data = get_json_safe()
    question = ValidationQuestion.query.get_or_404(question_id)
    try:
        apply_manual_question_update(
            question,
            question_text=data.get("question_text", ""),
            definition_text=data.get("definition_text", ""),
            status=data.get("status", ""),
            answer_text=data.get("answer_text", ""),
            severity=data.get("severity", question.severity),
            answer_outcome=data.get("answer_outcome"),
            updated_by_user_id=current_user.id,
        )
    except ValueError as exc:
        return json_bad_request(str(exc))
    except Exception as exc:
        db.session.rollback()
        return json_server_error(str(exc))

    db.session.commit()
    return json_ok(
        id=question.id,
        status=question.status,
        severity=question.severity,
        question_text=question.question_text,
        definition_text=question.definition_text,
        answer_text=question.answer_text,
        answer_outcome=question.answer_outcome,
        answered_at=question.answered_at.isoformat() if question.answered_at else None,
        changes_made_approved_at=question.changes_made_approved_at.isoformat()
        if question.changes_made_approved_at
        else None,
        no_changes_approved_at=question.no_changes_approved_at.isoformat()
        if question.no_changes_approved_at
        else None,
    )


@bp.route("/validation-questions/api/<int:question_id>/status", methods=["POST"])
@login_required
@permission_required(VALIDATION_QUESTIONS_PERMISSION)
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
        if not question.answered_at:
            mark_answer_received(question, user_id=current_user.id)
        else:
            question.answered_by_user_id = current_user.id
    elif status == "open":
        question.answer_text = None
        clear_answer_received(question)
        clear_review_state(question)
    elif status == "waived":
        clear_review_state(question)
    db.session.commit()
    return json_ok(id=question.id, status=question.status)


@bp.route("/validation-questions/export", methods=["GET"])
@login_required
@permission_required(VALIDATION_QUESTIONS_PERMISSION)
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
@permission_required(VALIDATION_QUESTIONS_PERMISSION)
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
@permission_required(VALIDATION_QUESTIONS_PERMISSION)
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


