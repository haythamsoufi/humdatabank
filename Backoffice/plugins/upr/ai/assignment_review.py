"""Structural assignment review for Unified Plan/Report forms.

Builds a deterministic pack (figures + flags/highlights) that the assignment-level
LLM summary and per-field validation both consume. Keep UPR review rules here and
in ``KNOWLEDGE.md`` §14 / ``prompts.py`` — not in the core validation service.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from plugins.upr.ai.matrix_reading import interpret_upr_matrix, parse_upr_number
from plugins.upr.ai.prompts import is_upr_form_template
from plugins.upr.catalog import (
    AREA_LABELS,
    PLAN_ITEM_FALLBACKS,
    PLAN_LABEL_NEEDLES,
    PLANNING_EA_FUNDING_AREAS,
    SP_CODES,
)

logger = logging.getLogger(__name__)

_IFRC_ROW_NEEDLES = ("ifrc secretariat", "ifrc")
_HEADER_KEY_RE = re.compile(r"^(?:col[ _]-?header\|)(.+)$", re.I)
_META_KEY_RE = re.compile(r"^(?:_|col[ _]-?header|col_header_go_unmatched|row_go_unmatched)", re.I)
_COMMENTS_ITEM_ID = 956
_REQUIRED_IFRC_STATIC_COLS = tuple(list(SP_CODES) + ["EFs"])
_NS_KPI_SECTION_NEEDLES = ("national society key figure", "key figures", "in support of")
_NS_KPI_LABEL_NEEDLES = ("volunteer", "staff", "branch", "local unit")


def _norm(text: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def _friendly_area_label(code: str) -> str:
    """Human-readable name for a Strategic Priority / Enabling Functions code.

    Falls back to the raw code (upper-cased match against AREA_LABELS) so unknown
    codes still render as something rather than raising, but end-user-facing text
    should almost always resolve to a real name (Climate and environment, etc.).
    """
    c = str(code or "").strip()
    if not c:
        return c
    return AREA_LABELS.get(c) or AREA_LABELS.get(c.upper()) or c


def _item_id(item: Any) -> Optional[int]:
    try:
        raw = getattr(item, "id", None)
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _resolve_label_placeholders(
    text: str,
    resolved_variables: Optional[Dict[str, Any]],
    variable_configs: Optional[Dict[str, Any]],
) -> str:
    """Best-effort ``[variable]`` placeholder substitution (e.g. ``[assignment_period]``).

    Form item labels can carry template placeholders that the entry-form UI resolves
    via ``VariableResolutionService``. The deterministic review pack reads
    ``FormItem.label`` directly, so any label headed for the end-user-facing numbered
    issues list / figure tiles must go through the same resolution — otherwise the
    literal ``[assignment_period]`` text leaks into the UI.
    """
    if not text or not resolved_variables or "[" not in str(text):
        return text
    try:
        from app.services.forms.variable_resolution_service import VariableResolutionService
        return VariableResolutionService.replace_variables_if_placeholders(
            str(text), resolved_variables, variable_configs or {}
        )
    except Exception:
        logger.debug("assignment review label variable resolution failed", exc_info=True)
        return text


def _item_label(
    item: Any,
    resolved_variables: Optional[Dict[str, Any]] = None,
    variable_configs: Optional[Dict[str, Any]] = None,
) -> str:
    raw = str(getattr(item, "label", None) or "").strip()
    return _resolve_label_placeholders(raw, resolved_variables, variable_configs)


def _section_name(item: Any) -> str:
    section = getattr(item, "form_section", None) or getattr(item, "section", None)
    parent = getattr(section, "parent_section", None) if section is not None else None
    names = [
        getattr(section, "name", None) if section is not None else None,
        getattr(parent, "name", None) if parent is not None else None,
    ]
    return " ".join(str(n) for n in names if n)


def _is_ifrc_row(row: str) -> bool:
    n = _norm(row)
    return n in {"ifrc", "ifrc secretariat"} or n.startswith("ifrc")


def _matrix_cells(entry: Any) -> Dict[str, Any]:
    if entry is None:
        return {}
    getter = getattr(entry, "get_display_disagg_data", None)
    try:
        disagg = getter() if callable(getter) else getattr(entry, "disagg_data", None)
    except Exception:
        disagg = getattr(entry, "disagg_data", None)
    if not isinstance(disagg, dict):
        return {}
    values = disagg.get("values") if isinstance(disagg.get("values"), dict) else disagg
    if not isinstance(values, dict):
        return {}
    out: Dict[str, Any] = {}
    for key, val in values.items():
        if not isinstance(key, str) or key.startswith("_") or key in {"mode", "values"}:
            continue
        if isinstance(val, dict) and ("modified" in val or "original" in val):
            val = val.get("modified") if val.get("modified") is not None else val.get("original")
        out[str(key)] = val
    return out


def _split_row_col(key: str) -> Tuple[str, str]:
    if _HEADER_KEY_RE.match(key) or _META_KEY_RE.match(key):
        return "", key
    if "_" not in key:
        return key, ""
    row, _sep, col = key.partition("_")
    if row.isdigit():
        return row, col
    row, col = key.rsplit("_", 1)
    return row, col


def _is_blank_cell(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip().lower() in ("", "null", "none", "-"):
        return True
    return False


def _scalar_text(entry: Any) -> str:
    if entry is None:
        return ""
    getter = getattr(entry, "get_display_value", None)
    raw = getter() if callable(getter) else getattr(entry, "value", None)
    text = str(raw or "").strip()
    if text.lower() in ("none", "null", "-"):
        return ""
    return text


def _finding(
    *,
    severity: str,
    code: str,
    form_item_id: Optional[int],
    label: str,
    text: str,
    figures: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "severity": severity,  # flag | highlight | ok | note
        "code": code,
        "form_item_id": form_item_id,
        "label": label,
        "text": text,
        "figures": figures or {},
    }


def selected_ea_headers(cells: Dict[str, Any]) -> Dict[str, str]:
    """Map EA column name → selected appeal label from ``col_header|EA*`` keys."""
    selected: Dict[str, str] = {}
    for key, raw in (cells or {}).items():
        m = _HEADER_KEY_RE.match(str(key))
        if not m:
            continue
        col = str(m.group(1) or "").strip()
        label = str(raw or "").strip()
        if col.upper() in PLANNING_EA_FUNDING_AREAS and label and label.lower() not in ("none", "null", "-"):
            selected[col] = label
    return selected


def matrix_row_ids(cells: Dict[str, Any]) -> List[str]:
    rows: List[str] = []
    seen = set()
    for key in cells or {}:
        if _HEADER_KEY_RE.match(str(key)) or _META_KEY_RE.match(str(key)):
            continue
        row, _col = _split_row_col(str(key))
        if not row or row in seen:
            continue
        seen.add(row)
        rows.append(row)
    return rows


def ifrc_row_values(cells: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, val in (cells or {}).items():
        if _HEADER_KEY_RE.match(str(key)) or _META_KEY_RE.match(str(key)):
            continue
        row, col = _split_row_col(str(key))
        if not col or not _is_ifrc_row(row):
            continue
        out[col] = val
    return out


def _emergency_label(op: Dict[str, Any]) -> str:
    custom = str(op.get("_display") or "").strip()
    if custom:
        return custom
    name = str(op.get("name") or "").strip()
    code = str(op.get("code") or "").strip()
    if name and code:
        return f"{name} ({code})"
    return name or code or str(op.get("id") or "")


def _emops_config_sources(mc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Every distinct emops filter config this matrix item can show options from.

    A matrix can source ``emergency_operations`` rows two different ways, and each
    needs its own filter config read from a different place — see
    ``app/static/js/forms/modules/matrix/selectable-headers.js`` (the live picker):

    - Row-mode/hybrid list-library rows (e.g. the "Emergency Appeals" people-to-be-
      reached matrix, item 960): a single matrix-level ``plugin_config``.
    - *Selectable header* columns (e.g. the EA1/EA2/EA3 funding columns, item 967):
      each column has its own ``header_plugin_config`` and can therefore filter
      differently from its neighbours (one EA slot can be pinned to the current
      assignment period while another stays static). The picker falls back to the
      matrix-level ``plugin_config`` only when a column has none of its own — a
      matrix built entirely of selectable EA columns commonly has *no* top-level
      ``plugin_config`` at all, so reading only that key (as this function used to)
      silently applies almost no filtering (all types, closed included, no date
      cutoff) and can surface emergencies as "available" that none of the item's
      real dropdowns would ever offer.

    Identical config dicts are only queried once (several EA columns often share
    the exact same filters).
    """
    sources: List[Dict[str, Any]] = []
    seen: set = set()

    def _add(cfg: Optional[Dict[str, Any]]) -> None:
        cfg = cfg if isinstance(cfg, dict) else {}
        key = tuple(sorted((k, str(v)) for k, v in cfg.items()))
        if key in seen:
            return
        seen.add(key)
        sources.append(cfg)

    matrix_plugin_cfg = mc.get("plugin_config") if isinstance(mc.get("plugin_config"), dict) else {}
    row_mode = str(mc.get("row_mode") or "").strip().lower()
    row_list_id = str(mc.get("lookup_list_id") or "").strip()
    if row_mode in ("list_library", "hybrid") and row_list_id == "emergency_operations":
        _add(matrix_plugin_cfg)

    for col in mc.get("columns") or []:
        if not isinstance(col, dict):
            continue
        if str(col.get("header_lookup_list_id") or "").strip() != "emergency_operations":
            continue
        col_cfg = col.get("header_plugin_config")
        # Same fallback order as the live "Selectable header" picker: the column's
        # own filters win; only fall back to the matrix-level config when it has none.
        _add(col_cfg if isinstance(col_cfg, dict) else matrix_plugin_cfg)

    return sources


