"""
AI Document Metadata Extractor

Extracts structured provenance metadata from documents during processing:
- document_date: publication/report date
- document_language: ISO 639-1 language code
- document_category: taxonomy classification
- quality_score: automated extraction quality (0.0–1.0)
- semantic_type: per-chunk content classification
- heading_hierarchy: per-chunk heading breadcrumb
"""

import logging
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Date extraction patterns
# ---------------------------------------------------------------------------

# Explicit month names (English, French, Spanish, Arabic transliterations)
_MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    # French
    "janvier": 1, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12,
    # Spanish
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}

_YEAR_RE = re.compile(r"\b(19[89]\d|20[012]\d)\b")
_ISO_DATE_RE = re.compile(r"\b(20[012]\d)-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])\b")
_SLASH_DATE_RE = re.compile(r"\b(0?[1-9]|1[0-2])/(0?[1-9]|[12]\d|3[01])/(20[012]\d)\b")
_MONTH_YEAR_RE = re.compile(
    r"\b(" + "|".join(_MONTH_NAMES.keys()) + r")\s+(20[012]\d|19[89]\d)\b",
    re.IGNORECASE,
)
_YEAR_ONLY_FROM_FILENAME_RE = re.compile(r"(19[89]\d|20[012]\d)")

# ---------------------------------------------------------------------------
# Category taxonomy
# ---------------------------------------------------------------------------

# Canonical category values stored in the database.
# The human-readable labels are defined in CATEGORY_LABELS below.
DOCUMENT_CATEGORIES: List[str] = [
    "country_plan",
    "country_report",
    "strategic_plan",
    "work_plan",
    "plan",
    "sitrep",
    "report",
    "assessment",
    "policy",
    "guideline",
    "resolution",
    "data_sheet",
    "training",
    "other",
]

# Display labels for each category value (used in UI dropdowns and badges).
CATEGORY_LABELS: dict = {
    "country_plan":   "Country Plan",
    "country_report": "Country Report",
    "strategic_plan": "Strategic Plan",
    "work_plan":      "Work Plan",
    "plan":           "Plan",
    "sitrep":         "Situation Report",
    "report":         "Report",
    "assessment":     "Assessment",
    "policy":         "Policy",
    "guideline":      "Guideline",
    "resolution":     "Resolution",
    "data_sheet":     "Data Sheet",
    "training":       "Training",
    "other":          "Other",
}

# ---------------------------------------------------------------------------
# Category keyword mapping — two passes (title/filename, then text body)
# ---------------------------------------------------------------------------
# Each entry: (category_value, title_keywords, body_keywords)
# title_keywords are matched against title+filename only (reliable).
# body_keywords are matched against the text sample as a fallback.
# More-specific multi-word phrases MUST appear before shorter ones.
_CATEGORY_RULES: List[Tuple[str, List[str], List[str]]] = [
    ("country_plan", [
        "country plan", "national society plan", "ns plan", "country strategic plan",
    ], [
        "country plan", "national society plan",
    ]),
    ("country_report", [
        "country report", "ns report", "national society report",
    ], [
        "country report", "national society report",
    ]),
    ("strategic_plan", [
        "strategic plan", "organisational strategy", "organizational strategy",
        "strategy 2030", "strategy 2025", "strategy 2035",
    ], [
        "strategic plan", "organisational strategy", "organizational strategy",
    ]),
    ("work_plan", [
        "work plan", "workplan", "action plan", "operational plan", "implementation plan", "roadmap",
    ], [
        "work plan", "workplan", "action plan", "operational plan", "implementation plan",
    ]),
    ("sitrep", [
        "situation report", "sitrep", "flash update", "emergency update",
    ], [
        "situation report", "sitrep", "flash update", "emergency update",
    ]),
    ("report", [
        "annual report", "progress report", "activity report", "field report", "report",
    ], [
        "annual report", "progress report", "activity report", "field report",
    ]),
    ("assessment", [
        "needs assessment", "rapid assessment", "assessment", "evaluation", "appraisal", "vulnerability",
    ], [
        "needs assessment", "rapid assessment", "assessment", "evaluation",
    ]),
    ("policy", [
        "policy", "policies", "statute", "constitution", "regulation", "directive",
    ], [
        "policy", "policies", "statute", "constitution",
    ]),
    ("guideline", [
        "guideline", "guidelines", "guidance", "standard", "protocol", "procedure",
        "sop", "manual", "handbook", "toolkit",
    ], [
        "guideline", "guidelines", "guidance", "manual", "handbook",
    ]),
    ("resolution", [
        "resolution", "decision", "declaration", "communiqué", "communique",
    ], [
        "resolution", "declaration",
    ]),
    # "plan" as a catch-all — title only; body "plan" is too common
    ("plan", [
        "plan", "planning", "strategy",
    ], []),
    ("data_sheet", [
        "data sheet", "datasheet", "fact sheet", "factsheet", "scorecard", "statistics",
    ], [
        "data sheet", "datasheet", "fact sheet", "factsheet",
    ]),
    ("training", [
        "training", "learning", "module", "curriculum", "course", "workshop",
    ], [
        "training", "learning", "curriculum",
    ]),
]

