"""
Country detection for AI documents.

Goal: best-effort detection of the document's countries from filename/title/content,
and link them to the ``country`` table when possible.  Supports multi-country
documents and global / IFRC regional / cluster scope inference.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from app.models import Country

logger = logging.getLogger(__name__)

# IFRC country-plan / appeal cover pages often list partner National Societies
# whose names embed country names (e.g. "Kuwait Red Crescent Society").
# Strip these so they don't inflate multi-country detection.
_PARTICIPATING_NS_HEADING_RE = re.compile(
    r"\bparticipating\s+national\s+societ(?:y|ies)\b", re.IGNORECASE,
)
_NS_ORG_LINE_RE = re.compile(
    r"^.*\b(?:red\s+cross|red\s+crescent)\b.*$",
    re.IGNORECASE | re.MULTILINE,
)


def strip_ns_org_references(text: str | None) -> str | None:
    """
    Remove National Society organization references from text before country detection.

    Two-pass approach to handle multi-column PDF extraction where headings may be
    interleaved with content from other columns:

    1. Truncate at "Participating National Societies" heading if present.
    2. Remove individual lines containing "Red Cross" / "Red Crescent" — these are
       almost always NS org names whose embedded country names would otherwise
       produce false-positive secondary country hits.
    """
    if text is None:
        return None
    s = str(text)
    if not s.strip():
        return s
    m = _PARTICIPATING_NS_HEADING_RE.search(s)
    if m:
        s = s[: m.start()].rstrip()
    s = _NS_ORG_LINE_RE.sub("", s)
    return s


# ---------------------------------------------------------------------------
# Scope constants
# ---------------------------------------------------------------------------
SCOPE_GLOBAL = "global"
SCOPE_REGIONAL = "regional"
SCOPE_CLUSTER = "cluster"
# NULL / None means country-specific (one or more countries)


@dataclass
class CountryDetectionResult:
    """Result of multi-country detection."""
    countries: List[Tuple[int, str]]  # [(country_id, country_name), ...]
    scope: Optional[str] = None       # 'global', 'regional', 'cluster', or None

    @property
    def primary_country_id(self) -> Optional[int]:
        return self.countries[0][0] if self.countries else None

    @property
    def primary_country_name(self) -> Optional[str]:
        return self.countries[0][1] if self.countries else None


# ---------------------------------------------------------------------------
# Keywords that hint at global or IFRC regional scope
# ---------------------------------------------------------------------------
_GLOBAL_KEYWORDS = [
    "global", "worldwide", "all countries",
    "cross country", "multi country", "multicountry",
]
# IFRC statutory regions and common phrasing (Africa, MENA, Asia Pacific, Americas, Europe, Central Asia).
# Do NOT use generic words like "regional" / "region" alone — those are not IFRC regional scope.
# Longer phrases first so _matched_scope_keyword prefers specific matches.
_IFRC_REGION_SCOPE_KEYWORDS = [
    "europe and central asia",
    "middle east and north africa",
    "asia pacific",
    "asia-pacific",
    "asia and pacific",
    "sub saharan africa",
    "sub-saharan africa",
    "east africa",
    "west africa",
    "southern africa",
    "central africa",
    "north africa",
    "southeast asia",
    "south asia",
    "east asia",
    "central america",
    "south america",
    "north america",
    "latin america",
    "middle east",
    "central asia",
    "mena",
    "americas",
    "caribbean",
    "pacific",
    "oceania",
    "africa",
    "europe",
    "asia",
]

# Strong global phrases that should remain "global" even if many countries are mentioned.
_STRONG_GLOBAL_KEYWORDS = [
    "worldwide",
    "all countries",
]

# Minimum number of distinct countries detected to auto-infer multi-country
_MULTI_COUNTRY_THRESHOLD = 3


def _fold(s: str) -> str:
    """Lowercase + strip diacritics (e.g., Côte -> cote)."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s.lower()


_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")

# UPL codes often embed ISO2 after "MAA", e.g. UPL-2025-MAASS001 -> ISO2 "SS"
_UPL_MAA_ISO2_RE = re.compile(r"\bUPL-\d{4}-MAA([A-Z]{2})[A-Z0-9]*\b", re.IGNORECASE)


def _norm_space_text(s: str) -> str:
    """
    Normalize text for boundary-safe substring matching:
    - fold (lower + remove diacritics)
    - replace non-alnum with spaces
    - collapse whitespace
    - pad with spaces so we can search for " <phrase> " safely
    """
    t = _fold(s or "")
    t = _NON_ALNUM_RE.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return f" {t} " if t else " "


