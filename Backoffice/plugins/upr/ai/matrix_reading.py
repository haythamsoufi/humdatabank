"""Interpret Unified Plan/Report form matrices for AI validation.

Turns opaque disagg keys (e.g. ``HNS - Resilience - Climate and environment``)
into a compact cell table, totals, and like-for-like PDF comparison notes so
the LLM is not asked to invent a mapping from a summed "matrix total".
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

_YEAR_RE = re.compile(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)")
_PLUS_OFFSET_RE = re.compile(r"\[\s*\[?\s*assignment_period\s*\]?\s*\+\s*(\d+)\s*\]", re.I)
_NUM_RE = re.compile(r"[-+]?\d[\d,\u00A0\u202F ]*(?:\.\d+)?")
_MAG_RE = re.compile(r"^\s*([-+]?\d+(?:\.\d+)?)\s*([kmb])\s*$", re.I)

_SP_KEYS = (
    ("emergency_operations", ("emergency operations", "emergency appeal", "ea1", "ea2", "ea3")),
    ("climate_and_environment", ("climate", "environment")),
    ("disasters_and_crises", ("disaster", "crises", "crisis")),
    ("health_and_wellbeing", ("health", "wellbeing", "well-being")),
    ("migration_and_displacement", ("migration", "displacement")),
    ("values_power_and_inclusion", ("values", "inclusion", "pgi")),
    ("enabling_functions", ("enabling", "efs", "ef1", "ef2", "ef3", "ef4")),
)

# Compact form keys: 2027_SP1, 2026_SP3 (people-to-be-reached year × Strategic Priority).
_SP_CODE_MAP = {
    "sp1": ("climate_and_environment", "climate and environment"),
    "sp2": ("disasters_and_crises", "disasters and crises"),
    "sp3": ("health_and_wellbeing", "health and wellbeing"),
    "sp4": ("migration_and_displacement", "migration and displacement"),
    "sp5": ("values_power_and_inclusion", "values power and inclusion"),
    "eo": ("emergency_operations", "emergency operations"),
    "efs": ("enabling_functions", "enabling functions"),
    "ef1": ("enabling_functions", "enabling functions"),
    "ef2": ("enabling_functions", "enabling functions"),
    "ef3": ("enabling_functions", "enabling functions"),
    "ef4": ("enabling_functions", "enabling functions"),
}
_COMPACT_YEAR_SP_RE = re.compile(
    r"^(?P<year>19\d{2}|20\d{2})[_ /\-]+(?P<code>SP[1-5]|EO|EFs?|EF[1-4])\b",
    re.I,
)

_PROGRAMME_KEYS = (
    ("resilience", "Resilience (longer-term)"),
    ("response", "Response (emergency)"),
)

_HEADER_KEY_RE = re.compile(r"^(col\s*-?\s*header|header\|)", re.I)


def _norm_key(raw: str) -> str:
    s = str(raw or "")
    s = s.replace("Climateand", "Climate and")
    s = s.replace("Disastersand", "Disasters and")
    s = re.sub(r"\bHNS-\s*", "HNS - ", s, flags=re.I)
    s = re.sub(r"\s*-\s*", " - ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _norm_text(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


def parse_upr_number(value: Any) -> Optional[float]:
    """Parse CHF / people figures that may use commas or K/M suffixes."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return float(value)
    if isinstance(value, float):
        return value if value == value else None  # NaN
    s = str(value).strip()
    if not s:
        return None
    mag = _MAG_RE.match(s.replace(",", ""))
    if mag:
        n = float(mag.group(1))
        suf = mag.group(2).lower()
        return n * (1_000 if suf == "k" else 1_000_000 if suf == "m" else 1_000_000_000)
    m = _NUM_RE.search(s)
    if not m:
        return None
    token = (m.group(0) or "").replace(",", "").replace("\u00a0", "").replace("\u202f", "").replace(" ", "")
    try:
        return float(token)
    except ValueError:
        return None


def classify_sp(text: str) -> Tuple[Optional[str], Optional[str]]:
    n = _norm_text(text)
    if not n:
        return None, None
    code = n.replace(" ", "")
    mapped = _SP_CODE_MAP.get(code)
    if mapped:
        return mapped
    for key, needles in _SP_KEYS:
        if any(needle in n for needle in needles):
            label = key.replace("_", " ")
            return key, label
    return None, None


