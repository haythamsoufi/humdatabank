"""UPR Tools Guidance tab — upload/list/delete official UPR guidance files."""

from __future__ import annotations

from flask import request
from flask_login import current_user, login_required

from app.routes.admin.shared import admin_required, system_manager_required
from app.services.documents.guidance_document_service import (
    GuidanceDocumentError,
    delete_guidance_document,
    get_guidance_document,
    list_guidance_documents,
    save_guidance_document,
)
from app.services.platform import storage_service as storage
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE
from app.utils.api_responses import json_bad_request, json_forbidden, json_not_found, json_ok
from app.utils.error_handling import handle_json_view_exception
from plugins.upr import bp

OWNER_KEY = "upr"


@bp.route("/admin/upr-tools/guidance/list", methods=["GET"])
@login_required
@admin_required
@system_manager_required
def guidance_list():
    try:
        return json_ok(documents=list_guidance_documents(OWNER_KEY))
    except Exception as exc:
        return handle_json_view_exception(exc, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/admin/upr-tools/guidance/upload", methods=["POST"])
@login_required
@admin_required
@system_manager_required
def guidance_upload():
    try:
        upload = request.files.get("file")
        if upload is None or not (upload.filename or "").strip():
            return json_bad_request("Please select a file")
        title = (request.form.get("title") or "").strip() or None
        description = (request.form.get("description") or "").strip() or None
        doc = save_guidance_document(
            upload,
            owner_key=OWNER_KEY,
            uploaded_by_user_id=int(current_user.id),
            title=title,
            description=description,
        )
        return json_ok(document=_serialize(doc.id), message="Guidance document uploaded")
    except GuidanceDocumentError as exc:
        return json_bad_request(str(exc))
    except Exception as exc:
        return handle_json_view_exception(exc, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/admin/upr-tools/guidance/<int:doc_id>/delete", methods=["POST"])
@login_required
@admin_required
@system_manager_required
def guidance_delete(doc_id: int):
    try:
        doc = get_guidance_document(doc_id)
        if not doc:
            return json_not_found("Guidance document not found")
        if doc.owner_key != OWNER_KEY:
            return json_forbidden("This document does not belong to UPR")
        delete_guidance_document(doc)
        return json_ok(message="Guidance document deleted")
    except Exception as exc:
        return handle_json_view_exception(exc, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/admin/upr-tools/guidance/<int:doc_id>/download", methods=["GET"])
@login_required
@admin_required
@system_manager_required
def guidance_download(doc_id: int):
    try:
        doc = get_guidance_document(doc_id)
        if not doc or doc.owner_key != OWNER_KEY:
            return json_not_found("Guidance document not found")
        return storage.stream_response(
            storage.ADMIN_DOCUMENTS,
            doc.storage_path,
            filename=doc.filename,
            as_attachment=True,
        )
    except Exception as exc:
        return handle_json_view_exception(exc, GENERIC_ERROR_MESSAGE, status_code=500)


def _serialize(doc_id: int) -> dict:
    rows = [row for row in list_guidance_documents(OWNER_KEY) if row["id"] == doc_id]
    return rows[0] if rows else {"id": doc_id}