def list_available_emergencies(form_item: Any, aes: Any) -> List[Dict[str, str]]:
    """Country-filtered GO emergency operations available to add/select on this item.

    Unions options across every emops-sourced row-mode/selectable-column config on
    the item (see ``_emops_config_sources``) so items like the funding matrix — whose
    EA1/EA2/EA3 columns each carry their own filters and no matrix-level
    ``plugin_config`` — are read the same way the live picker reads them, rather than
    only ever checking a matrix-level key that may not exist for this item's shape.
    """
    if form_item is None or aes is None:
        return []
    try:
        from app.services.assignments.completion_service import _form_item_matrix_config
        from app.services.forms.emergency_section_binding import (
            _assignment_period_for_aes,
            _country_iso_for_aes,
            _normalize_emops_config,
        )
        from plugins.emergency_operations.routes import get_emergency_operations_data
    except Exception:
        return []

    iso = _country_iso_for_aes(aes)
    if not iso:
        return []

    mc = _form_item_matrix_config(form_item)
    sources = _emops_config_sources(mc)
    if not sources:
        return []

    period = _assignment_period_for_aes(aes)
    out: List[Dict[str, str]] = []
    seen_codes: set = set()
    for raw_cfg in sources:
        try:
            ops = get_emergency_operations_data(
                country_iso=iso,
                config=_normalize_emops_config(raw_cfg, period),
            ) or []
        except Exception:
            logger.debug("available emergencies lookup failed", exc_info=True)
            continue
        for op in ops:
            if not isinstance(op, dict):
                continue
            label = _emergency_label(op)
            if not label:
                continue
            dedup_key = (str(op.get("code") or "").strip() or str(op.get("id") or "")).lower()
            if dedup_key:
                if dedup_key in seen_codes:
                    continue
                seen_codes.add(dedup_key)
            out.append({
                "id": str(op.get("id") or ""),
                "code": str(op.get("code") or "").strip(),
                "name": str(op.get("name") or "").strip(),
                "label": label,
            })
    return out