def classify_actor(text: str) -> Optional[str]:
    n = _norm_text(text)
    if not n:
        return None
    if n in {"hns", "host ns", "host national society"} or n.startswith("hns"):
        return "HNS"
    if "ifrc secretariat" in n or n == "ifrc":
        return "IFRC Secretariat"
    if n in {"pns", "participating national societies"}:
        return "PNS"
    return None


def classify_programme(text: str) -> Optional[str]:
    n = _norm_text(text)
    for needle, label in _PROGRAMME_KEYS:
        if needle in n:
            return label
    return None


def parse_matrix_cell_key(key: str) -> Dict[str, Any]:
    """Split a resolved disagg label into actor / programme / SP / year."""
    original = str(key or "").strip()
    s = _norm_key(original)
    out: Dict[str, Any] = {
        "raw": original,
        "year": None,
        "actor": None,
        "programme": None,
        "sp_key": None,
        "sp_label": None,
        "is_header": bool(_HEADER_KEY_RE.match(s)),
        "remainder": None,
    }
    if out["is_header"]:
        return out

    compact = _COMPACT_YEAR_SP_RE.match(s) or _COMPACT_YEAR_SP_RE.match(original.replace(" ", "_"))
    if compact:
        out["year"] = int(compact.group("year"))
        sp_key, sp_label = classify_sp(compact.group("code"))
        out["sp_key"] = sp_key
        out["sp_label"] = sp_label
        return out

    parts = [p.strip() for p in re.split(r"\s+-\s+", s) if p.strip()]
    leftover: List[str] = []
    for part in parts:
        if out["year"] is None:
            ym = _YEAR_RE.search(part)
            if ym and _norm_text(part) == ym.group(1):
                out["year"] = int(ym.group(1))
                continue
        sp_key, sp_label = classify_sp(part)
        if sp_key and out["sp_key"] is None:
            out["sp_key"] = sp_key
            out["sp_label"] = sp_label
            continue
        programme = classify_programme(part)
        if programme and out["programme"] is None:
            out["programme"] = programme
            continue
        actor = classify_actor(part)
        if actor and out["actor"] is None:
            out["actor"] = actor
            continue
        leftover.append(part)

    if leftover and out["actor"] is None:
        # Bilateral matrices use the National Society name (or unresolved lookup row id) as the row.
        joined = " - ".join(leftover)
        if joined and not classify_sp(joined)[0]:
            if re.fullmatch(r"\d+", joined):
                out["actor"] = f"PNS #{joined}"
            else:
                out["actor"] = joined
            leftover = []
    if leftover:
        out["remainder"] = " - ".join(leftover)
    return out


def year_slot_from_context(context: Dict[str, Any]) -> Optional[int]:
    """Resolve which planning year a funding matrix belongs to (period, +1, +2)."""
    try:
        base = int(context["period_year"]) if context.get("period_year") is not None else None
    except (TypeError, ValueError):
        base = None
    blob = " ".join(
        str(context.get(k) or "")
        for k in ("subsection_name", "section_name", "upr_effective_label", "form_item_label")
    )
    m = _PLUS_OFFSET_RE.search(blob)
    if m and base is not None:
        return base + int(m.group(1))
    # Unresolved Jinja-style "+1" / "+2" without the full placeholder.
    if base is not None:
        if re.search(r"\+2\b", blob):
            return base + 2
        if re.search(r"\+1\b", blob):
            return base + 1
    years = [int(y) for y in _YEAR_RE.findall(blob)]
    if years:
        return max(years)
    return base


def _is_header_cell(key: str, parsed: Dict[str, Any]) -> bool:
    if parsed.get("is_header"):
        return True
    s = _norm_text(key)
    return s.startswith("col header") or "header|" in str(key).lower()