def _country_name_variants(country: Country) -> list[str]:
    """
    Generate country name variants from the ``country`` row.
    We intentionally DO NOT match ISO2/ISO3 codes here to avoid false positives
    (e.g., 'in' for India, 'and' for Andorra, 'usa' appearing in unrelated contexts).
    """
    variants: list[str] = []
    if getattr(country, "name", None):
        variants.append(str(country.name))

    # Include translations (if present)
    nt = getattr(country, "name_translations", None)
    if isinstance(nt, dict):
        for v in nt.values():
            if isinstance(v, str) and v.strip():
                variants.append(v.strip())

    # Small curated aliases (best-effort)
    folded = _fold(getattr(country, "name", "") or "")
    if folded == "turkiye":
        variants.append("Turkey")
    if folded == "turkey":
        variants.append("Türkiye")
        variants.append("Turkiye")

    # De-dup while preserving order
    seen = set()
    out: list[str] = []
    for v in variants:
        nv = _norm_space_text(v).strip()
        if not nv:
            continue
        if nv in seen:
            continue
        seen.add(nv)
        out.append(v)
    return out


def _detect_country_from_upl_code(*sources: str | None) -> tuple[int, str] | None:
    """
    Detect country from a UPL code that includes ISO2 after "MAA".
    Example: "UPL-2025-MAASS001" -> ISO2 "SS" -> South Sudan.
    """
    try:
        for src in sources:
            t = (src or "").strip()
            if not t:
                continue
            m = _UPL_MAA_ISO2_RE.search(t)
            if not m:
                continue
            iso2 = (m.group(1) or "").strip().upper()
            if not iso2:
                continue
            c = Country.query.filter(Country.iso2 == iso2).first()
            if c and getattr(c, "id", None) and getattr(c, "name", None):
                return int(c.id), str(c.name)
    except Exception as e:
        logger.debug("UPL/MAA ISO2 heuristic failed: %s", e)
        return None
    return None


def _build_candidates() -> list[tuple[int, str, list[str]]]:
    """Load countries from DB and build candidate list for matching."""
    try:
        countries: list[Country] = Country.query.all()
    except Exception as e:
        logger.warning("Country detection: failed to load countries: %s", e)
        return []

    candidates: list[tuple[int, str, list[str]]] = []
    for c in countries:
        try:
            cid = int(getattr(c, "id", 0) or 0)
            cname = str(getattr(c, "name", "") or "").strip()
        except Exception as e:
            logger.debug("country candidate parse failed: %s", e)
            continue
        if not cid or not cname:
            continue
        variants = _country_name_variants(c)
        variant_norms = []
        for v in variants:
            vn = _norm_space_text(v).strip()
            if vn:
                variant_norms.append(vn)
        variant_norms = sorted(set(variant_norms), key=len, reverse=True)
        if variant_norms:
            candidates.append((cid, cname, variant_norms))
    return candidates


def _detect_scope_from_text(hay: str) -> Optional[str]:
    """Check normalized text for global or IFRC regional keywords."""
    for kw in _GLOBAL_KEYWORDS:
        needle = f" {_norm_space_text(kw).strip()} "
        if needle in hay:
            return SCOPE_GLOBAL
    for kw in _IFRC_REGION_SCOPE_KEYWORDS:
        needle = f" {_norm_space_text(kw).strip()} "
        if needle in hay:
            return SCOPE_REGIONAL
    return None


def _matched_scope_keyword(hay: str) -> tuple[Optional[str], Optional[str]]:
    """Return (scope, keyword) for the first matched scope hint."""
    for kw in _GLOBAL_KEYWORDS:
        needle = f" {_norm_space_text(kw).strip()} "
        if needle in hay:
            return SCOPE_GLOBAL, kw
    for kw in _IFRC_REGION_SCOPE_KEYWORDS:
        needle = f" {_norm_space_text(kw).strip()} "
        if needle in hay:
            return SCOPE_REGIONAL, kw
    return None, None


def _hay_matches_ifrc_region_scope(hay: str) -> bool:
    """True when text mentions IFRC statutory regions (Africa, MENA, Asia Pacific, Americas, Europe, Central Asia, etc.)."""
    for kw in _IFRC_REGION_SCOPE_KEYWORDS:
        needle = f" {_norm_space_text(kw).strip()} "
        if needle in hay:
            return True
    return False


def _has_strong_global_signal(hay: str) -> bool:
    """Return True when text contains explicit global scope markers."""
    for kw in _STRONG_GLOBAL_KEYWORDS:
        needle = f" {_norm_space_text(kw).strip()} "
        if needle in hay:
            return True
    return False


def _find_all_countries_in(
    hay: str,
    candidates: list[tuple[int, str, list[str]]],
) -> list[tuple[int, str, int]]:
    """
    Find ALL countries mentioned in normalized text.

    Returns list of (country_id, country_name, score) sorted by score descending.
    """
    results: list[tuple[int, str, int]] = []
    for cid, cname, norms in candidates:
        score = 0
        for vn in norms[:3]:
            needle = f" {vn} "
            cnt = hay.count(needle)
            if cnt:
                score += cnt * max(1, len(vn))
        if score > 0:
            results.append((cid, cname, score))
    results.sort(key=lambda t: t[2], reverse=True)
    return results


