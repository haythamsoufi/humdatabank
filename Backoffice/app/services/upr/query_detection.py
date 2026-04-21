"""
upr.query_detection
───────────────────
Heuristic detection of whether a user query targets UPR / Unified Plan
documents.  Used by document search tools and the ``is_api_import`` filter
to narrow results when both system and UPR document sources are enabled.

Single source of truth – replaces duplicate regexes that previously lived in
``ai_tools._query_utils`` and ``routes.ai_documents``.
"""

import re

_UPR_ONLY_QUERY_RE = re.compile(
    r"\b("
    r"unified\s+plan|"
    r"\bupl[-\s]?\d{4}\b|"
    r"\bupl\b|"
    r"\bupr\b|"
    r"up\s*plan"
    r")\b",
    re.IGNORECASE,
)
_UPR_ONLY_NEGATIVE_RE = re.compile(
    r"\b("
    r"annual\s+report|"
    r"semi-annual\s+report|"
    r"midyear\s+report|"
    r"\bar\b|"
    r"\bmyr\b"
    r")\b",
    re.IGNORECASE,
)


def query_prefers_upr_documents(query: str) -> bool:
    """Return True if *query* clearly targets Unified Plans / UPL / UPR
    documents but does *not* explicitly mention Annual Reports or MYRs.

    This NEVER widens access -- it only narrows from (system + UPR) to
    (UPR only).
    """
    q = (query or "").strip()
    if not q:
        return False
    if not _UPR_ONLY_QUERY_RE.search(q):
        return False
    if _UPR_ONLY_NEGATIVE_RE.search(q):
        return False
    return True
