"""Validation questions API for focal points."""

from flask import request
from flask_login import login_required, current_user

from app import db
from app.models.validation import ValidationQuestion
from app.services.validation.question_lifecycle import clear_answer_received, clear_review_state, mark_answer_received
from app.routes.api import api_bp
from app.utils.api_helpers import json_response, api_error, get_json_safe
from app.utils.request_validation import enforce_csrf_json


def _user_can_access_entity(entity_type: str, entity_id: int) -> bool:
    return current_user.has_entity_access(entity_type, entity_id)


@api_bp.route("/validation-questions", methods=["GET"])
@login_required
def list_validation_questions():
    template_id = request.args.get("template_id", type=int)
    entity_type = request.args.get("entity_type", type=str)
    entity_id = request.args.get("entity_id", type=int)
    period = request.args.get("period", type=str)
    status = request.args.get("status", default="open", type=str)
    aes_id = request.args.get("assignment_entity_status_id", type=int)

    has_entity_scope = entity_type and entity_id is not None
    if not has_entity_scope and not aes_id:
        return api_error("entity_type+entity_id or assignment_entity_status_id is required", 400)

    q = ValidationQuestion.query
    if template_id:
        q = q.filter_by(template_id=template_id)

    if has_entity_scope:
        if not _user_can_access_entity(entity_type, entity_id):
            return api_error("Access denied", 403)
        q = q.filter_by(entity_type=entity_type, entity_id=entity_id)

    if aes_id:
        from app.models.assignments import AssignmentEntityStatus
        aes = AssignmentEntityStatus.query.get(aes_id)
        if not aes:
            return api_error("Assignment not found", 404)
        if not _user_can_access_entity(aes.entity_type, aes.entity_id):
            return api_error("Access denied", 403)
        q = q.filter_by(assignment_entity_status_id=aes_id)

    if period:
        q = q.filter_by(period_name=period)
    if status and status != "all":
        q = q.filter_by(status=status)

    rows = q.order_by(ValidationQuestion.severity, ValidationQuestion.asked_at.desc()).all()
    return json_response(
        {
            "questions": [
                {
                    "id": r.id,
                    "rule_code": r.rule_code,
                    "question_text": r.question_text,
                    "definition_text": r.definition_text,
                    "severity": r.severity,
                    "status": r.status,
                    "context": r.context,
                    "form_item_id": r.form_item_id,
                    "answer_text": r.answer_text,
                    "sent_at": r.sent_at.isoformat() if r.sent_at else None,
                    "parent_question_id": r.parent_question_id,
                    "follow_up_round": r.follow_up_round or 0,
                }
                for r in rows
            ]
        }
    )


@api_bp.route("/validation-questions/<int:question_id>/answer", methods=["POST"])
@login_required
def answer_validation_question(question_id: int):
    enforce_csrf_json()
    data = get_json_safe()
    answer_text = (data.get("answer_text") or "").strip()
    if not answer_text:
        return api_error("answer_text is required", 400)

    question = ValidationQuestion.query.get_or_404(question_id)
    if not _user_can_access_entity(question.entity_type, question.entity_id):
        return api_error("Access denied", 403)

    question.answer_text = answer_text
    question.status = "answered"
    mark_answer_received(question, user_id=current_user.id)
    db.session.commit()

    return json_response({"success": True, "id": question.id, "status": question.status})
