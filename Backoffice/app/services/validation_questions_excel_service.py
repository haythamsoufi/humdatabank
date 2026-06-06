"""Excel export/import for admin validation questions."""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd
from werkzeug.datastructures import FileStorage

from app import db
from app.models import Country, FormItem, FormTemplate
from app.models.validation import ValidationQuestion
from app.services.data_quality.helpers import form_item_label
from app.utils.file_parsing import parse_csv_or_excel_to_rows
from sqlalchemy.orm import joinedload
from app.services.validation_question_lifecycle import (
    apply_answer_outcome,
    clear_answer_received,
    clear_review_state,
    format_lifecycle_timestamp,
    mark_answer_received,
)

EXPORT_COLUMNS = [
    "ID",
    "Parent ID",
    "Follow-up Round",
    "Template ID",
    "Template",
    "Country",
    "Period",
    "Rule Code",
    "Indicator",
    "Severity",
    "Status",
    "Question",
    "Definition",
    "Answer Text",
    "Source",
    "Created At",
    "Drafted At",
    "Sent At",
    "Answer Received At",
    "Changes Made and Approved At",
    "No Changes Required and Approved At",
    "Language",
]

IMPORT_COLUMNS = ["ID", "Status", "Answer Text"]

VALID_STATUSES = {"open", "answered", "waived", "resolved"}
VALID_SEVERITIES = {"error", "warning", "info"}


@dataclass
class ValidationQuestionsImportResult:
    updated: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


def query_validation_questions(
    *,
    template_id: int | None = None,
    period: str | None = None,
    status: str | None = None,
    country_id: int | None = None,
    limit: int = 5000,
) -> list[ValidationQuestion]:
    q = ValidationQuestion.query
    if template_id:
        q = q.filter_by(template_id=template_id)
    if period:
        q = q.filter_by(period_name=period)
    if status:
        q = q.filter_by(status=status)
    if country_id:
        q = q.filter_by(entity_type="country", entity_id=country_id)
    return q.order_by(ValidationQuestion.asked_at.desc()).limit(limit).all()


def _country_names() -> dict[int, str]:
    return {c.id: c.name for c in Country.query.all()}


def _template_names() -> dict[int, str]:
    return {t.id: t.name for t in FormTemplate.query.all()}


def form_item_labels_for_questions(questions: list[ValidationQuestion]) -> dict[int, str]:
    item_ids = list({q.form_item_id for q in questions if q.form_item_id})
    if not item_ids:
        return {}
    items = (
        FormItem.query.options(joinedload(FormItem.indicator_bank))
        .filter(FormItem.id.in_(item_ids))
        .all()
    )
    return {item.id: form_item_label(item, f"Item {item.id}") for item in items}


def serialize_validation_question_grid_row(
    question: ValidationQuestion,
    *,
    countries: dict[int, str] | None = None,
    templates: dict[int, str] | None = None,
    form_item_labels: dict[int, str] | None = None,
    blocked_follow_up_parents: set[int] | None = None,
) -> dict[str, Any]:
    """JSON row for the Validation Questions admin AG Grid."""
    countries = countries or _country_names()
    templates = templates or _template_names()
    form_item_labels = form_item_labels if form_item_labels is not None else {}
    blocked_follow_up_parents = blocked_follow_up_parents or set()
    indicator_name = ""
    if question.form_item_id:
        indicator_name = form_item_labels.get(question.form_item_id, "")
    entity_name = (
        countries.get(question.entity_id)
        if question.entity_type == "country"
        else f"{question.entity_type}:{question.entity_id}"
    )
    return {
        "id": question.id,
        "parent_question_id": question.parent_question_id,
        "follow_up_round": question.follow_up_round or 0,
        "can_follow_up": question.status == "answered" and question.id not in blocked_follow_up_parents,
        "template_id": question.template_id,
        "template_name": templates.get(question.template_id, ""),
        "entity_type": question.entity_type,
        "entity_id": question.entity_id,
        "entity_name": entity_name or "",
        "period_name": question.period_name or "",
        "rule_code": question.rule_code or "",
        "indicator_name": indicator_name,
        "severity": question.severity or "",
        "status": question.status or "",
        "question_text": question.question_text or "",
        "definition_text": question.definition_text or "",
        "answer_text": question.answer_text or "",
        "answer_outcome": question.answer_outcome,
        "answered_at": question.answered_at.isoformat() if question.answered_at else None,
        "drafted_at": question.drafted_at.isoformat() if question.drafted_at else None,
        "changes_made_approved_at": question.changes_made_approved_at.isoformat()
        if question.changes_made_approved_at
        else None,
        "no_changes_approved_at": question.no_changes_approved_at.isoformat()
        if question.no_changes_approved_at
        else None,
        "sent_at": question.sent_at.isoformat() if question.sent_at else None,
        "source": question.source or "",
        "form_item_id": question.form_item_id,
    }


