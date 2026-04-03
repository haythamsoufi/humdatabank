"""
ai_tools._focus_area_analysis
─────────────────────────────
Constants and helper functions for ``analyze_unified_plans_focus_areas``.

Extracted from ``registry.py`` for maintainability: hardcoded seed-term
dictionaries, regex pattern sets, and matching pipeline helpers live here
so the tool method stays focused on orchestration.
"""

import logging
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Built-in focus-area seed terms
# ──────────────────────────────────────────────────────────────────────

DEFAULT_AREA_SEED_TERMS: Dict[str, List[str]] = {
    "cash": [
        "cash", "cash assistance", "cash transfer", "cash-based",
        "cash and voucher", "voucher", "cva",
    ],
    "cea": [
        "cea", "community engagement and accountability",
        "accountability to affected populations", "community feedback", "aap",
    ],
    "livelihoods": [
        "livelihood", "livelihoods", "economic security", "income generation",
        "food security", "economic recovery", "vocational training",
        "skills training", "cash for work", "income-generating activities",
        "economic inclusion", "economic empowerment", "market-based programming",
    ],
    "social_protection": [
        "social protection", "social assistance", "social safety net",
        "social welfare", "social insurance", "social inclusion",
        "social cohesion", "social services",
    ],
}

DEFAULT_AREA_REGEX_PATTERNS: Dict[str, List[str]] = {
    "cash": [
        r"\bcash\b",
        r"\bcash(?:\s|-)?assistance\b",
        r"\bcash(?:\s|-)?transfer(?:s)?\b",
        r"\bcash(?:\s|-)?based\b",
        r"\bcash\s+and\s+voucher(?:s)?\b",
        r"\bcva\b",
    ],
    "cea": [
        r"\bcea\b",
        r"\bcommunity\s+engagement\s+and\s+accountability\b",
    ],
    "livelihoods": [
        r"\blivelihood(?:s)?\b",
        r"\bfood\s+security\b",
        r"\bincome\s+generat(?:ion|ing)\b",
        r"\beconomic\s+(?:security|recovery|inclusion|empowerment)\b",
        r"\bvocational\s+training\b",
        r"\bskills\s+training\b",
        r"\bcash\s+for\s+work\b",
        r"\bmarket[- ]based\s+programming\b",
    ],
    "social_protection": [
        r"\bsocial\s+protection\b",
        r"\bsocial\s+(?:assistance|welfare|insurance|inclusion)\b",
        r"\bsocial\s+safety\s+net(?:s)?\b",
        r"\bsocial\s+cohesion\b",
        r"\bsafety\s+net(?:s)?\b",
    ],
}

DEFAULT_AREA_STRICT_REGEX_PATTERNS: Dict[str, List[str]] = {
    "cash": [
        r"\bcash\b",
        r"\bcash(?:\s|-)?assistance\b",
        r"\bcash(?:\s|-)?transfer(?:s)?\b",
        r"\bcash\s+and\s+voucher(?:s)?\b",
        r"\bcva\b",
    ],
    "cea": [
        r"\bcea\b",
        r"\bcommunity\s+engagement\s+and\s+accountability\b",
        r"\baccountability\s+to\s+affected\s+populations\b",
        r"\baap\b",
        r"\bcommunity\s+feedback\b",
        r"\bcommunity\s+engagement\b.{0,60}\baccountability\b",
        r"\baccountability\b.{0,60}\bcommunity\s+engagement\b",
    ],
    "livelihoods": [
        r"\blivelihood(?:s)?\b",
        r"\beconomic\s+security\b",
        r"\bfood\s+security\b",
        r"\bincome\s+generat(?:ion|ing)\b",
        r"\bvocational\s+training\b",
        r"\bcash\s+for\s+work\b",
    ],
    "social_protection": [
        r"\bsocial\s+protection\b",
        r"\bsocial\s+assistance\b",
        r"\bsocial\s+safety\s+net(?:s)?\b",
        r"\bsocial\s+welfare\b",
        r"\bsocial\s+inclusion\b",
    ],
}

# ──────────────────────────────────────────────────────────────────────
# Extended / thematic area definitions
# ──────────────────────────────────────────────────────────────────────

