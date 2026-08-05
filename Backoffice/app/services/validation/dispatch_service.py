"""
Prepare and send validation questions to focal points (email + in-app).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from flask import url_for

from app import db
from app.models import FormTemplate, User
from app.models.enums import NotificationType
from app.models.validation import ValidationDispatchBatch, ValidationQuestion
from app.services.organization.entity_service import EntityService
from app.services.notification.audience import get_assignment_editor_submitter_user_ids_for_entity
from app.services.notification.core import create_notification
from app.utils.datetime_helpers import utcnow


@dataclass
class DispatchPreview:
    entities: list[dict[str, Any]] = field(default_factory=list)
    questions: list[dict[str, Any]] = field(default_factory=list)
    total_recipients: int = 0


def _questions_query(
    template_id: int,
    period_name: str,
    *,
    entity_type: str | None = None,
    entity_id: int | None = None,
    question_ids: list[int] | None = None,
    status: str = "open",
):
    q = ValidationQuestion.query.filter_by(
        template_id=template_id,
        period_name=period_name,
        status=status,
    )
    if entity_type and entity_id is not None:
        q = q.filter_by(entity_type=entity_type, entity_id=entity_id)
    if question_ids:
        q = q.filter(ValidationQuestion.id.in_(question_ids))
    return q.order_by(ValidationQuestion.severity, ValidationQuestion.rule_code)


def preview_dispatch(
    template_id: int,
    period_name: str,
    *,
    entity_type: str | None = None,
    entity_id: int | None = None,
    question_ids: list[int] | None = None,
    channels: list[str] | None = None,
) -> DispatchPreview:
    questions = _questions_query(
        template_id, period_name, entity_type=entity_type, entity_id=entity_id, question_ids=question_ids
    ).all()

    entity_keys: set[tuple[str, int]] = set()
    for q in questions:
        entity_keys.add((q.entity_type, q.entity_id))

    entity_name_map = EntityService.batch_entity_names(
        list(entity_keys), include_hierarchy=False, localized=True,
    ) if entity_keys else {}

    entities_out = []
    total_recipients = 0
    for et, eid in sorted(entity_keys):
        user_ids = get_assignment_editor_submitter_user_ids_for_entity(et, eid)
        users = User.query.filter(User.id.in_(user_ids)).all() if user_ids else []
        total_recipients += len(users)
        name = entity_name_map.get((et, eid)) or f"{et}:{eid}"
        entities_out.append(
            {
                "entity_type": et,
                "entity_id": eid,
                "entity_name": name,
                "recipient_count": len(users),
                "recipients": [{"id": u.id, "email": u.email, "name": u.name} for u in users],
            }
        )

    q_rows = [
        {
            "id": q.id,
            "rule_code": q.rule_code,
            "severity": q.severity,
            "question_text": q.question_text[:500],
            "entity_type": q.entity_type,
            "entity_id": q.entity_id,
            "form_item_id": q.form_item_id,
            "context": q.context,
        }
        for q in questions
    ]
    return DispatchPreview(entities=entities_out, questions=q_rows, total_recipients=total_recipients)


def build_validation_email_html(
    questions: list[ValidationQuestion],
    entity_name: str,
    period_name: str,
    template_name: str,
    entry_url: str,
    intro_message: str | None = None,
) -> str:
    intro = intro_message or f"Please review the following data validation questions for {entity_name} ({period_name})."
    rows_html = ""
    for q in questions:
        ctx_preview = ""
        if q.context:
            parts = [f"{k}: {v}" for k, v in list(q.context.items())[:5] if k != "triggered_rules"]
            ctx_preview = "<br>".join(parts)
        rows_html += f"""
        <tr>
          <td style="border:1px solid #ddd;padding:8px;">{q.severity}</td>
          <td style="border:1px solid #ddd;padding:8px;">{q.rule_code}</td>
          <td style="border:1px solid #ddd;padding:8px;">{q.question_text}</td>
          <td style="border:1px solid #ddd;padding:8px;font-size:12px;">{ctx_preview}</td>
        </tr>"""

    return f"""
    <html><body style="font-family:Arial,sans-serif;">
    <p>{intro}</p>
    <p><strong>{template_name}</strong> — {period_name} — {entity_name}</p>
    <table style="border-collapse:collapse;width:100%;margin:16px 0;">
      <thead><tr style="background:#f3f4f6;">
        <th style="border:1px solid #ddd;padding:8px;">Severity</th>
        <th style="border:1px solid #ddd;padding:8px;">Rule</th>
        <th style="border:1px solid #ddd;padding:8px;">Question</th>
        <th style="border:1px solid #ddd;padding:8px;">Context</th>
      </tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
    <p><a href="{entry_url}">Open assignment to respond</a></p>
    </body></html>
    """


def send_dispatch(
    template_id: int,
    period_name: str,
    *,
    created_by_user_id: int,
    channels: list[str],
    entity_type: str | None = None,
    entity_id: int | None = None,
    question_ids: list[int] | None = None,
    intro_message: str | None = None,
    override_email_preferences: bool = False,
) -> ValidationDispatchBatch:
    template = FormTemplate.query.get_or_404(template_id)
    batch = ValidationDispatchBatch(
        template_id=template_id,
        period_name=period_name,
        created_by_user_id=created_by_user_id,
        channels=channels,
        scope={
            "entity_type": entity_type,
            "entity_id": entity_id,
            "question_ids": question_ids,
        },
        status="draft",
        intro_message=intro_message,
    )
    db.session.add(batch)
    db.session.flush()

    questions = _questions_query(
        template_id, period_name, entity_type=entity_type, entity_id=entity_id, question_ids=question_ids
    ).all()

    by_entity: dict[tuple[str, int], list[ValidationQuestion]] = {}
    for q in questions:
        by_entity.setdefault((q.entity_type, q.entity_id), []).append(q)

    dispatch_entity_names = EntityService.batch_entity_names(
        list(by_entity.keys()), include_hierarchy=True, localized=True,
    ) if by_entity else {}

    sent_count = 0
    failed_count = 0
    now = utcnow()

    for (et, eid), entity_questions in by_entity.items():
        user_ids = get_assignment_editor_submitter_user_ids_for_entity(et, eid)
        if not user_ids:
            failed_count += 1
            continue

        aes_id = entity_questions[0].assignment_entity_status_id
        entry_path = f"/forms/assignment/{aes_id}?validation_panel=open" if aes_id else None
        entry_url = ""
        if entry_path:
            try:
                entry_url = url_for("forms.view_edit_form", form_type="assignment", form_id=aes_id, _external=True)
                entry_url += "?validation_panel=open"
            except Exception:
                entry_url = entry_path

        entity_name = dispatch_entity_names.get((et, eid)) or str(eid)

        assignment_title = template.name
        if period_name:
            assignment_title = f"{template.name} \u2013 {period_name}"
        if aes_id:
            try:
                from app.models.assignments import AssignmentEntityStatus

                aes = AssignmentEntityStatus.query.get(aes_id)
                if aes and aes.assigned_form:
                    assignment_title = aes.assigned_form.display_name or assignment_title
            except Exception:
                pass

        title_params = {"assignment_title": assignment_title}

        if "in_app" in channels:
            n = len(entity_questions)
            create_notification(
                user_ids=user_ids,
                notification_type=NotificationType.validation_questions,
                title_key="notification.validation_questions.title",
                title_params=title_params,
                message_key="notification.validation_questions.message",
                message_params={"count": n, "entity": entity_name},
                entity_type=et,
                entity_id=eid,
                related_object_type="validation_dispatch_batch",
                related_object_id=batch.id,
                related_url=entry_path,
                priority="high" if any(q.severity == "error" for q in entity_questions) else "normal",
                respect_preferences=False,
                send_email_notifications=False,
                action_buttons=[{"label": "Review questions", "endpoint": entry_path}] if entry_path else None,
            )

        if "email" in channels:
            summary_lines = [f"- [{q.severity}] {q.question_text[:200]}" for q in entity_questions[:20]]
            plain_summary = "\n".join(summary_lines)
            create_notification(
                user_ids=user_ids,
                notification_type=NotificationType.validation_questions,
                title_key="notification.validation_questions.title",
                title_params=title_params,
                message_key="notification.validation_questions.message",
                message_params={"count": len(entity_questions), "entity": entity_name, "summary": plain_summary},
                entity_type=et,
                entity_id=eid,
                related_url=entry_path,
                priority="high" if any(q.severity == "error" for q in entity_questions) else "normal",
                respect_preferences=not override_email_preferences,
                override_email_preferences=override_email_preferences,
                send_email_notifications=True,
                send_push_notifications=False,
            )

        for q in entity_questions:
            q.dispatch_batch_id = batch.id
            q.sent_at = now
            q.delivery_channels = channels
        sent_count += len(user_ids)

    batch.status = "sent"
    batch.sent_at = now
    batch.summary = {"sent": sent_count, "failed": failed_count, "questions": len(questions)}
    db.session.commit()
    return batch
