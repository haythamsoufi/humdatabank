"""
AI Document Management Routes Package

Handles uploading, processing, searching, and managing documents for the RAG system.
Split into submodules by functional area; all routes register on the shared ``ai_docs_bp`` blueprint.

Access is governed by route-level RBAC (e.g. admin.ai.manage, admin.documents.manage), not AI beta
allow-listing — beta gating applies to the chatbot (/api/ai/v2/*, WebSocket chat) only.
"""

import logging
from flask import Blueprint

logger = logging.getLogger(__name__)

ai_docs_bp = Blueprint('ai_documents', __name__, url_prefix='/api/ai/documents')

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