KNOWN_THEME_SEEDS: Dict[str, Dict[str, List[str]]] = {
    "migration": {
        "seeds": [
            "migration", "migrant", "migrants", "refugee", "refugees",
            "displacement", "displaced", "internally displaced person",
            "IDP", "asylum seeker", "forced displacement", "mixed migration",
            "stateless", "statelessness", "human trafficking",
        ],
        "patterns": [
            r"\bmigr(?:ation|ant|ants)\b",
            r"\brefugee(?:s)?\b",
            r"\bdisplac(?:ement|ed)\b",
            r"\bIDP(?:s)?\b",
            r"\basylum\s+seeker(?:s)?\b",
            r"\bforced\s+(?:migration|displacement)\b",
            r"\bmixed\s+migration\b",
            r"\bstateless(?:ness)?\b",
        ],
        "strict": [
            r"\bmigr(?:ation|ant|ants)\b",
            r"\brefugee(?:s)?\b",
            r"\bdisplac(?:ed\s+persons?|ement)\b",
            r"\bIDP(?:s)?\b",
            r"\bforced\s+(?:migration|displacement)\b",
        ],
    },
    "displacement": {
        "seeds": [
            "displacement", "displaced", "IDP", "internally displaced",
            "forced displacement", "internal displacement", "migration",
        ],
        "patterns": [
            r"\bdisplac(?:ement|ed)\b",
            r"\bIDP(?:s)?\b",
            r"\bforced\s+displacement\b",
            r"\binternal\s+displacement\b",
        ],
        "strict": [
            r"\bdisplac(?:ed\s+persons?|ement)\b",
            r"\bIDP(?:s)?\b",
            r"\bforced\s+displacement\b",
        ],
    },
    "migration_displacement": {
        "seeds": [
            "migration", "displacement", "migrant", "refugee", "IDP",
            "asylum", "forced migration", "mixed migration", "displaced",
            "stateless", "human trafficking",
        ],
        "patterns": [
            r"\bmigr(?:ation|ant|ants)\b",
            r"\brefugee(?:s)?\b",
            r"\bdisplac(?:ement|ed)\b",
            r"\bIDP(?:s)?\b",
            r"\basylum\s+seeker(?:s)?\b",
            r"\bforced\s+(?:migration|displacement)\b",
            r"\bmixed\s+migration\b",
        ],
        "strict": [
            r"\bmigr(?:ation|ant|ants)\b",
            r"\brefugee(?:s)?\b",
            r"\bdisplac(?:ed\s+persons?|ement)\b",
            r"\bIDP(?:s)?\b",
        ],
    },
    "climate": {
        "seeds": [
            "climate change", "climate adaptation", "climate risk",
            "climate resilience", "climate crisis", "climate action",
            "environmental degradation", "climate-smart",
        ],
        "patterns": [
            r"\bclimate\s+(?:change|adapt\w*|risk|resilien\w*|crisis|action|smart)\b",
            r"\benvironmental\s+(?:degradation|risk)\b",
        ],
        "strict": [
            r"\bclimate\s+(?:change|adapt\w*|risk|resilien\w*)\b",
        ],
    },
    "mhpss": {
        "seeds": [
            "MHPSS", "mental health", "psychosocial support",
            "psychological first aid", "mental wellbeing",
            "mental health and psychosocial",
        ],
        "patterns": [
            r"\bMHPSS\b",
            r"\bmental\s+health\b",
            r"\bpsychosocial\s+support\b",
            r"\bpsychological\s+first\s+aid\b",
            r"\bmental\s+wellbeing\b",
        ],
        "strict": [
            r"\bMHPSS\b",
            r"\bmental\s+health\b",
            r"\bpsychosocial\b",
        ],
    },
    "pgi": {
        "seeds": [
            "PGI", "protection gender inclusion",
            "protection gender and inclusion",
            "gender-based violence", "GBV", "gender equality", "inclusion",
            "disability inclusion", "protection mainstreaming",
        ],
        "patterns": [
            r"\bPGI\b",
            r"\bprotection\s+gender\s+(?:and\s+)?inclusion\b",
            r"\bgender[- ]based\s+violence\b",
            r"\bGBV\b",
            r"\bgender\s+equality\b",
            r"\bdisability\s+inclusion\b",
            r"\bprotection\s+mainstreaming\b",
        ],
        "strict": [
            r"\bPGI\b",
            r"\bgender[- ]based\s+violence\b",
            r"\bGBV\b",
            r"\bdisability\s+inclusion\b",
        ],
    },
    "health": {
        "seeds": [
            "health", "health services", "primary health care",
            "community health", "public health", "health promotion",
            "disease prevention", "health emergency", "epidemic", "pandemic",
        ],
        "patterns": [
            r"\bhealth\b",
            r"\bprimary\s+health\s+care\b",
            r"\bcommunity\s+health\b",
            r"\bhealth\s+(?:promotion|services|emergency)\b",
            r"\bepidemic\b",
            r"\bpandemic\b",
        ],
        "strict": [
            r"\bhealth\b",
            r"\bprimary\s+health\s+care\b",
            r"\bepidemic\b",
            r"\bpandemic\b",
        ],
    },
    "disaster_risk_reduction": {
        "seeds": [
            "disaster risk reduction", "DRR", "disaster preparedness",
            "risk reduction", "resilience", "early warning",
            "community preparedness", "disaster management",
        ],
        "patterns": [
            r"\bDRR\b",
            r"\bdisaster\s+risk\s+reduction\b",
            r"\bdisaster\s+preparedness\b",
            r"\bearly\s+warning\b",
            r"\brisk\s+reduction\b",
            r"\bdisaster\s+management\b",
        ],
        "strict": [
            r"\bDRR\b",
            r"\bdisaster\s+risk\s+reduction\b",
            r"\bdisaster\s+preparedness\b",
        ],
    },
}

