# ========== File: app/routes/public.py ==========
from pathlib import Path
from urllib.parse import urlparse

from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app, abort, jsonify
from app.models import db, Resource, SubmittedDocument
from app.models.enums import DocumentStatus
from sqlalchemy import text
import os
from datetime import datetime
from app.utils.datetime_helpers import utcnow
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE
from app.utils.api_responses import json_error
from app.services.platform import storage_service as storage

from app.services.forms.processing_service import slugify_age_group

bp = Blueprint("public", __name__)

THUMBNAIL_SUBFOLDER_NAME = 'thumbnails'

_ALLOWED_CUSTOM_GPT_HOSTS = frozenset({'chatgpt.com', 'www.chatgpt.com'})


def _custom_gpt_redirect_url() -> str:
    """Return a validated Custom GPT URL from app config, or abort 404."""
    url = (current_app.config.get('CUSTOM_GPT_URL') or '').strip()
    if not url:
        abort(404)
    parsed = urlparse(url)
    host = (parsed.hostname or '').lower()
    if parsed.scheme != 'https' or host not in _ALLOWED_CUSTOM_GPT_HOSTS:
        current_app.logger.error('Invalid CUSTOM_GPT_URL configured: %s', url)
        abort(404)
    return url

# =================== RESOURCE DOWNLOAD ROUTES ===================
# These routes allow public access to resources without API key

@bp.route("/resources/download/<int:resource_id>/<language>", methods=["GET"])
def download_resource_file(resource_id, language):
    """Download a resource file in a specific language."""
    resource = Resource.query.get_or_404(resource_id)
    translation = resource.get_translation(language)

    if not translation or not translation.file_relative_path:
        current_app.logger.error(f"Public download (doc): No file path for resource ID {resource_id} in language {language}")
        abort(404, description="Document file not found for this resource.")

    if not storage.exists(storage.RESOURCES, translation.file_relative_path):
        current_app.logger.error(f"Public download (doc): File not found for ID {resource_id}")
        abort(404)

    mimetype = 'application/pdf' if translation.filename.lower().endswith('.pdf') else None
    response = storage.stream_response(
        storage.RESOURCES, translation.file_relative_path,
        filename=translation.filename, mimetype=mimetype, as_attachment=False,
    )

    if translation.filename.lower().endswith('.pdf'):
        response.headers['Accept-Ranges'] = 'bytes'
        allowed_origins = current_app.config.get('CORS_ALLOWED_ORIGINS') or []
        request_origin = request.headers.get('Origin', '')
        if request_origin and (allowed_origins == '*' or request_origin in allowed_origins):
            response.headers['Access-Control-Allow-Origin'] = request_origin
            response.headers['Vary'] = 'Origin'
        else:
            response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Headers'] = 'Range'
        response.headers['Access-Control-Expose-Headers'] = 'Accept-Ranges, Content-Encoding, Content-Length, Content-Range'

    return response

@bp.route("/resources/thumbnail/<int:resource_id>/<language>", methods=["GET"])
def download_resource_thumbnail(resource_id, language):
    """Download a resource thumbnail in a specific language with fallback to English."""
    resource = Resource.query.get_or_404(resource_id)
    translation = resource.get_translation(language)

    # If requested language doesn't have thumbnail, try English fallback
    if (not translation or not translation.thumbnail_relative_path) and language != 'en':
        current_app.logger.info(f"Public download (thumb): No thumbnail for resource ID {resource_id} in {language}, trying English fallback")
        translation = resource.get_translation('en')

    if not translation or not translation.thumbnail_relative_path:
        current_app.logger.warning(f"Public download (thumb): No thumbnail path for resource ID {resource_id} in language {language} or English fallback")
        abort(404, description="Thumbnail not found for this resource.")

    if not storage.exists(storage.RESOURCES, translation.thumbnail_relative_path):
        current_app.logger.error(f"Public download (thumb): Thumbnail not found for ID {resource_id}")
        abort(404)

    return storage.stream_response(
        storage.RESOURCES, translation.thumbnail_relative_path,
        filename=os.path.basename(translation.thumbnail_relative_path),
        as_attachment=False,
    )

# =================== PUBLIC DOCUMENT THUMBNAILS ===================
# Serve document thumbnails publicly for approved public documents

@bp.route("/documents/thumbnail/<int:doc_id>", methods=["GET"])
def download_document_thumbnail_public(doc_id):
    """Serve a public thumbnail for a submitted document."""
    document = SubmittedDocument.query.get_or_404(doc_id)

    if not document.is_public or DocumentStatus.normalize(document.status) != DocumentStatus.APPROVED:
        abort(404)

    if not document.thumbnail_relative_path:
        abort(404)

    thumb_cat = storage.submitted_document_rel_storage_category(document.thumbnail_relative_path)
    if not storage.exists(thumb_cat, document.thumbnail_relative_path):
        abort(404)

    return storage.stream_response(
        thumb_cat, document.thumbnail_relative_path,
        filename=os.path.basename(document.thumbnail_relative_path),
        as_attachment=False,
    )