def _labels_match(left: str, right: str) -> bool:
    a, b = _norm(left), _norm(right)
    if not a or not b:
        return False
    if a == b:
        return True
    if a in b or b in a:
        return True
    a_codes = set(re.findall(r"mdr[a-z]{2}\d+", a))
    b_codes = set(re.findall(r"mdr[a-z]{2}\d+", b))
    return bool(a_codes and a_codes & b_codes)


def unmatched_emergencies(
    available: Sequence[Dict[str, str]],
    selected_labels: Sequence[str],
) -> List[str]:
    unmatched: List[str] = []
    for op in available:
        label = op.get("label") or op.get("name") or ""
        code = op.get("code") or ""
        if any(_labels_match(label, sel) or (code and _labels_match(code, sel)) for sel in selected_labels):
            continue
        unmatched.append(label)
    return unmatched


def _resolve_item(items: Sequence[Any], *, fallback_id: Optional[int], needles: Sequence[str]) -> Any:
    for item in items:
        if fallback_id is not None and _item_id(item) == int(fallback_id):
            return item
    lowered = [(item, _norm(_item_label(item) + " " + _section_name(item))) for item in items]
    for item, blob in lowered:
        if any(needle in blob for needle in needles):
            return item
    return None


def _entry_for_item(by_item_id: Dict[int, Any], item: Any) -> Any:
    iid = _item_id(item)
    if iid is None:
        return None
    return by_item_id.get(iid)