# ──────────────────────────────────────────────────────────────────────
# Labels
# ──────────────────────────────────────────────────────────────────────

DEFAULT_AREA_LABELS: Dict[str, str] = {
    "cash": "Cash",
    "cea": "CEA",
    "livelihoods": "Livelihoods",
    "social_protection": "Social Protection",
}

KNOWN_THEME_LABELS: Dict[str, str] = {
    "migration": "Migration",
    "displacement": "Displacement",
    "migration_displacement": "Migration & Displacement",
    "climate": "Climate",
    "mhpss": "MHPSS",
    "pgi": "PGI",
    "health": "Health",
    "disaster_risk_reduction": "Disaster Risk Reduction",
}


# ──────────────────────────────────────────────────────────────────────
# Pure helper functions
# ──────────────────────────────────────────────────────────────────────

def generate_area_from_key(area_key: str) -> Dict[str, List[str]]:
    """Auto-generate seed terms and regex patterns from a free-text area key."""
    words = re.split(r"[_\-\s]+", str(area_key or "").lower())
    words = [w for w in words if w and len(w) >= 3]
    if not words:
        return {"seeds": [], "patterns": [], "strict": []}
    seeds: List[str] = []
    patterns: List[str] = []
    if len(words) >= 2:
        phrase = " ".join(words)
        seeds.append(phrase)
        esc = r"\s+".join(re.escape(w) for w in words)
        patterns.append(rf"\b{esc}\b")
    for w in words:
        seeds.append(w)
        esc = re.escape(w)
        patterns.append(rf"\b{esc}(?:s|ed|ment|ments|ion|ions|ing)?\b")
    return {
        "seeds": list(dict.fromkeys(seeds)),
        "patterns": list(dict.fromkeys(patterns)),
        "strict": list(dict.fromkeys(patterns)),
    }


def normalise_area_key(raw: str) -> str:
    """Collapse spaces/hyphens to underscores, lowercase."""
    return re.sub(r"[\s\-]+", "_", raw.strip().lower())


def extract_plan_year(*texts: str) -> Optional[int]:
    """Extract a 4-digit year from text strings."""
    joined = " ".join([str(t or "") for t in texts])
    m = re.search(r"\b(19\d{2}|20\d{2})\b", joined)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def extract_plan_code(*texts: str) -> Optional[str]:
    """Extract a UPL-style plan code from text strings."""
    joined = " ".join([str(t or "") for t in texts]).upper()
    m = re.search(r"\bUPL[-_\s]?\d{4}[-_A-Z0-9]+\b", joined)
    if not m:
        return None
    return re.sub(r"[\s_]+", "-", m.group(0).strip())


def extract_country_from_title(title: Any) -> Optional[str]:
    """Extract country name from a Unified Plan document title."""
    t = str(title or "").strip()
    if not t:
        return None
    m = re.match(
        r"^\s*([A-Za-z][A-Za-z ,'\-\(\)]{2,80}?)\s+\d{4}\s+Unified\s+Plan\b",
        t, re.IGNORECASE,
    )
    if not m:
        return None
    return re.sub(r"\s+", " ", str(m.group(1) or "")).strip()


def norm_country_name(name: Any) -> str:
    """Normalize a country name for comparison."""
    s = re.sub(r"[^a-z0-9 ]+", " ", str(name or "").strip().lower())
    return re.sub(r"\s+", " ", s).strip()


def alias_to_regex(alias: str) -> Optional[str]:
    """Convert a seed-term alias to a word-boundary regex pattern string."""
    a = str(alias or "").strip()
    if not a:
        return None
    esc = re.escape(a).replace(r"\ ", r"\s+")
    if re.search(r"[A-Za-z0-9]", a):
        return rf"\b{esc}\b"
    return esc


