"""Template image upload and serve routes for form-builder Image items."""

import os

from flask import abort, current_app, request
from flask_login import current_user

from app.routes.admin.shared import permission_required
from app.services import storage_service as storage
from app.utils.api_responses import json_bad_request, json_ok, json_server_error
from app.utils.template_image_assets import (
    TEMPLATE_ASSETS,
    upload_template_image,
    normalize_storage_path,
)

from . import bp


@bp.route("/templates/<int:template_id>/image-assets/upload", methods=["POST"])
@permission_required("admin.templates.edit")
def upload_template_image_asset(template_id):
    """Multipart upload for template-owned image assets (separate from JSON item save)."""
    from app.models import FormTemplate, FormTemplateVersion
    from .helpers import _ensure_template_access_or_redirect

    access_redirect = _ensure_template_access_or_redirect(template_id, request.form.get("version_id"))
    if access_redirect:
        return json_bad_request("Access denied", success=False)

    file = request.files.get("file")
    language = (request.form.get("language") or "en").strip().lower().split("_", 1)[0] or "en"
    version_id_raw = request.form.get("version_id")
    item_id_raw = request.form.get("item_id")
    current_path = request.form.get("current_storage_path")

    try:
        version_id = int(version_id_raw) if version_id_raw else None
    except (TypeError, ValueError):
        version_id = None
    try:
        item_id = int(item_id_raw) if item_id_raw else None
    except (TypeError, ValueError):
        item_id = None

    if not version_id:
        return json_bad_request("version_id is required", success=False)

    FormTemplate.query.get_or_404(template_id)
    FormTemplateVersion.query.filter_by(id=version_id, template_id=template_id).first_or_404()

    try:
        meta = upload_template_image(
            file,
            template_id=template_id,
            version_id=version_id,
            language=language,
            item_id=item_id,
        )
    except ValueError as exc:
        return json_bad_request(str(exc), success=False)
    except Exception as exc:
        current_app.logger.error("Template image upload failed: %s", exc, exc_info=True)
        return json_server_error("Upload failed", success=False)

    if current_path:
        from app.utils.template_image_assets import delete_template_image_if_present

        delete_template_image_if_present(current_path)

    serve_url = ""
    try:
        from flask import url_for

        serve_url = url_for(
            "form_builder.serve_template_image_asset",
            template_id=template_id,
            rel_path=meta["storage_path"],
        )
    except Exception:
        pass

    return json_ok(
        message="Uploaded",
        storage_path=meta["storage_path"],
        filename=meta.get("filename"),
        serve_url=serve_url,
        language=language,
        source_type="upload",
    )


@bp.route("/templates/<int:template_id>/image-assets/<path:rel_path>", methods=["GET"])
@permission_required("admin.templates.edit")
def serve_template_image_asset(template_id, rel_path):
    """Serve a template image for form-builder preview."""
    from .helpers import _ensure_template_access_or_redirect

    access_redirect = _ensure_template_access_or_redirect(template_id, request.args.get("version_id"))
    if access_redirect:
        abort(403)

    rel = normalize_storage_path(rel_path)
    if not rel or not rel.startswith(f"{template_id}/"):
        abort(404)
    safe_name = os.path.basename(rel.replace("\\", "/"))
    try:
        return storage.stream_response(
            TEMPLATE_ASSETS,
            rel,
            filename=safe_name,
            as_attachment=False,
        )
    except Exception as exc:
        current_app.logger.error("Error serving template image %s: %s", rel_path, exc)
        abort(404)
