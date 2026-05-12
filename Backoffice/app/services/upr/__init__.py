"""
upr – Unified Planning and Reporting domain package.

Centralises all UPR-specific logic: document processing (visual chunking,
deterministic answering), KPI data retrieval, AI tool definitions/specs,
prompt fragments, form-data validation helpers, query detection heuristics,
configuration, focus-area analysis, and UX labels.

Public API
──────────
is_upr_active()              – request-scoped gate: True when UPR tools/prompts
                               should be active.
query_prefers_upr_documents  – heuristic: does the query target UPR docs?

Sub-modules (import directly when you need specific pieces):
    upr.visual_chunking      – PDF visual extraction + training/eval helpers
    upr.document_answering   – deterministic QA from metadata["upr"]
    upr.data_retrieval       – SQL queries against AIDocumentChunk UPR metadata
    upr.query_detection      – regex-based UPR query detection
    upr.tools                – AI tool wrapper implementations
    upr.tool_specs           – OpenAI-format tool definitions + constants
    upr.prompts              – prompt fragments, rewriter rules, gap-fill text
    upr.validation           – form-data validation helpers
    upr.ux                   – step labels, tool humanisation, source qualifiers
    upr.config               – AI_UPR_* configuration reader
    upr.focus_area_analysis  – fast-path for Unified Plans focus-area review
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def is_upr_active() -> bool:
    """Return True when UPR tools and prompts should be active for the current request.

    Decision order:
    1. ``flask.g.ai_sources_cfg["upr_documents"]`` – explicit user toggle from
       the chat UI checkbox.
    2. Falls back to ``True`` when ``sources_cfg`` is ``None`` (back-compat /
       no explicit selection).
    3. Returns ``True`` outside a Flask request context (scripts, CLI, tests).
    """
    try:
        from flask import g
        cfg: Optional[dict] = getattr(g, "ai_sources_cfg", None)
        if cfg is None:
            return True
        return bool(cfg.get("upr_documents", False))
    except RuntimeError:
        return True


# Convenience re-exports
from app.services.upr.query_detection import query_prefers_upr_documents  # noqa: E402,F401
from app.services.upr.prompts import get_upr_knowledge  # noqa: E402,F401

__all__ = [
    "is_upr_active",
    "query_prefers_upr_documents",
    "get_upr_knowledge",
]
