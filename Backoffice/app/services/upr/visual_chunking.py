"""
UPR (Unified Planning and Reporting) visual chunking.

UPR is an annual process. For each year (UPR started in 2023 and continues through 2026+),
most countries publish a small set of external-facing PDF documents:
- Plan
- Midyear report (MYR)
- Annual report

Across years and countries, the visuals (infographics / panels) change slightly in layout,
but they represent largely the same underlying data. These visuals are expected on pages 1–5.

Why this exists:
- Standard PDF "chunking" (text/OCR/table heuristics) often fails on infographic-heavy pages
  where figures are embedded in shapes, icons, and mixed table-like layouts.
- To support reliable retrieval/QA, we extract UPR visuals into **structured JSON metadata**
  (attached to chunks as `metadata["upr"]`) and a clean embedding-friendly text rendering.

Design goal:
- Organize extraction around **visual type** and **year/doc-type** variants.
- Keep parsing robust to within-year, within-doc-type country differences
  (e.g. a Funding Requirements panel may show one year for one country, and 3 years for another).

Funding requirements visual (version: plans 2025 / multi-year) is supported in two layouts:
- Current Planning: "IFRC network Funding Requirements" panel with year totals and breakdowns.
- Full-page multi-column (plans 2025): Entire page titled "Funding requirements" with year columns
  (e.g. 2025 | 2026 | 2027), each with Total, funding sources (Through Host NS, PNS, IFRC), and
  IFRC Breakdown (Ongoing emergency operations, Longer term needs).

Older country-plan pages may also include:
- Hazards: a "Hazards" section listing hazard types (e.g. Conflict, Earthquakes, Displacement,
  Wildfires, Heatwaves), often with icons.
- Participating National Societies bilateral support: table "Participating National Societies
  bilateral support for YYYY" with NS names, funding requirement per NS, and Total Funding
  requirement CHF; on the same page as the Participating National Societies list (bilateral/multilateral).

These variants are visually similar but can differ slightly (e.g., KPI card ordering), so extraction
must be robust to those differences.

Start with the "IN SUPPORT OF THE <...> SOCIETY" KPI header cards (4 indicators):
- National Society branches
- National Society local units
- National Society volunteers
- National Society staff

Goal:
- Create a deterministic, structured representation (metadata) similar to table chunks
- Provide a clean text representation for embeddings/retrieval

Note: Other UPR document types may require separate extraction logic.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Callable

logger = logging.getLogger(__name__)


_NUM_RE = re.compile(r"\b\d[\d,]*(?:\.\d+)?[mkMK]?\b")
_IN_SUPPORT_RE = re.compile(r"\bIN\s+SUPPORT\s+OF\s+THE\s+(.+?)\s*$", re.IGNORECASE)
_PEOPLE_REACHED_HEADER_RE = re.compile(
    r"^\s*PEOPLE\s+(?:TO\s+BE\s+)?REACHED(?:\s+(?:IN\s+)?\d{4})?\s*$",
    re.IGNORECASE,
)
_FIN_OVERVIEW_RE = re.compile(r"^\s*FINANCIAL\s+OVERVIEW\s*$", re.IGNORECASE)
_FUNDING_REQUIREMENTS_RE = re.compile(r"\bfunding\s+requirements?\b", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(20\d{2})\b")
_PARTICIPATING_NS_RE = re.compile(r"^\s*participating\s+national\s+societies\s*$", re.IGNORECASE)
_HAZARDS_HEADER_RE = re.compile(r"^\s*hazards\s*$", re.IGNORECASE)
_PNS_BILATERAL_SUPPORT_RE = re.compile(
    r"participating\s+national\s+societies\s+bilateral\s+support\s+for\s+(\d{4})",
    re.IGNORECASE,
)
_TOTAL_FUNDING_REQUIREMENT_RE = re.compile(
    r"total\s+funding\s+requirement\s+(?:chf\s+)?([\d.,]+[mMK]?)",
    re.IGNORECASE,
)


# UPR context helpers
_UPR_YEARS = set(range(2023, 2031))  # keep permissive for future years


@dataclass(frozen=True)
class UPRDocumentContext:
    """
    Best-effort context inferred from document title/filename/pages.

    This is attached to each extracted UPR visual block as `block["upr_context"]` so downstream
    QA logic can interpret ambiguous visuals (e.g. which year a multi-year panel is about).
    """

    # Document year as encoded in filename/title (e.g. "INP_2024").
    # IMPORTANT: For Plans this is typically the *start year* of a multi-year plan horizon.
    document_year: Optional[int]
    doc_type: str  # "plan" | "midyear_report" | "annual_report" | "unknown"
    # Years mentioned in the first pages' extracted text (useful for multi-year visuals like Funding Requirements).
    covered_years: Optional[list[int]]
    # For plans, default planning horizon is typically 3 years: start_year..start_year+2.
    planning_horizon_years: Optional[list[int]]


def _norm_key(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def infer_upr_document_context(
    *,
    title: Optional[str] = None,
    filename: Optional[str] = None,
    pages: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Infer UPR context (year, doc_type) from title/filename and the first pages' OCR text.

    This is intentionally best-effort and non-fatal: UPR visuals can be parsed without it,
    but context improves downstream QA and helps choose defaults (e.g. most recent year).
    """

    text_hint = ""
    try:
        first_pages = _first_upr_pages(pages, max_pages=5)
        text_hint = "\n".join([str((p or {}).get("text") or "") for p in first_pages])[:8000]
    except Exception as e:
        logger.debug("is_likely_upr_document text_hint extraction failed: %s", e)
        text_hint = ""

    t = " ".join([(title or ""), (filename or ""), (text_hint or "")]).strip()
    low = t.lower()
    qk = _norm_key(t)

    # Doc type (prefer explicit phrases; keep permissive aliases)
    doc_type = "unknown"
    if "midyear" in qk or "mid-year" in low or "myr" in qk or "mid year" in low:
        doc_type = "midyear_report"
    elif "annualreport" in qk or ("annual" in low and "report" in low):
        doc_type = "annual_report"
    elif "planning" in low or "plan" in low or "network plan" in low:
        doc_type = "plan"

    # Year: Prefer filename/title (usually stable), then fall back to OCR text.
    doc_year: Optional[int] = None

    def _years_from(s: str | None) -> list[int]:
        if not s:
            return []
        ys = []
        # Use digit boundaries (not word boundaries) so filenames like "INP_2023_Foo.pdf"
        # are correctly parsed (underscore counts as a "word" char, so \b fails there).
        for y in re.findall(r"(?<!\d)(20\d{2})(?!\d)", s):
            try:
                yy = int(y)
            except Exception as e:
                logger.debug("Year parse failed: %s", e)
                continue
            if yy in _UPR_YEARS:
                ys.append(yy)
        return ys

    years_filename = _years_from(filename or "")
    years_title = _years_from(title or "")
    years_text = _years_from(text_hint or "")
    # Most reliable: explicit year token in filename
    if years_filename:
        doc_year = max(years_filename)
    elif years_title:
        doc_year = max(years_title)
    elif years_text:
        # Least reliable: OCR text can mention multiple years (e.g. multi-year funding),
        # so prefer the most recent year only as a fallback for document year.
        doc_year = max(years_text)

    covered_years: Optional[list[int]] = None
    try:
        if years_text:
            covered_years = sorted(set(years_text))
    except Exception as e:
        logger.debug("covered_years extraction failed: %s", e)
        covered_years = None

    planning_horizon_years: Optional[list[int]] = None
    try:
        # UPR Plans are often multi-year (e.g. "2024 plan" covering 2024, 2025, 2026).
        if doc_type == "plan" and isinstance(doc_year, int):
            planning_horizon_years = [int(doc_year), int(doc_year) + 1, int(doc_year) + 2]
    except Exception as e:
        logger.debug("planning_horizon_years extraction failed: %s", e)
        planning_horizon_years = None

    ctx = UPRDocumentContext(
        document_year=doc_year,
        doc_type=doc_type,
        covered_years=covered_years,
        planning_horizon_years=planning_horizon_years,
    )
    # Keep backward compatibility: `year` == `document_year` for downstream code.
    return {
        "document_year": ctx.document_year,
        "year": ctx.document_year,
        "doc_type": ctx.doc_type,
        "covered_years": ctx.covered_years,
        "planning_horizon_years": ctx.planning_horizon_years,
    }


def _upr_visual_extractors_for_context(ctx: Dict[str, Any]) -> List[Callable[[Optional[List[Dict[str, Any]]]], List[Dict[str, Any]]]]:
    """
    Choose which visual-type extractors to run based on inferred UPR context.

    This is where year/doc-type-specific chunking differences should be encoded.
    For now the pipeline is shared across 2023–2026, with extractors internally handling
    known layout variants (e.g. Funding Requirements full-page vs panel).
    """
    _year = ctx.get("year") if isinstance(ctx, dict) else None
    _doc_type = ctx.get("doc_type") if isinstance(ctx, dict) else None
    # Keep the pipeline explicit and ordered by typical appearance on pages 1–5.
    pipeline = [
        extract_in_support_kpis,
        extract_people_reached,
        extract_financial_overview,
        extract_funding_requirements,
        extract_hazards,
        extract_pns_bilateral_support,
    ]
    # Example hook for future: year- or doc-type-specific tweaks
    if _year and int(_year) >= 2025 and _doc_type == "plan":
        return pipeline
    return pipeline

# IMPORTANT: In UPR documents, these visuals are expected to appear in the first 1–3 pages.
# Keeping extraction scoped to the first pages reduces false positives and speeds up chunking.
_UPR_VISUAL_MAX_PAGES = 3
# Funding requirements can appear as a full-page visual (older UPR layout) on a dedicated page,
# so we search one more page when looking for that block.
_FUNDING_REQUIREMENTS_MAX_PAGES = 5


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()

def _first_upr_pages(pages: Optional[List[Dict[str, Any]]], *, max_pages: int = _UPR_VISUAL_MAX_PAGES) -> List[Dict[str, Any]]:
    """
    Return the first N pages (best-effort).
    Prefer ordering by `page_number` when present; otherwise keep input order.
    """
    if not pages:
        return []
    safe: List[Dict[str, Any]] = [p for p in pages if isinstance(p, dict)]
    if not safe:
        return []

    with_numbers: List[tuple[int, Dict[str, Any]]] = []
    without_numbers: List[Dict[str, Any]] = []
    for p in safe:
        pn = p.get("page_number")
        if isinstance(pn, int):
            with_numbers.append((pn, p))
        else:
            without_numbers.append(p)

    if with_numbers:
        with_numbers.sort(key=lambda t: t[0])
        ordered = [p for _pn, p in with_numbers] + without_numbers
        return ordered[:max_pages]
    return safe[:max_pages]


def is_likely_upr_document(*, title: Optional[str], filename: Optional[str], pages: Optional[List[Dict[str, Any]]]) -> bool:
    """
    Best-effort detector for UPR documents (including MYR and Planning).
    We keep it permissive: if it contains the UPR visual markers, treat it as UPR-like.
    """
    t = (title or "") + " " + (filename or "")
    t_low = t.lower()
    if (
        "upr" in t_low
        or "unified planning" in t_low
        or "network mid-year report" in t_low
        or "upr planning" in t_low
        or "network plan" in t_low
    ):
        return True
    # Fallback: look for UPR-specific visuals in the first few pages.
    #
    # Important: Some older UPR country-plan PDFs do not include the "IN SUPPORT OF ..." KPI block
    # (or it is not captured by OCR), but they still contain a very distinctive full-page
    # "Funding requirements" visual with year columns and "IFRC Breakdown".
    for p in (pages or [])[:5]:
        txt = (p or {}).get("text") or ""
        if not isinstance(txt, str) or not txt.strip():
            continue
        low = txt.lower()
        if "in support of" in low and "national society" in low:
            return True
        if _is_fullpage_funding_requirements_layout(txt):
            return True
        # Additional strong marker for the same visual when OCR is noisy:
        if _FUNDING_REQUIREMENTS_RE.search(txt) and "ifrc" in low and "breakdown" in low:
            return True
    return False