def normalized_plan_key(doc: Any) -> str:
    """Create a deduplication key for a document (UPL code or fallback)."""
    t = str(getattr(doc, "title", "") or "")
    f = str(getattr(doc, "filename", "") or "")
    text = f"{t} {f}".upper()
    m = re.search(r"\bUPL[-_\s]?\d{4}[-_A-Z0-9]+\b", text)
    if m:
        code = re.sub(r"[\s_]+", "-", m.group(0).strip())
        return f"upl:{code}"
    year = None
    m_year = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    if m_year:
        year = m_year.group(1)
    country_hint = (
        str(getattr(doc, "country_name", "") or "").strip().lower()
        or str(getattr(doc, "country_id", "") or "")
    )
    normalized_title = re.sub(r"\s+", " ", t.strip().lower())[:80]
    return f"fallback:{country_hint}:{year or 'na'}:{normalized_title}"


# ──────────────────────────────────────────────────────────────────────
# Area configuration
# ──────────────────────────────────────────────────────────────────────

def resolve_area_config(
    areas: Optional[List[str]] = None,
) -> Tuple[
    List[str],
    Dict[str, List[str]],
    Dict[str, List[str]],
    Dict[str, List[str]],
    Dict[str, str],
]:
    """
    Normalize requested area keys, expand with known themes, and build
    seed-term / pattern / label lookups.

    Returns:
        (area_keys, area_seed_terms, area_regex_patterns, strict_patterns, area_labels)
    """
    area_seed_terms = {k: list(v) for k, v in DEFAULT_AREA_SEED_TERMS.items()}
    area_regex_patterns = {k: list(v) for k, v in DEFAULT_AREA_REGEX_PATTERNS.items()}
    strict_patterns = {k: list(v) for k, v in DEFAULT_AREA_STRICT_REGEX_PATTERNS.items()}

    requested = [normalise_area_key(a) for a in (areas or []) if str(a or "").strip()]

    for req_key in requested:
        if req_key in area_seed_terms:
            continue
        theme = KNOWN_THEME_SEEDS.get(req_key) or generate_area_from_key(req_key)
        area_seed_terms[req_key] = theme.get("seeds") or []
        area_regex_patterns[req_key] = theme.get("patterns") or []
        strict_patterns[req_key] = theme.get("strict") or []

    area_keys = requested if requested else list(area_seed_terms.keys())[:4]

    area_labels: Dict[str, str] = dict(DEFAULT_AREA_LABELS)
    for k in area_keys:
        if k not in area_labels:
            area_labels[k] = KNOWN_THEME_LABELS.get(k) or k.replace("_", " ").title()

    return area_keys, area_seed_terms, area_regex_patterns, strict_patterns, area_labels


def compile_area_regexes(
    area_keys: List[str],
    area_seed_terms: Dict[str, List[str]],
    area_regex_patterns: Dict[str, List[str]],
    strict_patterns: Dict[str, List[str]],
) -> Tuple[Dict[str, List[Any]], Dict[str, List[Any]]]:
    """
    Enrich seed terms from IFRC terminology service, build alias regexes,
    and compile all patterns.

    Returns:
        (compiled_area_regexes, compiled_strict_area_regexes)
    """
    from app.services.ifrc_terminology_service import get_focus_area_aliases

    for k in area_keys:
        try:
            enriched = get_focus_area_aliases(k, max_aliases=120)
        except Exception as exc:
            logger.debug("get_focus_area_aliases failed for %r: %s", k, exc)
            enriched = []
        if enriched:
            area_seed_terms[k] = list(dict.fromkeys(
                (area_seed_terms.get(k) or []) + enriched
            ))

    compiled: Dict[str, List[Any]] = {}
    compiled_strict: Dict[str, List[Any]] = {}

    for k in area_keys:
        pats = list(area_regex_patterns.get(k) or [])
        for a in (area_seed_terms.get(k) or [])[:120]:
            rx = alias_to_regex(a)
            if rx:
                pats.append(rx)
        dedup_pats = list(dict.fromkeys(pats))[:220]
        compiled[k] = [re.compile(p, re.IGNORECASE) for p in dedup_pats]

        s_pats = list(dict.fromkeys(strict_patterns.get(k) or []))[:80]
        compiled_strict[k] = [re.compile(p, re.IGNORECASE) for p in s_pats]

    return compiled, compiled_strict


# ──────────────────────────────────────────────────────────────────────
# Boilerplate / header detection
# ──────────────────────────────────────────────────────────────────────

