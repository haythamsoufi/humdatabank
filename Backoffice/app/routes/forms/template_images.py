"""Serve template-owned images on the entry form."""
from __future__ import annotations

import os
import uuid

from flask import abort, current_app, request
from flask_login import current_user

from app.models import AssignedForm, FormItem
from app.services.platform import storage_service as storage
from app.utils.template_image_assets import TEMPLATE_ASSETS


def _normalize_storage_path(storage_path: str | None) -> str | None:
    if not storage_path or not isinstance(storage_path, str):
        return None
    rel = storage_path.strip().replace("\\", "/").strip("/")
    if not rel or ".." in rel.split("/"):
        return None
    return rel


def _public_form_token_from_request() -> str | None:
    raw = request.args.get("public_token")
    if not raw:
        return None
    try:
        return str(uuid.UUID(raw))
    except (ValueError, AttributeError, TypeError):
        return None


def _public_form_grants_image_access(form_item: FormItem, token: str) -> bool:
    """Anonymous visitors may load an image only through a live public form that renders it."""
    assigned_form = AssignedForm.query.filter_by(unique_token=token).first()
    if assigned_form is None:
        return False
    if not (assigned_form.is_public_active and assigned_form.is_public_submission_allowed):
        return False
    template = assigned_form.template
    return bool(
        template is not None
        and template.published_version_id is not None
        and form_item.version_id == template.published_version_id
    )


def register_template_image_routes(bp):
    """Register template image serve routes onto the forms blueprint."""

    @bp.route("/template-image/<int:item_id>/<path:rel_path>", methods=["GET"])
    def serve_template_image(item_id, rel_path):
        """Serve a template image asset for entry-form display.

        Authenticated users are served directly. Anonymous visitors must present the
        ``public_token`` of an active public form whose published version contains the item.
        """
        public_token = None
        if not current_user.is_authenticated:
            public_token = _public_form_token_from_request()
            if public_token is None:
                abort(403)

        form_item = FormItem.query.get_or_404(item_id)
        if form_item.item_type != "image":
            abort(404)

        rel = _normalize_storage_path(rel_path)
        if not rel:
            abort(404)

        config = form_item.config if isinstance(form_item.config, dict) else {}
        image_cfg = config.get("image") if isinstance(config, dict) else {}
        sources = image_cfg.get("sources") if isinstance(image_cfg, dict) else {}
        allowed_paths = set()
        if isinstance(sources, dict):
            for src in sources.values():
                if isinstance(src, dict) and src.get("source_type") == "upload":
                    path = _normalize_storage_path(src.get("storage_path"))
                    if path:
                        allowed_paths.add(path)
        if rel not in allowed_paths:
            abort(404)

        if public_token is not None and not _public_form_grants_image_access(form_item, public_token):
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
