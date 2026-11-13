"""Edit fields and replace the file on a focal entity-repository document.

The web document modal and the mobile repository share this so a replaced
file is archived the same way in both places.
"""

from __future__ import annotations

import os
import uuid

from werkzeug.utils import secure_filename

COVER_IMAGE_TYPE = "Cover Image"

_ALLOWED_DOC_EXTS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".csv"}
_ALLOWED_IMG_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
_MAX_FILE_SIZE_MB = 50


class DocumentEditError(ValueError):
    """Field value the client sent cannot be stored."""


def user_manages_submitted_documents(user) -> bool:
    """System managers and document admins may edit rows the focal page locks."""
    from app.services.organization.authorization_service import AuthorizationService

    if not user or not getattr(user, "is_authenticated", False):
        return False
    return AuthorizationService.is_system_manager(user) or AuthorizationService.has_rbac_permission(
        user, "admin.documents.manage"
    )


def can_use_entity_document_repository(user) -> bool:
    """Focal uploaders, plus admins who manage documents on this same screen."""
    from app.services.organization.authorization_service import AuthorizationService

    return AuthorizationService.can_access_entity_document_repository(user) or user_manages_submitted_documents(
        user
    )


def focal_repository_can_edit(user, document) -> bool:
    """Focal uploaders edit pending rows. Document admins also edit approved ones."""
    from app.models.enums import DocumentStatus
    from app.routes.admin.content_management import _focal_user_can_access_submitted_document
    from app.services.organization.authorization_service import AuthorizationService

    if AuthorizationService.is_system_manager(user):
        return True
    if AuthorizationService.has_rbac_permission(user, "admin.documents.manage"):
        return _focal_user_can_access_submitted_document(document, user)
    if not AuthorizationService.can_access_entity_document_repository(user):
        return False
    status = DocumentStatus.normalize(getattr(document, "status", None))
    if status == DocumentStatus.APPROVED:
        return False
    return _focal_user_can_access_submitted_document(document, user)


def document_language_options() -> list[dict[str, str]]:
    """Every document language, matching the web document modal.

    Supported UI languages are pinned first. Every other code in
    ``Config.ALL_LANGUAGES_DISPLAY_NAMES`` follows, sorted by English name.
    ``name`` is the endonym when Babel knows it; ``english_name`` is the catalog
    name so clients can search in English too.
    """
    from config import Config
    from app.utils.i18n.language_names import language_endonym

    names = getattr(Config, "ALL_LANGUAGES_DISPLAY_NAMES", None) or {}
    catalog: dict[str, str] = {}
    for code, name in names.items():
        base = str(code).strip().replace("-", "_").split("_")[0].lower()
        label = str(name).strip() if name is not None else ""
        if not base or base in catalog or len(base) > 10:
            continue
        catalog[base] = label or base

    pinned: list[str] = []
    for code in _pinned_language_codes():
        if code in catalog and code not in pinned:
            pinned.append(code)

    others = sorted(
        (code for code in catalog if code not in pinned),
        key=lambda code: (catalog[code].casefold(), code),
    )

    options: list[dict[str, str]] = []
    for code in [*pinned, *others]:
        english = catalog[code]
        endonym = language_endonym(code)
        shown = endonym.strip() if isinstance(endonym, str) and endonym.strip() else english
        options.append({"code": code, "name": shown, "english_name": english})
    return options


def _pinned_language_codes() -> list[str]:
    """``en`` plus the configured UI languages, in that order."""
    raw = None
    try:
        from flask import current_app, has_app_context

        if has_app_context():
            raw = current_app.config.get("SUPPORTED_LANGUAGES") or current_app.config.get(
                "LANGUAGES"
            )
    except Exception:
        raw = None
    if not raw:
        from config import Config

        raw = getattr(Config, "LANGUAGES", None) or ["en"]

    pinned = ["en"]
    for code in raw:
        base = str(code).strip().replace("-", "_").split("_")[0].lower()
        if base and base not in pinned and len(base) <= 10:
            pinned.append(base)
    return pinned


def _coerce_checkbox(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "on", "yes"}


