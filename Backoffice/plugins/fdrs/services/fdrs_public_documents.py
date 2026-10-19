"""Legacy ``GET /api/documents`` from Backoffice publications and submitted documents.

The data.ifrc.org client reads ``response[0].documents``.

- No ``ns``: publications from Manage Resources (``resource_type = publication``).
  ``type`` is ``EveryoneCounts``, ``Analysis``, ``FrontendVideo``, or ``DocumentGuide``,
  matched to the resource subcategory name. A video translation has no file; ``url``
  is the YouTube link. A document translation's ``url`` is the download route.
- ``ns``: public approved submitted documents for that society's country
  (the country column, the assignment, or the extra country links).
"""

from __future__ import annotations

import re
from typing import Any, Optional

from flask import url_for
from sqlalchemy import and_, or_
from sqlalchemy.orm import joinedload

from app.models import Country, NationalSociety, Resource, SubmittedDocument
from app.models.assignments import AssignmentEntityStatus
from app.models.enums import DocumentStatus
from app.services.data_quality.helpers import parse_period_year
from app.services.documents.public_access import (
    is_public_and_approved,
    public_document_display_url,
    public_document_thumbnail_url,
)

_TYPE_BY_SUBCATEGORY = {
    "everyonecounts": "EveryoneCounts",
    "everyonecountsreport": "EveryoneCounts",
    "analysis": "Analysis",
    "covid19": "Analysis",
    "ukraineandimpactedcountries": "Analysis",
    "frontendvideo": "FrontendVideo",
    "videoguide": "FrontendVideo",
    "video": "FrontendVideo",
    "videos": "FrontendVideo",
    "documentguide": "DocumentGuide",
}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").casefold())


def publication_type_code(resource: Resource) -> Optional[str]:
    """Legacy ``type`` for a publication, taken from its subcategory name."""
    subcategory = resource.resource_subcategory
    return _TYPE_BY_SUBCATEGORY.get(_slug(subcategory.name if subcategory else ""))


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = value.isoformat()
    return text.replace("+00:00", "Z") if text.endswith("+00:00") else text


def _resource_file_url(resource_id: int, language: str) -> str:
    return url_for(
        "public.download_resource_file",
        resource_id=resource_id,
        language=language,
        _external=True,
    )


def _resource_thumb_url(resource_id: int, language: str) -> str:
    return url_for(
        "public.download_resource_thumbnail",
        resource_id=resource_id,
        language=language,
        _external=True,
    )


def _translation_public_url(translation) -> str | None:
    """YouTube (or other allowlisted) link for a translation that has no uploaded file."""
    if translation is None:
        return None
    from app.utils.external_url_validation import safe_resource_external_url

    raw = getattr(translation, "external_url", None)
    if not isinstance(raw, str):
        return None
    return safe_resource_external_url(raw)


def _publication_entries(resource: Resource) -> list[dict[str, Any]]:
    year = resource.publication_date.year if resource.publication_date else None
    subcategory = resource.resource_subcategory.name if resource.resource_subcategory else "Publication"
    legacy_type = publication_type_code(resource) or subcategory
    translations = list(resource.translations)
    # A video has no file. Include it when the link is allowlisted. A publication
    # with neither a file nor a link still returns one row, matching the previous shape.
    with_assets = [
        row for row in translations
        if row.has_uploaded_document or _translation_public_url(row)
    ]
    if with_assets:
        rows = with_assets
    elif any(row.has_external_link for row in translations):
        # A link was stored, but it is not allowlisted. Do not invent a null URL.
        return []
    else:
        rows = [None]
    documents = []
    for translation in rows:
        language = (translation.language_code if translation else "en") or "en"
        title = translation.title if translation else resource.default_title
        filename = translation.document_display_name if translation else None
        has_file = bool(translation and translation.file_relative_path)
        external_url = _translation_public_url(translation) or ""
        thumb = translation if translation and translation.thumbnail_relative_path else None
        if thumb is None:
            english = resource.get_translation("en")
            if english and english.thumbnail_relative_path:
                thumb = english
        thumb_language = thumb.language_code if thumb else language
        documents.append(
            {
                "name": filename or title,
                "title": title,
                "description": (translation.description if translation else None) or resource.default_description,
                "url": (
                    _resource_file_url(resource.id, language)
                    if has_file
                    else (external_url or None)
                ),
                "thumbnail": _resource_thumb_url(resource.id, thumb_language) if thumb else None,
                "year": year,
                "YearText": str(year) if year else None,
                "document_type": legacy_type,
                "LangCode": language,
                "ApprovalStatus": "Validated (Public)",
                "Public": 1,
                "ModifiedAt": _iso(resource.updated_at),
            }
        )
    return documents


