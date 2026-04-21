"""
UPR Document Answering Helpers

This module contains deterministic extraction/answering logic that is specific to
UPR-style documents (visual blocks embedded as structured metadata, plus a few
OCR-text heuristics for common UPR panels).

UPR context:
- UPR (Unified Planning and Reporting) runs annually (started 2023 and continues through 2026+).
- For most countries and years there is typically a Plan, Midyear report, and Annual report.
- These PDFs are infographic-heavy, with repeated visuals expected on pages 1–5.
- Because normal OCR/table chunking is unreliable for infographics, upstream chunking attaches
  structured JSON under `metadata["upr"]` (see `app.services.upr_visual_chunking`).

Keeping this separate prevents `routes/ai_documents.py` from accumulating
UPR-only logic and makes it easier to evolve UPR handling independently.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
# Numeric token, allowing thousand separators and magnitude suffixes (e.g. 1.4M).
_NUM_RE = re.compile(r"\b\d[\d,]*(?:\.\d+)?[mkMK]?\b")


def _norm_key(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _infer_country_label(doc_title: str | None, doc_filename: str | None) -> str | None:
    """
    Best-effort country label from document title/filename.

    Note: This is duplicated from `routes/ai_documents.py` on purpose to keep this
    module independent of route-layer imports.
    """
    for s in ((doc_title or "").strip(), (doc_filename or "").strip()):
        if not s:
            continue
        base = s
        base = re.sub(r"\.(pdf|docx|doc|txt|md|html|xlsx|xls)$", "", base, flags=re.IGNORECASE).strip()
        if not base:
            continue
        parts = [p for p in re.split(r"[_\-\s]+", base) if p]
        if not parts:
            continue
        first = parts[0].strip()
        if not first:
            continue
        norm = _norm_key(first)
        if not norm:
            continue
        if norm == "turkiye":
            return "Türkiye"
        return first[0].upper() + first[1:]
    return None


def detect_people_reached_intent(query: str) -> str | None:
    """
    Detect People Reached category queries.

    Examples:
      - "PEOPLE REACHED in Disasters and crises"
      - "people reached disasters and crises"
    """
    q = (query or "").lower()
    # allow normalized lookup for compact phrases
    _ = _norm_key(query or "")

    # Category detection (allow partial mentions)
    if ("disasters" in q) or ("and crises" in q) or ("crises" in q and "disaster" in q):
        return "disasters_and_crises"
    if "emergency operations" in q or ("emergency" in q and "operations" in q):
        return "emergency_operations"
    if "climate" in q and "environment" in q:
        return "climate_and_environment"
    if "health" in q and "wellbeing" in q:
        return "health_and_wellbeing"
    if "migration" in q and "displacement" in q:
        return "migration_and_displacement"
    if ("values" in q and "inclusion" in q) or ("power" in q and "inclusion" in q):
        return "values_power_and_inclusion"
    return None


def is_people_to_be_reached_query(query: str) -> bool:
    q = (query or "").lower()
    qk = _norm_key(query or "")
    return ("tobereached" in qk) or ("to be reached" in q) or ("people to be reached" in q)


def people_reached_query_text(category: str | None, *, to_be: bool = False) -> str:
    prefix = "people to be reached" if to_be else "people reached"
    if not category:
        return prefix
    return {
        "emergency_operations": f"{prefix} emergency operations",
        "climate_and_environment": f"{prefix} climate and environment",
        "disasters_and_crises": f"{prefix} disasters and crises",
        "health_and_wellbeing": f"{prefix} health and wellbeing",
        "migration_and_displacement": f"{prefix} migration and displacement",
        "values_power_and_inclusion": f"{prefix} values power and inclusion",
    }.get(category, prefix)


def _extract_people_reached_value(content: str, category: str) -> str | None:
    """
    Extract People Reached value for a category from OCR/PDF text blocks.
    Handles column-aligned layouts by matching label position to a nearby numeric row.
    """
    t = (content or "")
    if not t.strip():
        return None
    lines = [ln.rstrip("\n") for ln in t.splitlines()]

    terms_by_cat = {
        "emergency_operations": ["emergency", "operations"],
        "climate_and_environment": ["climate", "environment"],
        "disasters_and_crises": ["disasters", "crises"],
        "health_and_wellbeing": ["health", "wellbeing"],
        "migration_and_displacement": ["migration", "displacement"],
        "values_power_and_inclusion": ["values", "inclusion"],
    }
    terms = terms_by_cat.get(category, [])
    if not terms:
        return None

    # Locate label position (best-effort).
    label_idx = None
    label_pos = None
    for i, ln in enumerate(lines):
        low = ln.lower()
        hits = [low.find(t) for t in terms if low.find(t) != -1]
        if hits:
            p = min(hits)
            label_idx, label_pos = i, p
            break

    if label_idx is None or label_pos is None:
        return None

    # Search nearby for a numeric row with multiple numbers.
    for j in range(label_idx, min(len(lines), label_idx + 10)):
        row = lines[j]
        nums = list(_NUM_RE.finditer(row))
        if len(nums) >= 3:
            best = min(nums, key=lambda m: abs(((m.start() + m.end()) / 2.0) - float(label_pos)))
            return best.group(0).strip()
    for j in range(label_idx - 1, max(-1, label_idx - 10), -1):
        row = lines[j]
        nums = list(_NUM_RE.finditer(row))
        if len(nums) >= 3:
            best = min(nums, key=lambda m: abs(((m.start() + m.end()) / 2.0) - float(label_pos)))
            return best.group(0).strip()
    return None


def extract_people_reached_value(content: str, category: str) -> str | None:
    """
    Public wrapper for People Reached OCR extraction.
    Kept to provide a stable API surface for callers outside this module.
    """
    return _extract_people_reached_value(content, category)


def try_answer_people_reached(query: str, results: list[dict]) -> tuple[str, dict] | None:
    category = detect_people_reached_intent(query)
    if not category:
        return None
    label = "People to be reached" if is_people_to_be_reached_query(query) else "People reached"
    for r in results or []:
        content = (r or {}).get("content") or ""
        val = _extract_people_reached_value(content, category)
        if not val:
            continue
        country = _infer_country_label(r.get("document_title"), r.get("document_filename")) or "this country"
        cat_label = {
            "emergency_operations": "Emergency Operations",
            "climate_and_environment": "Climate and environment",
            "disasters_and_crises": "Disasters and crises",
            "health_and_wellbeing": "Health and wellbeing",
            "migration_and_displacement": "Migration and displacement",
            "values_power_and_inclusion": "Values, power and inclusion",
        }.get(category, category)
        return (f"In **{country}**, **{label}** in **{cat_label}** is **{val}**.", r)
    return None


def detect_participating_national_societies_intent(query: str) -> str | None:
    """
    Detect queries asking for the "Participating National Societies" list from Planning visuals.
    Returns one of: "both" | "bilateral" | "multilateral"
    """
    q = (query or "").lower()
    qk = _norm_key(query or "")

    has_trigger = ("participating national societies" in q) or (
        "participating" in q and "national societ" in q
    ) or ("participatingnationalsocieties" in qk)
    if not has_trigger:
        return None

    if "multilateral" in q or "multilater" in q or "with*" in qk or ("with" in q and "*" in q):
        return "multilateral"
    if "bilateral" in q or "bilater" in q or "no*" in qk or ("no" in q and "*" in q) or ("without" in q and "*" in q):
        return "bilateral"
    return "both"


def _extract_participating_national_societies(content: str) -> dict | None:
    """
    Parse a Participating National Societies list from OCR text.
    Splits names into bilateral (no *) vs multilateral (with *).
    """
    t = (content or "")
    if not t.strip():
        return None
    lines = [ln.rstrip("\\n") for ln in t.splitlines()]

    start = None
    for i, ln in enumerate(lines):
        s = (ln or "").strip()
        low = s.lower()
        if low == "participating national societies":
            start = i + 1
            break
        if low == "participating" and i + 1 < len(lines):
            nxt = (lines[i + 1] or "").strip().lower()
            if nxt == "national societies":
                start = i + 2
                break
        if "participating" in low and i + 1 < len(lines):
            nxt = (lines[i + 1] or "").strip().lower()
            if "national societies" in nxt:
                start = i + 2
                break
        if "national societies" in low and i - 1 >= 0:
            prv = (lines[i - 1] or "").strip().lower()
            if "participating" in prv:
                start = i + 1
                break
    if start is None:
        return None

    body: list[str] = []
    for ln in lines[start:]:
        s = (ln or "").strip()
        if not s:
            continue
        low = s.lower()
        if ("hazards" in low) or ("ifrc country delegation" in low):
            break
        if "national societies which have contributed" in low and "multilateral" in low:
            break
        if ("ifrc" in low and "breakdown" in low):
            break
        if re.fullmatch(r"[-_—–]{2,}", s):
            continue
        body.append(s)

    if not body:
        return None

    names_raw: list[str] = []
    pending_prefix: str | None = None

    def add_name(name: str):
        nm = (name or "").strip()
        if nm:
            names_raw.append(nm)

    for line in body:
        cells = [c.strip() for c in re.split(r"\s{2,}", line) if c.strip()]
        if not cells:
            continue

        if pending_prefix:
            for c in cells:
                cl = c.lower()
                if cl in {"cross", "cross*", "crescent", "crescent*"}:
                    add_name(pending_prefix + " " + c)
                    pending_prefix = None
                    break

        for c in cells:
            cl = c.lower()
            if "mdr" in cl:
                continue
            if ("total" in cl and "chf" in cl) or ("projected funding requirements" in cl):
                continue
            if cl.startswith("emergency appeal") or cl.startswith("longer-term needs") or cl.startswith("longer term needs"):
                continue

            if ("red cross" in cl) or ("red crescent" in cl):
                add_name(c)
                continue

            if cl.endswith(" red") and ("national red" in cl or cl.endswith("national red")):
                pending_prefix = c

    if not names_raw:
        return None

    seen: set[str] = set()
    bilateral: list[str] = []
    multilateral: list[str] = []
    raw_out: list[str] = []
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

    if not bilateral and not multilateral:
        return None

    return {"bilateral": bilateral, "multilateral": multilateral, "raw": raw_out}


def extract_participating_national_societies(content: str) -> dict | None:
    """
    Public wrapper for Participating National Societies OCR extraction.
    Kept to provide a stable API surface for callers outside this module.
    """
    return _extract_participating_national_societies(content)


def try_answer_participating_national_societies(query: str, results: list[dict]) -> tuple[str, dict] | None:
    intent = detect_participating_national_societies_intent(query)
    if not intent:
        return None

    def extract_pns_amount(text: str) -> str | None:
        t = (text or "")
        low = t.lower()
        key = "through participating national societies"
        pos = low.find(key)
        if pos == -1:
            return None
        window = t[pos : min(len(t), pos + 260)]
        nums = list(_NUM_RE.finditer(window))
        if not nums:
            return None
        val = nums[0].group(0).strip()
        if "chf" in window.lower() and "chf" not in val.lower():
            val = f"{val} CHF"
        return val

    for r in results or []:
        content = (r or {}).get("content") or ""
        parsed = _extract_participating_national_societies(content)
        if not parsed:
            continue
        country = _infer_country_label(r.get("document_title"), r.get("document_filename")) or "this plan"
        bi = parsed.get("bilateral") or []
        ml = parsed.get("multilateral") or []
        pns_amt = extract_pns_amount(content)

        if intent == "bilateral":
            if bi:
                parts = [f"In **{country}**, **Participating National Societies (bilateral / no \\*)**: " + "; ".join(bi) + "."]
                if pns_amt:
                    parts.append(f"- **Through Participating National Societies (PNS funding)**: **{pns_amt}**")
                return ("\n".join(parts).strip(), r)
            continue
        if intent == "multilateral":
            if ml:
                parts = [f"In **{country}**, **Participating National Societies (multilateral / with \\*)**: " + "; ".join(ml) + "."]
                if pns_amt:
                    parts.append(f"- **Through Participating National Societies (PNS funding)**: **{pns_amt}**")
                return ("\n".join(parts).strip(), r)
            continue

        parts = [f"In **{country}**, **Participating National Societies**:"]
        if pns_amt:
            parts.append(f"- **Through Participating National Societies (PNS funding)**: **{pns_amt}**")
        if bi:
            parts.append(f"- **Bilateral (no \\*)**: " + "; ".join(bi))
        if ml:
            parts.append(f"- **Multilateral (with \\*)**: " + "; ".join(ml))
        return ("\n".join(parts).strip(), r)

    return None


def _detect_metric_intent(query: str) -> str | None:
    q = _norm_key(query)
    if not q:
        return None
    if "branch" in q or "branches" in q:
        return "branches"
    if "localunit" in q or ("local" in q and "unit" in q):
        return "local_units"
    if "volunteer" in q or "volunteers" in q:
        return "volunteers"
    if "staff" in q:
        return "staff"
    return None


def try_answer_from_upr_metadata(query: str, results: list[dict]) -> tuple[str, dict] | None:
    """
    Deterministically answer from UPR visual chunks (metadata['upr']).
    This is the preferred path when present because it avoids OCR/layout ambiguity.
    """
    metric = _detect_metric_intent(query)
    pr_category = detect_people_reached_intent(query)
    pns_intent = detect_participating_national_societies_intent(query)

    qk = _norm_key(query or "")

    def infer_country_from_context(upr: dict[str, Any], r: dict) -> str | None:
        # Prefer explicit query mention
        if "afghanistan" in qk:
            return "Afghanistan"
        if "syria" in qk or "syrian" in qk:
            return "Syria"
        if "turkiye" in qk or "türkiye" in (query or "").lower():
            return "Türkiye"
        society = (upr.get("society") or "").strip()
        if society:
            s = society.lower()
            if "afghan" in s:
                return "Afghanistan"
            if "turk" in s or "türkiye" in s:
                return "Türkiye"
        return _infer_country_label(r.get("document_title"), r.get("document_filename"))

    for r in results or []:
        md = (r or {}).get("metadata") or {}
        if not isinstance(md, dict):
            continue
        upr = md.get("upr")
        if not isinstance(upr, dict):
            continue

        block = (upr.get("block") or "").strip()

        # IN SUPPORT KPI cards (4 indicators)
        if metric and block == "in_support_kpis":
            kpis = upr.get("kpis") if isinstance(upr.get("kpis"), dict) else {}
            val = (kpis or {}).get(metric)
            if val:
                country = infer_country_from_context(upr, r) or "this country"
                label = {
                    "branches": "National Society branches",
                    "local_units": "National Society local units",
                    "volunteers": "National Society volunteers",
                    "staff": "National Society staff",
                }.get(metric, metric)
                # Attach Indicator Bank ID when known (for downstream linking / UI hints)
                bank_ids = upr.get("kpi_indicator_bank_ids") if isinstance(upr.get("kpi_indicator_bank_ids"), dict) else {}
                bank_id = bank_ids.get(metric)
                if bank_id:
                    return (f"In **{country}**, **{label}** is **{val}**. (Indicator Bank ID: {int(bank_id)})", r)
                return (f"In **{country}**, **{label}** is **{val}**.", r)

        # PEOPLE REACHED (6 categories)
        if pr_category and block in {"people_reached", "people_to_be_reached"}:
            if block == "people_to_be_reached":
                pr = upr.get("people_to_be_reached") if isinstance(upr.get("people_to_be_reached"), dict) else {}
                pr_label = "People to be reached"
            else:
                pr = upr.get("people_reached") if isinstance(upr.get("people_reached"), dict) else {}
                pr_label = "People reached"
            val = (pr or {}).get(pr_category)
            if val:
                country = infer_country_from_context(upr, r) or "this country"
                cat_label = {
                    "emergency_operations": "Emergency Operations",
                    "climate_and_environment": "Climate and environment",
                    "disasters_and_crises": "Disasters and crises",
                    "health_and_wellbeing": "Health and wellbeing",
                    "migration_and_displacement": "Migration and displacement",
                    "values_power_and_inclusion": "Values, power and inclusion",
                }.get(pr_category, pr_category)
                return (f"In **{country}**, **{pr_label}** in **{cat_label}** is **{val}**.", r)

        # PARTICIPATING NATIONAL SOCIETIES (Planning funding requirements visual)
        if pns_intent and block == "funding_requirements":
            fr = upr.get("funding_requirements") if isinstance(upr.get("funding_requirements"), dict) else {}
            pns = fr.get("participating_national_societies") if isinstance(fr.get("participating_national_societies"), dict) else {}
            bi = pns.get("bilateral") if isinstance(pns.get("bilateral"), list) else []
            ml = pns.get("multilateral") if isinstance(pns.get("multilateral"), list) else []
            if not bi and not ml:
                continue

            country = infer_country_from_context(upr, r) or "this plan"
            totals_by_year = fr.get("totals_by_year") if isinstance(fr.get("totals_by_year"), dict) else {}
            breakdown_by_year = fr.get("breakdown_by_year") if isinstance(fr.get("breakdown_by_year"), dict) else {}
            currency = (fr.get("currency") or "CHF") if isinstance(fr, dict) else "CHF"

            years_in_q = _YEAR_RE.findall(query or "")
            year = None
            for y in years_in_q:
                if y in (breakdown_by_year or {}) or y in (totals_by_year or {}):
                    year = y
                    break
            if year is None:
                # Default year logic:
                # - Plans can be multi-year (e.g. a 2024 plan covers 2024–2026). In that case,
                #   prefer the *document start year* when present.
                ctx = upr.get("upr_context") if isinstance(upr.get("upr_context"), dict) else {}
                doc_year = None
                try:
                    doc_year = str((ctx or {}).get("document_year") or (ctx or {}).get("year") or "").strip() or None
                except Exception as e:
                    logger.debug("doc_year extraction failed: %s", e)
                    doc_year = None

                all_years = []
                try:
                    all_years = sorted(
                        set([str(y) for y in list((breakdown_by_year or {}).keys()) + list((totals_by_year or {}).keys()) if str(y)])
                    )
                except Exception as e:
                    logger.debug("all_years extraction failed: %s", e)
                    all_years = []

                if doc_year and doc_year in all_years:
                    year = doc_year
                elif all_years:
                    # If we can't infer doc year, default to the earliest year shown (start of horizon).
                    year = all_years[0]

            def fmt_amt(v: Any) -> str | None:
                if v is None:
                    return None
                s = str(v).strip()
                if not s:
                    return None
                if currency and currency.lower() not in s.lower():
                    return f"{s} {currency}"
                return s

            pns_amt = None
            total_amt = None
            try:
                if year and isinstance(breakdown_by_year, dict):
                    row = breakdown_by_year.get(year) if isinstance(breakdown_by_year.get(year), dict) else {}
                    pns_amt = fmt_amt((row or {}).get("through_participating_national_societies"))
                if year and isinstance(totals_by_year, dict):
                    total_amt = fmt_amt(totals_by_year.get(year))
            except Exception as e:
                logger.debug("pns_amt/total_amt extraction failed: %s", e)
                pns_amt = None
                total_amt = None

            if pns_intent == "bilateral":
                if bi:
                    parts = [f"In **{country}**, **Participating National Societies (bilateral / no \\*)**: " + "; ".join([str(x) for x in bi]) + "."]
                    if pns_amt and year:
                        parts.append(f"- **Through Participating National Societies (PNS funding)** for **{year}**: **{pns_amt}**")
                    if total_amt and year:
                        parts.append(f"- **Total federation network funding requirement** for **{year}**: **{total_amt}** (overall total, not the PNS amount)")
                    return ("\n".join(parts).strip(), r)
                continue
            if pns_intent == "multilateral":
                if ml:
                    parts = [f"In **{country}**, **Participating National Societies (multilateral / with \\*)**: " + "; ".join([str(x) for x in ml]) + "."]
                    if pns_amt and year:
                        parts.append(f"- **Through Participating National Societies (PNS funding)** for **{year}**: **{pns_amt}**")
                    if total_amt and year:
                        parts.append(f"- **Total federation network funding requirement** for **{year}**: **{total_amt}** (overall total, not the PNS amount)")
                    return ("\n".join(parts).strip(), r)
                continue

            parts = [f"In **{country}**, **Participating National Societies**:"]
            if pns_amt and year:
                parts.append(f"- **Through Participating National Societies (PNS funding)** for **{year}**: **{pns_amt}**")
            if total_amt and year:
                parts.append(f"- **Total federation network funding requirement** for **{year}**: **{total_amt}** (overall total, not the PNS amount)")
            if bi:
                parts.append("- **Bilateral (no \\*)**: " + "; ".join([str(x) for x in bi]))
            if ml:
                parts.append("- **Multilateral (with \\*)**: " + "; ".join([str(x) for x in ml]))
            return ("\n".join(parts).strip(), r)

    return None
