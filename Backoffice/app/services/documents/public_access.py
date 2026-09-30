"""Authorization policy and URL generation for unauthenticated ``SubmittedDocument`` access.

Authorization (visibility + approval) is the primary control for every no-login route.
The opaque ``public_id`` is defense in depth: it keeps files from being discoverable by
counting integer ids and limits the blast radius of a future policy regression. Every
link handed to a browser, API client, email or the Website must be built here so the
integer primary key is never embedded in a public URL.
"""

from __future__ import annotations

import os
import uuid
from typing import Optional, Union

from flask import current_app, url_for

from app.models import SubmittedDocument
from app.models.enums import DocumentStatus

DocumentIdentifier = Union[int, uuid.UUID]


def public_download_rate_limit() -> str:
    """Flask-Limiter rate string for unauthenticated file downloads (per client IP)."""
    return (
        current_app.config.get("PUBLIC_DOWNLOAD_RATE_LIMIT")
        or os.environ.get("PUBLIC_DOWNLOAD_RATE_LIMIT")
        or "60 per minute"
    )


def is_public_and_approved(document: SubmittedDocument) -> bool:
    """Visibility gate shared by all unauthenticated document routes."""
    return bool(document.is_public) and DocumentStatus.normalize(document.status) == DocumentStatus.APPROVED


def is_publicly_downloadable(document: SubmittedDocument) -> bool:
    """Files uploaded through a public form become downloadable only once published and approved."""
    return bool(document.public_submission_id) and is_public_and_approved(document)


def is_publicly_displayable(document: SubmittedDocument) -> bool:
    """Thumbnails and inline cover images require the same visibility gate."""
    return is_public_and_approved(document)


def parse_public_id(raw: object) -> Optional[uuid.UUID]:
    if isinstance(raw, uuid.UUID):
        return raw
    try:
        return uuid.UUID(str(raw))
    except (ValueError, AttributeError, TypeError):
        return None


def find_document(identifier: DocumentIdentifier) -> Optional[SubmittedDocument]:
    """Resolve a document by opaque ``public_id`` (``UUID``) or legacy integer id (``int``)."""
    if isinstance(identifier, uuid.UUID):
        return SubmittedDocument.query.filter_by(public_id=identifier).first()
    if isinstance(identifier, int) and not isinstance(identifier, bool):
        return SubmittedDocument.query.get(identifier)
    return None


def public_document_download_url(document: SubmittedDocument, *, external: bool = False) -> str:
    return url_for(
        "forms.download_public_document_by_public_id",
        public_id=document.public_id,
        _external=external,
    )


def public_document_display_url(document: SubmittedDocument, *, external: bool = False) -> str:
    return url_for(
        "public.display_document_file_by_public_id",
        public_id=document.public_id,
        _external=external,
    )


def public_document_thumbnail_url(document: SubmittedDocument, *, external: bool = False) -> str:
    return url_for(
        "public.download_document_thumbnail_by_public_id",
        public_id=document.public_id,
        _external=external,
    )
