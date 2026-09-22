"""UPR AI / RAG document-intelligence package."""

from __future__ import annotations

from typing import Optional

from plugins.upr.ai.prompts import get_upr_knowledge, is_upr_form_template
from plugins.upr.ai.query_detection import query_prefers_upr_documents

__all__ = [
    "is_upr_active",
    "query_prefers_upr_documents",
    "get_upr_knowledge",
    "is_upr_form_template",
]


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