# Compiled once: patterns that match standard Unified Plan section headers,
# table column rows, and strategic-priority banners where focus-area keywords
# appear as labels, not as descriptions of actual activities.
_BOILERPLATE_RE = re.compile(
    r"(?:"
    # Standard strategic-priority header row and its common variants:
    #   "Climate and Disasters Health and Migration and Values, power"
    #   "Ongoing Climate and Disasters Health and Migration & Values, power"
    #   "Ongoing Climate and Disasters Migration and Health and Values, power"  (swapped)
    #   "Climate and Health and Migration and Values, power"  (no Disasters)
    r"(?:Ongoing\s+)?Climate\s+(?:and\s+)?(?:environment\s+)?"
    r"(?:(?:and\s+)?Disasters?\s+(?:and\s+crises?\s+)?)?"
    r"(?:Health\s+(?:and\s+(?:wellbeing\s+)?)?(?:and\s+)?Migration|Migration\s+(?:and\s+)?Health)"
    r"(?:\s*[&]\s*|\s+and\s+)?"
    r"Values"
    r"|"
    # Table column header rows (non-greedy to avoid backtracking)
    r"Columns:\s*National\s+Society\s*\|[^\n]+?(?:Migration|Displacement)"
    r"|"
    # Standalone column-header style rows (pipe-delimited with focus area labels)
    r"(?:Disasters?\s+(?:and\s+)?(?:crises?\s+)?\|?\s*)?Health\s+(?:and\s+)?(?:wellbeing\s+)?\|?\s*"
    r"(?:Migration\s+(?:and\s+)?(?:displacement\s+)?\|?\s*)?Values"
    r"|"
    # IFRC strategic-priority breakdown rows
    r"IFRC\s+breakdown\s+\d{4}\s+\(strategic\s+priorities\)"
    r")",
    re.IGNORECASE,
)


def _strip_boilerplate(text: str) -> str:
    """Remove recognised boilerplate header/column patterns from *text*
    and return the remainder.  Used to test whether a chunk has substantive
    keyword mentions beyond the standard strategic-priority labels."""
    return _BOILERPLATE_RE.sub("", text)


def _chunk_has_substantive_match(text: str, regexes: list) -> bool:
    """Return True if *text* matches any of *regexes* in content that is
    NOT purely boilerplate header text."""
    if not text or not regexes:
        return False
    if not any(rx.search(text) for rx in regexes):
        return False
    stripped = _strip_boilerplate(text)
    if not stripped.strip():
        return False
    return any(rx.search(stripped) for rx in regexes)


# ──────────────────────────────────────────────────────────────────────
# Focus-area matching pipeline
# ──────────────────────────────────────────────────────────────────────

