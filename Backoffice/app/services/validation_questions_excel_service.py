"""Excel export/import for admin validation questions."""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd
from werkzeug.datastructures import FileStorage

from app import db
from app.models import Country, FormTemplate
from app.models.validation import ValidationQuestion
from app.utils.datetime_helpers import utcnow
from app.utils.file_parsing import parse_csv_or_excel_to_rows

EXPORT_COLUMNS = [
    "ID",
    "Template ID",
    "Template",
    "Country",
    "Period",
    "Rule Code",
    "Severity",
    "Status",
    "Question",
    "Definition",
    "Answer Text",
    "Source",
    "Asked At",
    "Sent At",
    "Language",
]

IMPORT_COLUMNS = ["ID", "Status", "Answer Text"]

VALID_STATUSES = {"open", "answered", "waived"}


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


def serialize_question_row(
    question: ValidationQuestion,
    *,
    countries: dict[int, str] | None = None,
    templates: dict[int, str] | None = None,
) -> dict[str, Any]:
    countries = countries or _country_names()
    templates = templates or _template_names()
    entity_name = (
        countries.get(question.entity_id)
        if question.entity_type == "country"
        else f"{question.entity_type}:{question.entity_id}"
    )
    return {
        "ID": question.id,
        "Template ID": question.template_id,
        "Template": templates.get(question.template_id, ""),
        "Country": entity_name or "",
        "Period": question.period_name or "",
        "Rule Code": question.rule_code or "",
        "Severity": question.severity or "",
        "Status": question.status or "",
        "Question": question.question_text or "",
        "Definition": question.definition_text or "",
        "Answer Text": question.answer_text or "",
        "Source": question.source or "",
        "Asked At": question.asked_at.isoformat(sep=" ", timespec="seconds") if question.asked_at else "",
        "Sent At": question.sent_at.isoformat(sep=" ", timespec="seconds") if question.sent_at else "",
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
    rows = [serialize_question_row(q, countries=countries, templates=templates) for q in questions]
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
                question.answered_at = utcnow()
                question.answered_by_user_id = updated_by_user_id
                changed = True
            elif status == "waived":
                question.status = "waived"
                if answer_text:
                    question.answer_text = answer_text
                question.answered_at = None
                question.answered_by_user_id = None
                changed = True
            elif status == "open":
                question.status = "open"
                question.answer_text = None
                question.answered_at = None
                question.answered_by_user_id = None
                changed = True
        elif answer_text:
            question.status = "answered"
            question.answer_text = answer_text
            question.answered_at = utcnow()
            question.answered_by_user_id = updated_by_user_id
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