def _filter_substring_country_hits(hay: str, countries: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """
    Filter out false-positive country hits where a shorter country name is only
    matched as part of a longer country name (e.g., "Sudan" within "South Sudan").

    Heuristic:
    - For each detected country name (using canonical `Country.name`), count how
      many times it appears as a whole phrase in `hay`.
    - If country B's phrase is contained within country A's phrase AND the counts
      are equal, treat B as an overlap-only match and drop it (keep the longer A).
    """
    if not hay or not countries or len(countries) < 2:
        return countries

    # Canonical phrase counts (boundary-safe via normalized text + padded spaces).
    norm = {}
    counts: dict[int, int] = {}
    for cid, cname in countries:
        nn = _norm_space_text(str(cname)).strip()
        norm[cid] = nn
        if nn:
            counts[cid] = hay.count(f" {nn} ")
        else:
            counts[cid] = 0

    remove: set[int] = set()
    ids = [cid for cid, _ in countries]
    for a in ids:
        na = norm.get(a) or ""
        ca = counts.get(a, 0) or 0
        if not na or ca <= 0:
            continue
        for b in ids:
            if a == b:
                continue
            nb = norm.get(b) or ""
            cb = counts.get(b, 0) or 0
            if not nb or cb <= 0:
                continue
            # Drop B if it only appears as part of A.
            if len(na) > len(nb) and f" {nb} " in f" {na} " and cb == ca:
                remove.add(b)

    if not remove:
        return countries
    return [(cid, cname) for (cid, cname) in countries if cid not in remove]


def _drop_countries_that_are_substrings(countries: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """
    Remove any country whose name is a proper substring of another country's name
    in the list (e.g. "Guinea" when "Papua New Guinea" is present, "Sudan" when
    "South Sudan" is present). Uses normalized names for comparison.
    """
    if not countries or len(countries) < 2:
        return countries
    norm_by_id: dict[int, str] = {}
    for cid, cname in countries:
        norm_by_id[cid] = _fold(_norm_space_text(str(cname)).strip())
    remove: set[int] = set()
    ids = [cid for cid, _ in countries]
    for aid in ids:
        na = norm_by_id.get(aid) or ""
        if not na:
            continue
        for bid in ids:
            if aid == bid:
                continue
            nb = norm_by_id.get(bid) or ""
            if not nb or len(na) <= len(nb):
                continue
            # If shorter name is a substring of longer, drop the shorter
            if nb in na:
                remove.add(bid)
    if not remove:
        return countries
    return [(cid, cname) for (cid, cname) in countries if cid not in remove]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_countries(
    *,
    filename: str | None,
    title: str | None,
    text: str | None,
    max_text_chars: int = 60000,
) -> CountryDetectionResult:
    """
    Detect countries and geographic scope for a document.

    Returns a ``CountryDetectionResult`` with all detected countries and scope.
    """
    candidates = _build_candidates()
    if not candidates:
        return CountryDetectionResult(countries=[], scope=None)

    detected_scope: Optional[str] = None
    scope_source: str | None = None

    logger.info(
        "country_detection:start filename=%r title=%r text_chars=%s candidates=%s",
        (filename or "")[:120],
        (title or "")[:120],
        len(str(text)) if text is not None else 0,
        len(candidates),
    )

    # 1) Collect filename/title countries for fallback/context
    title_filename_countries: list[tuple[int, str]] = []

    # 0) High-confidence: extract ISO2 from UPL code in title/filename
    upl_country = _detect_country_from_upl_code(title, filename)
    if upl_country:
        title_filename_countries.append(upl_country)

    for src in (filename, title):
        if src and str(src).strip():
            hay = _norm_space_text(str(src))
            hits = _find_all_countries_in(hay, candidates)
            # Convert to (id, name) and filter substring overlaps like "Sudan" in "South Sudan".
            src_countries = [(cid, cname) for cid, cname, _score in hits]
            src_countries = _filter_substring_country_hits(hay, src_countries)

            for cid, cname in src_countries:
                if not any(c[0] == cid for c in title_filename_countries):
                    title_filename_countries.append((cid, cname))

    logger.info(
        "country_detection:title_filename countries=%s",
        [name for _cid, name in title_filename_countries],
    )

    # 2) Content-based detection (preferred when available): find all countries with scoring
    content_countries: list[tuple[int, str]] = []
    if text and str(text).strip():
        snippet = str(text)[: max(0, int(max_text_chars or 0))]
        hay = _norm_space_text(snippet)

        # Content is the primary signal for scope when available.
        if not detected_scope:
            detected_scope, scope_kw = _matched_scope_keyword(hay)
            if detected_scope:
                scope_source = "content"
                logger.info("country_detection:scope_from_content scope=%r keyword=%r", detected_scope, scope_kw)

        hits = _find_all_countries_in(hay, candidates)
        if hits:
            # Use the top-scoring country's score as reference
            top_score = hits[0][2]
            # Include countries scoring at least 10% of the top score
            threshold = max(1, top_score * 0.10)
            for cid, cname, score in hits:
                if score >= threshold:
                    content_countries.append((cid, cname))
        logger.info(
            "country_detection:content hits=%s kept=%s threshold=%.2f",
            [(cname, score) for _cid, cname, score in hits[:15]],
            [name for _cid, name in content_countries],
            float(threshold) if hits else 0.0,
        )
    else:
        logger.info("country_detection:content unavailable_or_empty")

    # 3) If scope was not inferred from content, use title/filename scope hints as fallback.
    if not detected_scope:
        for src in (title, filename):
            if src and str(src).strip():
                scope_hit, scope_kw = _matched_scope_keyword(_norm_space_text(str(src)))
                if scope_hit:
                    detected_scope = scope_hit
                    scope_source = "title_or_filename"
                    logger.info(
                        "country_detection:scope_from_title_filename scope=%r keyword=%r source_text=%r",
                        detected_scope,
                        scope_kw,
                        str(src)[:120],
                    )
                    break

    # 4) Merge countries.
    # Prefer content ordering when content yields matches; otherwise fall back to title/filename.
    if content_countries:
        all_countries: list[tuple[int, str]] = list(content_countries)
        for cid, cname in title_filename_countries:
            if not any(c[0] == cid for c in all_countries):
                all_countries.append((cid, cname))
    else:
        all_countries = list(title_filename_countries)

    # Final guard (filename/title-only fallback path): if filename/title clearly
    # contains a longer country name that subsumes a shorter one (e.g., "South Sudan"
    # vs "Sudan"), drop the overlap-only shorter country.
    #
    # We intentionally do not apply this when content produced matches, because that can
    # hide genuine multi-country coverage present in the document body.
    try:
        tf_hay = _norm_space_text(f"{filename or ''} {title or ''}")
        if tf_hay.strip() and len(all_countries) >= 2 and not content_countries:
            all_countries = _filter_substring_country_hits(tf_hay, all_countries)
    except Exception as e:
        logger.debug("ai_country_detection: _filter_substring_country_hits failed: %s", e)

    # Drop any country whose name is a proper substring of another (e.g. Guinea vs Papua New Guinea)
    if len(all_countries) >= 2:
        all_countries = _drop_countries_that_are_substrings(all_countries)

    # Many countries: IFRC "regional" only when the text signals an IFRC region (Africa, MENA,
    # Asia Pacific, Americas, Europe, Central Asia, …). Otherwise use "cluster" (multi-NS / ad hoc
    # country sets), not generic "regional".
    if len(all_countries) >= _MULTI_COUNTRY_THRESHOLD:
        combined_hay = _norm_space_text(f"{title or ''} {filename or ''} {(text or '')[: max(0, int(max_text_chars or 0))]}")
        ifrc_region = _hay_matches_ifrc_region_scope(combined_hay)
        target_scope = SCOPE_REGIONAL if ifrc_region else SCOPE_CLUSTER
        if detected_scope == SCOPE_GLOBAL and not _has_strong_global_signal(combined_hay):
            logger.info(
                "country_detection:multi_country_override from=%r to=%r countries=%s ifrc_region=%s",
                detected_scope,
                target_scope,
                [name for _cid, name in all_countries],
                ifrc_region,
            )
            detected_scope = target_scope
            scope_source = "multi_country_override"
        elif not detected_scope:
            detected_scope = target_scope
            scope_source = "multi_country_default_ifrc" if ifrc_region else "multi_country_default_cluster"

    logger.info(
        "country_detection:final primary=%r countries=%s scope=%r scope_source=%r",
        (all_countries[0][1] if all_countries else None),
        [name for _cid, name in all_countries],
        detected_scope,
        scope_source,
    )

    return CountryDetectionResult(
        countries=all_countries,
        scope=detected_scope,
    )


def detect_country_id_and_name(
    *,
    filename: str | None,
    title: str | None,
    text: str | None,
    max_text_chars: int = 60000,
) -> tuple[int | None, str | None]:
    """
    Legacy single-country detection (backward compatible).

    Returns the primary (highest-scoring) country as ``(country_id, country_name)``.
    """
    result = detect_countries(
        filename=filename,
        title=title,
        text=text,
        max_text_chars=max_text_chars,
    )
    return result.primary_country_id, result.primary_country_name