def match_focus_areas(
    doc_ids: List[int],
    area_keys: List[str],
    area_seed_terms: Dict[str, List[str]],
    compiled_area_regexes: Dict[str, List[Any]],
    compiled_strict_area_regexes: Dict[str, List[Any]],
) -> Tuple[Dict[str, Set[int]], str, Dict[str, Any]]:
    """
    Run semantic → lexical rescue → per-area lexical fallback → strict confirmation.

    Returns:
        (hits_by_area, detection_method, debug_info)
    """
    from sqlalchemy import or_, func
    from app.models.embeddings import AIDocumentChunk
    from app.extensions import db
    from app.services.ifrc_terminology_service import get_focus_area_semantic_doc_hits
    from flask import current_app

    import time as _time
    _t0 = _time.time()

    hits_by_area: Dict[str, Set[int]] = {k: set() for k in area_keys}
    detection_method = "semantic_vectors"
    semantic_debug: Dict[str, Any] = {}

    if not doc_ids:
        return hits_by_area, "no_documents", {}

    # ── Phase 1: Semantic similarity ──
    try:
        sem_hits = get_focus_area_semantic_doc_hits(
            doc_ids=doc_ids,
            area_keys=area_keys,
            return_debug=True,
            include_per_doc_debug=bool(
                current_app.config.get("AI_TERM_INCLUDE_PER_DOC_DEBUG", False)
            ),
        )
    except Exception as exc:
        logger.debug("get_focus_area_semantic_doc_hits failed: %s", exc)
        sem_hits = {}

    logger.info("match_focus_areas: semantic phase done in %dms, docs=%d",
                int((_time.time() - _t0) * 1000), len(doc_ids))

    sem_hit_map = (
        sem_hits.get("hits_by_area")
        if isinstance(sem_hits, dict) and isinstance(sem_hits.get("hits_by_area"), dict)
        else sem_hits
    )
    margin_rejected = (
        sem_hits.get("margin_rejected_by_area")
        if isinstance(sem_hits, dict) and isinstance(sem_hits.get("margin_rejected_by_area"), dict)
        else {}
    )
    semantic_debug = (
        sem_hits.get("debug")
        if isinstance(sem_hits, dict) and isinstance(sem_hits.get("debug"), dict)
        else {}
    )

    content_lc = func.lower(func.coalesce(AIDocumentChunk.content, ""))

    if sem_hit_map and any(len(v or []) > 0 for v in sem_hit_map.values()):
        for k in area_keys:
            hits_by_area[k] = set(sem_hit_map.get(k) or [])

        # Lexical rescue for margin-rejected docs
        lexical_rescued_debug: Dict[str, Any] = {}
        for key in area_keys:
            rejected_docs = sorted(list(margin_rejected.get(key) or []))
            if not rejected_docs:
                continue
            strict_regexes = compiled_strict_area_regexes.get(key) or []
            if not strict_regexes:
                continue
            rows = (
                db.session.query(AIDocumentChunk.document_id, AIDocumentChunk.content)
                .filter(AIDocumentChunk.document_id.in_(rejected_docs))
                .all()
            )
            rescued: Set[int] = set()
            for row in rows or []:
                if not row or row[0] is None:
                    continue
                did = int(row[0])
                txt = str(row[1] or "")
                if txt and _chunk_has_substantive_match(txt, strict_regexes):
                    rescued.add(did)
            if rescued:
                hits_by_area[key] |= rescued
            lexical_rescued_debug[key] = {
                "margin_rejected_docs": len(rejected_docs),
                "rescued_docs": len(rescued),
                "strict_patterns": len(strict_regexes),
            }
        semantic_debug["lexical_rescue"] = lexical_rescued_debug

        # Per-area lexical fallback for areas still at zero
        zero_areas = [k for k in area_keys if not hits_by_area.get(k)]
        if zero_areas:
            lexical_fallback_debug: Dict[str, Any] = {}
            for key in zero_areas:
                terms = area_seed_terms.get(key) or []
                conds = [content_lc.like(f"%{t.lower()}%") for t in terms if t]
                if not conds:
                    continue
                rows = (
                    db.session.query(AIDocumentChunk.document_id, AIDocumentChunk.content)
                    .filter(AIDocumentChunk.document_id.in_(doc_ids))
                    .filter(or_(*conds))
                    .all()
                )
                doc_hits_fb: Set[int] = set()
                strict_rxs = (
                    compiled_strict_area_regexes.get(key)
                    or compiled_area_regexes.get(key)
                    or []
                )
                for row in rows or []:
                    if not row or row[0] is None:
                        continue
                    did = int(row[0])
                    txt = str(row[1] or "")
                    if txt and _chunk_has_substantive_match(txt, strict_rxs):
                        doc_hits_fb.add(did)
                hits_by_area[key] = doc_hits_fb
                lexical_fallback_debug[key] = {
                    "candidate_chunks": len(rows or []),
                    "docs_found": len(doc_hits_fb),
                }
            semantic_debug["per_area_lexical_fallback"] = lexical_fallback_debug
            if all(not hits_by_area.get(k) for k in area_keys):
                detection_method = "semantic_vectors_plus_lexical_fallback"
            elif any(
                lexical_fallback_debug.get(k, {}).get("docs_found", 0) > 0
                for k in zero_areas
            ):
                detection_method = "semantic_vectors_plus_lexical_fallback"
    else:
        # Full lexical fallback (no semantic results at all)
        detection_method = "lexical_fallback"
        for key in area_keys:
            terms = area_seed_terms.get(key) or []
            conds = [content_lc.like(f"%{t.lower()}%") for t in terms if t]
            if not conds:
                continue
            rows = (
                db.session.query(AIDocumentChunk.document_id, AIDocumentChunk.content)
                .filter(AIDocumentChunk.document_id.in_(doc_ids))
                .filter(or_(*conds))
                .all()
            )
            doc_hits: Set[int] = set()
            regexes = compiled_area_regexes.get(key) or []
            for row in rows or []:
                if not row:
                    continue
                did = int(row[0]) if row[0] is not None else None
                if not did:
                    continue
                text = str(row[1] or "")
                if not text:
                    continue
                if _chunk_has_substantive_match(text, regexes):
                    doc_hits.add(did)
            hits_by_area[key] = doc_hits

    _t_lexical_done = _time.time()
    logger.info("match_focus_areas: semantic+lexical phases done, total %dms so far",
                int((_t_lexical_done - _t0) * 1000))

    # ── Phase 2: Strict lexical confirmation ──
    # A document is confirmed only if at least one chunk has a substantive
    # (non-boilerplate) match for the area's strict patterns.
    strict_confirmation_debug: Dict[str, Any] = {}
    if doc_ids and any(hits_by_area.get(k) for k in area_keys):
        for key in area_keys:
            candidates = sorted(list(hits_by_area.get(key) or set()))
            if not candidates:
                continue
            strict_rxs = compiled_strict_area_regexes.get(key) or []
            if not strict_rxs:
                continue
            rows = (
                db.session.query(AIDocumentChunk.document_id, AIDocumentChunk.content)
                .filter(AIDocumentChunk.document_id.in_(candidates))
                .all()
            )
            keep: Set[int] = set()
            for row in rows or []:
                if not row or row[0] is None:
                    continue
                did = int(row[0])
                txt = str(row[1] or "")
                if txt and _chunk_has_substantive_match(txt, strict_rxs):
                    keep.add(did)
            removed = set(candidates) - keep
            hits_by_area[key] = keep
            strict_confirmation_debug[key] = {
                "candidate_docs": len(candidates),
                "kept_docs": len(keep),
                "removed_docs": len(removed),
                "strict_patterns": len(strict_rxs),
            }

    logger.info("match_focus_areas: strict confirmation done, total %dms",
                int((_time.time() - _t0) * 1000))

    debug_info = {
        "semantic_debug": semantic_debug if detection_method.startswith("semantic") else {},
        "strict_lexical_confirmation": strict_confirmation_debug,
    }
    return hits_by_area, detection_method, debug_info


