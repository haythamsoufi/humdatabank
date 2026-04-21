"""
AI Document Management Routes Package

Handles uploading, processing, searching, and managing documents for the RAG system.
Split into submodules by functional area; all routes register on the shared ``ai_docs_bp`` blueprint.
"""

import logging
from flask import Blueprint
from flask_login import current_user

from app.utils.api_responses import json_auth_required, json_forbidden

logger = logging.getLogger(__name__)

ai_docs_bp = Blueprint('ai_documents', __name__, url_prefix='/api/ai/documents')


@ai_docs_bp.before_request
def _enforce_ai_beta_access():
    """Restrict AI document endpoints when AI beta mode is enabled."""
    try:
        from app.services.app_settings_service import is_ai_beta_restricted, user_has_ai_beta_access

        if not is_ai_beta_restricted():
            return None
        if not getattr(current_user, "is_authenticated", False):
            return json_auth_required("AI beta access is limited to selected users.")
        if not user_has_ai_beta_access(current_user):
            return json_forbidden("AI beta access is limited to selected users.")
    except Exception as e:
        logger.debug("AI documents beta gate check failed: %s", e, exc_info=True)
    return None


# Import submodules so their @ai_docs_bp.route decorators register on the blueprint.
from . import upload     # noqa: E402,F401 – upload/reprocess routes + processing pipeline
from . import management # noqa: E402,F401 – list/get/update/download/delete routes
from . import search     # noqa: E402,F401 – search route
from . import qa         # noqa: E402,F401 – answer/QA route
from . import workflows  # noqa: E402,F401 – workflow documentation routes
from . import ifrc       # noqa: E402,F401 – IFRC API integration routes

# Re-export commonly used symbols so existing ``from app.routes.ai_documents import X``
# statements in other modules continue to work without path changes.
from .upload import get_document_processing_stage  # noqa: E402,F401