def extract_in_support_kpis(pages: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """
    Extract UPR (MYR/Planning) "IN SUPPORT OF ..." KPI cards as structured blocks.

    Returns a list of blocks like:
    {
      "block": "in_support_kpis",
      "page_number": 3,
      "society": "Afghan Red Crescent Society",
      "kpis": {"branches": "34", "local_units": "329", "volunteers": "26,000", "staff": "4,000"},
      "extraction": "fixed_4col_v1",
      "confidence": 0.9,
      "debug": {...}
    }
    """
    out: List[Dict[str, Any]] = []

    # Mapping of UPR "IN SUPPORT OF" KPI card keys to Indicator Bank IDs.
    # Keep this stable so downstream services can link extracted KPI values
    # to indicator definitions in the Indicator Bank.
    kpi_indicator_bank_ids: Dict[str, int] = {
        "volunteers": 724,
        "staff": 727,
        "branches": 1117,
        "local_units": 723,
    }

    def _cfg(name: str, default: Any) -> Any:
        """
        Best-effort access to Flask config (when running inside app context).
        Keep extraction deterministic even when Flask is not available.
        """
        try:
            from flask import current_app  # type: ignore

            return current_app.config.get(name, default)
        except Exception as e:
            logger.debug("_config_int failed for %s: %s", name, e)
            return default

    def _is_year_token(s: str) -> bool:
        try:
            return bool(re.fullmatch(r"(?:19|20)\d{2}", (s or "").strip()))
        except Exception as e:
            logger.debug("_is_year_token failed: %s", e)
            return False

    def _extract_num_tokens_from_line(ln: str) -> List[str]:
        """
        Extract numeric tokens from a line, excluding likely years.
        """
        vals: List[str] = []
        for m in _NUM_RE.finditer(ln or ""):
            v = (m.group(0) or "").strip()
            if not v:
                continue
            if _is_year_token(v):
                continue
            vals.append(v)
        return vals

    def _contains_any_kpi_keyword(low_ln: str) -> bool:
        if not low_ln:
            return False
        # Keep this strict: avoid enqueueing numbers from label lines.
        if "branches" in low_ln or "volunteers" in low_ln or "staff" in low_ln:
            return True
        # local units may be split; treat either token as keyword-ish here
        if "local units" in low_ln or ("local" in low_ln and "units" in low_ln):
            return True
        return False

    def _label_order_in_window(window_lines_low: List[str]) -> List[str]:
        """
        Determine KPI label order as it appears in the OCR window.
        This is used to map a 4-number KPI row to labels without relying on fragile proximity.
        """
        order: List[str] = []
        for i, low_ln in enumerate(window_lines_low):
            if "branches" in low_ln and "branches" not in order:
                order.append("branches")
            # local_units: allow split across adjacent lines
            if "local_units" not in order:
                if "local units" in low_ln:
                    order.append("local_units")
                elif "local" in low_ln:
                    if i + 1 < len(window_lines_low) and "units" in window_lines_low[i + 1]:
                        order.append("local_units")
                    elif i - 1 >= 0 and "units" in window_lines_low[i - 1]:
                        order.append("local_units")
            if "staff" in low_ln and "staff" not in order:
                order.append("staff")
            if "volunteers" in low_ln and "volunteers" not in order:
                order.append("volunteers")
            if len(order) == 4:
                break
        return order

    def _choose_best_4_number_cluster(
        tokens: List[Dict[str, Any]],
        *,
        label_min_idx: int,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Choose the most likely KPI 4-number sequence from a list of numeric tokens.

        We expect the KPI numbers to appear in a tight cluster right above the labels.
        If OCR includes other numbers (e.g., years), we pick the 4-token window with:
        - minimal vertical spread (line span)
        - closest to label_min_idx (prefer clusters near labels)
        """
        if len(tokens) < 4:
            return None
        best: Optional[tuple[tuple[int, int, int], List[Dict[str, Any]]]] = None
        for start in range(0, len(tokens) - 3):
            window = tokens[start : start + 4]
            line_idxs = [int(t.get("line_idx") or 0) for t in window]
            line_span = (max(line_idxs) - min(line_idxs)) if line_idxs else 999
            # Prefer clusters that end close to the first label line (numbers are typically just above).
            end_distance = abs(int(label_min_idx) - max(line_idxs)) if line_idxs else 999
            # Mild penalty for obviously "page-like" contexts
            page_penalty = 0
            try:
                if any("page" in str(t.get("line") or "").lower() for t in window):
                    page_penalty = 2
            except Exception as e:
                logger.debug("page_penalty check failed: %s", e)
                page_penalty = 0
            score = (int(line_span), int(end_distance), int(page_penalty))
            if best is None or score < best[0]:
                best = (score, window)
        return best[1] if best else None

    def _extract_in_support_kpis_layout_v1(
        *,
        page: Dict[str, Any],
        page_number: Optional[int],
        society_hint: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """
        Option 3 (layout-based): Use word bounding boxes to map KPI numbers to labels by column geometry.
        Requires `page["words"]` as a list of {x0,y0,x1,y1,text}.
        """
        try:
            words = page.get("words")
            if not isinstance(words, list) or not words:
                return None

            w = float(page.get("page_width") or 0.0) or None
            h = float(page.get("page_height") or 0.0) or None
            if not w or not h:
                return None

            def norm(s: str) -> str:
                return re.sub(r"\s+", " ", (s or "")).strip()

            def center_x(wd: Dict[str, Any]) -> float:
                return (float(wd["x0"]) + float(wd["x1"])) / 2.0

            def center_y(wd: Dict[str, Any]) -> float:
                return (float(wd["y0"]) + float(wd["y1"])) / 2.0

            # Filter to sane words
            toks: List[Dict[str, Any]] = []
            for wd in words:
                if not isinstance(wd, dict):
                    continue
                t = (wd.get("text") or "").strip()
                if not t:
                    continue
                try:
                    toks.append(
                        {
                            "x0": float(wd["x0"]),
                            "y0": float(wd["y0"]),
                            "x1": float(wd["x1"]),
                            "y1": float(wd["y1"]),
                            "text": t,
                        }
                    )
                except Exception as e:
                    logger.debug("Token extraction failed: %s", e)
                    continue
            if not toks:
                return None

            toks.sort(key=lambda d: (float(d["y0"]), float(d["x0"])))

            # Cluster words into lines by y-center (tolerant to minor OCR jitter)
            y_tol = max(2.5, float(h) * 0.0035)
            lines: List[Dict[str, Any]] = []
            cur: List[Dict[str, Any]] = []
            cur_y: Optional[float] = None
            for wd in toks:
                yc = center_y(wd)
                if cur_y is None:
                    cur = [wd]
                    cur_y = yc
                    continue
                if abs(yc - cur_y) <= y_tol:
                    cur.append(wd)
                    # keep average y for stability
                    cur_y = (cur_y * 0.8) + (yc * 0.2)
                else:
                    cur.sort(key=lambda d: float(d["x0"]))
                    txt = norm(" ".join([x["text"] for x in cur]))
                    lines.append(
                        {
                            "y0": min(float(x["y0"]) for x in cur),
                            "y1": max(float(x["y1"]) for x in cur),
                            "words": cur,
                            "text": txt,
                            "text_low": txt.lower(),
                        }
                    )
                    cur = [wd]
                    cur_y = yc
            if cur:
                cur.sort(key=lambda d: float(d["x0"]))
                txt = norm(" ".join([x["text"] for x in cur]))
                lines.append(
                    {
                        "y0": min(float(x["y0"]) for x in cur),
                        "y1": max(float(x["y1"]) for x in cur),
                        "words": cur,
                        "text": txt,
                        "text_low": txt.lower(),
                    }
                )

            # Find header line and an upper boundary
            header_idx = None
            for i, ln in enumerate(lines[:40]):  # header is near top
                if "in support of" in (ln.get("text_low") or ""):
                    header_idx = i
                    break
            if header_idx is None:
                return None

            header_line = lines[header_idx].get("text") or ""
            society = society_hint
            m = _IN_SUPPORT_RE.search(header_line)
            if m:
                society = _norm_ws(m.group(1))
            else:
                # Sometimes OCR splits the society name; search next couple lines
                for j in range(header_idx, min(len(lines), header_idx + 3)):
                    mm = _IN_SUPPORT_RE.search(lines[j].get("text") or "")
                    if mm:
                        society = _norm_ws(mm.group(1))
                        break

            header_y1 = float(lines[header_idx].get("y1") or 0.0)

            # Stop at PEOPLE REACHED if present (avoid collecting numbers from other visuals)
            stop_y0 = None
            for i in range(header_idx + 1, min(len(lines), header_idx + 120)):
                if "people reached" in (lines[i].get("text_low") or ""):
                    stop_y0 = float(lines[i].get("y0") or 0.0)
                    break
            if stop_y0 is None:
                stop_y0 = header_y1 + (float(h) * 0.42)

            # Find label word positions (use word-level hit to get x-center)
            def find_label_x(key: str) -> Optional[Dict[str, Any]]:
                # Search within the KPI region only
                for ln in lines[header_idx + 1 :]:
                    y0 = float(ln.get("y0") or 0.0)
                    if y0 < header_y1:
                        continue
                    if y0 > float(stop_y0):
                        break
                    ws = ln.get("words") or []
                    if not isinstance(ws, list) or not ws:
                        continue
                    low = (ln.get("text_low") or "")
                    if key == "branches" and "branches" in low:
                        for wd in ws:
                            if "branches" in (wd.get("text") or "").lower():
                                return wd
                    if key == "staff" and "staff" in low:
                        for wd in ws:
                            if "staff" in (wd.get("text") or "").lower():
                                return wd
                    if key == "volunteers" and "volunteers" in low:
                        for wd in ws:
                            if "volunteers" in (wd.get("text") or "").lower():
                                return wd
                    if key == "local_units":
                        # local + units may be separate words
                        if "local units" in low or ("local" in low and "units" in low):
                            for wd in ws:
                                if (wd.get("text") or "").lower() == "local":
                                    return wd
                            # fallback: any word containing "local"
                            for wd in ws:
                                if "local" in (wd.get("text") or "").lower():
                                    return wd
                return None

            label_words = {
                "branches": find_label_x("branches"),
                "local_units": find_label_x("local_units"),
                "staff": find_label_x("staff"),
                "volunteers": find_label_x("volunteers"),
            }
            if not all(label_words.values()):
                return None

            label_xs = [center_x(wd) for wd in label_words.values() if wd]
            label_xs_sorted = sorted(label_xs)
            gaps = [label_xs_sorted[i + 1] - label_xs_sorted[i] for i in range(len(label_xs_sorted) - 1)]
            gap = sorted(gaps)[len(gaps) // 2] if gaps else (w * 0.25)
            x_tol = max(18.0, min(float(w) * 0.18, float(gap) * 0.55))

            # Candidate number words in the KPI region
            num_words: List[Dict[str, Any]] = []
            for wd in toks:
                if float(wd["y0"]) < header_y1 or float(wd["y0"]) > float(stop_y0):
                    continue
                t = (wd.get("text") or "").strip()
                if not t:
                    continue
                if _is_year_token(t):
                    continue
                if not _NUM_RE.fullmatch(t):
                    continue
                num_words.append(wd)

            if not num_words:
                return None

            def pick_number_for_label(label_key: str) -> Optional[str]:
                wd = label_words.get(label_key)
                if not wd:
                    return None
                lx = center_x(wd)
                ly0 = float(wd["y0"])
                best: Optional[tuple[float, float, str]] = None
                for nw in num_words:
                    ny1 = float(nw["y1"])
                    # must be above the label word line (numbers are above)
                    if ny1 > ly0 + 1.5:
                        continue
                    dx = abs(center_x(nw) - lx)
                    if dx > x_tol:
                        continue
                    dy = max(0.0, ly0 - ny1)
                    height = float(nw["y1"]) - float(nw["y0"])
                    v = (nw.get("text") or "").strip()
                    if not v:
                        continue
                    score = (dy, -height, v)
                    if best is None or score < best:
                        best = score
                return best[2] if best else None

            kpis = {
                "branches": pick_number_for_label("branches"),
                "local_units": pick_number_for_label("local_units"),
                "staff": pick_number_for_label("staff"),
                "volunteers": pick_number_for_label("volunteers"),
            }
            if not all(kpis.values()):
                return None

            # Ensure uniqueness (avoid mapping same number twice)
            if len(set(str(v) for v in kpis.values() if v)) < 4:
                return None

            return {
                "template": "UPR",
                "block": "in_support_kpis",
                "page_number": int(page_number) if isinstance(page_number, int) else None,
                "society": society,
                "kpis": {k: str(v) for k, v in kpis.items() if v},
                "kpi_indicator_bank_ids": dict(kpi_indicator_bank_ids),
                "extraction": "layout_words_v1",
                "confidence": 0.97,
                "debug": {
                    "x_tol": x_tol,
                    "header_line": header_line[:250],
                    "upr_kpi_stop_y0": stop_y0,
                },
            }
        except Exception as e:
            logger.debug("_extract_financial_overview_block failed: %s", e)
            return None

    def _extract_in_support_kpis_vision_openai_v1(
        *,
        page: Dict[str, Any],
        page_number: Optional[int],
        society_hint: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """
        Option 4 (vision-based): Use a vision-capable model on a cropped top-of-page image.
        Requires `page["upr_kpi_clip_png_b64"]`.
        """
        try:
            enabled = bool(_cfg("AI_UPR_VISION_KPI_ENABLED", False))
            if not enabled:
                return None
            if not _cfg("OPENAI_API_KEY", None):
                return None

            b64 = page.get("upr_kpi_clip_png_b64")
            if not isinstance(b64, str) or not b64.strip():
                return None

            model_name = str(_cfg("AI_UPR_VISION_MODEL", "gpt-4o-mini"))

            prompt = (
                "Context: This is an IFRC UPR (Unified Planning and Reporting) PDF (Plan / Midyear report / Annual report).\n"
                "UPR visuals are infographic-like and layouts can vary slightly by year and country.\n"
                "Task: Extract the KPI values from the header visual.\n\n"
                "Read the 'IN SUPPORT OF THE <SOCIETY>' KPI cards (4 cards) and return ONLY a JSON object:\n"
                "{\n"
                '  "society": string|null,\n'
                '  "branches": string,\n'
                '  "local_units": string,\n'
                '  "staff": string,\n'
                '  "volunteers": string\n'
                "}\n\n"
                "Rules:\n"
                "- Use the numbers exactly as shown (keep commas).\n"
                "- branches/local_units/staff/volunteers must be the KPI values.\n"
                "- society should be the name shown after 'IN SUPPORT OF THE' (no extra words).\n"
                "- Return ONLY valid JSON. No markdown.\n"
            )
            if society_hint:
                prompt += f"\nHint: The society may be '{society_hint}'.\n"

            def _extract_json(text: str) -> Optional[Dict[str, Any]]:
                if not text:
                    return None
                s = text.strip()
                start = s.find("{")
                end = s.rfind("}")
                if start < 0 or end < 0 or end <= start:
                    return None
                blob = s[start : end + 1]
                try:
                    import json

                    obj = json.loads(blob)
                    return obj if isinstance(obj, dict) else None
                except Exception as e:
                    logger.debug("JSON parse of clip blob failed: %s", e)
                    return None

            from openai import OpenAI  # type: ignore
            import os

            openai_key = _cfg("OPENAI_API_KEY", None) or os.getenv("OPENAI_API_KEY")
            client = OpenAI(api_key=openai_key)

            data_url = f"data:image/png;base64,{b64}"
            resp = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": "Return ONLY valid JSON."},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    },
                ],
                max_completion_tokens=400,
            )
            msg = resp.choices[0].message if (resp and resp.choices) else None
            raw = (getattr(msg, "content", None) or "").strip() if msg else ""
            obj = _extract_json(raw) or {}

            branches = (obj.get("branches") or "").strip()
            local_units = (obj.get("local_units") or "").strip()
            staff = (obj.get("staff") or "").strip()
            volunteers = (obj.get("volunteers") or "").strip()
            society = (obj.get("society") or "").strip() if isinstance(obj.get("society"), str) else (society_hint or None)

            if not (branches and local_units and staff and volunteers):
                return None

            # Basic sanity: must contain at least one digit each
            if not all(re.search(r"\d", v or "") for v in (branches, local_units, staff, volunteers)):
                return None

            return {
                "template": "UPR",
                "block": "in_support_kpis",
                "page_number": int(page_number) if isinstance(page_number, int) else None,
                "society": society,
                "kpis": {
                    "branches": branches,
                    "local_units": local_units,
                    "staff": staff,
                    "volunteers": volunteers,
                },
                "kpi_indicator_bank_ids": dict(kpi_indicator_bank_ids),
                "extraction": "vision_openai_v1",
                "confidence": 0.92,
                "debug": {"model": model_name, "clip_box": page.get("upr_kpi_clip_box")},
            }
        except Exception as e:
            logger.debug("_extract_in_support_kpis_vision_openai_v1 failed: %s", e)
            return None

    def _has_local_units_marker(text_low: str) -> bool:
        # Handle OCR splitting "local units" across lines.
        return ("local units" in text_low) or ("local" in text_low and "units" in text_low)

    def _find_first_label_idx(window_lines_low: List[str], *, key: str) -> Optional[int]:
        """
        Find the first line index that matches a KPI label marker.
        We match the keyword itself and allow for common OCR splits.
        """
        if key == "local_units":
            for i, low_ln in enumerate(window_lines_low):
                if "local units" in low_ln:
                    return i
                if "local" in low_ln:
                    if i + 1 < len(window_lines_low) and "units" in window_lines_low[i + 1]:
                        return i
                    if i - 1 >= 0 and "units" in window_lines_low[i - 1]:
                        return i - 1
            return None

        keyword = {"branches": "branches", "volunteers": "volunteers", "staff": "staff"}.get(key, key)
        for i, low_ln in enumerate(window_lines_low):
            if keyword in low_ln:
                return i
        return None

    def _nearest_number(
        window_lines: List[str],
        *,
        around_idx: int,
        radius: int = 7,
        exclude_values: Optional[set[str]] = None,
    ) -> Optional[str]:
        """
        Find the nearest numeric token to a given line index.
        Prefer values above labels (numbers often appear above card labels).
        If exclude_values is set, skip those values so the same number is not
        assigned to multiple labels when all four KPIs are on one line.
        """
        if around_idx < 0 or around_idx >= len(window_lines):
            return None
        exclude = exclude_values or set()

        candidates: List[tuple[int, int, int, str]] = []
        start = max(0, around_idx - radius)
        # IMPORTANT: For this visual, KPI values are above their labels.
        # Scanning below the label is a common source of swapped values (e.g. branches picking the next card's number).
        for j in range(around_idx, start - 1, -1):
            ln = window_lines[j]
            for pos, m in enumerate(_NUM_RE.finditer(ln)):
                num = m.group(0).strip()
                if _is_year_token(num):
                    continue
                if num in exclude:
                    continue
                dist = abs(j - around_idx)
                # Break ties by position on line (left-to-right)
                candidates.append((dist, j, pos, num))

        if not candidates:
            return None
        candidates.sort(key=lambda t: (t[0], t[1], t[2]))
        return candidates[0][3]

    for p in _first_upr_pages(pages):
        if not isinstance(p, dict):
            continue
        page_number = p.get("page_number")
        text = (p.get("text") or "")
        words = p.get("words") if isinstance(p.get("words"), list) else None

        # Some infographic-heavy plan PDFs can yield near-empty OCR text on page 1.
        # If we have word-level layout data, we can still attempt deterministic extraction.
        low = (text or "").lower()
        # OCR varies across years/countries; some PDFs don't include "National Society" in the extracted text.
        # The "IN SUPPORT OF ..." header is the strongest marker here.
        has_text_marker = ("in support of" in low)
        if (not has_text_marker) and (not words):
            continue

        lines = [ln.rstrip("\n") for ln in text.splitlines()]
        # Narrow search window: between "IN SUPPORT..." and "PEOPLE REACHED" when present.
        start_i = 0
        end_i = len(lines)
        for i, ln in enumerate(lines):
            if "in support of" in ln.lower():
                start_i = i
                break
        # If OCR doesn't contain the marker but we do have layout words, keep a small synthetic window.
        if not has_text_marker and words:
            start_i = 0
            end_i = min(len(lines), 80) if lines else 0
        for i in range(start_i, len(lines)):
            if "people reached" in lines[i].lower():
                end_i = i
                break

        window_lines = lines[start_i:end_i]
        window_text = "\n".join(window_lines)
        window_text_low = window_text.lower()
        window_lines_low = [ln.lower() for ln in window_lines]

        # Extract society name
        society = None
        for ln in window_lines[:6]:
            m = _IN_SUPPORT_RE.search(ln)
            if m:
                society = _norm_ws(m.group(1))
                break

        # Guardrail to reduce false-positives:
        # - If we have OCR text, require all 4 labels in the window.
        # - If OCR is weak but we have `words`, allow the layout-words extractor to decide.
        if window_text_low.strip() and not words:
            if not (
                "branches" in window_text_low
                and _has_local_units_marker(window_text_low)
                and "volunteers" in window_text_low
                and "staff" in window_text_low
            ):
                continue

        # Option 4: vision-based extraction (off by default).
        # If enabled and a cropped render is provided, prefer this.
        vision_enabled = bool(_cfg("AI_UPR_VISION_KPI_ENABLED", False))
        if vision_enabled and isinstance(p.get("upr_kpi_clip_png_b64"), str):
            block_v = _extract_in_support_kpis_vision_openai_v1(
                page=p,
                page_number=int(page_number) if isinstance(page_number, int) else None,
                society_hint=society,
            )
            if block_v:
                out.append(block_v)
                continue

        # Option 3: layout-based extraction using word bboxes (off by default).
        layout_enabled = bool(_cfg("AI_UPR_LAYOUT_KPI_ENABLED", False))
        if layout_enabled and isinstance(p.get("words"), list):
            block_l = _extract_in_support_kpis_layout_v1(
                page=p,
                page_number=int(page_number) if isinstance(page_number, int) else None,
                society_hint=society,
            )
            if block_l:
                out.append(block_l)
                continue

        # v3 (preferred): robust mapping scoped to the KPI block.
        # Strategy:
        # - v3a: parse repeated "card" pattern: <number> -> "National Society" -> <label>
        # - v3b: fallback to a 4-number cluster (when OCR linearizes numbers into one row)
        # Both approaches avoid the fragile "closest number within N lines" heuristic.
        label_idxs_v3 = {
            "branches": _find_first_label_idx(window_lines_low, key="branches"),
            "local_units": _find_first_label_idx(window_lines_low, key="local_units"),
            "volunteers": _find_first_label_idx(window_lines_low, key="volunteers"),
            "staff": _find_first_label_idx(window_lines_low, key="staff"),
        }
        present_label_idxs = [i for i in label_idxs_v3.values() if isinstance(i, int)]
        if len(present_label_idxs) >= 3:
            label_min_idx = min(int(i) for i in present_label_idxs)
            label_max_idx = max(int(i) for i in present_label_idxs)

            # v3a: "card" parsing (most robust for the KPI header visual)
            # Expected repeated pattern in OCR reading order:
            #   <number>
            #   National Society
            #   <label: branches/local units/staff/volunteers>
            used: set[str] = set()
            kpis_cards: Dict[str, str] = {}

            def _kpi_key_from_span(i0: int, i1: int) -> Optional[str]:
                span_low = " ".join(window_lines_low[i0:i1]).lower()
                if "branches" in span_low:
                    return "branches"
                if "volunteers" in span_low:
                    return "volunteers"
                if "staff" in span_low:
                    return "staff"
                # local units can be split
                if ("local units" in span_low) or ("local" in span_low and "units" in span_low):
                    return "local_units"
                return None

            def _looks_like_kpi_number_line(ln: str) -> bool:
                s = (ln or "").strip()
                if not s:
                    return False
                low = s.lower()
                if "chf" in low or "page" in low:
                    return False
                vals = _extract_num_tokens_from_line(s)
                if not vals:
                    return False
                # Prefer lines that are short / numeric-dense
                try:
                    non_space = re.sub(r"\s+", "", s)
                    non_numeric = re.sub(r"[0-9,.\-]", "", non_space)
                    dense = (len(non_space) > 0) and (len(non_numeric) <= max(1, int(len(non_space) * 0.35)))
                    if dense:
                        return True
                except Exception as e:
                    logger.debug("_has_local_units_marker dense check failed: %s", e)
                return len(s) <= 18

            def _nearest_number_above(i: int, *, max_up: int = 6) -> Optional[str]:
                for j in range(i - 1, max(-1, i - max_up - 1), -1):
                    ln = window_lines[j] or ""
                    if not _looks_like_kpi_number_line(ln):
                        continue
                    vals = _extract_num_tokens_from_line(ln)
                    for v in vals:
                        if v and (v not in used):
                            return v
                return None

            # Scan a bounded region around the labels to avoid later narrative numbers.
            scan_start = max(0, label_min_idx - 25)
            scan_end = min(len(window_lines), label_max_idx + 25)
            for i in range(scan_start, scan_end):
                low_ln = (window_lines_low[i] or "").strip()
                if "national society" not in low_ln:
                    continue
                key = _kpi_key_from_span(i, min(len(window_lines_low), i + 4))
                if not key or key in kpis_cards:
                    continue
                val = _nearest_number_above(i, max_up=6)
                if val:
                    kpis_cards[key] = val
                    used.add(val)
                if len(kpis_cards) == 4:
                    break

            if len(kpis_cards) == 4:
                block = {
                    "template": "UPR",
                    "block": "in_support_kpis",
                    "page_number": int(page_number) if isinstance(page_number, int) else None,
                    "society": society,
                    "kpis": kpis_cards,
                    "kpi_indicator_bank_ids": dict(kpi_indicator_bank_ids),
                    "extraction": "kpi_cards_v3",
                    "confidence": 0.94,
                    "debug": {
                        "label_idxs": label_idxs_v3,
                        "scan_start": scan_start,
                        "scan_end": scan_end,
                    },
                }
                out.append(block)
                continue

            num_tokens: List[Dict[str, Any]] = []
            # v3b: 4-number cluster mapping (fallback when OCR linearizes all KPI numbers into one row)
            # Scan only up to the last label area to avoid narrative numbers later in the page.
            scan_end = min(len(window_lines), max(0, label_max_idx + 6))
            for li in range(0, scan_end):
                ln = window_lines[li] or ""
                low_ln = (ln or "").lower()
                if _contains_any_kpi_keyword(low_ln):
                    continue
                if "chf" in low_ln:
                    continue
                if "people reached" in low_ln:
                    continue
                vals = _extract_num_tokens_from_line(ln)
                if not vals:
                    continue
                # Keep only "KPI-like" number lines: high numeric density or short lines.
                # This rejects paragraphs that just happen to contain a number.
                dense = False
                try:
                    non_space = re.sub(r"\s+", "", ln)
                    numericish = re.sub(r"[0-9,.\-]", "", non_space)
                    dense = (len(non_space) > 0) and (len(numericish) <= max(1, int(len(non_space) * 0.35)))
                except Exception as e:
                    logger.debug("dense numericish check failed: %s", e)
                    dense = False
                if not dense and len((ln or "").strip()) > 18:
                    continue

                for pos, v in enumerate(vals):
                    num_tokens.append({"line_idx": li, "pos": pos, "value": v, "line": ln})

            cluster = _choose_best_4_number_cluster(num_tokens, label_min_idx=label_min_idx)
            label_order_v3 = _label_order_in_window(window_lines_low[label_min_idx : min(len(window_lines_low), label_max_idx + 15)])
            if cluster and len(label_order_v3) == 4:
                nums = [str(t.get("value") or "").strip() for t in cluster]
                if all(nums) and len(set(nums)) == 4:
                    kpis_v3 = dict(zip(label_order_v3, nums))
                    # Ensure all expected keys exist (order detection can miss one if OCR is noisy)
                    if all(k in kpis_v3 for k in ("branches", "local_units", "volunteers", "staff")):
                        block = {
                            "template": "UPR",
                            "block": "in_support_kpis",
                            "page_number": int(page_number) if isinstance(page_number, int) else None,
                            "society": society,
                            "kpis": kpis_v3,
                            "kpi_indicator_bank_ids": dict(kpi_indicator_bank_ids),
                            "extraction": "kpi_cluster_v3",
                            "confidence": 0.93,
                            "debug": {
                                "label_idxs": label_idxs_v3,
                                "label_order": label_order_v3,
                                "label_min_idx": label_min_idx,
                                "label_max_idx": label_max_idx,
                                "chosen_cluster": cluster,
                            },
                        }
                        out.append(block)
                        continue

        # Preferred approach (v2): map values by proximity to labels (robust to Planning vs MYR ordering).
        # Call in fixed order and exclude already-assigned values so one line with 4 numbers
        # does not get the same value for every label.
        label_idxs = {
            "branches": _find_first_label_idx(window_lines_low, key="branches"),
            "local_units": _find_first_label_idx(window_lines_low, key="local_units"),
            "volunteers": _find_first_label_idx(window_lines_low, key="volunteers"),
            "staff": _find_first_label_idx(window_lines_low, key="staff"),
        }
        kpis_by_label: Dict[str, str] = {}
        used_values: set[str] = set()
        for key in ("branches", "local_units", "volunteers", "staff"):
            idx = label_idxs.get(key)
            if idx is None:
                continue
            val = _nearest_number(
                window_lines, around_idx=idx, exclude_values=used_values
            )
            if val:
                kpis_by_label[key] = val
                used_values.add(val)

        if len(kpis_by_label) == 4:
            block = {
                "template": "UPR",
                "block": "in_support_kpis",
                "page_number": int(page_number) if isinstance(page_number, int) else None,
                "society": society,
                "kpis": kpis_by_label,
                "kpi_indicator_bank_ids": dict(kpi_indicator_bank_ids),
                "extraction": "label_proximity_v2",
                "confidence": 0.9,
                "debug": {"label_idxs": label_idxs},
            }
            out.append(block)
            continue

        # Fallback (v1): try to find a line containing 4 numeric values and map them by label order.
        kpi_nums: Optional[List[str]] = None
        kpi_row_line: Optional[str] = None
        for ln in window_lines:
            nums = [m.group(0).strip() for m in _NUM_RE.finditer(ln)]
            # Prefer exactly 4 numbers (the KPI row). If more, it's likely "People reached" or finance.
            if len(nums) == 4:
                kpi_nums = nums
                kpi_row_line = ln
                break
        if not kpi_nums:
            # Last resort: keep partial extraction if it's still useful.
            if len(kpis_by_label) >= 3:
                block = {
                    "template": "UPR",
                    "block": "in_support_kpis",
                    "page_number": int(page_number) if isinstance(page_number, int) else None,
                    "society": society,
                    "kpis": kpis_by_label,
                    "kpi_indicator_bank_ids": dict(kpi_indicator_bank_ids),
                    "extraction": "label_proximity_partial_v2",
                    "confidence": 0.75,
                    "debug": {"label_idxs": label_idxs},
                }
                out.append(block)
            continue

        # Determine label order as it appears in text (handles Planning templates where staff/volunteers can swap).
        label_order: List[str] = []
        for low_ln in window_lines_low:
            if "branches" in low_ln and "branches" not in label_order:
                label_order.append("branches")
            if ("local units" in low_ln or "local" in low_ln or "units" in low_ln) and "local_units" not in label_order:
                # Only accept as "local_units" if we can see both parts somewhere.
                if _has_local_units_marker(window_text_low):
                    label_order.append("local_units")
            if "staff" in low_ln and "staff" not in label_order:
                label_order.append("staff")
            if "volunteers" in low_ln and "volunteers" not in label_order:
                label_order.append("volunteers")
            if len(label_order) == 4:
                break

        default_order = ["branches", "local_units", "volunteers", "staff"]
        final_order = label_order if len(label_order) == 4 else default_order
        mapped = dict(zip(final_order, kpi_nums))

        block = {
            "template": "UPR",
            "block": "in_support_kpis",
            "page_number": int(page_number) if isinstance(page_number, int) else None,
            "society": society,
            "kpis": mapped,
            "kpi_indicator_bank_ids": dict(kpi_indicator_bank_ids),
            "extraction": "fixed_4col_v1",
            "confidence": 0.85,
            "debug": {
                "kpi_row": kpi_row_line,
                "label_order": final_order,
                "label_idxs": label_idxs,
                "partial_label_kpis": kpis_by_label,
            },
        }
        out.append(block)

    ctx = infer_upr_document_context(pages=pages)
    for b in out:
        try:
            if isinstance(b, dict):
                b.setdefault("upr_context", ctx)
        except Exception as e:
            logger.debug("Block upr_context setdefault failed: %s", e)
            continue
    return out


def extract_people_reached(pages: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """
    Extract UPR (MYR/Planning) People reached visual blocks.

    Reporting (MYR) uses a header like "PEOPLE REACHED".
    Planning uses a header like "PEOPLE TO BE REACHED (IN <year>)".

    Categories (fixed order in the template):
    - Emergency Operations
    - Climate and environment
    - Disasters and crises
    - Health and wellbeing
    - Migration and displacement
    - Values, power and inclusion
    """
    out: List[Dict[str, Any]] = []
    for p in _first_upr_pages(pages):
        if not isinstance(p, dict):
            continue
        page_number = p.get("page_number")
        text = (p.get("text") or "")
        if not text.strip():
            continue

        lines = [ln.rstrip("\n") for ln in text.splitlines()]
        # Locate PEOPLE REACHED / PEOPLE TO BE REACHED header
        pr_idx = None
        header_line = None
        for i, ln in enumerate(lines):
            if _PEOPLE_REACHED_HEADER_RE.match(ln.strip()):
                pr_idx = i
                header_line = ln.strip()
                break
        if pr_idx is None:
            continue
        header_low = (header_line or "").lower()
        is_to_be = ("to be" in header_low) or ("to  be" in header_low)
        block_name = "people_to_be_reached" if is_to_be else "people_reached"
        data_key = "people_to_be_reached" if is_to_be else "people_reached"

        # End at FINANCIAL OVERVIEW if present
        end_idx = len(lines)
        for i in range(pr_idx + 1, len(lines)):
            if _FIN_OVERVIEW_RE.match(lines[i].strip()):
                end_idx = i
                break
        window_lines = lines[pr_idx:end_idx]
        window_text = "\n".join(window_lines).lower()

        # Find a numeric row with 6 values (often appears below the labels/icons)
        nums6 = None
        num_line = None
        for ln in window_lines:
            nums = [m.group(0).strip() for m in _NUM_RE.finditer(ln)]
            if len(nums) == 6:
                nums6 = nums
                num_line = ln
                break
        if not nums6:
            # Sometimes values are split across two lines; try to accumulate across adjacent lines.
            for i in range(len(window_lines) - 1):
                nums = [m.group(0).strip() for m in _NUM_RE.finditer(window_lines[i])] + [
                    m.group(0).strip() for m in _NUM_RE.finditer(window_lines[i + 1])
                ]
                if len(nums) == 6:
                    nums6 = nums
                    num_line = (window_lines[i] + " | " + window_lines[i + 1]).strip()
                    break
        if not nums6:
            continue

        # Require the category labels to appear somewhere in the window to avoid false matches.
        required = ["emergency", "climate", "disasters", "health", "migration", "values"]
        if not all(r in window_text for r in required):
            continue

        block = {
            "template": "UPR",
            "block": block_name,
            "page_number": int(page_number) if isinstance(page_number, int) else None,
            data_key: {
                "emergency_operations": nums6[0],
                "climate_and_environment": nums6[1],
                "disasters_and_crises": nums6[2],
                "health_and_wellbeing": nums6[3],
                "migration_and_displacement": nums6[4],
                "values_power_and_inclusion": nums6[5],
            },
            "extraction": "fixed_6col_v1",
            "confidence": 0.9,
            "debug": {"values_row": num_line, "header": header_line},
        }
        out.append(block)

    ctx = infer_upr_document_context(pages=pages)
    for b in out:
        try:
            if isinstance(b, dict):
                b.setdefault("upr_context", ctx)
        except Exception as e:
            logger.debug("Block upr_context setdefault failed: %s", e)
            continue
    return out


def extract_financial_overview(pages: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """
    Extract UPR (MYR/Planning) "FINANCIAL OVERVIEW" key figures (best-effort).

    This section is visually a chart/table; text extraction is often lossy.
    We focus on consistently-labeled fields:
    - Funding Requirement
    - Funding
    - Expenditure
    and keep the raw text window for traceability.
    """
    out: List[Dict[str, Any]] = []

    def norm_amount(s: str) -> Optional[str]:
        s = _norm_ws(s)
        if not s:
            return None
        if s.lower() in {"not reported", "n/a", "na"}:
            return "Not reported"
        # Normalize spacing, keep magnitude suffixes
        return s

    def ensure_leaf(d: Dict[str, Any], *path: str) -> Dict[str, Optional[str]]:
        cur: Dict[str, Any] = d
        for k in path:
            if k not in cur or not isinstance(cur.get(k), dict):
                cur[k] = {}
            cur = cur[k]
        cur.setdefault("funding_requirement", None)
        cur.setdefault("funding", None)
        cur.setdefault("expenditure", None)
        return cur  # type: ignore[return-value]

    def extract_labeled_value(window_lines: List[str], i: int, label: str) -> Optional[str]:
        """
        Extract the value associated with a label on line i, with a simple lookahead.
        Handles common OCR patterns where the value is on the next line.
        """
        if i < 0 or i >= len(window_lines):
            return None
        ln = window_lines[i]
        low = ln.lower()
        if label not in low:
            return None
        # Prevent "Funding" from matching "Funding Requirement" lines.
        if label == "funding" and "funding requirement" in low:
            return None
        if "not reported" in low:
            return "Not reported"
        nums = [m.group(0) for m in _NUM_RE.finditer(ln)]
        if nums:
            return norm_amount(nums[-1])
        # Lookahead: sometimes the value is on the next line
        if i + 1 < len(window_lines):
            nxt = window_lines[i + 1]
            low_nxt = nxt.lower()
            if "not reported" in low_nxt:
                return "Not reported"
            nums2 = [m.group(0) for m in _NUM_RE.finditer(nxt)]
            if nums2:
                return norm_amount(nums2[-1])
        return None

    for p in _first_upr_pages(pages):
        if not isinstance(p, dict):
            continue
        page_number = p.get("page_number")
        text = (p.get("text") or "")
        if not text.strip():
            continue
        lines = [ln.rstrip("\n") for ln in text.splitlines()]

        # Locate FINANCIAL OVERVIEW
        fin_idx = None
        for i, ln in enumerate(lines):
            if _FIN_OVERVIEW_RE.match(ln.strip()):
                fin_idx = i
                break
        if fin_idx is None:
            continue

        # Take a bounded window after the header (to end of page)
        window_lines = lines[fin_idx : min(len(lines), fin_idx + 220)]

        # Prefer parsing from the "IFRC network" table portion. This avoids capturing the earlier
        # "Funding sources" panel (e.g., "Afghan Red Crescent") which appears above the table.
        start_idx = 0
        for i, ln in enumerate(window_lines):
            if "ifrc network" in ln.lower():
                start_idx = i
                break

        end_idx = len(window_lines)
        for i in range(start_idx, len(window_lines)):
            low = window_lines[i].lower()
            if low.strip().startswith("*information on data scope") or "international federation of red cross" in low:
                end_idx = i
                break

        parse_lines = window_lines[start_idx:end_idx]
        raw_window = "\n".join(parse_lines).strip()

        # Schema (v2):
        # - ifrc_network is the top row (Funding Requirement)
        # - ifrc_secretariat contains sub-rows: longer_term, emergency_operations
        # - other rows are single entities
        parsed: Dict[str, Any] = {}

        current_main: Optional[str] = None
        current_sub: Optional[str] = None

        def set_main(key: str):
            nonlocal current_main, current_sub
            current_main = key
            current_sub = None

        def set_sub(key: str):
            nonlocal current_sub
            current_sub = key

        for i, ln in enumerate(parse_lines):
            low = ln.lower()
            low_next = parse_lines[i + 1].lower() if i + 1 < len(parse_lines) else ""

            # Main row detection (column 1)
            if "ifrc network" in low:
                set_main("ifrc_network")
                ensure_leaf(parsed, "ifrc_network")
            if "ifrc secretariat" in low:
                set_main("ifrc_secretariat")
                parsed.setdefault("ifrc_secretariat", {})
            if "participating national societies" in low:
                set_main("participating_national_societies")
                ensure_leaf(parsed, "participating_national_societies")
            if "hns other funding sources" in low:
                set_main("hns_other_funding_sources")
                ensure_leaf(parsed, "hns_other_funding_sources")

            # Sub-row detection (column 2) for IFRC Secretariat
            if current_main == "ifrc_secretariat":
                if "longer-term" in low or "longer term" in low:
                    set_sub("longer_term")
                    ensure_leaf(parsed, "ifrc_secretariat", "longer_term")
                # OCR can split "Emergency" and "Operations" across lines.
                if ("emergency" in low and "operations" in low) or ("emergency" in low and "operations" in low_next) or (
                    low.strip() == "operations" and "emergency" in (parse_lines[i - 1].lower() if i > 0 else "")
                ):
                    set_sub("emergency_operations")
                    ensure_leaf(parsed, "ifrc_secretariat", "emergency_operations")

            # Decide where to write labeled values
            target: Optional[Dict[str, Optional[str]]] = None
            if current_main == "ifrc_secretariat":
                if current_sub:
                    target = ensure_leaf(parsed, "ifrc_secretariat", current_sub)
            elif current_main:
                target = ensure_leaf(parsed, current_main)

            if not target:
                continue

            fr = extract_labeled_value(parse_lines, i, "funding requirement")
            if fr:
                target["funding_requirement"] = fr

            fu = extract_labeled_value(parse_lines, i, "funding")
            if fu:
                target["funding"] = fu

            ex = extract_labeled_value(parse_lines, i, "expenditure")
            if ex:
                target["expenditure"] = ex

        block = {
            "template": "UPR",
            "block": "financial_overview",
            "page_number": int(page_number) if isinstance(page_number, int) else None,
            "financial_overview": parsed,
            "extraction": "labeled_fields_v2",
            "confidence": 0.72,
            "debug": {"raw": raw_window[:5000]},
        }
        out.append(block)

    ctx = infer_upr_document_context(pages=pages)
    for b in out:
        try:
            if isinstance(b, dict):
                b.setdefault("upr_context", ctx)
        except Exception as e:
            logger.debug("Block upr_context setdefault failed: %s", e)
            continue
    return out


def _is_fullpage_funding_requirements_layout(window_text: str) -> bool:
    """
    Detect the full-page "Funding requirements" visual (version: plans 2025 / multi-year).

    This visual is the funding-requirements infographic used in UPR country plans (e.g. plans 2025).
    That layout typically fills an entire page with:
    - Title "Funding requirements"
    - Multiple year columns (e.g. 2025, 2026**, 2027**) each with "Total X.XM CHF"
    - Funding sources: "Through Host National Society", "Through Participating National Societies", "Through the IFRC"
    - "IFRC Breakdown" with "Ongoing emergency operations" and "Longer term needs" (strategic priorities)
    """
    low = window_text.lower()
    has_title = bool(_FUNDING_REQUIREMENTS_RE.search(window_text))
    has_host_ns = "through host national society" in low or ("host" in low and "national society" in low and "through" in low)
    has_ifrc_breakdown = "ifrc" in low and "breakdown" in low
    has_longer_term = "longer term needs" in low or ("longer term" in low and "needs" in low)
    years = _YEAR_RE.findall(window_text)
    unique_years = len(set(years))
    # Strong markers: title + (Host NS or IFRC breakdown + longer term) + at least 2 years
    return (
        has_title
        and (has_host_ns or (has_ifrc_breakdown and has_longer_term))
        and unique_years >= 2
    )


def extract_funding_requirements(pages: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """
    Extract the UPR "Funding requirements" visual (version: plans 2025), best-effort.

    This visual is the funding-requirements infographic (plans 2025 / multi-year layout).
    Supports two layout variants:
    - **Current Planning**: "IFRC network Funding Requirements" with totals by year and optional
      breakdown (through IFRC / PNS / Host NS) and IFRC breakdown panel.
    - **Full-page multi-column (plans 2025)**: Entire page titled "Funding requirements" with
      year columns (e.g. 2025 | 2026 | 2027), each with Total, funding sources (Through Host NS,
      Through PNS, Through the IFRC), and IFRC Breakdown (Ongoing emergency operations, Longer term needs).
    """
    out: List[Dict[str, Any]] = []

    _TOTAL_CHF_RE = re.compile(r"\btotal\s+([\d.,]+(?:\.\d+)?[mMkK]?)\s*chf\b", re.IGNORECASE)
    _AMOUNT_CHF_RE = re.compile(r"\b([\d.,]+(?:\.\d+)?[mMkK]?)\s*chf\b", re.IGNORECASE)
    _FUNDING_REQUIREMENT_AMOUNT_RE = re.compile(
        r"\bfunding\s+requirement\s+(?:in\s+)?(?:swiss\s+francs\s+)?(?:\(?chf\)?\s*)?([\d.,]+(?:\.\d+)?[mMkK]?)\b",
        re.IGNORECASE,
    )
    _FUNDING_REQUIREMENT_CHF_AFTER_RE = re.compile(
        r"\bfunding\s+requirement\s+chf\s+([\d.,]+(?:\.\d+)?[mMkK]?)\b",
        re.IGNORECASE,
    )

    # Document context helps assign a year when the visual only shows a single total
    # (common in some UPR plan layouts where the "Funding Requirement CHF X" callout is present
    # but a year column header is missing or not captured by OCR).
    # Prefer context provided by the orchestrator (includes filename/title),
    # otherwise infer from pages only.
    ctx = None
    try:
        if isinstance(pages, list) and pages and isinstance(pages[0], dict) and isinstance(pages[0].get("_upr_context"), dict):
            ctx = pages[0].get("_upr_context")
    except Exception as e:
        logger.debug("ctx from _upr_context failed: %s", e)
        ctx = None
    if not isinstance(ctx, dict):
        ctx = infer_upr_document_context(pages=pages)
    doc_year = None
    try:
        dy = ctx.get("document_year") or ctx.get("year")
        doc_year = int(dy) if isinstance(dy, int) or (isinstance(dy, str) and dy.isdigit()) else None
    except Exception as e:
        logger.debug("doc_year extraction failed: %s", e)
        doc_year = None

    def _single_year_total_from_words(page_words: Any) -> Optional[str]:
        """
        Extract a single "Funding Requirement CHF <amount>" total using word-level layout.
        This handles cases where the OCR text lines do not contain "funding requirement"
        contiguously, but `page["words"]` contains the tokens.
        """
        if not isinstance(page_words, list) or not page_words:
            return None
        toks = []
        for w in page_words:
            if not isinstance(w, dict):
                continue
            t = (w.get("text") or "").strip()
            if not t:
                continue
            try:
                x0 = float(w.get("x0"))
                y0 = float(w.get("y0"))
                x1 = float(w.get("x1"))
                y1 = float(w.get("y1"))
            except Exception as e:
                logger.debug("Word coord parse failed: %s", e)
                continue
            toks.append({"t": t, "low": t.lower(), "x0": x0, "y0": y0, "x1": x1, "y1": y1})
        if not toks:
            return None
        # Approximate reading order
        toks.sort(key=lambda w: (w["y0"], w["x0"]))

        def is_year_token(s: str) -> bool:
            try:
                return bool(re.fullmatch(r"(?:19|20)\\d{2}", (s or "").strip()))
            except Exception as e:
                logger.debug("is_year_token failed: %s", e)
                return False

        # Look for a CHF token with a nearby numeric token and "funding"/"requirement" in the vicinity.
        for i, w in enumerate(toks):
            if w["low"] not in {"chf", "(chf)"}:
                continue
            win0 = max(0, i - 30)
            win1 = min(len(toks), i + 31)
            vicinity = " ".join([t["low"] for t in toks[win0:win1]])
            if ("funding" not in vicinity) or ("requirement" not in vicinity):
                continue

            # Find numeric token closest to CHF (same line preferred)
            candidates = []
            for j in range(max(0, i - 6), min(len(toks), i + 7)):
                tj = toks[j]["t"]
                if not tj:
                    continue
                if is_year_token(tj):
                    continue
                if not _NUM_RE.fullmatch(tj):
                    continue
                # Prefer amount-like numbers (M/K, commas, decimals)
                score_kind = 0
                if any(ch in tj for ch in (",", ".")) or ("m" in tj.lower()) or ("k" in tj.lower()):
                    score_kind = -1
                # Prefer same-line (y overlap)
                dy = abs(toks[j]["y0"] - w["y0"])
                dx = abs(((toks[j]["x0"] + toks[j]["x1"]) / 2.0) - ((w["x0"] + w["x1"]) / 2.0))
                candidates.append((score_kind, dy, dx, tj))
            if candidates:
                candidates.sort(key=lambda t: (t[0], t[1], t[2]))
                return candidates[0][3]
        return None

    def _dedupe_repeated_phrase(label: str) -> str:
        """
        OCR of 3-column layouts often concatenates the same label 3 times, e.g.:
        "Climate and environment Climate and environment Climate and environment".
        Collapse exact repetitions to a single phrase.
        """
        s = _norm_ws(label)
        if not s:
            return s
        toks = s.split()
        for n in (3, 2):
            if len(toks) % n != 0:
                continue
            part_len = len(toks) // n
            if part_len <= 0:
                continue
            part = toks[:part_len]
            if part * n == toks:
                return " ".join(part).strip()
        return s

    def _years_in_order(text: str) -> List[str]:
        ys = _YEAR_RE.findall(text or "")
        out_years: List[str] = []
        seen: set[str] = set()
        for y in ys:
            if y in seen:
                continue
            seen.add(y)
            out_years.append(y)
        return out_years

    def _extract_amounts_chf_from_lines(lines: List[str], start_idx: int, *, max_lookahead: int = 4) -> List[str]:
        """
        Extract CHF amount tokens across a small lookahead window.
        Returns tokens like "51.6M", "411,000", "26M".
        """
        vals: List[str] = []
        for j in range(start_idx, min(len(lines), start_idx + max_lookahead)):
            ln = lines[j] or ""
            for m in _AMOUNT_CHF_RE.finditer(ln):
                vals.append(m.group(1).strip())
            if vals:
                break
        return vals

    def _label_positions(line_low: str) -> List[tuple[int, str]]:
        """
        Return a list of (position, key) for funding-source labels in this line,
        sorted by left-to-right occurrence within the line.
        """
        found: List[tuple[int, str]] = []
        # Host NS
        if "through" in line_low and ("host national society" in line_low or ("host" in line_low and "national society" in line_low)):
            found.append((line_low.find("host"), "host_national_society"))
        # Participating NS
        if "through" in line_low and ("participating national societies" in line_low or ("participating" in line_low and "national societ" in line_low)):
            found.append((line_low.find("participating"), "through_participating_national_societies"))
        # IFRC
        if "through" in line_low and "ifrc" in line_low:
            found.append((line_low.find("ifrc"), "through_ifrc"))
        found = [(p, k) for p, k in found if p >= 0]
        found.sort(key=lambda t: t[0])
        return found

    def _parse_fullpage_totals_and_sources(window_lines: List[str]) -> tuple[List[str], Dict[str, str], Dict[str, Dict[str, str]]]:
        """
        Parse totals and funding-source breakdown for the "Funding requirements" visual (plans 2025).
        Full-page 2–3 column layout in a column-aware way:
        - years appear on one line (e.g. "2025 2026** 2027**")
        - totals appear as "Total X CHF" for each year
        - funding sources appear as one or more rows of labels + amount rows, with amounts aligned to year order
          (missing columns may be omitted, yielding 1–2 amounts on a row).
        """
        years_order: List[str] = []
        for ln in window_lines[:25]:
            ys = _years_in_order(ln)
            if len(ys) >= 1:
                # Prefer a line that contains 2+ years (the header row)
                if len(ys) >= 2:
                    years_order = ys
                    break
                years_order = years_order or ys
        if not years_order:
            # Fallback: any years in the entire window
            years_order = _years_in_order("\n".join(window_lines))

        totals_by_year: Dict[str, str] = {}
        # Totals are explicit "Total <amount> CHF" phrases; map in appearance order to year order.
        total_vals: List[str] = []
        for ln in window_lines:
            for m in _TOTAL_CHF_RE.finditer(ln or ""):
                total_vals.append(m.group(1).strip())
        if years_order and total_vals:
            for y, v in zip(years_order, total_vals[: len(years_order)]):
                totals_by_year[y] = v

        breakdown_by_year: Dict[str, Dict[str, str]] = {}
        if not years_order:
            return years_order, totals_by_year, breakdown_by_year

        # Funding-source rows (labels + amounts). We map amounts to years in *year order*.
        i = 0
        while i < len(window_lines):
            ln = window_lines[i] or ""
            low = ln.lower()
            labels = _label_positions(low)
            if not labels:
                i += 1
                continue
            keys = [k for _pos, k in labels]
            amounts = _extract_amounts_chf_from_lines(window_lines, i + 1, max_lookahead=4)
            if amounts and keys:
                # Map amounts to the *leftmost* years by default (missing right columns are common).
                years_subset = years_order[: min(len(amounts), len(keys), len(years_order))]
                for idx, y in enumerate(years_subset):
                    k = keys[idx] if idx < len(keys) else None
                    v = amounts[idx] if idx < len(amounts) else None
                    if not k or not v:
                        continue
                    breakdown_by_year.setdefault(y, {})
                    breakdown_by_year[y].setdefault(k, v)
                # Skip ahead a bit to avoid re-reading the same row.
                i += 2
                continue
            i += 1

        return years_order, totals_by_year, breakdown_by_year

    def _parse_fullpage_ifrc_breakdown(window_lines: List[str], years_order: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Parse the full-page "Funding requirements" IFRC Breakdown section per-year (plans 2025).

        In 3-column layouts, OCR often linearizes rows like:
          "340,000 CHF 374,000 CHF 411,000 CHF"
          "Climate and environment Climate and environment Climate and environment"
        We interpret 3 values as (year1, year2, year3) in year order.
        """
        if not years_order:
            return {}

        # Find the first IFRC Breakdown marker and parse until a footer/next section.
        start = None
        for idx, ln in enumerate(window_lines):
            low = (ln or "").lower()
            if "ifrc" in low and "breakdown" in low:
                start = idx
                break
        if start is None:
            return {}

        parse_lines = window_lines[start : min(len(window_lines), start + 260)]

        # Init per-year output with stable keys
        out_by_year: Dict[str, Dict[str, Any]] = {}
        for y in years_order:
            out_by_year[y] = {
                "ongoing_emergency_operations": None,
                "strategic_priorities": {},
                "enabling_functions": None,
                "items": [],
            }

        def assign_value_to_years(label: str, values: List[str]):
            clean_label = _dedupe_repeated_phrase(label)
            label_low = clean_label.lower()

            # Map values to years (left-to-right years). If fewer values, fill earliest years only.
            ys = years_order[: min(len(values), len(years_order))]
            for j, y in enumerate(ys):
                v = values[j]
                if not v:
                    continue
                item = {"label": clean_label, "value": v}
                out_by_year[y]["items"].append(item)

                if "enabling" in label_low:
                    out_by_year[y]["enabling_functions"] = v
                    continue
                if "ongoing" in label_low and "emergency" in label_low:
                    out_by_year[y]["ongoing_emergency_operations"] = v
                    continue

                # Strategic priorities mapping (same as Planning, but per-year)
                known = {
                    "climate_and_environment": ["climate", "environment"],
                    "disasters_and_crises": ["disasters", "crises"],
                    "health_and_wellbeing": ["health", "wellbeing"],
                    "migration_and_displacement": ["migration", "displacement"],
                    "values_power_and_inclusion": ["values", "inclusion"],
                }
                matched_key = None
                for k, terms in known.items():
                    if all(t in label_low for t in terms):
                        matched_key = k
                        break
                if matched_key:
                    out_by_year[y]["strategic_priorities"][matched_key] = v
                else:
                    # Only store as strategic priority if we are in "Longer term needs" area (heuristic)
                    if "longer term" in (" ".join([ln.lower() for ln in parse_lines[:50]]) if parse_lines else ""):
                        out_by_year[y]["strategic_priorities"][_norm_key(clean_label)] = v

        # Scan for amount lines; label is usually on the next non-empty, non-amount line(s).
        i = 0
        while i < len(parse_lines):
            ln = (parse_lines[i] or "").strip()
            low = ln.lower()
            # Stop before footers
            if low.startswith("*information on data scope") or "see back page" in low:
                break

            # Extract CHF amounts from this line
            values = [m.group(1).strip() for m in _AMOUNT_CHF_RE.finditer(ln)]
            if not values:
                i += 1
                continue

            # Find a label in following lines (avoid headers and amount-only lines)
            label_parts: List[str] = []
            j = i + 1
            while j < min(len(parse_lines), i + 6):
                nxt = (parse_lines[j] or "").strip()
                if not nxt:
                    j += 1
                    continue
                nxt_low = nxt.lower()
                # Stop if next line is another amount line
                if _AMOUNT_CHF_RE.search(nxt):
                    break
                # Skip section headers
                if "ifrc breakdown" in nxt_low or "longer term needs" in nxt_low:
                    j += 1
                    continue
                if "ongoing emergency" in nxt_low and "operations" in nxt_low:
                    label_parts = ["Ongoing emergency operations"]
                    break
                # Prefer the first real label line; in 3-column layouts it may include repeats
                label_parts.append(nxt)
                # Usually a single line is enough; don't over-collect to avoid concatenating repeats
                break
            label = _norm_ws(" ".join(label_parts))
            if label:
                assign_value_to_years(label, values)
            i += 1

        # Clean up empty dicts / lists for each year
        cleaned: Dict[str, Dict[str, Any]] = {}
        for y, d in out_by_year.items():
            sp = d.get("strategic_priorities")
            if isinstance(sp, dict) and not sp:
                d.pop("strategic_priorities", None)
            items = d.get("items")
            if isinstance(items, list) and not items:
                d.pop("items", None)
            # Keep years that have at least one meaningful value
            if d.get("ongoing_emergency_operations") or d.get("enabling_functions") or (isinstance(sp, dict) and sp) or (isinstance(items, list) and items):
                cleaned[y] = d
        return cleaned

    def has_chf_near(lines: List[str], i: int) -> bool:
        if i < 0 or i >= len(lines):
            return False
        if "chf" in (lines[i] or "").lower():
            return True
        if i + 1 < len(lines) and "chf" in (lines[i + 1] or "").lower():
            return True
        if i - 1 >= 0 and "chf" in (lines[i - 1] or "").lower():
            return True
        return False

    def extract_amount_near(lines: List[str], i: int) -> Optional[str]:
        if i < 0 or i >= len(lines):
            return None
        # OCR can push the amount a couple lines below the label (esp. in multi-column layouts).
        # Scan a small lookahead window but prefer lines that mention CHF near the number.
        best: Optional[str] = None
        for j in range(i, min(len(lines), i + 4)):
            ln = lines[j] or ""
            nums = [m.group(0).strip() for m in _NUM_RE.finditer(ln)]
            if not nums:
                continue
            # If this line looks currency-related, take it immediately.
            if "chf" in ln.lower() or has_chf_near(lines, j):
                return nums[-1]
            best = best or nums[-1]
        return best

    def nearest_year_above(lines: List[str], i: int) -> Optional[str]:
        for j in range(i, max(-1, i - 16), -1):
            ys = _YEAR_RE.findall(lines[j])
            if ys:
                return ys[0]
        return None

    def _norm_key(s: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", (s or "").strip().lower()).strip("_")

    def parse_ifrc_breakdown(panel_lines: List[str]) -> Dict[str, Any]:
        """
        Parse the optional Planning panel:
        - "IFRC Breakdown"
        - "Ongoing emergency operations" (often)
        - "Longer term needs" (header)
        - 5 strategic priorities (often)
        - 1 enabling functions (often called "Enabling local actors")
        """
        out: Dict[str, Any] = {
            "ongoing_emergency_operations": None,
            "strategic_priorities": {},
            "enabling_functions": None,
            "items": [],
        }

        # Find the start after "IFRC Breakdown"
        start = 0
        for i, ln in enumerate(panel_lines):
            ll = (ln or "").lower()
            if "ifrc" in ll and "breakdown" in ll:
                start = i + 1
                break
            if "breakdown" in ll and i - 1 >= 0 and "ifrc" in (panel_lines[i - 1] or "").lower():
                start = i + 1
                break

        lines = panel_lines[start:]
        mode = "pre"  # pre | strategic

        def is_amount_line(idx: int) -> bool:
            if idx < 0 or idx >= len(lines):
                return False
            # Ignore year-only lines by requiring CHF nearby.
            if not has_chf_near(lines, idx):
                return False
            return bool(_NUM_RE.search(lines[idx] or "")) or (idx + 1 < len(lines) and bool(_NUM_RE.search(lines[idx + 1] or "")))

        i = 0
        while i < len(lines):
            ln = lines[i] or ""
            ll = ln.lower()

            if "longer term needs" in ll or (ll.strip() == "longer term" and i + 1 < len(lines) and "needs" in (lines[i + 1] or "").lower()):
                mode = "strategic"
                i += 1
                continue

            if not is_amount_line(i):
                i += 1
                continue

            val = extract_amount_near(lines, i)
            if not val:
                i += 1
                continue

            # Label is usually on following line(s) (avoid picking up CHF/amount lines).
            label_parts: List[str] = []
            for j in range(i + 1, min(len(lines), i + 4)):
                if is_amount_line(j):
                    break
                lnj = (lines[j] or "").strip()
                if not lnj:
                    continue
                lowj = lnj.lower()
                if "chf" in lowj:
                    continue
                # Skip panel headers
                if "ifrc breakdown" in lowj or "longer term needs" in lowj:
                    continue
                label_parts.append(lnj)

            label = _norm_ws(" ".join(label_parts)).strip()
            if not label:
                i += 1
                continue

            item = {"label": label, "value": val}
            out["items"].append(item)

            label_low = label.lower()
            # Enabling functions (often "Enabling local actors")
            if "enabling" in label_low:
                out["enabling_functions"] = val
            elif "ongoing" in label_low and "emergency" in label_low:
                out["ongoing_emergency_operations"] = val
            else:
                # Strategic priorities (5 in Planning; keep flexible)
                if mode == "strategic":
                    known = {
                        "climate_and_environment": ["climate", "environment"],
                        "disasters_and_crises": ["disasters", "crises"],
                        "health_and_wellbeing": ["health", "wellbeing"],
                        "migration_and_displacement": ["migration", "displacement"],
                        "values_power_and_inclusion": ["values", "inclusion"],
                    }
                    matched_key = None
                    for k, terms in known.items():
                        if all(t in label_low for t in terms):
                            matched_key = k
                            break
                    if matched_key:
                        out["strategic_priorities"][matched_key] = val
                    else:
                        out["strategic_priorities"][_norm_key(label)] = val

            i += 1

        # Drop empty dicts for cleanliness
        if not out["strategic_priorities"]:
            out.pop("strategic_priorities", None)
        if not out.get("items"):
            out.pop("items", None)
        return out

    def parse_participating_national_societies(panel_lines: List[str]) -> Dict[str, Any]:
        """
        Parse the optional "Participating National Societies" list.

        Convention used in Planning visuals:
        - Names with "*" are considered multilateral (through IFRC)
        - Names without "*" are considered bilateral
        """
        # Find header line (robust to OCR splits and multi-column noise).
        start = None
        for i, ln in enumerate(panel_lines):
            s = (ln or "").strip()
            low = s.lower()
            # Exact match
            if _PARTICIPATING_NS_RE.match(s):
                start = i + 1
                break
            # Split across two lines: "Participating" / "National Societies"
            if low == "participating" and i + 1 < len(panel_lines):
                nxt = (panel_lines[i + 1] or "").strip().lower()
                if nxt == "national societies":
                    start = i + 2
                    break
            # Noisy split across columns:
            # e.g. "IFRC network Funding ... Participating ... IFRC Appeal codes" then next line contains "National Societies"
            if "participating" in low and i + 1 < len(panel_lines):
                nxt = (panel_lines[i + 1] or "").strip().lower()
                if "national societies" in nxt:
                    start = i + 2
                    break
            if "national societies" in low and i - 1 >= 0:
                prv = (panel_lines[i - 1] or "").strip().lower()
                if "participating" in prv:
                    start = i + 1
                    break
        if start is None:
            return {}

        # Collect the panel body
        body_lines: List[str] = []
        for ln in panel_lines[start:]:
            s = (ln or "").strip()
            if not s:
                continue
            low = s.lower()
            # Stop at common next panels / footnotes
            if ("hazards" in low) or ("ifrc country delegation" in low):
                break
            if "national societies" in low and "contributed" in low and "multilateral" in low:
                break
            # Don't stop on "funding requirements" because it can appear in another column while the NS list continues.
            if ("ifrc" in low and "breakdown" in low):
                break
            # Skip separator-like lines (OCR sometimes produces underscores/dashes)
            if re.fullmatch(r"[-_—–]{2,}", s):
                continue
            body_lines.append(s)

        if not body_lines:
            return {}

        # Parse names from multi-column OCR:
        # - Split each line into "cells" by 2+ spaces
        # - Take the cell that contains "Red Cross"/"Red Crescent"
        # - Handle OCR splitting "... National Red" + "Cross*" across lines
        names_raw: List[str] = []
        pending_prefix: Optional[str] = None

        def add_name(name: str):
            nm = (name or "").strip()
            if not nm:
                return
            names_raw.append(nm)

        for line in body_lines:
            # Cells split by multi-space (column separators)
            cells = [c.strip() for c in re.split(r"\s{2,}", line) if c.strip()]
            if not cells:
                continue

            # If we have a pending "... Red" prefix, try to complete it with a "Cross" cell
            if pending_prefix:
                for c in cells:
                    cl = c.lower()
                    if cl in {"cross", "cross*", "crescent", "crescent*"}:
                        add_name(pending_prefix + " " + c)
                        pending_prefix = None
                        break

            for c in cells:
                cl = c.lower()
                # Ignore obvious non-name cells
                if "mdr" in cl:
                    continue
                if ("total" in cl and "chf" in cl) or ("projected funding requirements" in cl):
                    continue
                if cl.startswith("emergency appeal") or cl.startswith("longer-term needs") or cl.startswith("longer term needs"):
                    continue

                if ("red cross" in cl) or ("red crescent" in cl):
                    add_name(c)
                    continue

                # Capture split prefix like "The Republic of Korea National Red"
                if cl.endswith(" red") and ("national red" in cl or cl.endswith("national red")):
                    pending_prefix = c

        if not names_raw:
            return {}

        # Normalize + de-dupe preserving order
        seen: set[str] = set()
        bilateral: List[str] = []
        multilateral: List[str] = []
        raw_out: List[str] = []
        for n in names_raw:
            n2 = (n or "").strip()
            if not n2:
                continue
            starred = n2.endswith("*")
            clean = n2[:-1].rstrip() if starred else n2
            clean = clean.rstrip(" ,.;")
            if not clean:
                continue
            key = clean.lower()
            if key in seen:
                continue
            seen.add(key)
            raw_out.append(clean + ("*" if starred else ""))
            if starred:
                multilateral.append(clean)
            else:
                bilateral.append(clean)

        return {"bilateral": bilateral, "multilateral": multilateral, "raw": raw_out}

    # Avoid emitting duplicate single-year fallback blocks (some layouts repeat the callout).
    seen_single_year: set[tuple[str, str]] = set()

    for p in _first_upr_pages(pages, max_pages=_FUNDING_REQUIREMENTS_MAX_PAGES):
        if not isinstance(p, dict):
            continue
        page_number = p.get("page_number")
        text = (p.get("text") or "")
        if not text.strip():
            # Allow word-layout fallback for infographic-heavy pages with weak OCR.
            pass

        low = text.lower()
        if "funding" not in low or "requirement" not in low:
            # Word-layout fallback: OCR may be empty, but words may contain the tokens.
            amt_w = _single_year_total_from_words(p.get("words"))
            if amt_w and doc_year:
                key = (str(int(doc_year)), str(amt_w))
                if key in seen_single_year:
                    continue
                seen_single_year.add(key)
                out.append(
                    {
                        "template": "UPR",
                        "block": "funding_requirements",
                        "page_number": int(page_number) if isinstance(page_number, int) else None,
                        "funding_requirements": {
                            "currency": "CHF",
                            "totals_by_year": {str(int(doc_year)): str(amt_w)},
                            "breakdown_by_year": {},
                            "ifrc_breakdown_by_year": {},
                            "participating_national_societies": {},
                        },
                        "extraction": "funding_requirements_single_year_words_v0",
                        "confidence": 0.66,
                        "debug": {"word_fallback": True},
                    }
                )
            continue

        lines = [ln.rstrip("\n") for ln in text.splitlines()]

        # Locate the header (OCR may split "Funding" / "Requirements" across lines).
        hdr_idx = None
        for i, ln in enumerate(lines):
            ll = ln.lower()
            if "funding" in ll and "requirement" in ll:
                hdr_idx = i
                break
            if "funding" in ll and i + 1 < len(lines) and "requirement" in lines[i + 1].lower():
                hdr_idx = i
                break
        if hdr_idx is None:
            # Word-layout fallback: OCR line splitting can hide the contiguous header.
            amt_w = _single_year_total_from_words(p.get("words"))
            if amt_w and doc_year:
                key = (str(int(doc_year)), str(amt_w))
                if key in seen_single_year:
                    continue
                seen_single_year.add(key)
                out.append(
                    {
                        "template": "UPR",
                        "block": "funding_requirements",
                        "page_number": int(page_number) if isinstance(page_number, int) else None,
                        "funding_requirements": {
                            "currency": "CHF",
                            "totals_by_year": {str(int(doc_year)): str(amt_w)},
                            "breakdown_by_year": {},
                            "ifrc_breakdown_by_year": {},
                            "participating_national_societies": {},
                        },
                        "extraction": "funding_requirements_single_year_words_v0",
                        "confidence": 0.66,
                        "debug": {"word_fallback": True, "hdr_idx": None},
                    }
                )
            continue

        window_lines = lines[hdr_idx : min(len(lines), hdr_idx + 240)]
        window_text = "\n".join(window_lines)
        window_low = window_text.lower()
        if not _FUNDING_REQUIREMENTS_RE.search(window_text):
            continue

        # Funding requirements visual: plans 2025 (full-page multi-column) vs current planning panel.
        is_fullpage_variant = _is_fullpage_funding_requirements_layout(window_text)
        currency = "CHF" if "chf" in window_low else None

        totals_by_year: Dict[str, str] = {}
        breakdown_by_year: Dict[str, Dict[str, str]] = {}
        ifrc_breakdown_by_year: Dict[str, Dict[str, Any]] = {}

        # Full-page "Funding requirements" (plans 2025): column-aware parsing; proximity-to-year breaks when OCR linearizes columns.
        if is_fullpage_variant:
            years_order, totals_by_year, breakdown_by_year = _parse_fullpage_totals_and_sources(window_lines)
            ifrc_breakdown_by_year = _parse_fullpage_ifrc_breakdown(window_lines, years_order)
        else:
            # Collect year lines and total lines (legacy proximity-based assignment)
            year_lines: List[tuple[int, List[str], str]] = []
            total_lines: List[tuple[int, List[str], str]] = []
            for i, ln in enumerate(window_lines):
                ys = _YEAR_RE.findall(ln)
                if ys:
                    year_lines.append((i, ys, ln))
                if "total" in ln.lower():
                    nums = [m.group(0).strip() for m in _NUM_RE.finditer(ln)]
                    if nums:
                        total_lines.append((i, nums, ln))

            used_total: set[int] = set()

            # Assign totals to years by proximity.
            for y_idx, years, _ in year_lines:
                if not years:
                    continue

                # Single year: find the nearest "Total" line shortly after.
                if len(years) == 1:
                    y = years[0]
                    if y in totals_by_year:
                        continue
                    candidates = [
                        (t_idx, nums, ln)
                        for (t_idx, nums, ln) in total_lines
                        if (t_idx not in used_total) and (t_idx >= y_idx) and (t_idx <= y_idx + 8)
                    ]
                    if candidates:
                        t_idx, nums, _ln = sorted(candidates, key=lambda t: (t[0] - y_idx, t[0]))[0]
                        totals_by_year[y] = nums[0]
                        used_total.add(t_idx)
                    continue

                # Multiple years on one line: pair with a nearby line with multiple totals.
                candidates_multi = [
                    (t_idx, nums, ln)
                    for (t_idx, nums, ln) in total_lines
                    if (t_idx >= y_idx) and (t_idx <= y_idx + 10) and len(nums) >= len(years)
                ]
                if candidates_multi:
                    t_idx, nums, _ln = sorted(candidates_multi, key=lambda t: (t[0] - y_idx, t[0]))[0]
                    for y, v in zip(years, nums[: len(years)]):
                        totals_by_year.setdefault(y, v)
                    used_total.add(t_idx)
                    continue

                # Otherwise, gather individual total lines in the vicinity.
                vals: List[str] = []
                for t_idx, nums, _ln in sorted(total_lines, key=lambda t: t[0]):
                    if t_idx < y_idx or t_idx > y_idx + 10:
                        continue
                    if t_idx in used_total:
                        continue
                    if len(nums) == 1:
                        vals.append(nums[0])
                        used_total.add(t_idx)
                    if len(vals) >= len(years):
                        break
                if len(vals) >= len(years):
                    for y, v in zip(years, vals[: len(years)]):
                        totals_by_year.setdefault(y, v)

            # Breakdown (can appear for one or multiple years, depending on template)
            for i, ln in enumerate(window_lines):
                ll = ln.lower()
                key = None
                if "through" in ll and ("participating" in ll or ("national" in ll and "societ" in ll)):
                    key = "through_participating_national_societies"
                elif "through" in ll and "ifrc" in ll:
                    key = "through_ifrc"
                elif ("host" in ll and "national" in ll and "societ" in ll) or ("host national society" in ll):
                    key = "host_national_society"
                if not key:
                    continue
                val = extract_amount_near(window_lines, i)
                if not val:
                    continue
                yr = nearest_year_above(window_lines, i) or (sorted(totals_by_year.keys())[0] if totals_by_year else None)
                if not yr:
                    continue
                breakdown_by_year.setdefault(yr, {})
                breakdown_by_year[yr][key] = val

            # Optional IFRC breakdown panel (often for the first immediate year)
            ifrc_idx = None
            for i, ln in enumerate(window_lines):
                ll = (ln or "").lower()
                if "ifrc" in ll and "breakdown" in ll:
                    ifrc_idx = i
                    break
                if "breakdown" in ll and i + 1 < len(window_lines) and "ifrc" in (window_lines[i + 1] or "").lower():
                    ifrc_idx = i
                    break
            if ifrc_idx is not None:
                # Stop before other panels to avoid mixing numbers from unrelated sections.
                stop = min(len(window_lines), ifrc_idx + 220)
                for j in range(ifrc_idx, min(len(window_lines), ifrc_idx + 220)):
                    lowj = (window_lines[j] or "").lower()
                    if "participating national societies" in lowj or "hazards" in lowj or "appeal codes" in lowj:
                        stop = j
                        break
                panel_lines = window_lines[ifrc_idx:stop]
                parsed_panel = parse_ifrc_breakdown(panel_lines)
                # Attach to the nearest year above, otherwise first year in totals.
                yr = nearest_year_above(window_lines, ifrc_idx) or (sorted(totals_by_year.keys())[0] if totals_by_year else None)
                if yr and (parsed_panel.get("ongoing_emergency_operations") or parsed_panel.get("enabling_functions") or parsed_panel.get("strategic_priorities") or parsed_panel.get("items")):
                    ifrc_breakdown_by_year[yr] = parsed_panel

        # Optional "Participating National Societies" list (with "*" markers)
        participating_national_societies: Dict[str, Any] = {}
        pns_idx = None
        for i, ln in enumerate(window_lines):
            s = (ln or "").strip()
            low = s.lower()
            if _PARTICIPATING_NS_RE.match(s):
                pns_idx = i
                break
            # Split header across lines
            if low == "participating" and i + 1 < len(window_lines) and (window_lines[i + 1] or "").strip().lower() == "national societies":
                pns_idx = i
                break
            # Noisy split across columns (look for "participating" then "national societies" nearby)
            if "participating" in low and i + 1 < len(window_lines) and "national societies" in (window_lines[i + 1] or "").strip().lower():
                pns_idx = i
                break
        if pns_idx is not None:
            stop = min(len(window_lines), pns_idx + 260)
            for j in range(pns_idx, min(len(window_lines), pns_idx + 260)):
                lowj = (window_lines[j] or "").lower()
                # Don't stop on "appeal codes" here because some OCR outputs place it on the same header line
                # as "Participating". We stop on clearer boundaries.
                if "hazards" in lowj or "ifrc country delegation" in lowj:
                    stop = j
                    break
            panel_lines = window_lines[pns_idx:stop]
            participating_national_societies = parse_participating_national_societies(panel_lines)

        if not totals_by_year:
            # Fallback: single-year "Funding Requirement CHF X" callout with no year columns.
            # If we can find an amount and we have a document year, attach it as totals_by_year[doc_year].
            amt = None
            try:
                m2 = _FUNDING_REQUIREMENT_CHF_AFTER_RE.search(window_text) or _FUNDING_REQUIREMENT_AMOUNT_RE.search(window_text)
                if m2:
                    amt = (m2.group(1) or "").strip()
            except Exception as e:
                logger.debug("amt regex extraction failed: %s", e)
                amt = None
            if amt and doc_year:
                totals_by_year = {str(int(doc_year)): amt}
                extraction_tag = "funding_requirements_single_year_v0"
                conf = 0.68
            else:
                continue

        raw_window = window_text.strip()
        # Confidence heuristic
        conf = 0.75
        if len(totals_by_year) >= 2:
            conf = 0.82
        if breakdown_by_year:
            conf = max(conf, 0.86)
        if is_fullpage_variant:
            conf = max(conf, 0.85)
        extraction_tag = locals().get("extraction_tag") or ("funding_requirements_fullpage_v1" if is_fullpage_variant else "funding_requirements_v1")

        block = {
            "template": "UPR",
            "block": "funding_requirements",
            "page_number": int(page_number) if isinstance(page_number, int) else None,
            "funding_requirements": {
                "currency": currency,
                "totals_by_year": totals_by_year,
                "breakdown_by_year": breakdown_by_year,
                "ifrc_breakdown_by_year": ifrc_breakdown_by_year,
                "participating_national_societies": participating_national_societies,
            },
            "extraction": extraction_tag,
            "confidence": conf,
            "debug": {"raw": raw_window[:5000], "fullpage_variant": is_fullpage_variant},
        }
        out.append(block)

    ctx = infer_upr_document_context(pages=pages)
    for b in out:
        try:
            if isinstance(b, dict):
                b.setdefault("upr_context", ctx)
        except Exception as e:
            logger.debug("Block upr_context setdefault failed: %s", e)
            continue
    return out


# Known hazard labels (older UPR country-plan pages list hazards with icons).
_KNOWN_HAZARDS = frozenset({
    "conflict", "earthquakes", "displacement", "wildfires", "heatwaves",
    "floods", "drought", "storms", "landslides", "epidemics", "cyclones",
    "tsunami", "volcanic", "avalanche", "food insecurity",
})


def extract_hazards(pages: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """
    Extract UPR (older country-plan) "Hazards" section: list of hazards (e.g. Conflict,
    Earthquakes, Displacement, Wildfires, Heatwaves) often shown with icons on the same
    page as Participating National Societies and bilateral support table.
    """
    out: List[Dict[str, Any]] = []
    for p in _first_upr_pages(pages, max_pages=_FUNDING_REQUIREMENTS_MAX_PAGES):
        if not isinstance(p, dict):
            continue
        page_number = p.get("page_number")
        text = (p.get("text") or "")
        if not text.strip():
            continue
        lines = [ln.rstrip("\n") for ln in text.splitlines()]

        hazards_idx = None
        for i, ln in enumerate(lines):
            if _HAZARDS_HEADER_RE.match((ln or "").strip()):
                hazards_idx = i
                break
            # OCR may split or duplicate: "Hazard" or "Hazards" as standalone
            low = (ln or "").strip().lower()
            if low == "hazards" or low == "hazard":
                hazards_idx = i
                break
        if hazards_idx is None:
            continue

        # Collect hazard names in the following lines (stop at next section or blank block).
        hazard_names: List[str] = []
        seen_lower: set[str] = set()
        for ln in lines[hazards_idx + 1 : min(len(lines), hazards_idx + 30)]:
            s = (ln or "").strip()
            if not s:
                continue
            low = s.lower()
            # Stop at next section headers
            if "participating national societies" in low and "bilateral" not in low:
                break
            if "ifrc appeal" in low or "appeal codes" in low:
                break
            if "red cross" in low or "red crescent" in low:
                break
            # Single-word or short phrase: treat as hazard if it matches known or looks like a label
            if len(s) > 50:
                continue
            if low in _KNOWN_HAZARDS:
                if low not in seen_lower:
                    seen_lower.add(low)
                    hazard_names.append(s)
                continue
            for known in _KNOWN_HAZARDS:
                if known in low:
                    if low not in seen_lower:
                        seen_lower.add(low)
                        hazard_names.append(s)
                    break

        if not hazard_names:
            continue

        block = {
            "template": "UPR",
            "block": "hazards",
            "page_number": int(page_number) if isinstance(page_number, int) else None,
            "hazards": hazard_names,
            "extraction": "hazards_v1",
            "confidence": 0.85,
            "debug": {"header_line": lines[hazards_idx].strip()},
        }
        out.append(block)

    ctx = infer_upr_document_context(pages=pages)
    for b in out:
        try:
            if isinstance(b, dict):
                b.setdefault("upr_context", ctx)
        except Exception as e:
            logger.debug("Block upr_context setdefault failed: %s", e)
            continue
    return out


def extract_pns_bilateral_support(pages: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """
    Extract UPR (older country-plan) "Participating National Societies bilateral support
    for YYYY" table: NS names, funding requirement per NS, and optional support-area columns.
    Often on the same page as Hazards and the Participating National Societies list.
    """
    out: List[Dict[str, Any]] = []
    for p in _first_upr_pages(pages, max_pages=_FUNDING_REQUIREMENTS_MAX_PAGES):
        if not isinstance(p, dict):
            continue
        page_number = p.get("page_number")
        text = (p.get("text") or "")
        if not text.strip():
            continue
        window_text = text
        low = window_text.lower()
        m = _PNS_BILATERAL_SUPPORT_RE.search(window_text)
        if not m:
            continue
        year = m.group(1)
        lines = [ln.rstrip("\n") for ln in text.splitlines()]

        # Find start of table (line containing "bilateral support for YYYY")
        start_idx = None
        for i, ln in enumerate(lines):
            if _PNS_BILATERAL_SUPPORT_RE.search((ln or "")):
                start_idx = i
                break
        if start_idx is None:
            continue

        # Find "Total Funding requirement CHF X.XM" and parse rows between start and total (or next section).
        total_funding: Optional[str] = None
        end_idx = min(len(lines), start_idx + 120)
        for i in range(start_idx, end_idx):
            ln = lines[i] or ""
            tm = _TOTAL_FUNDING_REQUIREMENT_RE.search(ln)
            if tm:
                total_funding = tm.group(1).strip()
                end_idx = i
                break
            if i > start_idx + 2 and ("hazards" in ln.lower() or "ifrc appeal" in ln.lower() or "appeal codes" in ln.lower()):
                end_idx = i
                break

        table_lines = lines[start_idx + 1 : end_idx]
        rows: List[Dict[str, Any]] = []
        for ln in table_lines:
            s = (ln or "").strip()
            if not s:
                continue
            low_ln = s.lower()
            if "total funding requirement" in low_ln:
                continue
            if "national society name" in low_ln or ("funding requirement" in low_ln and "climate" in low_ln):
                continue
            # Row: NS name (contains "Red Cross" or "Red Crescent") and optional funding amount
            if "red cross" in low_ln or "red crescent" in low_ln:
                nums = [m.group(0).strip() for m in _NUM_RE.finditer(s)]
                funding_requirement = None
                name = s
                if nums:
                    # First amount-like number (with M, K, or comma/decimal) is usually funding
                    for n in nums:
                        if "m" in n.lower() or "k" in n.lower() or "," in n or ("." in n and len(n) > 1):
                            funding_requirement = n
                            name = s.replace(n, "", 1).strip()
                            break
                    if funding_requirement is None:
                        funding_requirement = nums[0]
                        name = s.replace(nums[0], "", 1).strip()
                name = _norm_ws(name)
                if name:
                    rows.append({"national_society": name, "funding_requirement": funding_requirement})

        if not rows and not total_funding:
            continue

        block = {
            "template": "UPR",
            "block": "pns_bilateral_support",
            "page_number": int(page_number) if isinstance(page_number, int) else None,
            "pns_bilateral_support": {
                "year": year,
                "currency": "CHF" if "chf" in low else None,
                "rows": rows,
                "total_funding_requirement": total_funding,
            },
            "extraction": "pns_bilateral_support_v1",
            "confidence": 0.8,
            "debug": {"raw": "\n".join(table_lines[:30])[:2000]},
        }
        out.append(block)

    ctx = infer_upr_document_context(pages=pages)
    for b in out:
        try:
            if isinstance(b, dict):
                b.setdefault("upr_context", ctx)
        except Exception as e:
            logger.debug("Block upr_context setdefault failed: %s", e)
            continue
    return out


def block_to_embedding_text(block: Dict[str, Any]) -> str:
    """
    Render a UPR (MYR/Planning) visual block into a clear, embedding-friendly text form.
    """
    btype = (block or {}).get("block")
    ctx = (block or {}).get("upr_context")
    ctx_line = None
    try:
        if isinstance(ctx, dict):
            y = ctx.get("document_year") or ctx.get("year")
            dt = ctx.get("doc_type")
            covered = ctx.get("covered_years")
            horizon = ctx.get("planning_horizon_years")
            parts = []
            if dt:
                parts.append(f"doc_type={dt}")
            if y:
                parts.append(f"year={y}")
            if isinstance(covered, list) and covered:
                parts.append("covered_years=" + ",".join([str(int(v)) for v in covered if isinstance(v, (int, float, str))]))
            if isinstance(horizon, list) and horizon:
                parts.append("plan_horizon_years=" + ",".join([str(int(v)) for v in horizon if isinstance(v, (int, float, str))]))
            if parts:
                ctx_line = "UPR context: " + "; ".join(parts)
    except Exception as e:
        logger.debug("ctx_line build failed: %s", e)
        ctx_line = None

    if btype == "in_support_kpis":
        kpis = (block or {}).get("kpis") or {}
        society = (block or {}).get("society") or ""
        header = "UPR visual block: IN SUPPORT OF"
        if society:
            header += f" THE {society}"
        lines = [
            header.strip(),
            "- National Society branches: {}".format(kpis.get("branches", "")),
            "- National Society local units: {}".format(kpis.get("local_units", "")),
            "- National Society volunteers: {}".format(kpis.get("volunteers", "")),
            "- National Society staff: {}".format(kpis.get("staff", "")),
        ]
        if ctx_line:
            lines.insert(1, ctx_line)
        return "\n".join([ln for ln in lines if ln.strip()]).strip()

    if btype == "people_reached":
        pr = (block or {}).get("people_reached") or {}
        lines = [
            "UPR visual block: PEOPLE REACHED",
            "- Emergency Operations: {}".format(pr.get("emergency_operations", "")),
            "- Climate and environment: {}".format(pr.get("climate_and_environment", "")),
            "- Disasters and crises: {}".format(pr.get("disasters_and_crises", "")),
            "- Health and wellbeing: {}".format(pr.get("health_and_wellbeing", "")),
            "- Migration and displacement: {}".format(pr.get("migration_and_displacement", "")),
            "- Values, power and inclusion: {}".format(pr.get("values_power_and_inclusion", "")),
        ]
        if ctx_line:
            lines.insert(1, ctx_line)
        return "\n".join([ln for ln in lines if ln.strip()]).strip()

    if btype == "people_to_be_reached":
        pr = (block or {}).get("people_to_be_reached") or {}
        lines = [
            "UPR visual block: PEOPLE TO BE REACHED",
            "- Emergency Operations: {}".format(pr.get("emergency_operations", "")),
            "- Climate and environment: {}".format(pr.get("climate_and_environment", "")),
            "- Disasters and crises: {}".format(pr.get("disasters_and_crises", "")),
            "- Health and wellbeing: {}".format(pr.get("health_and_wellbeing", "")),
            "- Migration and displacement: {}".format(pr.get("migration_and_displacement", "")),
            "- Values, power and inclusion: {}".format(pr.get("values_power_and_inclusion", "")),
        ]
        if ctx_line:
            lines.insert(1, ctx_line)
        return "\n".join([ln for ln in lines if ln.strip()]).strip()

    if btype == "financial_overview":
        fo = (block or {}).get("financial_overview") or {}
        lines = ["UPR visual block: FINANCIAL OVERVIEW (CHF)"]
        # Keep it compact but unambiguous (v2 schema only).
        if ctx_line:
            lines.append(ctx_line)

        def add_line(label: str, vals: Dict[str, Any]):
            if not isinstance(vals, dict):
                return
            fr = vals.get("funding_requirement")
            fu = vals.get("funding")
            ex = vals.get("expenditure")
            parts = []
            if fr:
                parts.append(f"Funding Requirement: {fr}")
            if fu:
                parts.append(f"Funding: {fu}")
            if ex:
                parts.append(f"Expenditure: {ex}")
            if parts:
                lines.append(f"- {label}: " + "; ".join(parts))

        add_line("IFRC network", (fo or {}).get("ifrc_network") or {})

        sec = (fo or {}).get("ifrc_secretariat") or {}
        if isinstance(sec, dict):
            add_line("IFRC Secretariat - Longer-term", sec.get("longer_term") or {})
            add_line("IFRC Secretariat - Emergency Operations", sec.get("emergency_operations") or {})

        add_line("Participating National Societies", (fo or {}).get("participating_national_societies") or {})
        add_line("HNS other funding sources", (fo or {}).get("hns_other_funding_sources") or {})
        return "\n".join(lines).strip()

    if btype == "funding_requirements":
        fr = (block or {}).get("funding_requirements") or {}
        currency = (fr.get("currency") or "CHF") if isinstance(fr, dict) else "CHF"
        totals = fr.get("totals_by_year") if isinstance(fr, dict) else {}
        breakdown_by_year = fr.get("breakdown_by_year") if isinstance(fr, dict) else {}
        ifrc_breakdown_by_year = fr.get("ifrc_breakdown_by_year") if isinstance(fr, dict) else {}
        pns = fr.get("participating_national_societies") if isinstance(fr, dict) else {}
        lines = [f"UPR visual block: IFRC NETWORK FUNDING REQUIREMENTS ({currency})"]
        if ctx_line:
            lines.append(ctx_line)

        if isinstance(totals, dict) and totals:
            for y in sorted(totals.keys()):
                lines.append(f"- Total {y}: {totals.get(y)}")

        if isinstance(breakdown_by_year, dict) and breakdown_by_year:
            for y in sorted(breakdown_by_year.keys()):
                b = breakdown_by_year.get(y) or {}
                if not isinstance(b, dict) or not b:
                    continue
                parts = []
                if b.get("through_ifrc"):
                    parts.append(f"Through the IFRC: {b.get('through_ifrc')}")
                if b.get("through_participating_national_societies"):
                    parts.append(f"Through Participating National Societies: {b.get('through_participating_national_societies')}")
                if b.get("host_national_society"):
                    parts.append(f"Host National Society: {b.get('host_national_society')}")
                if parts:
                    lines.append(f"- Breakdown {y}: " + "; ".join(parts))

        if isinstance(ifrc_breakdown_by_year, dict) and ifrc_breakdown_by_year:
            for y in sorted(ifrc_breakdown_by_year.keys()):
                b = ifrc_breakdown_by_year.get(y) or {}
                if not isinstance(b, dict) or not b:
                    continue
                if b.get("ongoing_emergency_operations"):
                    lines.append(f"- IFRC breakdown {y} (ongoing emergency operations): {b.get('ongoing_emergency_operations')}")
                sp = b.get("strategic_priorities")
                if isinstance(sp, dict) and sp:
                    # Stable ordering for known keys
                    key_order = [
                        "climate_and_environment",
                        "disasters_and_crises",
                        "health_and_wellbeing",
                        "migration_and_displacement",
                        "values_power_and_inclusion",
                    ]
                    emitted = set()
                    parts = []
                    for k in key_order:
                        if k in sp:
                            parts.append(f"{k.replace('_', ' ')}: {sp.get(k)}")
                            emitted.add(k)
                    for k in sorted([k for k in sp.keys() if k not in emitted]):
                        parts.append(f"{k.replace('_', ' ')}: {sp.get(k)}")
                    if parts:
                        lines.append(f"- IFRC breakdown {y} (strategic priorities): " + "; ".join(parts))
                if b.get("enabling_functions"):
                    lines.append(f"- IFRC breakdown {y} (enabling functions): {b.get('enabling_functions')}")

        if isinstance(pns, dict) and pns:
            bi = pns.get("bilateral") if isinstance(pns.get("bilateral"), list) else []
            ml = pns.get("multilateral") if isinstance(pns.get("multilateral"), list) else []
            if bi:
                lines.append("- Participating National Societies (bilateral): " + "; ".join([str(x) for x in bi[:50]]))
            if ml:
                lines.append("- Participating National Societies (multilateral): " + "; ".join([str(x) for x in ml[:50]]))

        return "\n".join([ln for ln in lines if ln.strip()]).strip()

    if btype == "hazards":
        hazards_list = (block or {}).get("hazards") or []
        if isinstance(hazards_list, list) and hazards_list:
            lines = ["UPR visual block: HAZARDS", "- " + "; ".join([str(h) for h in hazards_list])]
            if ctx_line:
                lines.insert(1, ctx_line)
            return "\n".join(lines).strip()
        return "UPR visual block: HAZARDS (no hazards extracted)"

    if btype == "pns_bilateral_support":
        pns_bi = (block or {}).get("pns_bilateral_support") or {}
        if not isinstance(pns_bi, dict):
            return _norm_ws(str(block))
        year = pns_bi.get("year") or ""
        currency = pns_bi.get("currency") or "CHF"
        total = pns_bi.get("total_funding_requirement")
        rows = pns_bi.get("rows") or []
        lines = [f"UPR visual block: PARTICIPATING NATIONAL SOCIETIES BILATERAL SUPPORT FOR {year} ({currency})"]
        if ctx_line:
            lines.append(ctx_line)
        for r in rows[:80]:
            if isinstance(r, dict):
                ns = r.get("national_society") or ""
                fr = r.get("funding_requirement")
                if fr:
                    lines.append(f"- {ns}: {fr}")
                else:
                    lines.append(f"- {ns}")
        if total:
            lines.append(f"- Total Funding requirement: {total} {currency}")
        return "\n".join([ln for ln in lines if ln.strip()]).strip()

    # Fallback
    return _norm_ws(str(block))


def extract_upr_visual_blocks(
    *,
    pages: Optional[List[Dict[str, Any]]],
    document_title: Optional[str] = None,
    document_filename: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Extract all known UPR visual blocks from the expected UPR visual pages (1–5).

    This is the preferred entry-point for UPR visual chunking because it:
    - runs all visual-type extractors in one place
    - attaches a single, consistent `upr_context` to every extracted block
    """
    if not pages:
        return []

    ctx = infer_upr_document_context(title=document_title, filename=document_filename, pages=pages)

    # Visuals are expected on pages 1–5 (older layouts may place some visuals on pages 3–5).
    upr_pages = (pages or [])[:5]

    # Make context available to extractors without changing signatures.
    # This is only used in-memory during extraction (not persisted).
    try:
        for p in upr_pages:
            if isinstance(p, dict):
                p["_upr_context"] = ctx
    except Exception as e:
        logger.debug("_upr_context set failed: %s", e)

    blocks: List[Dict[str, Any]] = []
    for extractor in _upr_visual_extractors_for_context(ctx):
        try:
            blocks.extend(extractor(upr_pages))
        except Exception as e:
            logger.debug("extractor %s failed: %s", extractor.__name__ if hasattr(extractor, "__name__") else "?", e)
            continue

    # Normalize context across all blocks
    for b in blocks:
        try:
            if isinstance(b, dict):
                b["upr_context"] = ctx
        except Exception as e:
            logger.debug("Block upr_context assign failed: %s", e)
            continue

    return blocks


def load_upr_visual_training_cases(cases_dir: str) -> List[Dict[str, Any]]:
    """
    Load UPR visual extraction "training cases" from a directory.

    This loader is intentionally flexible so you can iterate quickly without code changes.
    Supported case formats:

    1) Single-file cases (recommended):
       - `*.upr_case.json` anywhere under `cases_dir`
       - JSON shape:
         {
           "name": "...",
           "input": { "title": "...", "filename": "...", "pages": [...] },
           "expected": { "blocks": [...] }   // optional
         }

    2) Folder cases:
       - `<case>/input.json` required
       - `<case>/expected.json` optional
    """
    root = Path(cases_dir)
    if not root.exists():
        return []

    cases: List[Dict[str, Any]] = []

    # Format (1): *.upr_case.json
    for p in root.rglob("*.upr_case.json"):
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(obj, dict) and isinstance(obj.get("input"), dict):
                obj.setdefault("name", p.stem)
                obj.setdefault("_path", str(p))
                cases.append(obj)
        except Exception as e:
            logger.debug("input.json case load failed: %s", e)
            continue

    # Format (2): */input.json
    for p in root.rglob("input.json"):
        try:
            input_obj = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(input_obj, dict):
                continue
            exp_path = p.parent / "expected.json"
            expected_obj = None
            if exp_path.exists():
                try:
                    expected_obj = json.loads(exp_path.read_text(encoding="utf-8"))
                except Exception as e:
                    logger.debug("expected.json load failed: %s", e)
                    expected_obj = None
            cases.append(
                {
                    "name": p.parent.name,
                    "input": input_obj,
                    "expected": expected_obj,
                    "_path": str(p),
                }
            )
        except Exception as e:
            logger.debug("expected case load failed: %s", e)
            continue

    # Stable ordering
    cases.sort(key=lambda c: str(c.get("name") or ""))
    return cases


def evaluate_upr_visual_extraction_cases(cases_dir: str) -> Dict[str, Any]:
    """
    Run extraction against a training-cases directory and return a compact summary.

    This is meant for local iterative improvement (not production runtime).
    """
    cases = load_upr_visual_training_cases(cases_dir)
    out: Dict[str, Any] = {"cases": [], "count": len(cases)}

    for c in cases:
        try:
            inp = (c or {}).get("input") or {}
            pages = inp.get("pages")
            title = inp.get("title")
            filename = inp.get("filename")
            blocks = extract_upr_visual_blocks(pages=pages, document_title=title, document_filename=filename)

            expected = (c or {}).get("expected") or {}
            exp_blocks = expected.get("blocks") if isinstance(expected, dict) else None

            # Very lightweight comparison: just count block types when expected is present.
            produced_types = [str((b or {}).get("block") or "") for b in blocks if isinstance(b, dict)]
            exp_types = None
            if isinstance(exp_blocks, list):
                exp_types = [str((b or {}).get("block") or "") for b in exp_blocks if isinstance(b, dict)]

            out["cases"].append(
                {
                    "name": c.get("name"),
                    "path": c.get("_path"),
                    "produced_block_types": produced_types,
                    "expected_block_types": exp_types,
                    "produced_count": len(blocks),
                    "expected_count": len(exp_blocks) if isinstance(exp_blocks, list) else None,
                }
            )
        except Exception as e:
            logger.debug("Run case failed: %s", e)
            out["cases"].append({"name": c.get("name"), "path": c.get("_path"), "error": True})

    return out
