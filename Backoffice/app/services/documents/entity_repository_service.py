"""Focal entity document repository — shared by web ``/documents`` and mobile API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import and_, literal, or_

from app.models import AssignedForm, SubmittedDocument, User
from app.models.assignments import AssignmentEntityStatus
from app.models.documents import submitted_document_countries
from app.models.enums import DocumentStatus, EntityType
from app.services.assignments.access_service import assignment_access_clause
from app.services.organization.entity_service import EntityService


def list_entity_repository_rows(user, entity_type: str, entity_id: int) -> list[tuple]:
    """
    Assignment-linked and standalone documents for one entity (same merge as
    ``main.documents_submit``).
    """
    from app.models import db

    sel_type = entity_type
    sel_id = int(entity_id)

    aes_id_subq = db.session.query(AssignmentEntityStatus.id).filter(
        AssignmentEntityStatus.entity_type == sel_type,
        AssignmentEntityStatus.entity_id == sel_id,
    )

    assignment_access = assignment_access_clause(user, AssignmentEntityStatus.assigned_form_id)
    assignment_raw_query = (
        db.session.query(
            SubmittedDocument,
            SubmittedDocument.status.label("status"),
            User,
            SubmittedDocument.uploaded_at.label("uploaded_at"),
            AssignedForm.period_name.label("assignment_period"),
            AssignmentEntityStatus,
        )
        .join(User, SubmittedDocument.uploaded_by_user_id == User.id)
        .join(AssignmentEntityStatus, SubmittedDocument.assignment_entity_status_id == AssignmentEntityStatus.id)
        .join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
        .filter(SubmittedDocument.assignment_entity_status_id.in_(aes_id_subq))
    )
    if assignment_access is not None:
        assignment_raw_query = assignment_raw_query.filter(assignment_access)
    assignment_raw = assignment_raw_query.order_by(SubmittedDocument.uploaded_at.desc()).all()

    _entity_country = EntityService.get_country_for_entity(sel_type, sel_id)

    assignment_tuples = []
    for doc, status, upload_user, uploaded_at, assignment_period, aes in assignment_raw:
        assignment_tuples.append((doc, status, _entity_country, upload_user, uploaded_at, assignment_period))

    standalone_clauses = [
        and_(
            SubmittedDocument.linked_entity_type == sel_type,
            SubmittedDocument.linked_entity_id == sel_id,
        ),
        SubmittedDocument.storage_path.startswith(f"{sel_type}/{sel_id}/", autoescape=True),
    ]
    if sel_type == EntityType.country.value:
        m2m_for_country = db.session.query(submitted_document_countries.c.submitted_document_id).filter(
            submitted_document_countries.c.country_id == sel_id
        )
        standalone_clauses.extend(
            [
                SubmittedDocument.country_id == sel_id,
                SubmittedDocument.id.in_(m2m_for_country),
            ]
        )

    from app.models import Country

    standalone_docs_query = (
        db.session.query(
            SubmittedDocument,
            SubmittedDocument.status.label("status"),
            Country,
            User,
            SubmittedDocument.uploaded_at.label("uploaded_at"),
            literal(None).label("assignment_period"),
        )
        .join(User, SubmittedDocument.uploaded_by_user_id == User.id)
        .outerjoin(Country, SubmittedDocument.country_id == Country.id)
        .filter(
            SubmittedDocument.assignment_entity_status_id.is_(None),
            SubmittedDocument.public_submission_id.is_(None),
            or_(*standalone_clauses),
        )
        .order_by(SubmittedDocument.uploaded_at.desc())
    )

    by_doc_id: dict[int, tuple] = {}
    for t in assignment_tuples:
        by_doc_id[t[0].id] = t
    standalone_query_rows = standalone_docs_query.all()
    for t in standalone_query_rows:
        if t[0].id not in by_doc_id:
            by_doc_id[t[0].id] = t

    return sorted(by_doc_id.values(), key=lambda row: row[4] or datetime.min, reverse=True)


def serialize_entity_document_row(row: tuple, *, viewer=None) -> dict[str, Any]:
    """JSON row for mobile ``Document`` model."""
    doc = row[0]
    status = row[1]
    country = row[2]
    user_or_name = row[3]
    uploaded_at = row[4]
    assignment_period = row[5]

    if hasattr(user_or_name, "name"):
        uploaded_by_name = user_or_name.name or user_or_name.email
    elif isinstance(user_or_name, str):
        uploaded_by_name = user_or_name
    else:
        uploaded_by_name = None

    status_value = getattr(status, "value", status)
    if hasattr(status_value, "value"):
        status_value = status_value.value

    country_name = None
    if country is not None:
        country_name = getattr(country, "name", None)

    own_period = (getattr(doc, "period", None) or "").strip()
    period_value = own_period or assignment_period or None

    from app.services.documents.entity_document_edit import (
        focal_repository_can_edit,
        user_manages_submitted_documents,
    )

    return {
        "id": doc.id,
        "file_name": doc.filename,
        "document_type": getattr(doc, "document_type", None) or getattr(doc, "document_label", None),
        "language": getattr(doc, "language", None),
        "period": period_value,
        "status": status_value,
        "country_name": country_name,
        "uploaded_by_name": uploaded_by_name,
        "uploaded_at": uploaded_at.isoformat() if uploaded_at else None,
        "assignment_period": (assignment_period or getattr(doc, "period", None)),
        "is_public": bool(getattr(doc, "is_public", False)),
        "can_edit": bool(viewer is not None and focal_repository_can_edit(viewer, doc)),
        "can_change_status": bool(
            viewer is not None and user_manages_submitted_documents(viewer)
        ),
    }


def serialize_submitted_document(doc, *, viewer=None) -> dict[str, Any]:
    """JSON row after an edit, when the list query tuple is not in hand."""
    aes = getattr(doc, "assignment_entity_status", None)
    assigned_form = getattr(aes, "assigned_form", None) if aes is not None else None
    assignment_period = getattr(assigned_form, "period_name", None) if assigned_form is not None else None
    country = None
    try:
        country = doc.document_country
    except Exception:
        country = getattr(doc, "country", None)
    return serialize_entity_document_row(
        (
            doc,
            getattr(doc, "status", None),
            country,
            getattr(doc, "uploaded_by_user", None),
            getattr(doc, "uploaded_at", None),
            assignment_period,
        ),
        viewer=viewer,
    )


def _row_status_value(row: tuple) -> str:
    status = row[1]
    if status is None:
        status = getattr(row[0], "status", None)
    return (getattr(status, "value", status) or "").lower()


def filter_entity_document_rows(
    rows: list[tuple],
    *,
    search: str | None = None,
    status: str | None = None,
    document_type: str | None = None,
) -> list[tuple]:
    """Client-side filters matching admin mobile list behaviour."""
    out = rows
    if search:
        needle = search.strip().lower()
        if needle:
            out = [
                r
                for r in out
                if needle in (getattr(r[0], "filename", "") or "").lower()
            ]
    if status:
        status_l = status.strip().lower()
        if status_l in DocumentStatus.ALL:
            out = [
                r
                for r in out
                if _row_status_value(r) == status_l
            ]
    if document_type:
        dtype = document_type.strip().lower()
        if dtype:
            out = [
                r
                for r in out
                if dtype in (getattr(r[0], "document_type", "") or "").lower()
                or dtype in (getattr(r[0], "document_label", "") or "").lower()
            ]
    return out
