"""Document upload/download routes within forms."""
from __future__ import annotations

from flask import abort, current_app, flash, redirect, request, url_for
from flask_login import current_user, login_required
from flask_wtf import FlaskForm


def register_document_routes(bp):
    """Register document-related routes onto the forms blueprint."""

    @bp.route("/download_document/<int:submitted_document_id>", methods=["GET"])
    @login_required
    def download_document(submitted_document_id):
        from app.services.document_service import DocumentService
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
        from app.services.document_service import DocumentService
        from app.utils.redirect_utils import is_safe_redirect_url
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

    @bp.route("/public-document/<int:document_id>/download", methods=["GET"])
    def download_public_document_public(document_id):
        """Download a document from a public submission (public access)."""
        from app.services.document_service import DocumentService
        try:
            return DocumentService.stream_public_download_response(document_id)
        except PermissionError:
            abort(404)
        except Exception as e:
            current_app.logger.error(f"Error serving public document {document_id}: {e}", exc_info=True)
            flash("An error occurred while trying to download the file.", "danger")
            return redirect(url_for("main.dashboard"))