def serialize_question_row(
    question: ValidationQuestion,
    *,
    countries: dict[int, str] | None = None,
    templates: dict[int, str] | None = None,
    form_item_labels: dict[int, str] | None = None,
) -> dict[str, Any]:
    countries = countries or _country_names()
    templates = templates or _template_names()
    form_item_labels = form_item_labels if form_item_labels is not None else {}
    indicator_name = ""
    if question.form_item_id:
        indicator_name = form_item_labels.get(question.form_item_id, "")
    entity_name = (
        countries.get(question.entity_id)
        if question.entity_type == "country"
        else f"{question.entity_type}:{question.entity_id}"
    )
    return {
        "ID": question.id,
        "Parent ID": question.parent_question_id or "",
        "Follow-up Round": question.follow_up_round or 0,
        "Template ID": question.template_id,
        "Template": templates.get(question.template_id, ""),
        "Country": entity_name or "",
        "Period": question.period_name or "",
        "Rule Code": question.rule_code or "",
        "Indicator": indicator_name,
        "Severity": question.severity or "",
        "Status": question.status or "",
        "Question": question.question_text or "",
        "Definition": question.definition_text or "",
        "Answer Text": question.answer_text or "",
        "Source": question.source or "",
        "Created At": format_lifecycle_timestamp(question.asked_at),
        "Drafted At": format_lifecycle_timestamp(question.drafted_at),
        "Sent At": format_lifecycle_timestamp(question.sent_at),
        "Answer Received At": format_lifecycle_timestamp(question.answered_at),
        "Changes Made and Approved At": format_lifecycle_timestamp(question.changes_made_approved_at),
        "No Changes Required and Approved At": format_lifecycle_timestamp(question.no_changes_approved_at),
        "Language": question.language or "",
    }


def _auto_size_worksheet(ws) -> None:
    for column in ws.columns:
        max_length = max(len(str(cell.value or "")) for cell in column)
        column_letter = column[0].column_letter
        ws.column_dimensions[column_letter].width = min(max_length + 2, 60)


def build_workbook_bytes(rows: list[dict[str, Any]], sheet_name: str) -> io.BytesIO:
    df = pd.DataFrame(rows)
    if df.empty:
        df = pd.DataFrame(columns=EXPORT_COLUMNS if sheet_name != "Import Template" else IMPORT_COLUMNS)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)
        _auto_size_worksheet(writer.sheets[sheet_name])
    output.seek(0)
    return output


def export_questions_workbook(
    *,
    template_id: int | None = None,
    period: str | None = None,
    status: str | None = None,
    country_id: int | None = None,
) -> io.BytesIO:
    questions = query_validation_questions(
        template_id=template_id,
        period=period,
        status=status,
        country_id=country_id,
    )
    countries = _country_names()
    templates = _template_names()
    form_item_labels = form_item_labels_for_questions(questions)
    rows = [
        serialize_question_row(q, countries=countries, templates=templates, form_item_labels=form_item_labels)
        for q in questions
    ]
    return build_workbook_bytes(rows, "Validation Questions")


def build_import_template_workbook() -> io.BytesIO:
    sample = [
        {
            "ID": 1,
            "Status": "answered",
            "Answer Text": "Example response from focal point or admin.",
        },
        {
            "ID": 2,
            "Status": "waived",
            "Answer Text": "",
        },
    ]
    return build_workbook_bytes(sample, "Import Template")