# ──────────────────────────────────────────────────────────────────────
# Evidence extraction
# ──────────────────────────────────────────────────────────────────────

def extract_area_evidence(
    area_keys: List[str],
    hits_by_area: Dict[str, Set[int]],
    area_seed_terms: Dict[str, List[str]],
    compiled_strict_area_regexes: Dict[str, List[Any]],
    compiled_area_regexes: Dict[str, List[Any]],
) -> Dict[int, Dict[str, Dict[str, Any]]]:
    """Build evidence snippets (matched terms, activity examples) per (document, area)."""
    from sqlalchemy import or_, func
    from app.models.embeddings import AIDocumentChunk
    from app.extensions import db

    area_evidence: Dict[int, Dict[str, Dict[str, Any]]] = defaultdict(dict)
    content_lc = func.lower(func.coalesce(AIDocumentChunk.content, ""))

    for key in area_keys:
        target_docs = sorted(list(hits_by_area.get(key) or set()))
        if not target_docs:
            continue
        regexes = (
            (compiled_strict_area_regexes.get(key) or [])
            or (compiled_area_regexes.get(key) or [])
        )
        terms = area_seed_terms.get(key) or []
        conds = [
            content_lc.like(f"%{str(t).lower()}%")
            for t in terms if str(t).strip()
        ][:40]
        q = db.session.query(
            AIDocumentChunk.document_id, AIDocumentChunk.content
        ).filter(AIDocumentChunk.document_id.in_(target_docs))
        if conds:
            q = q.filter(or_(*conds))
        rows = q.all()

        for row in rows or []:
            if not row or row[0] is None:
                continue
            did = int(row[0])
            text = str(row[1] or "")
            if not text or not regexes:
                continue
            if not _chunk_has_substantive_match(text, regexes):
                continue

            store = area_evidence[did].setdefault(
                key,
                {
                    "matched_terms": [],
                    "activity_examples": [],
                    "evidence_chunks": 0,
                    "mentioned": True,
                },
            )
            store["evidence_chunks"] = int(store.get("evidence_chunks") or 0) + 1

            stripped_text = _strip_boilerplate(text)
            mvals: List[str] = []
            for rx in regexes[:30]:
                try:
                    for m in rx.finditer(stripped_text):
                        v = re.sub(r"\s+", " ", str(m.group(0) or "")).strip()
                        if v:
                            mvals.append(v)
                        if len(mvals) >= 6:
                            break
                    if len(mvals) >= 6:
                        break
                except Exception:
                    continue
            if mvals:
                merged = list(dict.fromkeys(
                    (store.get("matched_terms") or []) + mvals
                ))
                store["matched_terms"] = merged[:8]

            snippets = re.split(r"(?<=[\.\!\?])\s+|\n+", stripped_text)
            for s in snippets:
                s_clean = re.sub(r"\s+", " ", str(s or "")).strip(" \t-\u2022")
                if not s_clean:
                    continue
                if len(s_clean) < 45 or len(s_clean.split()) < 7:
                    continue
                if s_clean.endswith(":"):
                    continue
                if re.fullmatch(r"[A-Za-z][A-Za-z\s/&\-\(\)]{0,80}", s_clean):
                    continue
                if any(rx.search(s_clean) for rx in regexes):
                    sample = s_clean[:240]
                    sample = re.sub(r"([a-z])([A-Z][a-z])", r"\1. \2", sample)
                    sample = re.sub(r"(\w)-\s+(\w)", r"\1\2", sample)
                    sample = re.sub(r"\s{2,}", " ", sample).strip()
                    if sample and sample not in (store.get("activity_examples") or []):
                        store["activity_examples"] = (
                            (store.get("activity_examples") or []) + [sample]
                        )
                    if len(store.get("activity_examples") or []) >= 3:
                        break

    return dict(area_evidence)


# ──────────────────────────────────────────────────────────────────────
# Result assembly
# ──────────────────────────────────────────────────────────────────────