def interpret_upr_matrix(context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Build a structured reading of the form matrix plus PDF comparison notes."""
    kind = str(context.get("upr_item_kind") or "")
    if kind in ("", "comments", "other", "ns_kpis"):
        return None
    disagg = context.get("disagg_values")
    if not isinstance(disagg, dict) or not disagg:
        return None

    year_slot = year_slot_from_context(context)
    cells: List[Dict[str, Any]] = []
    skipped_headers: List[str] = []
    numeric_values: List[float] = []

    for raw_key, raw_val in disagg.items():
        parsed = parse_matrix_cell_key(str(raw_key))
        if _is_header_cell(str(raw_key), parsed):
            skipped_headers.append(str(raw_key))
            continue
        num = parse_upr_number(raw_val)
        if parsed.get("year") is None and year_slot is not None and kind == "funding":
            parsed["year"] = year_slot
        cell = {
            "key": str(raw_key),
            "value": raw_val if num is None else (int(num) if float(num).is_integer() else num),
            "actor": parsed.get("actor"),
            "programme": parsed.get("programme"),
            "sp_key": parsed.get("sp_key"),
            "sp_label": parsed.get("sp_label"),
            "year": parsed.get("year"),
        }
        cells.append(cell)
        if num is not None:
            numeric_values.append(float(num))

    if not cells:
        return None

    nonzero = [c for c in cells if parse_upr_number(c.get("value")) not in (None, 0.0)]
    zeros = len(cells) - len(nonzero)
    max_abs = max((abs(v) for v in numeric_values), default=0.0)
    all_small_ints = bool(numeric_values) and max_abs < 100 and all(float(v).is_integer() for v in numeric_values)

    if kind == "funding":
        unit = "CHF"
        value_role = "funding_requirement_chf"
        if all_small_ints:
            value_role = "possibly_not_chf_small_integers"
    elif kind in ("people_to_be_reached", "people_reached"):
        # These matrices store people targets/actuals. Small integers are implausible
        # people counts (often a data-entry error), not a different unit such as flags.
        unit = "people"
        value_role = "people_count"
    elif kind == "bilateral_support":
        unit = "tick_or_count"
        value_role = "pns_presence_not_chf" if all_small_ints else "mixed"
    else:
        unit = "unknown"
        value_role = "unknown"

    by_actor: Dict[str, float] = {}
    by_sp: Dict[str, float] = {}
    by_programme: Dict[str, float] = {}
    by_year: Dict[str, float] = {}
    for cell in cells:
        num = parse_upr_number(cell.get("value"))
        if num is None:
            continue
        if cell.get("actor"):
            by_actor[str(cell["actor"])] = by_actor.get(str(cell["actor"]), 0.0) + num
        if cell.get("sp_key"):
            by_sp[str(cell["sp_key"])] = by_sp.get(str(cell["sp_key"]), 0.0) + num
        if cell.get("programme"):
            by_programme[str(cell["programme"])] = by_programme.get(str(cell["programme"]), 0.0) + num
        if cell.get("year"):
            yk = str(int(cell["year"]))
            by_year[yk] = by_year.get(yk, 0.0) + num

    def _round_map(d: Dict[str, float]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for k, v in d.items():
            out[k] = int(v) if float(v).is_integer() else round(v, 2)
        return out

    grand = sum(numeric_values) if numeric_values else 0.0
    pns_ticked = sorted({
        str(c.get("actor"))
        for c in nonzero
        if c.get("actor") and c.get("actor") not in ("HNS", "IFRC Secretariat", "PNS")
    })

    reading: Dict[str, Any] = {
        "kind": kind,
        "unit": unit,
        "value_role": value_role,
        "year_slot": year_slot,
        "cell_count": len(cells),
        "nonzero_count": len(nonzero),
        "zero_count": zeros,
        "grand_total": int(grand) if float(grand).is_integer() else round(grand, 2),
        "by_actor": _round_map(by_actor),
        "by_sp": _round_map(by_sp),
        "by_programme": _round_map(by_programme),
        "by_year": _round_map(by_year),
        "nonzero_cells": nonzero[:40],
        "do_not_treat_grand_total_as_single_indicator": True,
    }
    if pns_ticked:
        reading["pns_with_support"] = pns_ticked
    if skipped_headers:
        reading["ignored_header_cells"] = skipped_headers[:8]
    if kind in ("people_to_be_reached", "people_reached") and all_small_ints:
        reading["implausible_small_people_targets"] = True

    if reading.get("implausible_small_people_targets"):
        reading["value_preview"] = (
            f"{len(cells)} cells, {len(nonzero)} non-zero people targets "
            f"(largest cell {int(max_abs) if float(max_abs).is_integer() else max_abs} — "
            "implausibly small for people to be reached)"
        )
    elif value_role == "pns_presence_not_chf":
        n_pns = len(pns_ticked) or len(nonzero)
        reading["value_preview"] = (
            f"{n_pns} National Societ{'y' if n_pns == 1 else 'ies'} ticked across {len(nonzero)} cells (not CHF)"
        )
    elif kind == "funding":
        yr = f"{int(year_slot)} " if year_slot else ""
        reading["value_preview"] = f"{yr}funding matrix {int(grand):,} CHF ({len(nonzero)} non-zero of {len(cells)} cells)"
    else:
        reading["value_preview"] = f"{len(cells)} cells, {len(nonzero)} non-zero"

    reading["pdf_comparison"] = compare_matrix_to_upr_visuals(reading, context.get("upr_visuals"))
    return reading


def _visual_payload(block: Dict[str, Any]) -> Dict[str, Any]:
    payload = block.get("payload") if isinstance(block.get("payload"), dict) else {}
    inner_key = str(block.get("block") or "")
    if inner_key and isinstance(payload.get(inner_key), dict):
        return payload.get(inner_key) or {}
    return payload


def compare_matrix_to_upr_visuals(
    reading: Dict[str, Any],
    upr_visuals: Any,
) -> List[Dict[str, Any]]:
    """Like-for-like notes between form totals and PDF visual blocks (not cell-perfect)."""
    notes: List[Dict[str, Any]] = []
    if not isinstance(upr_visuals, dict):
        return notes
    kind = reading.get("kind")
    year_slot = reading.get("year_slot")
    by_sp = reading.get("by_sp") if isinstance(reading.get("by_sp"), dict) else {}

    for block in upr_visuals.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        btype = str(block.get("block") or "")
        payload = _visual_payload(block)
        src = block.get("source") if isinstance(block.get("source"), dict) else {}
        src_label = (src.get("document_title") or src.get("document_filename") or "UPR document")
        block_year = block.get("year")

        if kind == "funding" and btype == "funding_requirements":
            totals = payload.get("totals_by_year") if isinstance(payload.get("totals_by_year"), dict) else {}
            breakdown = payload.get("breakdown_by_year") if isinstance(payload.get("breakdown_by_year"), dict) else {}
            target_year = str(int(year_slot)) if year_slot else None
            pdf_total = parse_upr_number(totals.get(target_year)) if target_year else None
            form_total = parse_upr_number(reading.get("grand_total"))
            note: Dict[str, Any] = {
                "block": btype,
                "source": src_label,
                "pdf_year": block_year or (int(target_year) if target_year else None),
                "form_year": year_slot,
                "form_total_chf": form_total,
                "pdf_network_total_chf": pdf_total,
                "alignment": "same_year_network_total_vs_form_hns_plus_ifrc_sp_grid",
            }
            if target_year and isinstance(breakdown.get(target_year), dict):
                bd = breakdown[target_year]
                note["pdf_through_ifrc"] = parse_upr_number(bd.get("through_ifrc"))
                note["pdf_through_pns"] = parse_upr_number(bd.get("through_participating_national_societies"))
                note["pdf_host_ns"] = parse_upr_number(bd.get("host_national_society"))
            if form_total and pdf_total and pdf_total > 0:
                ratio = form_total / pdf_total
                note["form_over_pdf_ratio"] = round(ratio, 3)
                if 0.85 <= ratio <= 1.15:
                    note["match"] = "totals_within_15_percent"
                else:
                    note["match"] = "totals_differ_compare_breakdown_not_cells"
            elif pdf_total is None:
                note["match"] = "no_pdf_total_for_this_year"
            notes.append(note)

            ifrc_bd = payload.get("ifrc_breakdown_by_year")
            if target_year and isinstance(ifrc_bd, dict) and isinstance(ifrc_bd.get(target_year), dict):
                sp = (ifrc_bd[target_year] or {}).get("strategic_priorities") or {}
                if isinstance(sp, dict) and by_sp:
                    sp_notes = []
                    for sp_key, form_val in by_sp.items():
                        pdf_val = parse_upr_number(sp.get(sp_key))
                        if pdf_val is None:
                            continue
                        sp_notes.append({
                            "sp": sp_key,
                            "form": form_val,
                            "pdf_ifrc_breakdown": pdf_val,
                            "note": "PDF figure is IFRC-channel SP split, not HNS+IFRC cell sum",
                        })
                    if sp_notes:
                        notes.append({"block": btype, "sp_channel_comparison": sp_notes})

        elif kind in ("people_to_be_reached", "people_reached") and btype in (
            "people_to_be_reached",
            "people_reached",
        ):
            people = payload
            if not any(k in payload for k in (
                "emergency_operations",
                "climate_and_environment",
                "disasters_and_crises",
                "health_and_wellbeing",
                "migration_and_displacement",
                "values_power_and_inclusion",
            )):
                inner = payload.get(btype) or payload.get("people_reached") or payload.get("people_to_be_reached")
                people = inner if isinstance(inner, dict) else {}
            sp_notes = []
            for sp_key, form_val in by_sp.items():
                pdf_val = parse_upr_number(people.get(sp_key))
                if pdf_val is None:
                    continue
                sp_notes.append({"sp": sp_key, "form": form_val, "pdf_people": pdf_val})
            note = {
                "block": btype,
                "source": src_label,
                "sp_comparison": sp_notes,
            }
            if reading.get("implausible_small_people_targets"):
                pdf_vals = [parse_upr_number(v) for v in people.values()]
                pdf_max = max((abs(v) for v in pdf_vals if v is not None), default=0.0)
                if pdf_max >= 1000:
                    note["match"] = "form_people_far_below_pdf"
                    note["reason"] = (
                        "Form people-to-be-reached cells are single-digit / tiny counts while the "
                        f"Unified Plan visual has people figures up to {pdf_max:,.0f}."
                    )
            notes.append(note)

        elif kind == "bilateral_support" and btype in ("pns_bilateral_support", "funding_requirements"):
            names: List[str] = []
            if btype == "pns_bilateral_support":
                rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
                if not rows and isinstance(payload.get("pns_bilateral_support"), dict):
                    rows = payload["pns_bilateral_support"].get("rows") or []
                for row in rows:
                    if isinstance(row, dict) and row.get("national_society"):
                        names.append(str(row["national_society"]))
            else:
                pns = payload.get("participating_national_societies") or {}
                if isinstance(pns, dict):
                    for group in ("bilateral", "multilateral"):
                        vals = pns.get(group)
                        if isinstance(vals, list):
                            names.extend(str(x) for x in vals if x)
            form_names = [str(x).lower() for x in (reading.get("pns_with_support") or [])]
            pdf_norm = [_norm_text(n) for n in names]
            matched = [n for n in names if _norm_text(n) in form_names or any(_norm_text(n) in f or f in _norm_text(n) for f in form_names)]
            notes.append({
                "block": btype,
                "source": src_label,
                "form_pns": reading.get("pns_with_support") or [],
                "pdf_pns": names[:30],
                "matched_names": matched,
                "alignment": "names_only_form_ticks_are_not_chf",
            })
    return notes


def format_upr_matrix_reading_for_prompt(context: Dict[str, Any]) -> str:
    reading = context.get("upr_matrix_reading")
    if not isinstance(reading, dict) or not reading:
        return ""

    kind = reading.get("kind") or "matrix"
    lines = [
        "\nUPR MATRIX READING (decode of THIS form — not independent confirmation):\n",
        "Use this to understand cells. Compare cells to Unified Plan/Report visual blocks or prior-round submissions. "
        "Do NOT mark good solely because the form matches this reading.\n",
        f"- Kind: {kind}\n",
        f"- Unit / value role: {reading.get('unit')} / {reading.get('value_role')}\n",
    ]
    if reading.get("year_slot"):
        lines.append(f"- Planning year for this matrix: {int(reading['year_slot'])}\n")
    lines.append(
        f"- Cells: {reading.get('cell_count')} total, {reading.get('nonzero_count')} non-zero, "
        f"{reading.get('zero_count')} zero\n"
    )
    if reading.get("do_not_treat_grand_total_as_single_indicator"):
        lines.append(
            f"- Arithmetic sum of numeric cells: {reading.get('grand_total')} "
            f"(DO NOT validate this sum as if it were one indicator)\n"
        )
    if reading.get("by_actor"):
        lines.append(f"- Totals by actor: {reading['by_actor']}\n")
    if reading.get("by_programme"):
        lines.append(f"- Totals by programme (Resilience=longer-term, Response=emergency): {reading['by_programme']}\n")
    if reading.get("by_sp"):
        lines.append(f"- Totals by Strategic Priority / EF: {reading['by_sp']}\n")
    if reading.get("by_year"):
        lines.append(f"- Totals by year: {reading['by_year']}\n")
    if reading.get("pns_with_support"):
        lines.append(f"- National Societies with a tick/amount: {reading['pns_with_support']}\n")

    nonzero = reading.get("nonzero_cells") or []
    if nonzero:
        lines.append("- Non-zero cells (actor | programme | SP | year | value):\n")
        for cell in nonzero[:25]:
            bits = [
                str(cell.get("actor") or "—"),
                str(cell.get("programme") or "—"),
                str(cell.get("sp_label") or cell.get("sp_key") or "—"),
                str(cell.get("year") or "—"),
                str(cell.get("value")),
            ]
            lines.append("  - " + " | ".join(bits) + "\n")

    comps = reading.get("pdf_comparison") or []
    if comps:
        lines.append("- Comparison with Unified Plan/Report visual blocks (like-for-like only):\n")
        for note in comps[:8]:
            lines.append(f"  - {note}\n")
    else:
        lines.append(
            "- No structured Unified Plan visual block was available to compare. "
            "Do not use Annual Report narrative as a cell-level conflict.\n"
        )

    if reading.get("implausible_small_people_targets"):
        lines.append(
            "- These cells ARE people-to-be-reached / people-reached TARGETS, not programme flags. "
            "Values of 0–99 (e.g. 5, 3, 1) are implausible as country-plan people figures. "
            "If a prior assignment for this field has thousands or millions, this is a discrepancy — "
            "not a valid flag grid and not confirmation that the form matches this reading.\n"
        )
    if reading.get("value_role") == "pns_presence_not_chf":
        lines.append(
            "- Compare PNS *names* to the Unified Plan bilateral list. "
            "Do not treat the count of ticks as a CHF amount.\n"
        )
    if kind == "funding":
        lines.append(
            "- Form grid is HNS vs IFRC Secretariat × Resilience/Response × SP/EF, in CHF. "
            "PDF network totals and 'through IFRC / PNS / HNS' splits are related but not the same cells. "
            "A close grand-total match supports plausibility; a missing SP×actor breakdown in an Annual Report is not a discrepancy.\n"
        )
    return "".join(lines)


_FLAG_ROLES = frozenset({
    "not_people_totals",
    "pns_presence_not_chf",
    "possibly_not_chf_small_integers",
})
_QUANTITY_ROLES = frozenset({"people_count", "funding_requirement_chf"})


def _max_abs_cell(reading: Dict[str, Any]) -> float:
    vals: List[float] = []
    for cell in reading.get("nonzero_cells") or []:
        num = parse_upr_number(cell.get("value") if isinstance(cell, dict) else None)
        if num is not None:
            vals.append(abs(float(num)))
    if vals:
        return max(vals)
    grand = parse_upr_number(reading.get("grand_total"))
    return abs(float(grand)) if grand is not None else 0.0


def _cell_identity(cell: Dict[str, Any], kind: str) -> Tuple[str, str, str]:
    actor = str(cell.get("actor") or "")
    programme = str(cell.get("programme") or "")
    sp = str(cell.get("sp_key") or cell.get("sp_label") or "")
    if kind in ("people_to_be_reached", "people_reached"):
        # Planning-year columns shift each assignment (2026/27/28 vs 2027/28/29).
        return ("", programme, sp)
    if kind == "bilateral_support":
        return (actor, "", sp)
    return (actor, programme, sp)


def compare_upr_matrix_to_history(
    current: Optional[Dict[str, Any]],
    historical_entries: Any,
) -> Dict[str, Any]:
    """Compare the current form matrix to prior-assignment matrices for the same field."""
    notes: List[Dict[str, Any]] = []
    unit_or_scale_change = False
    if not isinstance(current, dict) or not current:
        return {"unit_or_scale_change": False, "notes": notes}

    kind = str(current.get("kind") or "")
    cur_role = str(current.get("value_role") or "")
    cur_max = _max_abs_cell(current)
    current_by_id: Dict[Tuple[str, str, str], float] = {}
    for cell in current.get("nonzero_cells") or []:
        if not isinstance(cell, dict):
            continue
        num = parse_upr_number(cell.get("value"))
        if num is None:
            continue
        current_by_id[_cell_identity(cell, kind)] = float(num)

    for entry in historical_entries or []:
        if not isinstance(entry, dict):
            continue
        reading = entry.get("reading") if isinstance(entry.get("reading"), dict) else None
        if not reading:
            continue
        period = entry.get("period_name") or entry.get("period")
        hist_role = str(reading.get("value_role") or "")
        hist_max = _max_abs_cell(reading)
        note: Dict[str, Any] = {
            "period": period,
            "hist_role": hist_role,
            "hist_max": int(hist_max) if float(hist_max).is_integer() else round(hist_max, 2),
            "current_role": cur_role,
            "current_max": int(cur_max) if float(cur_max).is_integer() else round(cur_max, 2),
            "hist_preview": reading.get("value_preview"),
        }
        role_flip = (
            (cur_role in _FLAG_ROLES and hist_role in _QUANTITY_ROLES)
            or (hist_role in _FLAG_ROLES and cur_role in _QUANTITY_ROLES)
        )
        scale_flip = (cur_max < 100 and hist_max >= 1000) or (hist_max < 100 and cur_max >= 1000)
        people_collapse = (
            kind in ("people_to_be_reached", "people_reached")
            and hist_max >= 1000
            and cur_max < max(100.0, hist_max * 0.01)
        )
        if role_flip or scale_flip or people_collapse:
            unit_or_scale_change = True
            note["match"] = "unit_or_scale_change"
            if kind in ("people_to_be_reached", "people_reached"):
                note["reason"] = (
                    f"Prior {period} people-to-be-reached matrix has cells up to {hist_max:,.0f}; "
                    f"current people targets are at most {cur_max:,.0f}. "
                    "These cells are people targets, not programme counts or flags."
                )
            else:
                note["reason"] = (
                    f"Prior {period} matrix looks like {hist_role} (largest cell {hist_max:,.0f}); "
                    f"current matrix looks like {cur_role} (largest cell {cur_max:,.0f})."
                )
        else:
            note["match"] = "comparable"
            diffs: List[Dict[str, Any]] = []
            for cell in (reading.get("nonzero_cells") or [])[:30]:
                if not isinstance(cell, dict):
                    continue
                hist_val = parse_upr_number(cell.get("value"))
                if hist_val is None:
                    continue
                key = _cell_identity(cell, kind)
                cur_val = current_by_id.get(key)
                if cur_val is None:
                    diffs.append({
                        "identity": {"actor": key[0], "programme": key[1], "sp": key[2]},
                        "historical": hist_val,
                        "current": None,
                    })
                elif abs(float(hist_val)) > 0 and abs(float(cur_val) - float(hist_val)) / abs(float(hist_val)) > 0.5:
                    diffs.append({
                        "identity": {"actor": key[0], "programme": key[1], "sp": key[2]},
                        "historical": hist_val,
                        "current": cur_val,
                    })
            if diffs:
                note["cell_diffs"] = diffs[:12]
        notes.append(note)

    return {"unit_or_scale_change": unit_or_scale_change, "notes": notes}


def people_history_magnitude_reason(
    context: Dict[str, Any],
    historical: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Flag people-to-be-reached cells that collapsed versus a prior people-scale series.

    Works even when prior-row disagg was not decoded: uses comparison notes, historical
    matrix previews, or the scalar historical series max.
    """
    kind = str(context.get("upr_item_kind") or "")
    if kind not in ("people_to_be_reached", "people_reached"):
        return None
    reading = context.get("upr_matrix_reading")
    if not isinstance(reading, dict):
        return None
    cur_max = _max_abs_cell(reading)
    if cur_max >= 100:
        return None

    hist_max = 0.0
    comparison = context.get("upr_historical_comparison")
    if isinstance(comparison, dict):
        for note in comparison.get("notes") or []:
            if not isinstance(note, dict):
                continue
            hm = parse_upr_number(note.get("hist_max"))
            if hm is not None:
                hist_max = max(hist_max, abs(float(hm)))
    for item in context.get("upr_historical_matrices") or []:
        if not isinstance(item, dict):
            continue
        hist_max = max(hist_max, _max_abs_cell(item))
        gm = parse_upr_number(item.get("grand_total"))
        if gm is not None:
            hist_max = max(hist_max, abs(float(gm)))

    hist_obj = historical if isinstance(historical, dict) else context.get("historical")
    if isinstance(hist_obj, dict):
        summary = hist_obj.get("summary") if isinstance(hist_obj.get("summary"), dict) else None
        if summary is None and hist_obj.get("max") is not None:
            summary = hist_obj
        if isinstance(summary, dict):
            sm = parse_upr_number(summary.get("max"))
            if sm is not None:
                hist_max = max(hist_max, abs(float(sm)))
        for row in hist_obj.get("series") or []:
            if not isinstance(row, dict):
                continue
            for key in ("value_int", "value", "grand_total"):
                n = parse_upr_number(row.get(key))
                if n is not None:
                    hist_max = max(hist_max, abs(float(n)))

    if hist_max < 1000:
        return None
    label = "people to be reached" if kind == "people_to_be_reached" else "people reached"
    return (
        f"Prior assignment {label} figures reach {hist_max:,.0f}, but the current matrix "
        f"cells are at most {cur_max:,.0f}. These cells are {label} targets, not programme flags."
    )


def format_upr_historical_matrices_for_prompt(context: Dict[str, Any]) -> str:
    matrices = context.get("upr_historical_matrices")
    comparison = context.get("upr_historical_comparison")
    if not matrices and not comparison:
        return ""

    lines = [
        "\nHISTORICAL UPR MATRICES (same field, prior assignments for this country — compare cells, not the arithmetic total):\n"
    ]
    for item in (matrices or [])[:4]:
        if not isinstance(item, dict):
            continue
        period = item.get("period_name") or item.get("period") or "prior period"
        lines.append(
            f"- {period}: role={item.get('value_role')} preview={item.get('value_preview')} "
            f"grand_total={item.get('grand_total')} by_sp={item.get('by_sp')} "
            f"by_programme={item.get('by_programme')} by_actor={item.get('by_actor')}\n"
        )
        cells = item.get("nonzero_cells") or []
        if cells:
            lines.append("  Non-zero cells (actor | programme | SP | year | value):\n")
            for cell in cells[:15]:
                if not isinstance(cell, dict):
                    continue
                bits = [
                    str(cell.get("actor") or "—"),
                    str(cell.get("programme") or "—"),
                    str(cell.get("sp_label") or cell.get("sp_key") or "—"),
                    str(cell.get("year") or "—"),
                    str(cell.get("value")),
                ]
                lines.append("    - " + " | ".join(bits) + "\n")

    if isinstance(comparison, dict) and comparison.get("notes"):
        lines.append("- Comparison with the current matrix:\n")
        for note in (comparison.get("notes") or [])[:6]:
            if not isinstance(note, dict):
                continue
            period = note.get("period") or "prior period"
            match = note.get("match") or "compared"
            reason = note.get("reason")
            if reason:
                lines.append(f"  - {period}: {match} — {reason}\n")
            else:
                lines.append(
                    f"  - {period}: {match} (hist_role={note.get('hist_role')}, "
                    f"hist_max={note.get('hist_max')}, current_role={note.get('current_role')}, "
                    f"current_max={note.get('current_max')})\n"
                )
            for diff in (note.get("cell_diffs") or [])[:6]:
                if not isinstance(diff, dict):
                    continue
                ident = diff.get("identity") if isinstance(diff.get("identity"), dict) else {}
                cell_name = " / ".join(
                    str(x) for x in (ident.get("programme"), ident.get("actor"), ident.get("sp")) if x
                ) or "cell"
                lines.append(
                    f"      {cell_name}: historical={diff.get('historical')} current={diff.get('current')}\n"
                )
        if comparison.get("unit_or_scale_change"):
            lines.append(
                "- UNIT/SCALE CHANGE: a prior assignment stored people or CHF quantities "
                "(thousands to millions) while the current grid has tiny cells (0–99), or the reverse. "
                "For people-to-be-reached this is a collapsed people TARGET, not a valid flag grid. "
                "Verdict=discrepancy unless a comment on this assignment explains a form redesign. "
                "Do not mark good because the current grid is internally consistent or matches this decode.\n"
            )
    return "".join(lines)