def _normalize_row_keys(row: dict[str, Any]) -> dict[str, Any]:
    return {str(k).strip().lower(): v for k, v in row.items() if k is not None}


def _cell_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def apply_manual_question_update(
    question: ValidationQuestion,
    *,
    question_text: str,
    definition_text: str = "",
    status: str,
    answer_text: str = "",
    severity: str,
    answer_outcome: str | None = None,
    updated_by_user_id: int | None = None,
) -> None:
    """Apply admin edits to a validation question from the UI or API."""
    cleaned_question = (question_text or "").strip()
    if not cleaned_question:
        raise ValueError("question_text is required")

    normalized_status = (status or "").strip().lower()
    if normalized_status not in VALID_STATUSES:
        raise ValueError(f"Invalid status '{status}'.")

    normalized_severity = (severity or "").strip().lower()
    if normalized_severity not in VALID_SEVERITIES:
        raise ValueError(f"Invalid severity '{severity}'.")

    cleaned_answer = (answer_text or "").strip()
    question.question_text = cleaned_question
    question.definition_text = (definition_text or "").strip() or None
    question.severity = normalized_severity

    if normalized_status == "answered":
        if not cleaned_answer:
            raise ValueError("answer_text is required when status is answered")
        question.status = "answered"
        question.answer_text = cleaned_answer
        if not question.answered_at:
            mark_answer_received(question, user_id=updated_by_user_id)
        elif updated_by_user_id is not None:
            question.answered_by_user_id = updated_by_user_id
    elif normalized_status == "open":
        question.status = "open"
        question.answer_text = None
        clear_answer_received(question)
        clear_review_state(question)
    elif normalized_status == "waived":
        question.status = "waived"
        question.answer_text = cleaned_answer or None
        clear_review_state(question)
    else:
        question.status = "resolved"
        question.answer_text = cleaned_answer or None

    if normalized_status != "open":
        apply_answer_outcome(question, answer_outcome)
    elif answer_outcome:
        raise ValueError("answer_outcome cannot be set while status is open")


def import_question_updates(
    file: FileStorage,
    filename: str,
    *,
    updated_by_user_id: int | None = None,
) -> ValidationQuestionsImportResult:
    columns, rows = parse_csv_or_excel_to_rows(file, filename)
    if not rows:
        return ValidationQuestionsImportResult(errors=["No data rows found in file."])

    result = ValidationQuestionsImportResult()
    for idx, raw in enumerate(rows, start=2):
        row = _normalize_row_keys(raw)
        raw_id = row.get("id")
        if raw_id in (None, ""):
            result.skipped += 1
            continue

        try:
            question_id = int(float(raw_id))
        except (TypeError, ValueError):
            result.errors.append(f"Row {idx}: invalid ID '{raw_id}'.")
            continue

        question = ValidationQuestion.query.get(question_id)
        if not question:
            result.errors.append(f"Row {idx}: question ID {question_id} not found.")
            continue

        status = _cell_str(row.get("status")).lower()
        answer_text = _cell_str(row.get("answer text") or row.get("answer"))

        if status and status not in VALID_STATUSES:
            result.errors.append(f"Row {idx}: invalid status '{status}'.")
            continue

        changed = False
        if status:
            if status == "answered":
                if not answer_text:
                    result.errors.append(f"Row {idx}: answer text is required when status is answered.")
                    continue
                question.status = "answered"
                question.answer_text = answer_text
                mark_answer_received(question, user_id=updated_by_user_id)
                changed = True
            elif status == "waived":
                question.status = "waived"
                if answer_text:
                    question.answer_text = answer_text
                clear_answer_received(question)
                clear_review_state(question)
                changed = True
            elif status == "open":
                question.status = "open"
                question.answer_text = None
                clear_answer_received(question)
                clear_review_state(question)
                changed = True
        elif answer_text:
            question.status = "answered"
            question.answer_text = answer_text
            mark_answer_received(question, user_id=updated_by_user_id)
            changed = True

        if changed:
            result.updated += 1
        else:
            result.skipped += 1

    if result.updated:
        db.session.commit()
    else:
        db.session.rollback()

    return result


def export_filename() -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"validation_questions_{timestamp}.xlsx"