# ---------------------------------------------------------------------------
# Language detection (extends existing ai_utils heuristics)
# ---------------------------------------------------------------------------

_AR_RE = re.compile(r"[\u0600-\u06FF]")
_ZH_RE = re.compile(r"[\u4E00-\u9FFF]")
_RU_RE = re.compile(r"[\u0400-\u04FF]")
_HI_RE = re.compile(r"[\u0900-\u097F]")
_FR_MARKERS = re.compile(r"\b(le|la|les|de|du|des|et|en|un|une|pour|avec|dans|sur|par|au|aux|ce|cette|qui|que)\b", re.IGNORECASE)
_ES_MARKERS = re.compile(r"\b(el|la|los|las|de|del|un|una|y|en|para|con|por|que|su|sus|se|al|es|está)\b", re.IGNORECASE)
_EN_MARKERS = re.compile(r"\b(the|and|of|to|in|is|for|with|that|this|are|on|by|an|at|be|was|has)\b", re.IGNORECASE)


def detect_document_language(text: str, sample_chars: int = 3000) -> str:
    """
    Detect the primary language of document text.
    Returns ISO 639-1 code: 'en', 'fr', 'es', 'ar', 'ru', 'zh', 'hi', or 'en' as fallback.
    """
    sample = text[:sample_chars]
    if not sample.strip():
        return "en"

    # Script-based detection (fast and reliable)
    if len(_AR_RE.findall(sample)) > 10:
        return "ar"
    if len(_ZH_RE.findall(sample)) > 10:
        return "zh"
    if len(_RU_RE.findall(sample)) > 10:
        return "ru"
    if len(_HI_RE.findall(sample)) > 10:
        return "hi"

    # Latin-script scoring
    words = sample.lower().split()
    total = max(len(words), 1)
    fr_score = len(_FR_MARKERS.findall(sample)) / total
    es_score = len(_ES_MARKERS.findall(sample)) / total
    en_score = len(_EN_MARKERS.findall(sample)) / total

    best = max(
        [("en", en_score), ("fr", fr_score), ("es", es_score)],
        key=lambda x: x[1],
    )
    return best[0]


def classify_document_category(title: str, filename: str, text_sample: str) -> str:
    """
    Classify document into a category using keyword heuristics (first match wins).

    Two-pass strategy:
    1. Match against title + filename only — these are the most reliable signals
       and avoid false positives from contextual mentions in body text.
    2. Fall back to body-text keywords only if pass 1 finds nothing.

    Returns one of the values in DOCUMENT_CATEGORIES.
    """
    title_combined = f"{title} {filename}".lower()
    body_combined = text_sample[:1000].lower()

    # Pass 1: title + filename only
    for category, title_kws, _body_kws in _CATEGORY_RULES:
        for kw in title_kws:
            if kw in title_combined:
                return category

    # Pass 2: body text fallback (restricted keyword set to avoid over-matching)
    for category, _title_kws, body_kws in _CATEGORY_RULES:
        for kw in body_kws:
            if kw in body_combined:
                return category

    return "other"


def extract_document_date(
    title: str,
    filename: str,
    text_sample: str,
    pdf_creation_date: Optional[str] = None,
) -> Optional[date]:
    """
    Extract the best-guess publication date from available sources.
    Priority: ISO date in text > month+year in title > year in filename > year in text sample.
    """
    # 1. ISO date pattern in title or first part of text
    for src in (title, text_sample[:500]):
        m = _ISO_DATE_RE.search(src)
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                pass

    # 2. Month + Year in title or filename
    for src in (title, filename):
        m = _MONTH_YEAR_RE.search(src)
        if m:
            month_str = m.group(1).lower()
            year = int(m.group(2))
            month = _MONTH_NAMES.get(month_str)
            if month:
                try:
                    return date(year, month, 1)
                except ValueError:
                    pass

    # 3. PDF creation date metadata (may be a string like "D:20230801120000")
    if pdf_creation_date:
        try:
            raw = str(pdf_creation_date).strip("D: ")
            if len(raw) >= 8:
                return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
        except (ValueError, IndexError):
            pass

    # 4. Year from filename
    m = _YEAR_ONLY_FROM_FILENAME_RE.search(filename)
    if m:
        try:
            return date(int(m.group(1)), 1, 1)
        except ValueError:
            pass

    # 5. Year from text sample (first occurrence)
    m = _YEAR_RE.search(text_sample[:2000])
    if m:
        try:
            return date(int(m.group(1)), 1, 1)
        except ValueError:
            pass

    return None


