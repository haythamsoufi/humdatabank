"""Expand a Unified Plan/Report matrix into one labeled line per reported cell.

The validation summary used to show each matrix as a single row with an empty
value, because the numbers live in ``disagg_data`` cell keys rather than
``FormData.value``. These lines are what the summary lists and what per-cell
validation judges.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from plugins.upr.ai.assignment_review import _HEADER_KEY_RE, _META_KEY_RE, _friendly_area_label, _split_row_col
from plugins.upr.ai.matrix_reading import classify_actor, classify_sp, parse_upr_number
from plugins.upr.dashboards.catalog import AREA_LABELS

_YEAR_ROW_RE = re.compile(r"^(?:19|20)\d{2}$")
_AREA_CODES = {code.upper() for code in AREA_LABELS}


def matrix_cells_from_disagg(disagg: Any) -> Dict[str, Any]:
    """Flat ``cell key -> value`` map, unwrapping ``values`` and modified/original pairs."""
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
        out[key] = val
    return out


def _matrix_config(form_item: Any, matrix_schema: Any) -> Dict[str, Any]:
    if form_item is not None:
        cfg = getattr(form_item, "config", None) or {}
        if isinstance(cfg, dict):
            raw = cfg.get("matrix_config")
            if isinstance(raw, dict):
                return raw
    return matrix_schema if isinstance(matrix_schema, dict) else {}


def _is_year_row(row: str, column: str) -> bool:
    if not _YEAR_ROW_RE.match(row or ""):
        return False
    code = (column or "").strip().upper()
    if code in _AREA_CODES or code in {"EA1", "EA2", "EA3", "EO"}:
        return True
    return bool(classify_sp(column)[0])


def _lookup_row_labels(row_ids: List[str], lookup_id: str) -> Dict[str, str]:
    numeric: List[int] = []
    for rid in row_ids:
        try:
            numeric.append(int(rid))
        except (TypeError, ValueError):
            continue
    if not numeric:
        return {}
    try:
        from flask import has_app_context

        if not has_app_context():
            return {}
    except Exception:
        return {}

    labels: Dict[str, str] = {}
    try:
        if lookup_id == "national_society":
            from app.models.organization import NationalSociety

            rows = NationalSociety.query.filter(NationalSociety.id.in_(numeric)).all()
            for obj in rows:
                labels[str(obj.id)] = str(getattr(obj, "name", None) or obj.id)
        elif lookup_id == "country_map":
            from app.models import Country

            rows = Country.query.filter(Country.id.in_(numeric)).all()
            for obj in rows:
                labels[str(obj.id)] = str(getattr(obj, "name", None) or obj.id)
        elif str(lookup_id).isdigit():
            from app.models import LookupListRow

            rows = LookupListRow.query.filter(LookupListRow.id.in_(numeric)).all()
            for obj in rows:
                data = obj.data if isinstance(getattr(obj, "data", None), dict) else {}
                name = data.get("name") or data.get("title") or obj.id
                labels[str(obj.id)] = str(name)
    except Exception:
        return labels
    return labels


def _column_label(column: str, headers: Dict[str, str]) -> str:
    header = (headers.get(column) or "").strip()
    if header and header.lower() not in {"none", "null", "-"}:
        return header
    code = (column or "").strip().upper()
    if code in {"EA1", "EA2", "EA3"}:
        return f"Emergency appeal {code[-1]}"
    friendly = _friendly_area_label(column)
    if friendly and friendly != column:
        return friendly
    sp_key, sp_label = classify_sp(column)
    if sp_key and sp_label:
        return sp_label[:1].upper() + sp_label[1:]
    return column


def _row_label(row: str, column: str, lookup_labels: Dict[str, str]) -> str:
    if _is_year_row(row, column):
        return row
    actor = classify_actor(row)
    if actor == "HNS":
        return "Host National Society"
    if actor:
        return actor
    if row.isdigit():
        return lookup_labels.get(row) or f"National Society {row}"
    return row


def _unit_for_kind(kind: str) -> str:
    if kind in ("people_to_be_reached", "people_reached"):
        return "people"
    if kind == "bilateral_support":
        return "tick"
    if kind == "funding":
        return "chf"
    return "number"


def _item_kind(
    *,
    template_id: Any,
    item_label: str,
    section_name: str,
    subsection_name: str,
    cells: Dict[str, Any],
) -> str:
    from plugins.upr.ai.form_validation import infer_upr_item_kind

    return infer_upr_item_kind(
        {
            "template_id": template_id,
            "form_item_label": item_label,
            "form_item_type": "matrix",
            "section_name": section_name,
            "subsection_name": subsection_name,
            "disagg_values": cells,
        }
    )


def upr_matrix_detail_lines(
    *,
    disagg_data: Any,
    form_item: Any = None,
    matrix_schema: Any = None,
    template_id: Any = None,
    item_label: str = "",
    section_name: str = "",
    subsection_name: str = "",
    row_labels: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """One dict per reported cell: key, human label, value, and unit.

    Header cells (``col_header|EA1``) are not lines. They rename emergency-appeal
    columns. Numeric National Society ids are resolved when an app context is
    available; ``row_labels`` overrides that lookup (tests, or a caller that
    already resolved names).
    """
    cells = matrix_cells_from_disagg(disagg_data)
    if not cells:
        return []

    headers: Dict[str, str] = {}
    for key, raw in cells.items():
        match = _HEADER_KEY_RE.match(str(key))
        if not match:
            continue
        col = str(match.group(1) or "").strip()
        text = str(raw or "").strip()
        if col and text:
            headers[col] = text

    config = _matrix_config(form_item, matrix_schema)
    lookup_id = str(config.get("lookup_list_id") or getattr(form_item, "lookup_list_id", "") or "").strip()
    numeric_rows: List[str] = []
    for key in cells:
        if _META_KEY_RE.match(str(key)) or _HEADER_KEY_RE.match(str(key)):
            continue
        row, col = _split_row_col(str(key))
        if row.isdigit() and not _is_year_row(row, col):
            numeric_rows.append(row)
    resolved = _lookup_row_labels(numeric_rows, lookup_id)
    if row_labels:
        resolved.update({str(k): str(v) for k, v in row_labels.items() if v})

    kind = _item_kind(
        template_id=template_id,
        item_label=item_label or str(getattr(form_item, "label", "") or ""),
        section_name=section_name,
        subsection_name=subsection_name,
        cells=cells,
    )
    unit = _unit_for_kind(kind)
    lines: List[Dict[str, Any]] = []
    for key, raw in cells.items():
        if _META_KEY_RE.match(str(key)) or _HEADER_KEY_RE.match(str(key)):
            continue
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            continue
        row, col = _split_row_col(str(key))
        if not row:
            continue
        row_name = _row_label(row, col, resolved)
        col_name = _column_label(col, headers) if col else ""
        label = f"{row_name} — {col_name}" if col_name else row_name
        number = parse_upr_number(raw)
        value: Any = raw
        value_is_text = False
        value_display: Any = raw
        if unit == "tick" and number in (0.0, 1.0):
            value_is_text = True
            value_display = "Yes" if number == 1.0 else "No"
            value = int(number)
        elif number is not None:
            value = int(number) if float(number).is_integer() else number
            value_display = value
        else:
            value_is_text = True
            value_display = str(raw).strip()

        sp_key, _sp_label = classify_sp(col or row)
        actor = classify_actor(row_name) or classify_actor(row)
        if actor is None and row_name not in {"Host National Society"} and not _is_year_row(row, col):
            actor = row_name
        if row_name == "Host National Society":
            actor = "HNS"
        lines.append(
            {
                "key": str(key),
                "label": label,
                "row_label": row_name,
                "column_label": col_name,
                "value": value,
                "value_display": value_display,
                "value_is_text": value_is_text,
                "unit": unit,
                "kind": kind,
                "sp_key": sp_key,
                "actor": actor,
            }
        )
    return lines


def _fmt_number(value: Any) -> str:
    number = parse_upr_number(value)
    if number is None:
        return str(value)
    if float(number).is_integer():
        return f"{int(number):,}"
    return f"{number:,.2f}"


def _history_conflict(line: Dict[str, Any], comparison: Any) -> Optional[str]:
    if not isinstance(comparison, dict):
        return None
    sp = str(line.get("sp_key") or "").lower()
    actor = str(line.get("actor") or "").lower()
    if not sp and not actor:
        return None
    current = parse_upr_number(line.get("value"))
    for note in comparison.get("notes") or []:
        if not isinstance(note, dict):
            continue
        period = note.get("period") or "a prior assignment"
        for diff in note.get("cell_diffs") or []:
            if not isinstance(diff, dict):
                continue
            ident = diff.get("identity") if isinstance(diff.get("identity"), dict) else {}
            diff_sp = str(ident.get("sp") or "").lower()
            diff_actor = str(ident.get("actor") or "").lower()
            if sp and diff_sp and sp != diff_sp:
                continue
            if actor and diff_actor and actor not in diff_actor and diff_actor not in actor:
                continue
            if not sp and diff_sp:
                continue
            historical = parse_upr_number(diff.get("historical"))
            if current is None or historical is None or historical == 0:
                continue
            if abs(current - historical) / abs(historical) <= 0.5:
                continue
            return (
                f"{line.get('label')}: {_fmt_number(current)} differs from "
                f"{_fmt_number(historical)} in {period}."
            )
    return None


def _llm_line_map(llm_json: Any) -> Dict[str, Dict[str, Any]]:
    if not isinstance(llm_json, dict):
        return {}
    raw = llm_json.get("line_verdicts")
    if not isinstance(raw, list):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        verdict = str(item.get("verdict") or "").strip().lower()
        if not key or verdict not in {"good", "discrepancy", "uncertain"}:
            continue
        out[key] = item
    return out


def build_matrix_line_verdicts(
    lines: Any,
    *,
    parent_verdict: Optional[str] = None,
    parent_opinion: Optional[str] = None,
    parent_confidence: Any = None,
    comparison: Any = None,
    llm_json: Any = None,
) -> List[Dict[str, Any]]:
    """Per-cell verdicts for a matrix validation.

    Hard checks win over the matrix-level verdict: a people target below 100
    is a discrepancy, and a bilateral tick is not judged as CHF. Otherwise a
    line keeps the model's own line verdict, then the matrix verdict.
    """
    if not isinstance(lines, list) or not lines:
        return []
    parent = str(parent_verdict or "").strip().lower()
    if parent not in {"good", "discrepancy", "uncertain"}:
        parent = "uncertain"
    try:
        parent_conf = float(parent_confidence) if parent_confidence is not None else 0.55
    except (TypeError, ValueError):
        parent_conf = 0.55
    llm_lines = _llm_line_map(llm_json)
    parent_text = str(parent_opinion or "").strip()
    verdicts: List[Dict[str, Any]] = []

    for line in lines:
        if not isinstance(line, dict) or not line.get("key"):
            continue
        unit = str(line.get("unit") or "number")
        label = str(line.get("label") or line.get("key"))
        number = parse_upr_number(line.get("value"))
        hard = False
        verdict = parent
        confidence = parent_conf
        if unit == "tick":
            mark = "Yes" if number == 1.0 else "No"
            opinion = f"{label}: {mark}. This is a support tick, not a funding amount."
            verdict = "uncertain"
            confidence = 0.6
            hard = True
        elif unit == "people" and number is not None and 0 < abs(number) < 100:
            opinion = (
                f"{label}: {_fmt_number(number)} is far too small to be a people target. "
                "People-to-be-reached figures are usually in the thousands."
            )
            verdict = "discrepancy"
            confidence = 0.78
            hard = True
        elif unit == "people":
            shown = _fmt_number(number) if number is not None else line.get("value_display") or line.get("value")
            opinion = f"{label}: {shown} people."
        elif unit == "chf":
            shown = _fmt_number(number) if number is not None else line.get("value_display") or line.get("value")
            opinion = f"{label}: {shown} CHF."
        else:
            shown = line.get("value_display") if line.get("value_display") is not None else line.get("value")
            opinion = f"{label}: {shown}."

        conflict = _history_conflict(line, comparison)
        if conflict:
            opinion = conflict
            verdict = "discrepancy"
            confidence = max(confidence, 0.72)
            hard = True

        llm_line = llm_lines.get(str(line["key"]))
        if llm_line and not hard:
            verdict = str(llm_line.get("verdict") or verdict).strip().lower()
            llm_opinion = str(llm_line.get("opinion") or "").strip()
            if llm_opinion:
                opinion = llm_opinion
            if llm_line.get("confidence") is not None:
                try:
                    confidence = float(llm_line["confidence"])
                except (TypeError, ValueError):
                    pass
        elif not hard and parent_text and verdict != "good":
            extra = parent_text if len(parent_text) <= 280 else parent_text[:277] + "..."
            if extra.lower() not in opinion.lower():
                opinion = f"{opinion} {extra}"

        verdicts.append(
            {
                "key": str(line["key"]),
                "verdict": verdict,
                "confidence": confidence,
                "opinion": opinion,
            }
        )
    return verdicts