# =================== PUBLIC DOCUMENT DISPLAY (IMAGES ONLY) ===================

@bp.route("/documents/display/<int:doc_id>", methods=["GET"])
def display_document_file_public(doc_id):
    """Serve a public document file inline when it's an image (for cover images)."""
    document = SubmittedDocument.query.get_or_404(doc_id)

    if not document.is_public or DocumentStatus.normalize(document.status) != DocumentStatus.APPROVED:
        abort(404)

    # Only serve inline if it's an image
    lower = (document.filename or '').lower()
    if not lower.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
        abort(404)

    main_cat = storage.submitted_document_rel_storage_category(document.storage_path)
    if not storage.exists(main_cat, document.storage_path):
        abort(404)

    return storage.stream_response(
        main_cat, document.storage_path,
        filename=document.filename, as_attachment=False,
    )

# =================== LEGACY URL REDIRECTS ===================

@bp.route("/form/<uuid:public_token>", methods=["GET"])
def legacy_public_form_redirect(public_token):
    """Backward-compatible redirect for old public form URLs."""
    return redirect(url_for("forms.fill_public_form", public_token=public_token), code=302)


@bp.route("/public_submission_success/<int:submission_id>", methods=["GET"])
def legacy_public_submission_success_redirect(submission_id):
    """Backward-compatible redirect for old public submission success URLs."""
    return redirect(url_for("forms.public_submission_success", submission_id=submission_id), code=302)


@bp.route("/public_documents/download/<int:document_id>", methods=["GET"])
def legacy_public_document_download_redirect(document_id):
    """Backward-compatible redirect for old public document download URLs."""
    return redirect(url_for("forms.download_public_document_public", document_id=document_id), code=302)


@bp.route("/landing", methods=["GET"])
def landing_page():
    """Public landing page introducing the platform and its features."""
    return render_template("public/landing.html", current_year=utcnow().year)


@bp.route("/gpt", methods=["GET"])
@bp.route("/assistant", methods=["GET"])
def custom_gpt_redirect():
    """Short public link to the IFRC Network Databank Custom GPT on ChatGPT."""
    return redirect(_custom_gpt_redirect_url(), code=302)


@bp.route("/privacy", methods=["GET"])
@bp.route("/privacy-policy", methods=["GET"])
def privacy_policy():
    """Public privacy policy for the portal, public API, and MCP integrations."""
    from app.services.documentation import service as docs

    root = docs.docs_root()
    file_path = Path(root) / "public" / "privacy-policy.md"
    if not file_path.is_file():
        current_app.logger.error("Missing public privacy policy markdown: %s", file_path)
        abort(404)

    privacy_url = url_for("public.privacy_policy")

    content_html = docs.render_markdown_file(
        root=Path(root),
        file_path=file_path,
        current_rel="public/privacy-policy.md",
        doc_url_builder=lambda _rel: privacy_url,
        asset_url_builder=lambda _rel: privacy_url,
    )
    return render_template(
        "public/privacy.html",
        page_title=docs.extract_page_title(file_path),
        content_html=content_html,
        current_year=utcnow().year,
    )


@bp.route("/health", methods=["GET"])
def health_check():
    """Simple health check endpoint for Fly.io and load balancers.

    Returns 200 OK if the application is healthy.
    This is a lightweight endpoint that should respond quickly.
    Optionally checks database connectivity if DB_CHECK=true.
    """
    try:
        # Basic health check - just return OK immediately
        # This ensures the health check responds quickly even under load
        health_status = {
            "status": "healthy",
            "timestamp": utcnow().isoformat(),
            "service": "backoffice-databank"
        }

        # Optional: Check database connectivity (can be enabled via env var)
        # By default, this is disabled to keep health checks fast
        db_check_enabled = str(os.environ.get('HEALTH_CHECK_DB', 'false')).strip().lower() == 'true'
        if db_check_enabled:
            try:
                # Simple database connectivity check with timeout
                # Use a very simple query that should complete quickly
                db.session.execute(text('SELECT 1'))
                db.session.flush()  # Ensure transaction is committed
                health_status["database"] = "connected"
            except Exception as db_error:
                # Log but don't fail the health check unless critical
                current_app.logger.warning(f"Health check: Database connectivity issue: {db_error}")
                health_status["database"] = "error"
                # Only mark as degraded, not unhealthy, to avoid cascading failures
                health_status["status"] = "degraded"

        status_code = 200 if health_status["status"] in ["healthy", "degraded"] else 503
        return jsonify(health_status), status_code

    except Exception as e:
        # Log the error but still return a response
        current_app.logger.error(f"Health check failed: {e}", exc_info=True)
        try:
            ts = utcnow().isoformat()
        except Exception:
            ts = datetime.utcnow().isoformat()
        return json_error(GENERIC_ERROR_MESSAGE, 503, health_status="unhealthy", timestamp=ts)