def compute_quality_score(
    *,
    total_chars: int,
    total_pages: Optional[int],
    extraction_warnings: int = 0,
    has_tables: bool = False,
    table_extraction_success: bool = True,
) -> float:
    """
    Compute a text-extraction quality score (0.0–1.0).

    This measures how well the document was parsed — NOT content quality.
    A score of 1.0 means clean, dense text was extracted.  Low scores (< 0.7)
    usually indicate a scanned PDF without OCR, a password-protected file, or
    a largely image-based document.

    Factors:
    - chars/page < 100  → -0.4  (very sparse, likely scanned without OCR)
    - chars/page < 300  → -0.2  (below average density)
    - each extraction warning → -0.05 (capped at -0.30)
    - table extraction failed when tables present → -0.10
    """
    score = 1.0

    # Content density penalty (scanned PDFs with no OCR have very low chars/page)
    if total_pages and total_pages > 0:
        chars_per_page = total_chars / total_pages
        if chars_per_page < 100:
            score -= 0.4  # Very sparse — likely scanned without OCR
        elif chars_per_page < 300:
            score -= 0.2  # Below average

    # Penalty for each extraction warning
    score -= min(0.3, extraction_warnings * 0.05)

    # Table extraction failure
    if has_tables and not table_extraction_success:
        score -= 0.1

    return max(0.0, min(1.0, round(score, 2)))


# ---------------------------------------------------------------------------
# Chunk semantic typing
# ---------------------------------------------------------------------------

_TABLE_HINTS = re.compile(
    r"(\|\s*[-:]+\s*\|)|(<table)|(\btable\s+\d)|(\bfigure\s+\d)|(col_\d)",
    re.IGNORECASE,
)
_HEADER_HINTS = re.compile(
    r"^#{1,4}\s+\S|^[A-Z][A-Z\s]{5,50}$",
    re.MULTILINE,
)
_LIST_HINTS = re.compile(r"^\s*[-•*]\s+\S|^\s*\d+\.\s+\S", re.MULTILINE)


def classify_chunk_semantic_type(content: str, chunk_type: Optional[str] = None) -> str:
    """
    Classify a chunk's semantic type: paragraph | table | list | header | figure_caption.
    Uses content heuristics; chunk_type from chunking strategy is used as a hint.
    """
    if chunk_type == "table" or _TABLE_HINTS.search(content):
        return "table"
    if chunk_type == "header" or (len(content) < 200 and _HEADER_HINTS.search(content)):
        return "header"
    if _LIST_HINTS.search(content) and len(content) < 2000:
        return "list"
    lower = content.lower()
    if "figure" in lower and ("caption" in lower or len(content) < 300):
        return "figure_caption"
    return "paragraph"


def build_heading_hierarchy(
    section_title: Optional[str],
    chunk_index: int,
    page_number: Optional[int],
    document_title: Optional[str] = None,
) -> Optional[List[str]]:
    """
    Build a heading breadcrumb for a chunk from available position signals.
    Returns None if no meaningful hierarchy can be built.
    """
    hierarchy = []
    if document_title:
        hierarchy.append(document_title[:100])
    if section_title and section_title.strip():
        hierarchy.append(section_title.strip()[:200])
    if page_number:
        hierarchy.append(f"Page {page_number}")
    return hierarchy if len(hierarchy) > 1 else None


# ---------------------------------------------------------------------------
# Unified enrichment entry point
# ---------------------------------------------------------------------------

# Known IFRC/Red Cross/Red Crescent domain fragments used to identify IFRC-sourced documents.
_IFRC_URL_MARKERS = ("go.ifrc.org", "ifrc.org", "reliefweb.int")

