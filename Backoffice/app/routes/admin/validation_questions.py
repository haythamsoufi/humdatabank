"""Admin validation questions management."""

from flask import render_template, request
from flask_login import login_required, current_user

from app import db
from app.models import FormTemplate, Country
from app.models.validation import ValidationQuestion
from app.routes.admin import bp
from app.routes.admin.shared import permission_required
from app.services.validation_check_service import run_validation_checks
from app.services.validation_dispatch_service import preview_dispatch, send_dispatch
from app.utils.api_responses import json_bad_request, json_ok, json_server_error
from app.utils.api_helpers import get_json_safe
from app.utils.request_validation import enforce_csrf_json


@bp.route("/validation-questions", methods=["GET"])
@login_required
@permission_required("admin.data_explore.compliance")
def validation_questions_admin():
    templates = FormTemplate.query.order_by(FormTemplate.id).all()
    template_options = [{"id": t.id, "name": t.name} for t in templates]
    return render_template(
        "admin/validation_questions.html",
        template_options=template_options,
        title="Validation Questions",
    )


@bp.route("/validation-questions/api/list", methods=["GET"])
@login_required
@permission_required("admin.data_explore.compliance")
def validation_questions_list_api():
    template_id = request.args.get("template_id", type=int)
    period = request.args.get("period", type=str)
    status = request.args.get("status", type=str)
    country_id = request.args.get("country_id", type=int)

    q = ValidationQuestion.query
    if template_id:
        q = q.filter_by(template_id=template_id)
    if period:
        q = q.filter_by(period_name=period)
    if status:
        q = q.filter_by(status=status)
    if country_id:
        q = q.filter_by(entity_type="country", entity_id=country_id)

    rows = q.order_by(ValidationQuestion.asked_at.desc()).limit(500).all()
    countries = {c.id: c.name for c in Country.query.all()}
    return json_ok(
        rows=[
            {
                "id": r.id,
                "template_id": r.template_id,
                "entity_type": r.entity_type,
                "entity_id": r.entity_id,
                "entity_name": countries.get(r.entity_id) if r.entity_type == "country" else f"{r.entity_type}:{r.entity_id}",
                "period_name": r.period_name,
                "rule_code": r.rule_code,
                "severity": r.severity,
                "status": r.status,
                "question_text": r.question_text,
                "sent_at": r.sent_at.isoformat() if r.sent_at else None,
                "source": r.source,
            }
            for r in rows
        ]
    )


@bp.route("/validation-questions/run-checks", methods=["POST"])
@login_required
@permission_required("admin.data_explore.compliance")
def validation_questions_run_checks():
    enforce_csrf_json()
    data = get_json_safe()
    template_id = data.get("template_id")
    period = data.get("period_name")
    entity_type = data.get("entity_type", "country")
    entity_id = data.get("entity_id")
    if not template_id or not period or entity_id is None:
        return json_bad_request("template_id, period_name, and entity_id are required")

    try:
        result = run_validation_checks(
            int(template_id),
            entity_type,
            int(entity_id),
            period,
            language=data.get("language", "en"),
        )
        return json_ok(
            created=result.created,
            updated=result.updated,
            resolved=result.resolved,
            skipped=result.skipped,
        )
    except Exception as exc:
        db.session.rollback()
        return json_server_error(str(exc))


@bp.route("/validation-questions/dispatch/preview", methods=["POST"])
@login_required
@permission_required("admin.data_explore.compliance")
def validation_dispatch_preview():
    enforce_csrf_json()
    data = get_json_safe()
    preview = preview_dispatch(
        int(data["template_id"]),
        data["period_name"],
        entity_type=data.get("entity_type"),
        entity_id=data.get("entity_id"),
        question_ids=data.get("question_ids"),
        channels=data.get("channels", []),
    )
    return json_ok(
        entities=preview.entities,
        questions=preview.questions,
        total_recipients=preview.total_recipients,
    )


@bp.route("/validation-questions/dispatch/send", methods=["POST"])
@login_required
@permission_required("admin.data_explore.compliance")
def validation_dispatch_send():
    enforce_csrf_json()
    data = get_json_safe()
    try:
        batch = send_dispatch(
            int(data["template_id"]),
            data["period_name"],
            created_by_user_id=current_user.id,
            channels=data.get("channels", ["in_app"]),
            entity_type=data.get("entity_type"),
            entity_id=data.get("entity_id"),
            question_ids=data.get("question_ids"),
            intro_message=data.get("intro_message"),
            override_email_preferences=bool(data.get("override_email_preferences")),
        )
        return json_ok(batch_id=batch.id, status=batch.status, summary=batch.summary)
    except Exception as exc:
        db.session.rollback()
        return json_server_error(str(exc))