def _bounded_text(value, *, field: str, max_len: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > max_len:
        raise DocumentEditError(f"{field} is too long.")
    return text


def apply_entity_document_fields(document, data: dict, *, allow_status: bool = False) -> str | None:
    """Update filename, type, language, period, and public flag.

    Cover images drop language and period and stay public, matching the web modal.
    Linked entity is left unchanged. Approval status changes only when
    ``allow_status`` is true (system managers and document admins).

    Returns the previous normalized status when a status was applied, otherwise
    ``None``.
    """
    if "filename" in data:
        new_filename = _bounded_text(data.get("filename"), field="Filename", max_len=255)
        if new_filename and new_filename != document.filename:
            document.filename = secure_filename(new_filename) or document.filename

    if "document_type" in data:
        document_type = _bounded_text(data.get("document_type"), field="Document type", max_len=255)
        if document_type:
            document.document_type = document_type

    if document.document_type == COVER_IMAGE_TYPE:
        document.language = None
        document.period = None
        document.is_public = True
    else:
        if "language" in data:
            document.language = _bounded_text(data.get("language"), field="Language", max_len=10)

        if "period" in data or "year" in data:
            raw_period = data.get("period") if "period" in data else data.get("year")
            document.period = _bounded_text(raw_period, field="Period", max_len=100)

        if "is_public" in data:
            document.is_public = _coerce_checkbox(data.get("is_public"))

    return _apply_approval_status(document, data, allow_status=allow_status)


def _apply_approval_status(document, data: dict, *, allow_status: bool) -> str | None:
    if not allow_status or "status" not in data:
        return None
    raw = data.get("status")
    if raw is None or not str(raw).strip():
        return None
    from app.models.enums import DocumentStatus

    previous = DocumentStatus.normalize(getattr(document, "status", None))
    document.status = DocumentStatus.normalize(raw)
    return previous


def replace_submitted_document_file(document, file_storage) -> tuple[bool, list[str]]:
    """Archive the current file and store ``file_storage`` in its place.

    Returns ``(replaced, warnings)``. A warning means the file was left as it was.
    Metadata the caller already changed is not rolled back here.
    """
    from flask import current_app

    from app.models import PublicSubmission
    from app.models.assignments import AssignmentEntityStatus
    from app.routes.admin.content_management import _standalone_entity_for_library_paths
    from app.services.platform import storage_service as storage
    from app.utils.common.datetime_helpers import utcnow
    from app.utils.files.file_paths import save_submission_document

    new_filename = secure_filename(file_storage.filename or "")
    file_ext = os.path.splitext(new_filename)[1].lower()
    if file_ext not in _ALLOWED_DOC_EXTS and file_ext not in _ALLOWED_IMG_EXTS:
        return False, [
            f"File type '{file_ext}' is not allowed. Allowed types: PDF, DOC, DOCX, "
            "XLS, XLSX, PPT, PPTX, TXT, CSV, and images."
        ]

    file_storage.seek(0, 2)
    file_size = file_storage.tell()
    file_storage.seek(0)
    if file_size > _MAX_FILE_SIZE_MB * 1024 * 1024:
        return False, [f"File too large. Maximum size is {_MAX_FILE_SIZE_MB}MB."]

    old_storage_path = document.storage_path or ""
    old_thumb_path = document.thumbnail_relative_path
    old_main_cat = storage.submitted_document_rel_storage_category(old_storage_path)
    old_thumb_cat = (
        storage.submitted_document_rel_storage_category(old_thumb_path) if old_thumb_path else None
    )

    ps_for_replace = None
    replace_aes = None
    library_entity = None
    if document.assignment_entity_status_id and document.form_item_id:
        replace_aes = document.assignment_entity_status or AssignmentEntityStatus.query.get(
            document.assignment_entity_status_id
        )
        if not replace_aes:
            return False, ["Cannot replace file: assignment record missing."]
    elif document.public_submission_id and document.form_item_id:
        ps_for_replace = PublicSubmission.query.get(document.public_submission_id)
        if not ps_for_replace or not ps_for_replace.assigned_form_id:
            return False, ["Cannot replace file: public submission is missing assigned form."]
    else:
        library_entity = _standalone_entity_for_library_paths(document)
        if not library_entity:
            return False, ["Cannot replace file: linked entity is unknown."]

    archive_uuid = str(uuid.uuid4())
    version_record = {
        "filename": document.filename,
        "replaced_at": utcnow().isoformat(),
    }
    if old_storage_path:
        try:
            arc_rel = f"archive/{archive_uuid}/{os.path.basename(old_storage_path)}"
            storage.archive(old_main_cat, old_storage_path, arc_rel)
            storage.delete(old_main_cat, old_storage_path)
            version_record["storage_path"] = arc_rel
        except Exception as exc:
            current_app.logger.warning("[DOCUMENT_EDIT] Could not archive old file: %s", exc)

    if old_thumb_path and old_thumb_cat:
        try:
            arc_thumb = f"archive/{archive_uuid}/thumbnails/{os.path.basename(old_thumb_path)}"
            storage.archive(old_thumb_cat, old_thumb_path, arc_thumb)
            storage.delete(old_thumb_cat, old_thumb_path)
            version_record["thumbnail_relative_path"] = arc_thumb
        except Exception as exc:
            current_app.logger.warning("[DOCUMENT_EDIT] Could not archive old thumbnail: %s", exc)

    versions = list(document.archived_versions or [])
    versions.append(version_record)
    document.archived_versions = versions

    new_folder_uuid = str(uuid.uuid4())
    if document.assignment_entity_status_id and document.form_item_id and replace_aes:
        new_rel_path = save_submission_document(
            file_storage,
            document.assignment_entity_status_id,
            new_filename,
            is_public=False,
            entity_type=replace_aes.entity_type,
            entity_id=replace_aes.entity_id,
        )
    elif document.public_submission_id and document.form_item_id:
        new_rel_path = save_submission_document(
            file_storage,
            0,
            new_filename,
            is_public=True,
            form_id=ps_for_replace.assigned_form_id,
            submission_id=ps_for_replace.id,
            entity_type="country",
            entity_id=ps_for_replace.country_id,
        )
    else:
        et_slug, eid = library_entity
        new_rel_path = storage.upload(
            storage.ENTITY_REPO_ROOT,
            storage.standalone_entity_file_rel_path(et_slug, eid, new_folder_uuid, new_filename),
            file_storage,
        )

    document.filename = new_filename
    document.storage_path = new_rel_path
    document.thumbnail_filename = None
    document.thumbnail_relative_path = None
    current_app.logger.info(
        "[DOCUMENT_EDIT] File replaced for document %s: '%s' (old archived)",
        document.id,
        new_filename,
    )
    return True, []