# Org name patterns scanned in document text (longest/most-specific first).
_ORG_TEXT_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\bInternational Federation of Red Cross and Red Crescent Societies\b", re.IGNORECASE), "IFRC"),
    (re.compile(r"\bIFRC\b"), "IFRC"),
    (re.compile(r"\bUnited Nations\b", re.IGNORECASE), "United Nations"),
    (re.compile(r"\bWorld Health Organization\b|\bWHO\b"), "WHO"),
    (re.compile(r"\bWorld Food Programme\b|\bWFP\b"), "WFP"),
    (re.compile(r"\bUNICEF\b"), "UNICEF"),
    (re.compile(r"\bUNHCR\b"), "UNHCR"),
    (re.compile(r"\bWorld Bank\b", re.IGNORECASE), "World Bank"),
    (re.compile(r"\bInternational Committee of the Red Cross\b|\bICRC\b"), "ICRC"),
]


def extract_source_organization(
    pdf_metadata: Optional[Dict[str, Any]] = None,
    source_url: Optional[str] = None,
    text_sample: Optional[str] = None,
) -> Optional[str]:
    """
    Extract originating organization from available signals, in priority order:

    1. PDF author metadata field (most authoritative when set).
    2. source_url domain — IFRC API / go.ifrc.org imports → "IFRC".
    3. Text scan for well-known organization name patterns.

    creator/producer are intentionally ignored — they contain authoring software
    names (e.g. "Adobe InDesign"), not the source organization.
    """
    # 1. PDF author field
    if pdf_metadata:
        for key in ("author", "Author"):
            val = pdf_metadata.get(key)
            if val and isinstance(val, str) and val.strip():
                return val.strip()[:300]

    # 2. Source URL domain
    if source_url:
        url_lower = source_url.lower()
        if any(marker in url_lower for marker in _IFRC_URL_MARKERS):
            return "IFRC"

    # 3. Text scan (first 4 000 chars is enough for org identification)
    if text_sample:
        sample = text_sample[:4000]
        for pattern, org_name in _ORG_TEXT_PATTERNS:
            if pattern.search(sample):
                return org_name

    return None


def enrich_document_metadata(
    *,
    title: str,
    filename: str,
    text: str,
    total_pages: Optional[int] = None,
    pdf_metadata: Optional[Dict[str, Any]] = None,
    extraction_warnings: int = 0,
    has_tables: bool = False,
    table_extraction_success: bool = True,
    source_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Derive all enriched provenance metadata for an AIDocument in one call.

    Returns a dict with keys matching the new AIDocument columns:
        document_date, document_language, document_category, quality_score, source_organization
    """
    pdf_creation_date = (pdf_metadata or {}).get("creation_date") or (pdf_metadata or {}).get("CreationDate")
    text_sample = text[:3000] if text else ""

    doc_date = extract_document_date(
        title=title,
        filename=filename,
        text_sample=text_sample,
        pdf_creation_date=pdf_creation_date,
    )
    doc_language = detect_document_language(text, sample_chars=3000)
    doc_category = classify_document_category(title, filename, text_sample)
    source_org = extract_source_organization(
        pdf_metadata=pdf_metadata,
        source_url=source_url,
        text_sample=text_sample,
    )
    q_score = compute_quality_score(
        total_chars=len(text),
        total_pages=total_pages,
        extraction_warnings=extraction_warnings,
        has_tables=has_tables,
        table_extraction_success=table_extraction_success,
    )

    logger.info(
        "Document metadata extracted: date=%s lang=%s category=%s quality=%.2f org=%s [%s]",
        doc_date, doc_language, doc_category, q_score, source_org or "-", filename,
    )

    return {
        "document_date": doc_date,
        "document_language": doc_language,
        "document_category": doc_category,
        "quality_score": q_score,
        "source_organization": source_org,
    }


def enrich_chunks_metadata(
    chunks: List[Dict[str, Any]],
    document_title: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Add semantic_type, heading_hierarchy, and confidence_score to each chunk dict.
    Modifies dicts in-place and returns the list.
    """
    for chunk in chunks:
        content = chunk.get("content") or ""
        chunk_type = chunk.get("chunk_type")
        section_title = chunk.get("section_title")
        chunk_index = chunk.get("chunk_index", 0)
        page_number = chunk.get("page_number")

        chunk["semantic_type"] = classify_chunk_semantic_type(content, chunk_type)
        chunk["heading_hierarchy"] = build_heading_hierarchy(
            section_title=section_title,
            chunk_index=chunk_index,
            page_number=page_number,
            document_title=document_title,
        )
        # Default confidence; can be overridden by OCR-specific processors
        if "confidence_score" not in chunk:
            chunk["confidence_score"] = None

    return chunks