def audit_ns_key_figures(
    items: Sequence[Any],
    by_item_id: Dict[int, Any],
    *,
    resolved_variables: Optional[Dict[str, Any]] = None,
    variable_configs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    kpi_items = []
    for item in items:
        blob = _norm(_item_label(item) + " " + _section_name(item))
        if any(n in blob for n in _NS_KPI_SECTION_NEEDLES) or any(n in blob for n in _NS_KPI_LABEL_NEEDLES):
            if "comment" in blob:
                continue
            kpi_items.append(item)
    filled: List[str] = []
    empty: List[Dict[str, Any]] = []
    for item in kpi_items:
        entry = _entry_for_item(by_item_id, item)
        label = _item_label(item, resolved_variables, variable_configs) or f"Item {_item_id(item)}"
        text = _scalar_text(entry)
        num = parse_upr_number(text) if text else parse_upr_number(getattr(entry, "value", None) if entry else None)
        if text or (num is not None):
            filled.append(f"{label}={text or num}")
        else:
            empty.append({"form_item_id": _item_id(item), "label": label})
    total = len(kpi_items)
    figures = {"filled": len(filled), "total": total, "values": filled[:8]}
    if total and len(empty) == total:
        finding = _finding(
            severity="flag",
            code="ns_key_figures_empty",
            form_item_id=empty[0]["form_item_id"] if empty else None,
            label="National Society key figures",
            text=(
                "The 'National Society key figures' section is completely empty — "
                f"none of the {total} figures (volunteers, staff, branches, etc.) were filled in."
            ),
            figures=figures,
        )
    elif empty:
        finding = _finding(
            severity="highlight",
            code="ns_key_figures_partial",
            form_item_id=empty[0]["form_item_id"],
            label="National Society key figures",
            text=f"{len(empty)} of {total} National Society key figures are still missing a number.",
            figures=figures,
        )
    elif total:
        finding = _finding(
            severity="ok",
            code="ns_key_figures_ok",
            form_item_id=_item_id(kpi_items[0]),
            label="National Society key figures",
            text=f"All {total} National Society key figures have been filled in.",
            figures=figures,
        )
    else:
        finding = None
    return {"finding": finding, "empty": empty, "figures": figures}


def audit_people_longer_term(
    item: Any,
    entry: Any,
    *,
    resolved_variables: Optional[Dict[str, Any]] = None,
    variable_configs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if item is None:
        return {}
    label = _item_label(item, resolved_variables, variable_configs) or "Longer term programmes"
    cells = _matrix_cells(entry)
    reading = interpret_upr_matrix({
        "upr_item_kind": "people_to_be_reached",
        "form_item_label": label,
        "section_name": _section_name(item),
        "disagg_values": cells,
    })
    figures: Dict[str, Any] = {}
    if reading:
        figures = {
            "cell_count": reading.get("cell_count"),
            "nonzero_count": reading.get("nonzero_count"),
            "grand_total": reading.get("grand_total"),
            "max_cell": None,
            "by_sp": reading.get("by_sp"),
            "by_year": reading.get("by_year"),
            "implausible_small": bool(reading.get("implausible_small_people_targets")),
            "preview": reading.get("value_preview"),
        }
        vals = []
        for cell in reading.get("nonzero_cells") or []:
            num = parse_upr_number(cell.get("value") if isinstance(cell, dict) else None)
            if num is not None:
                vals.append(abs(float(num)))
        if vals:
            mx = max(vals)
            figures["max_cell"] = int(mx) if float(mx).is_integer() else mx
    if reading and reading.get("implausible_small_people_targets"):
        finding = _finding(
            severity="flag",
            code="people_targets_implausible_scale",
            form_item_id=_item_id(item),
            label=label,
            text=(
                "The longer-term people-to-be-reached numbers look far too small to be real targets — "
                f"the highest figure entered is only {figures.get('max_cell')} people "
                f"(total planned: {figures.get('grand_total')} people). Country plans are usually in the "
                "thousands or more, so please double-check these numbers against the actual plan."
            ),
            figures=figures,
        )
    elif reading and (reading.get("nonzero_count") or 0) > 0:
        grand_total = figures.get("grand_total")
        try:
            total_txt = f"{int(grand_total):,}"
        except (TypeError, ValueError):
            total_txt = str(grand_total or 0)
        finding = _finding(
            severity="ok",
            code="people_targets_present",
            form_item_id=_item_id(item),
            label=label,
            text=(
                f"Longer-term people-to-be-reached figures are filled in: {total_txt} people planned "
                f"in total across {figures.get('nonzero_count') or 0} of {figures.get('cell_count') or 0} entries."
            ),
            figures=figures,
        )
    else:
        finding = _finding(
            severity="highlight",
            code="people_targets_empty",
            form_item_id=_item_id(item),
            label=label,
            text="No longer-term people-to-be-reached targets have been entered yet.",
            figures=figures,
        )
    return {"finding": finding, "reading": reading, "figures": figures}


def audit_people_emergency(
    item: Any,
    entry: Any,
    aes: Any,
    *,
    resolved_variables: Optional[Dict[str, Any]] = None,
    variable_configs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if item is None:
        return {}
    cells = _matrix_cells(entry)
    rows = matrix_row_ids(cells)
    available = list_available_emergencies(item, aes)
    selected_labels = list(rows)
    unused = unmatched_emergencies(available, selected_labels) if available else []
    nonempty_rows = []
    for row in rows:
        has_val = False
        for key, val in cells.items():
            r, _c = _split_row_col(str(key))
            if r != row:
                continue
            if not _is_blank_cell(val) and parse_upr_number(val) not in (None, 0.0):
                has_val = True
                break
        if has_val:
            nonempty_rows.append(row)
    figures = {
        "available_count": len(available),
        "available": [op.get("label") for op in available[:8]],
        "selected_rows": rows,
        "rows_with_values": nonempty_rows,
    }
    label = _item_label(item, resolved_variables, variable_configs) or "Emergency appeals (people to be reached)"
    iid = _item_id(item)
    findings: List[Dict[str, Any]] = []
    if available and not rows:
        noun = "emergency" if len(available) == 1 else "emergencies"
        findings.append(_finding(
            severity="flag",
            code="emergency_people_not_added",
            form_item_id=iid,
            label=label,
            text=(
                f"There {'is' if len(available) == 1 else 'are'} {len(available)} active {noun} this country "
                f"could report people-to-be-reached figures for ({', '.join(figures['available'][:4])}), but "
                "none were added and no numbers were entered."
            ),
            figures=figures,
        ))
    elif available and unused:
        findings.append(_finding(
            severity="highlight",
            code="emergency_people_partial",
            form_item_id=iid,
            label=label,
            text=(
                "These active emergencies were not added to the people-to-be-reached figures: "
                + "; ".join(unused[:6])
                + "."
            ),
            figures=figures,
        ))
    if rows and not nonempty_rows:
        findings.append(_finding(
            severity="flag",
            code="emergency_people_no_values",
            form_item_id=iid,
            label=label,
            text=(
                "An emergency was added to the people-to-be-reached section, but no target number "
                "was entered for it."
            ),
            figures=figures,
        ))
    if not findings and nonempty_rows:
        findings.append(_finding(
            severity="ok",
            code="emergency_people_ok",
            form_item_id=iid,
            label=label,
            text=f"{len(nonempty_rows)} emergency operation(s) have people-to-be-reached numbers entered.",
            figures=figures,
        ))
    return {"findings": findings, "figures": figures, "available": available}


def audit_funding_ifrc_secretariat(
    item: Any,
    entry: Any,
    *,
    available_emergencies: Optional[Sequence[Dict[str, str]]] = None,
    year_label: str = "Funding Requirements",
    resolved_variables: Optional[Dict[str, Any]] = None,
    variable_configs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if item is None:
        return {}
    cells = _matrix_cells(entry)
    selected = selected_ea_headers(cells)
    ifrc_vals = ifrc_row_values(cells)
    static_missing: List[str] = []
    for col in _REQUIRED_IFRC_STATIC_COLS:
        if _is_blank_cell(ifrc_vals.get(col)):
            static_missing.append(col)
    ea_missing: List[str] = []
    ea_missing_cols: List[str] = []
    for col, appeal in selected.items():
        if _ifrc_blank_for_column(ifrc_vals, col):
            ea_missing.append(appeal or col)
            ea_missing_cols.append(col)
    available = list(available_emergencies or [])
    unused = unmatched_emergencies(available, list(selected.values())) if available else []
    filled_ifrc = {
        col: val for col, val in ifrc_vals.items()
        if not _is_blank_cell(val)
    }
    required_total = len(_REQUIRED_IFRC_STATIC_COLS) + len(selected)
    required_filled = required_total - len(static_missing) - len(ea_missing_cols)
    missing_labels = [_friendly_area_label(c) for c in static_missing] + ea_missing
    figures = {
        "ifrc_filled_columns": sorted(filled_ifrc.keys()),
        "ifrc_missing_static": static_missing,
        "selected_emergencies": selected,
        "ifrc_missing_selected_ea": ea_missing,
        "unused_available_emergencies": unused[:8],
        "ifrc_totals_preview": {
            k: filled_ifrc[k] for k in list(filled_ifrc)[:10]
        },
        # Pre-translated, end-user-friendly summary (no raw SP*/EA* codes) for the
        # assignment overview figure tile — see app/services/ai/validation/assignment_review.py.
        "required_total": required_total,
        "required_filled": max(required_filled, 0),
        "missing_labels": missing_labels,
    }
    iid = _item_id(item)
    label = _item_label(item, resolved_variables, variable_configs) or year_label
    if not label or label in ("-", "—"):
        label = year_label
    findings: List[Dict[str, Any]] = []
    if static_missing:
        friendly_missing = [_friendly_area_label(c) for c in static_missing]
        findings.append(_finding(
            severity="flag",
            code="ifrc_secretariat_static_columns_blank",
            form_item_id=iid,
            label=label,
            text=(
                f"IFRC Secretariat funding is missing an amount for: {', '.join(friendly_missing)}. "
                "Every Strategic Priority and Enabling Functions category needs a figure from IFRC Secretariat."
            ),
            figures=figures,
        ))
    if ea_missing:
        findings.append(_finding(
            severity="flag",
            code="ifrc_secretariat_selected_ea_blank",
            form_item_id=iid,
            label=label,
            text=(
                "An emergency appeal was selected for funding (" + ", ".join(ea_missing) + ") but "
                "IFRC Secretariat has not entered an amount for it."
            ),
            figures=figures,
        ))
    if available and not selected:
        findings.append(_finding(
            severity="highlight",
            code="ifrc_secretariat_ea_not_selected",
            form_item_id=iid,
            label=label,
            text=(
                f"No emergency appeal is selected for funding, but {len(available)} operation(s) are "
                f"available for this country. The focal point did not select "
                f"{'it' if len(available) == 1 else 'them'}: "
                f"{', '.join(op.get('label') or '' for op in available[:4])}."
            ),
            figures=figures,
        ))
    elif unused:
        findings.append(_finding(
            severity="highlight",
            code="ifrc_secretariat_ea_partial_selection",
            form_item_id=iid,
            label=label,
            text=(
                "These available emergency appeals were not selected for funding: "
                + "; ".join(unused[:6])
                + "."
            ),
            figures=figures,
        ))
    if not findings:
        findings.append(_finding(
            severity="ok",
            code="ifrc_secretariat_complete",
            form_item_id=iid,
            label=label,
            text=f"IFRC Secretariat funding is complete for {label}.",
            figures=figures,
        ))
    return {"findings": findings, "figures": figures, "selected": selected}


def _ifrc_blank_for_column(ifrc_vals: Dict[str, Any], col: str) -> bool:
    if col in ifrc_vals:
        return _is_blank_cell(ifrc_vals.get(col))
    col_u = col.upper()
    for key, val in ifrc_vals.items():
        if str(key).upper() == col_u:
            return _is_blank_cell(val)
    return True


def audit_comments(
    item: Any,
    entry: Any,
    *,
    resolved_variables: Optional[Dict[str, Any]] = None,
    variable_configs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    text = _scalar_text(entry)
    iid = _item_id(item) if item is not None else _COMMENTS_ITEM_ID
    label = _item_label(item, resolved_variables, variable_configs) if item is not None else "Comments"
    figures = {"length": len(text), "preview": text[:400]}
    finding = _finding(
        severity="note" if text else "highlight",
        code="assignment_comment_present" if text else "assignment_comment_empty",
        form_item_id=iid,
        label=label or "Comments",
        text=(
            "A comment was entered by the reporting country (it may not be in English) — its notes "
            "must be considered when reviewing this assignment."
            if text else
            "No comment was entered by the reporting country."
        ),
        figures=figures,
    )
    return {"finding": finding, "text": text, "figures": figures}


def _collect_items_and_entries(aes: Any, entries: Optional[Iterable[Any]]) -> Tuple[List[Any], Dict[int, Any]]:
    by_item_id: Dict[int, Any] = {}
    items: List[Any] = []
    for entry in entries or []:
        item = getattr(entry, "form_item", None)
        iid = _item_id(item) or getattr(entry, "form_item_id", None)
        try:
            iid = int(iid) if iid is not None else None
        except (TypeError, ValueError):
            iid = None
        if iid is None:
            continue
        by_item_id.setdefault(iid, entry)
        if item is not None:
            items.append(item)
    # Fill from the assignment so empty sections (never saved) still appear.
    try:
        from app.models.form_items import FormItem
        from app.models.forms import FormData
        aes_id = int(getattr(aes, "id"))
        af = getattr(aes, "assigned_form", None)
        tmpl = getattr(af, "template", None)
        tmpl_id = getattr(tmpl, "id", None)
        vid = getattr(tmpl, "published_version_id", None)
        if tmpl_id:
            q = FormItem.query.filter(FormItem.template_id == int(tmpl_id))
            if vid is not None:
                q = q.filter(FormItem.version_id == int(vid))
            for item in q.all():
                items.append(item)
        fds = FormData.query.filter_by(assignment_entity_status_id=aes_id).all()
        for fd in fds:
            if fd.form_item_id:
                by_item_id.setdefault(int(fd.form_item_id), fd)
    except Exception:
        logger.debug("assignment review item/entry load skipped", exc_info=True)

    dedup_items: List[Any] = []
    seen = set()
    for item in items:
        iid = _item_id(item)
        if iid is None or iid in seen:
            continue
        seen.add(iid)
        dedup_items.append(item)
    return dedup_items, by_item_id


def _status_for_figures(figures_dict: Dict[str, Any], *finding_sources: Any) -> Dict[str, Any]:
    """Tag a figures sub-dict with the worst severity among its own finding(s).

    Lets consumers (the overview-figures tiles in
    ``app/services/ai/validation/assignment_review.py``) show a tile only for checks
    that are fully "ok" — without re-deriving each audit function's pass/fail logic a
    second time and risking it drifting out of sync. ``finding_sources`` accepts each
    check's ``finding`` (a single dict) or ``findings`` (a list of dicts) return value
    directly — worst-first precedence: any "flag" wins over any "highlight", which
    wins over any "ok".

    Returns ``{}`` unchanged when there is no underlying figures dict, so existing
    truthiness checks (``if ns:`` etc.) keep treating an unresolved item as "nothing
    to report" rather than as a dict that only has a status key.
    """
    if not figures_dict:
        return {}
    sevs: List[str] = []
    for src in finding_sources:
        if isinstance(src, dict):
            sev = src.get("severity")
            if sev:
                sevs.append(sev)
        elif isinstance(src, list):
            sevs.extend(f.get("severity") for f in src if isinstance(f, dict) and f.get("severity"))
    status = "flag" if "flag" in sevs else "highlight" if "highlight" in sevs else "ok" if "ok" in sevs else None
    return {**figures_dict, "status": status}


def build_upr_assignment_review_pack(
    aes: Any,
    entries: Optional[Iterable[Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Deterministic UPR assignment audit used by the LLM summary and field prompts."""
    af = getattr(aes, "assigned_form", None) if aes is not None else None
    tmpl = getattr(af, "template", None)
    template_id = getattr(tmpl, "id", None)
    if not is_upr_form_template(template_id):
        return None

    resolved_variables: Dict[str, Any] = {}
    variable_configs: Dict[str, Any] = {}
    try:
        from app.services.forms.variable_resolution_service import VariableResolutionService
        resolved_variables, variable_configs = VariableResolutionService.resolve_for_assignment_display(aes)
    except Exception:
        logger.debug("assignment review variable resolution failed", exc_info=True)

    items, by_item_id = _collect_items_and_entries(aes, entries)
    reach_lt = _resolve_item(
        items,
        fallback_id=PLAN_ITEM_FALLBACKS.get("reach_longer_term"),
        needles=PLAN_LABEL_NEEDLES.get("reach_longer_term") or ("longer term programme",),
    )
    reach_ea = _resolve_item(
        items,
        fallback_id=PLAN_ITEM_FALLBACKS.get("reach_emergency"),
        needles=PLAN_LABEL_NEEDLES.get("reach_emergency") or ("emergency appeal",),
    )
    funding_y0 = _resolve_item(
        items,
        fallback_id=PLAN_ITEM_FALLBACKS.get("funding_y0"),
        needles=("funding requirement",),
    )
    comments = _resolve_item(
        items,
        fallback_id=_COMMENTS_ITEM_ID,
        needles=("comment",),
    )

    ns = audit_ns_key_figures(
        items, by_item_id,
        resolved_variables=resolved_variables, variable_configs=variable_configs,
    )
    people = audit_people_longer_term(
        reach_lt, _entry_for_item(by_item_id, reach_lt),
        resolved_variables=resolved_variables, variable_configs=variable_configs,
    )
    emergency = audit_people_emergency(
        reach_ea, _entry_for_item(by_item_id, reach_ea), aes,
        resolved_variables=resolved_variables, variable_configs=variable_configs,
    )
    funding = audit_funding_ifrc_secretariat(
        funding_y0,
        _entry_for_item(by_item_id, funding_y0),
        available_emergencies=(emergency.get("available") if emergency else None)
        or list_available_emergencies(funding_y0, aes),
        year_label="Funding Requirements for the assignment year",
        resolved_variables=resolved_variables, variable_configs=variable_configs,
    )
    comment = audit_comments(
        comments, _entry_for_item(by_item_id, comments),
        resolved_variables=resolved_variables, variable_configs=variable_configs,
    )

    findings: List[Dict[str, Any]] = []
    for block in (ns.get("finding"), people.get("finding"), comment.get("finding")):
        if block:
            findings.append(block)
    findings.extend(emergency.get("findings") or [])
    findings.extend(funding.get("findings") or [])

    flags = [f for f in findings if f.get("severity") == "flag"]
    highlights = [f for f in findings if f.get("severity") == "highlight"]
    oks = [f for f in findings if f.get("severity") == "ok"]

    country = None
    try:
        from app.utils.api_serialization import _country_for_aes
        c = _country_for_aes(aes)
        country = getattr(c, "name", None) if c else None
    except Exception:
        country = None

    return {
        "template_id": int(template_id) if template_id is not None else None,
        "period_name": getattr(af, "period_name", None),
        "country_name": country,
        "comment_text": comment.get("text") or "",
        "figures": {
            "ns_key_figures": _status_for_figures(ns.get("figures") or {}, ns.get("finding")),
            "people_longer_term": _status_for_figures(people.get("figures") or {}, people.get("finding")),
            "people_emergency": _status_for_figures(emergency.get("figures") or {}, emergency.get("findings")),
            "funding_y0_ifrc": _status_for_figures(funding.get("figures") or {}, funding.get("findings")),
        },
        "findings": findings,
        "flags": flags,
        "highlights": highlights,
        "ok": oks,
    }


def format_upr_assignment_review_for_prompt(pack: Optional[Dict[str, Any]]) -> str:
    if not isinstance(pack, dict) or not pack:
        return ""
    lines = [
        "\nUPR ASSIGNMENT REVIEW PACK (deterministic checks on THIS form — treat as facts):\n",
        f"- Country / period: {pack.get('country_name') or '—'} / {pack.get('period_name') or '—'}\n",
    ]
    figures = pack.get("figures") if isinstance(pack.get("figures"), dict) else {}
    people_fig = figures.get("people_longer_term") or {}
    if people_fig:
        lines.append(
            f"- Longer-term people to be reached: cells={people_fig.get('cell_count')} "
            f"nonzero={people_fig.get('nonzero_count')} max_cell={people_fig.get('max_cell')} "
            f"grand_total={people_fig.get('grand_total')} "
            f"implausible_small={people_fig.get('implausible_small')}\n"
        )
    ns_fig = figures.get("ns_key_figures") or {}
    if ns_fig:
        lines.append(
            f"- National Society key figures filled: {ns_fig.get('filled')} of {ns_fig.get('total')}\n"
        )
    em_fig = figures.get("people_emergency") or {}
    if em_fig:
        lines.append(
            f"- Emergency people-to-be-reached: available={em_fig.get('available_count')} "
            f"rows={em_fig.get('selected_rows')} with_values={em_fig.get('rows_with_values')}\n"
        )
    fund_fig = figures.get("funding_y0_ifrc") or {}
    if fund_fig:
        lines.append(
            f"- IFRC Secretariat funding (assignment year): "
            f"required_filled={fund_fig.get('required_filled')}/{fund_fig.get('required_total')} "
            f"(plain-language missing: {fund_fig.get('missing_labels')}) "
            f"filled={fund_fig.get('ifrc_filled_columns')} "
            f"missing_static={fund_fig.get('ifrc_missing_static')} "
            f"selected_EA={fund_fig.get('selected_emergencies')} "
            f"missing_selected_EA={fund_fig.get('ifrc_missing_selected_ea')} "
            f"unselected_available={fund_fig.get('unused_available_emergencies')}\n"
        )
    comment = str(pack.get("comment_text") or "").strip()
    if comment:
        preview = comment if len(comment) <= 1200 else comment[:1197] + "..."
        lines.append(
            "- Reporting-country COMMENT (item 956; may be non-English — translate and apply caveats):\n"
            f"  <<<\n{preview}\n  >>>\n"
        )
    else:
        lines.append("- Reporting-country comment (item 956): empty.\n")

    lines.append("- Findings:\n")
    for finding in (pack.get("findings") or [])[:16]:
        if not isinstance(finding, dict):
            continue
        lines.append(
            f"  - [{finding.get('severity')}] {finding.get('code')} "
            f"(item {finding.get('form_item_id')} {finding.get('label')}): {finding.get('text')}\n"
        )
    return "".join(lines)


def assignment_review_rules_for_field_kind(kind: str) -> str:
    """Extra per-field rules so details validation uses the same assignment-review policy."""
    if kind == "funding":
        return (
            "IFRC SECRETARIAT FUNDING COMPLETENESS (Unified Country Plan, assignment-year matrix / item 967):\n"
            "- The IFRC Secretariat row MUST have a value in every static column (SP1–SP5 and EFs).\n"
            "- Selectable emergency-appeal columns (EA1/EA2/EA3): if an emergency is selected "
            "(col_header|EA*) and IFRC Secretariat has no value in that column, verdict=discrepancy (flag).\n"
            "- If no emergency is selected in those columns BUT emergencies are listed as available for this "
            "country, highlight it (do not mark the whole matrix good solely because SP columns are filled).\n"
            "- HNS/PNS rows are not held to this IFRC Secretariat completeness rule.\n"
        )
    if kind == "people_to_be_reached":
        return (
            "EMERGENCY PEOPLE-TO-BE-REACHED (item 960) AND LONGER-TERM TARGETS (item 954):\n"
            "- Longer-term cells are people TARGETS. Tiny integers vs a prior assignment of thousands/millions "
            "is a discrepancy.\n"
            "- If GO emergencies are available for this country and the emergency matrix has no rows or no "
            "people values, that is a flag: the focal point did not add the emergency and did not report its value.\n"
        )
    if kind == "ns_kpis":
        return (
            "NATIONAL SOCIETY KEY FIGURES:\n"
            "- If this section is completely empty, that is a form-level issue (flag), not 'nothing to validate'.\n"
            "- Blank KPI with a matching Unified Plan IN SUPPORT OF card is a discrepancy when the card has a figure.\n"
        )
    if kind == "comments":
        return (
            "ASSIGNMENT COMMENT (item 956):\n"
            "- This free-text may be in a language other than English. Understand it and summarise in English.\n"
            "- Caveats here (why a year is blank, why people figures changed, why an emergency is omitted) "
            "MUST be applied when judging other fields on this assignment.\n"
        )
    return ""


__all__ = [
    "assignment_review_rules_for_field_kind",
    "audit_comments",
    "audit_funding_ifrc_secretariat",
    "audit_ns_key_figures",
    "audit_people_emergency",
    "audit_people_longer_term",
    "build_upr_assignment_review_pack",
    "format_upr_assignment_review_for_prompt",
    "ifrc_row_values",
    "list_available_emergencies",
    "selected_ea_headers",
    "unmatched_emergencies",
]