def publication_documents(type_name: Optional[str]) -> list[dict[str, Any]]:
    wanted = (type_name or "").strip()
    resources = (
        Resource.query.options(joinedload(Resource.resource_subcategory))
        .filter(Resource.resource_type == "publication")
        .order_by(Resource.publication_date.desc().nullslast(), Resource.id.desc())
        .all()
    )
    documents: list[dict[str, Any]] = []
    for resource in resources:
        code = publication_type_code(resource)
        if wanted and code != wanted:
            continue
        documents.extend(_publication_entries(resource))
    return documents


def _submitted_documents_for_country(country_id: int) -> list[SubmittedDocument]:
    rows = (
        SubmittedDocument.query.options(
            joinedload(SubmittedDocument.form_item),
            joinedload(SubmittedDocument.assignment_entity_status),
        )
        .outerjoin(
            AssignmentEntityStatus,
            SubmittedDocument.assignment_entity_status_id == AssignmentEntityStatus.id,
        )
        .filter(SubmittedDocument.is_public.is_(True))
        .filter(
            or_(
                SubmittedDocument.country_id == country_id,
                and_(
                    AssignmentEntityStatus.entity_type == "country",
                    AssignmentEntityStatus.entity_id == country_id,
                ),
                SubmittedDocument.countries.any(Country.id == country_id),
            )
        )
        .order_by(SubmittedDocument.uploaded_at.desc(), SubmittedDocument.id.desc())
        .all()
    )
    seen: set[int] = set()
    kept: list[SubmittedDocument] = []
    for document in rows:
        if document.id in seen or not is_public_and_approved(document):
            continue
        seen.add(document.id)
        kept.append(document)
    return kept


def _submitted_entry(document: SubmittedDocument) -> Optional[dict[str, Any]]:
    url = (document.source_url or "").strip() or None
    if document.storage_path and not document.file_pending:
        url = public_document_display_url(document, external=True)
    elif not url:
        return None
    thumbnail = (document.thumbnail_source_url or "").strip() or None
    if document.thumbnail_relative_path:
        thumbnail = public_document_thumbnail_url(document, external=True)
    year = parse_period_year(document.period or "") or (
        document.uploaded_at.year if document.uploaded_at else None
    )
    label = document.document_type or (document.form_item.label if document.form_item else None) or "Document"
    return {
        "name": document.filename,
        "title": document.document_label,
        "url": url,
        "thumbnail": thumbnail,
        "year": year,
        "YearText": document.period or (str(year) if year else None),
        "document_type": label,
        "LangCode": (document.language or "en").strip().lower() or "en",
        "ApprovalStatus": "Validated (Public)",
        "Public": 1,
        "ModifiedAt": _iso(document.uploaded_at),
    }


def society_documents(don_code: str) -> Optional[list[dict[str, Any]]]:
    """``None`` when the DON code is not an active society."""
    society = NationalSociety.query.filter(
        NationalSociety.fdrs_don_code == (don_code or "").strip().upper(),
        NationalSociety.is_active.is_(True),
    ).first()
    if society is None:
        return None
    documents: list[dict[str, Any]] = []
    if society.country_id is not None:
        for document in _submitted_documents_for_country(society.country_id):
            entry = _submitted_entry(document)
            if entry is not None:
                documents.append(entry)
    return [{"code": society.fdrs_don_code, "documents": documents}]


def list_documents(*, type_name: Optional[str], ns: Optional[str]) -> Optional[list[dict[str, Any]]]:
    if (ns or "").strip():
        return society_documents(ns)
    return [{"code": "", "documents": publication_documents(type_name)}]
