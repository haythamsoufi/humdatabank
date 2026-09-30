"""Document upload/download routes within forms."""
from __future__ import annotations

from flask import abort, current_app, flash, redirect, request, url_for
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from werkzeug.exceptions import HTTPException

from app.extensions import limiter
from app.services.documents import public_access
from app.services.documents.service import DocumentService
from app.utils.redirect_utils import is_safe_redirect_url


def register_document_routes(bp):
    """Register document-related routes onto the forms blueprint."""

    @bp.route("/download_document/<int:submitted_document_id>", methods=["GET"])
    @login_required
    def download_document(submitted_document_id):
        try:
            return DocumentService.stream_download_response(submitted_document_id, current_user)
        except PermissionError as e:
            flash("An error occurred. Please try again.", "warning")
            return redirect(url_for("main.dashboard"))
        except FileNotFoundError:
            current_app.logger.error(f"Attempted to download non-existent file for ID {submitted_document_id}")
            abort(404)
        except Exception as e:
            current_app.logger.error(f"Error serving document {submitted_document_id}: {e}", exc_info=True)
            flash("An error occurred while trying to download the file.", "danger")
            return redirect(url_for("main.dashboard"))

    @bp.route("/delete_document/<int:submitted_document_id>", methods=["POST"])
    @login_required
    def delete_document(submitted_document_id):
        from urllib.parse import urlparse as _urlparse
        csrf_form = FlaskForm()
        referrer = request.referrer
        # Extract only path+query from validated referrer to prevent open redirect
        safe_referrer = None
        if referrer and is_safe_redirect_url(referrer):
            _p = _urlparse(referrer)
            safe_referrer = _p.path + ('?' + _p.query if _p.query else '') or None
        if not csrf_form.validate_on_submit():
            flash("Document deletion failed due to a security issue. Please try again.", "danger")
            return redirect(safe_referrer or url_for("main.dashboard"))
        try:
            deleted_name = DocumentService.delete_assignment_document(submitted_document_id, current_user)
            flash(f"Document '{deleted_name}' deleted successfully.", "success")
        except PermissionError as e:
            flash("An error occurred. Please try again.", "warning")
        except Exception as e:
            current_app.logger.error(f"Error deleting document {submitted_document_id}: {e}", exc_info=True)
            flash("Error deleting document.", "danger")
        return redirect(safe_referrer or url_for("main.dashboard"))

    def _stream_public_document(identifier):
        try:
            return DocumentService.stream_public_download_response(identifier)
        except (PermissionError, FileNotFoundError):
            abort(404)
        except HTTPException:
            raise
        except Exception as e:
            current_app.logger.error("Error serving public document %s: %s", identifier, e, exc_info=True)
            flash("An error occurred while trying to download the file.", "danger")
            return redirect(url_for("main.dashboard"))

    @bp.route("/public-document/<uuid:public_id>/download", methods=["GET"])
    @limiter.limit(public_access.public_download_rate_limit)
    def download_public_document_by_public_id(public_id):
        """Download a document from a public submission (public access, opaque id)."""
        return _stream_public_document(public_id)

    @bp.route("/public-document/<int:document_id>/download", methods=["GET"])
    @limiter.limit(public_access.public_download_rate_limit)
    def download_public_document_public(document_id):
        """Deprecated integer-id URL: re-checks the public policy, then redirects to the opaque URL."""
        try:
            document = DocumentService.load_public_download_document(document_id)
        except PermissionError:
            abort(404)
        target = url_for("forms.download_public_document_by_public_id", public_id=document.public_id)
        response = redirect(target, code=302)
        response.headers["Deprecation"] = "true"
        response.headers["Link"] = f'<{target}>; rel="successor-version"'
        return response
