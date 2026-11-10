"""IFRC emergency-operation documents in the knowledge base.

The external catalogue is two APIs:

* GO ``/api/v2/appeal_document/`` ``type``, and PublicSiteAppeals ``AppealOrigType``
  / PublicSiteTypes ``AppealsName``: DREF Operation (including updates and final
  reports), Emergency Appeal (preliminary, revised, final), Operations Update,
  Emergency Plan of Action (EPoA), Early Action Protocol.
* GO ``/api/v2/situation_report/`` ``type.type``: Situation Reports, plus flash
  updates and emergency updates filed on the same operation.

Unified planning types are not emergency operations: Plan (1851), Mid-Year
Report (10009), Annual Report (10011).

Appeal codes look like ``MDRSY014``. GO filenames put the file kind after the
code: ``do`` DREF operation, ``ea`` emergency appeal, ``ou`` operations update,
``epoa`` emergency plan of action.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Optional

# Stored on AIDocument.document_category. ``sitrep`` already existed.
EMERGENCY_CATEGORY_VALUES = (
    "dref",
    "emergency_appeal",
    "operations_update",
    "sitrep",
    "emergency_operation",
)

CATEGORY_LABELS = {
    "dref": "DREF",
    "emergency_appeal": "Emergency Appeal",
    "operations_update": "Operations Update",
    "sitrep": "Situation Report",
    "emergency_operation": "Emergency operation",
}

# First matching phrase on title + filename wins. Longer phrases first.
_PHRASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("dref", ("imminent dref", "dref")),
    ("emergency_appeal", ("preliminary emergency appeal", "revised emergency appeal", "emergency appeal")),
    ("operations_update", ("operations update", "operation update", "operational update")),
    ("sitrep", ("situation reports", "situation report", "sitrep", "flash update", "emergency update")),
    ("emergency_operation", ("early action protocol", "emergency plan of action", "epoa")),
)

# GO filename kind after the appeal code.
_SUFFIX_CATEGORY = {
    "do": "dref",
    "ea": "emergency_appeal",
    "ou": "operations_update",
    "epoa": "emergency_operation",
}
_SUFFIX_RE = re.compile(
    r"mdr[a-z]{2}\d{2,}[\s_\-]*(do|ea|ou|epoa)(?![a-z])",
    re.IGNORECASE,
)
_APPEAL_CODE_RE = re.compile(r"mdr[a-z]{2}\d{2,}", re.IGNORECASE)

# Collection filter needles. ``emergency`` is the whole operation family, not a
# requirement that the title contain that word — ``mdr`` / ``dref`` / type
# phrases cover disaster-named files such as "Floods".
_SCOPE_CATEGORIES: dict[str, tuple[str, ...]] = {
    "emergency": EMERGENCY_CATEGORY_VALUES,
    "dref": ("dref",),
    "emergency_appeal": ("emergency_appeal",),
    "operations_update": ("operations_update",),
    "sitrep": ("sitrep",),
    "emergency_operation": ("emergency_operation",),
}

_SCOPE_NEEDLES: dict[str, tuple[str, ...]] = {
    "emergency": (
        "dref",
        "emergency appeal",
        "operations update",
        "operation update",
        "situation report",
        "sitrep",
        "flash update",
        "emergency update",
        "emergency plan of action",
        "early action protocol",
        "epoa",
        "mdr",
        "emergency",
    ),
    "dref": ("dref",),
    "emergency_appeal": ("emergency appeal",),
    "operations_update": ("operations update", "operation update"),
    "sitrep": ("situation report", "sitrep", "flash update", "emergency update"),
    "emergency_operation": ("emergency plan of action", "early action protocol", "epoa"),
}

# Filename shapes the word needles miss (MDRSY014do.pdf has no "dref").
_CODE_PATTERNS: dict[str, tuple[str, ...]] = {
    "dref": ("%mdr%do%",),
    "emergency_appeal": ("%mdr%ea%",),
    "operations_update": ("%mdr%ou%",),
    "emergency_operation": ("%mdr%epoa%",),
}

_QUERY_ALIASES = {
    "emergency": "emergency",
    "emergencies": "emergency",
    "emergency document": "emergency",
    "emergency documents": "emergency",
    "emergency operation": "emergency",
    "emergency operations": "emergency",
    "dref": "dref",
    "dref operation": "dref",
    "appeal": "emergency_appeal",
    "appeals": "emergency_appeal",
    "emergency appeal": "emergency_appeal",
    "emergency appeals": "emergency_appeal",
    "operations update": "operations_update",
    "operation update": "operations_update",
    "ops update": "operations_update",
    "sitrep": "sitrep",
    "situation report": "sitrep",
    "situation reports": "sitrep",
    "flash update": "sitrep",
}

# document_category argument. Includes the stored category values, which the
# free-text query aliases above do not spell with underscores.
_CATEGORY_SCOPES = {
    "emergency": "emergency",
    "emergencies": "emergency",
    "dref": "dref",
    "emergency_appeal": "emergency_appeal",
    "operations_update": "operations_update",
    "sitrep": "sitrep",
    "emergency_operation": "emergency_operation",
}


@dataclass(frozen=True)
class InventoryQuery:
    """How list_documents should filter. ``text`` is a title/filename substring."""

    text: Optional[str] = None
    scope: Optional[str] = None
    category: Optional[str] = None


def _norm(value: Optional[str]) -> str:
    return " ".join(str(value or "").lower().split())


def classify_operation_category(title: str, filename: str = "") -> Optional[str]:
    """Return an emergency category from a title, filename, or IFRC type label.

    The word "emergency" alone is not enough: disaster names such as
    "Complex Emergency" are operation names, and preparedness documents use the
    same word. An appeal code, a GO filename suffix, or a type phrase is required.
    """
    blob = _norm(f"{title or ''} {filename or ''}")
    if not blob:
        return None
    for category, phrases in _PHRASES:
        for phrase in phrases:
            if phrase in blob:
                return category
    suffix = _SUFFIX_RE.search(blob)
    if suffix:
        return _SUFFIX_CATEGORY.get(suffix.group(1).lower())
    if _APPEAL_CODE_RE.search(blob):
        return "emergency_operation"
    return None


def operation_kind(title: str, filename: str, category: Optional[str]) -> Optional[str]:
    """Label one stored row. The filename wins over a stale generic category."""
    classified = classify_operation_category(title or "", filename or "")
    if classified:
        return classified
    stored = _norm(category)
    if stored in EMERGENCY_CATEGORY_VALUES:
        return stored
    return None


def resolve_inventory_query(
    query: Optional[str],
    document_category: Optional[str] = None,
) -> InventoryQuery:
    """Turn a list_documents query into a collection scope and/or a substring.

    ``emergency``, ``dref``, ``appeal``, and ``sitrep`` are collection names.
    Anything else, including ``UPL-``, stays a title/filename substring.
    """
    q = _norm(query)
    cat = _norm(document_category)
    scope = _CATEGORY_SCOPES.get(cat)
    exact = None if not cat or scope else cat
    text: Optional[str] = q or None
    query_scope = _QUERY_ALIASES.get(q)
    if query_scope:
        text = None
        if scope is None:
            scope = query_scope
    if scope and scope not in _SCOPE_CATEGORIES:
        scope = None
    return InventoryQuery(text=text, scope=scope, category=exact)


def row_matches_scope(title: str, filename: str, category: Optional[str], scope: str) -> bool:
    """Python mirror of :func:`sql_scope_clause` for tests."""
    if _norm(category) in _SCOPE_CATEGORIES.get(scope, ()):
        return True
    blob = _norm(f"{title or ''} {filename or ''}")
    if any(needle in blob for needle in _SCOPE_NEEDLES.get(scope, ())):
        return True
    for pattern in _CODE_PATTERNS.get(scope, ()):
        if _ilike_parts(blob, pattern):
            return True
    return False


def _ilike_parts(blob: str, pattern: str) -> bool:
    parts = [part for part in pattern.lower().split("%") if part]
    idx = 0
    for part in parts:
        found = blob.find(part, idx)
        if found < 0:
            return False
        idx = found + len(part)
    return bool(parts)


def sql_scope_clause(scope: str):
    """SQLAlchemy filter for one emergency collection. Unknown scopes match nothing."""
    from sqlalchemy import false, or_

    from app.models.embeddings import AIDocument

    categories = _SCOPE_CATEGORIES.get(scope)
    if not categories:
        return false()
    clauses = [AIDocument.document_category.in_(categories)]
    for needle in _SCOPE_NEEDLES.get(scope, ()):
        like = f"%{needle}%"
        clauses.append(AIDocument.title.ilike(like))
        clauses.append(AIDocument.filename.ilike(like))
    for pattern in _CODE_PATTERNS.get(scope, ()):
        clauses.append(AIDocument.title.ilike(pattern))
        clauses.append(AIDocument.filename.ilike(pattern))
    return or_(*clauses)


def remember_ifrc_document_type(ai_doc, document_type: Optional[str]) -> None:
    """Keep the PublicSiteAppeals / GO type label on the document.

    Unified planning labels are stored but do not change the category. Emergency
    type labels set ``document_category`` so later enrichment does not turn a
    DREF final report into a generic report.
    """
    label = " ".join(str(document_type or "").split())
    if not ai_doc or not label:
        return
    extra = dict(getattr(ai_doc, "extra_metadata", None) or {})
    extra["ifrc_document_type"] = label[:300]
    ai_doc.extra_metadata = extra
    category = classify_operation_category(label, "")
    if category:
        ai_doc.document_category = category


def category_from_stored_ifrc_type(ai_doc) -> Optional[str]:
    extra = getattr(ai_doc, "extra_metadata", None)
    if not isinstance(extra, dict):
        return None
    label = extra.get("ifrc_document_type")
    if not isinstance(label, str) or not label.strip():
        return None
    return classify_operation_category(label, "")