def assemble_plan_results(
    docs: list,
    area_keys: List[str],
    hits_by_area: Dict[str, Set[int]],
    area_labels: Dict[str, str],
    area_evidence_by_doc: Dict[int, Dict[str, Dict[str, Any]]],
) -> Tuple[List[Dict[str, Any]], int, Dict[str, Dict[str, Any]], Set[str]]:
    """
    Build the plans list, country groups, and coverage tracking.

    Returns:
        (plans, none_count, country_groups_map, all_countries_considered)
    """
    plans: List[Dict[str, Any]] = []
    none_count = 0
    country_groups_map: Dict[str, Dict[str, Any]] = {}
    all_countries_considered: Set[str] = set()

    for d in docs or []:
        doc_payload = d.to_dict()
        countries = (
            doc_payload.get("countries")
            if isinstance(doc_payload.get("countries"), list) else []
        )
        countries_clean: List[Dict[str, Any]] = []
        for c in countries:
            if not isinstance(c, dict):
                continue
            countries_clean.append({
                "id": c.get("id"),
                "name": c.get("name"),
                "iso3": c.get("iso3"),
            })

        country_name = doc_payload.get("country_name")
        country_iso3 = doc_payload.get("country_iso3")
        if countries_clean:
            names = [
                str(c.get("name") or "").strip()
                for c in countries_clean if str(c.get("name") or "").strip()
            ]
            iso3s = [
                str(c.get("iso3") or "").strip()
                for c in countries_clean if str(c.get("iso3") or "").strip()
            ]
            if names:
                country_name = ", ".join(names[:3]) + (" (+more)" if len(names) > 3 else "")
            if iso3s:
                country_iso3 = ", ".join(iso3s[:4]) + (" (+more)" if len(iso3s) > 4 else "")

        title_country = extract_country_from_title(doc_payload.get("title"))
        if title_country and (not countries_clean or len(countries_clean) == 1):
            meta_norm = norm_country_name(country_name)
            title_norm = norm_country_name(title_country)
            names_conflict = bool(
                meta_norm and title_norm
                and meta_norm != title_norm
                and not (meta_norm in title_norm and len(meta_norm) > 4)
                and not (title_norm in meta_norm and len(title_norm) > 4)
            )
            title_is_more_specific = bool(
                meta_norm and title_norm
                and meta_norm != title_norm
                and meta_norm in title_norm
                and len(title_norm) > len(meta_norm) + 5
            )
            if names_conflict or title_is_more_specific:
                country_name = title_country
                country_iso3 = None
                countries_clean = [{"name": title_country, "iso3": None, "id": None}]

        coverage_candidates = countries_clean or [{"name": country_name, "iso3": country_iso3}]
        for cc in coverage_candidates:
            c_name = str(cc.get("name") or country_name or "Unknown").strip() or "Unknown"
            c_iso = str(cc.get("iso3") or country_iso3 or "").strip()
            all_countries_considered.add(f"{c_iso or 'NA'}::{c_name.lower()}")

        mentioned = sorted([
            k for k in area_keys if int(d.id) in hits_by_area.get(k, set())
        ])
        if not mentioned:
            none_count += 1
            continue

        plan_year = extract_plan_year(doc_payload.get("title"), doc_payload.get("filename"))
        plan_code = extract_plan_code(doc_payload.get("title"), doc_payload.get("filename"))
        area_details: Dict[str, Dict[str, Any]] = {}
        for key in area_keys:
            if key in mentioned:
                details = dict(
                    (area_evidence_by_doc.get(int(d.id), {}).get(key) or {})
                )
                if not details:
                    details = {
                        "mentioned": True,
                        "matched_terms": [],
                        "activity_examples": [],
                        "evidence_chunks": 0,
                    }
                details["label"] = area_labels.get(key, key)
                area_details[key] = details

        plan_row = {
            "document_id": int(d.id),
            "document_title": doc_payload.get("title"),
            "document_filename": doc_payload.get("filename"),
            "document_country_name": country_name,
            "document_country_iso3": country_iso3,
            "document_countries": countries_clean,
            "document_url": f"/api/ai/documents/{int(d.id)}/download",
            "plan_year": plan_year,
            "plan_code": plan_code,
            "areas_mentioned": mentioned,
            "area_details": area_details,
            "no_target_areas": False,
        }
        plans.append(plan_row)

        group_candidates = countries_clean or [{"name": country_name, "iso3": country_iso3}]
        for cc in group_candidates:
            cname = str(cc.get("name") or country_name or "Unknown").strip() or "Unknown"
            ciso = str(cc.get("iso3") or country_iso3 or "").strip()
            ckey = f"{ciso or 'NA'}::{cname.lower()}"
            group = country_groups_map.setdefault(
                ckey,
                {"country_name": cname, "country_iso3": ciso, "plans": []},
            )
            group["plans"].append(dict(plan_row))

    return plans, none_count, country_groups_map, all_countries_considered
