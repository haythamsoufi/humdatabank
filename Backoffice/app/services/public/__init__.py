"""Public integration services (Custom GPT Actions, MCP, unauthenticated API)."""

from app.services.public.analytics_service import (
    aggregate_global_trend,
    aggregate_submission_coverage,
    resolve_country_query,
    resolve_indicator_query,
)
from app.services.public.document_service import (
    PublicDocumentScopeTooLarge,
    PublicDocumentSearchUnavailable,
    catalog_public_documents,
    get_public_document_chunk_context,
    get_public_document_metadata,
    search_public_documents,
    stream_public_ai_document_download,
)
from app.services.public.report_service import build_country_report, get_report_template

__all__ = [
    "PublicDocumentScopeTooLarge",
    "PublicDocumentSearchUnavailable",
    "aggregate_global_trend",
    "aggregate_submission_coverage",
    "build_country_report",
    "catalog_public_documents",
    "get_public_document_chunk_context",
    "get_public_document_metadata",
    "get_report_template",
    "resolve_country_query",
    "resolve_indicator_query",
    "search_public_documents",
    "stream_public_ai_document_download",
]
