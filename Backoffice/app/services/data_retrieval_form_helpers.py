# ========== Data Retrieval: Form Helpers ==========
"""
Shared helpers for form-data value extraction, bulk RBAC, and template/field resolution.

Used by: data_retrieval_form (API queries), ai_data.form_retrieval (chatbot tools).
"""

import json
import logging
from datetime import datetime as _dt
from typing import Any, Dict, List, Optional, Union

from sqlalchemy import and_, or_

from app.models import FormTemplate, FormTemplateVersion, FormItem, FormSection, FormData
from app.models.assignments import AssignmentEntityStatus
from app.extensions import db
from app.services.reporting_period_service import period_chronology_sort_key
from app.utils.sql_utils import safe_ilike_pattern

from .data_retrieval_shared import (
    form_item_privacy_is_public_expr,
    user_allowed_country_ids,
)

logger = logging.getLogger(__name__)


def parse_matrix_disagg_payload(disagg_data: Any) -> dict:
    if not disagg_data:
        return {}
    if isinstance(disagg_data, str):
        try:
            disagg_data = json.loads(disagg_data) if disagg_data.strip() else {}
        except Exception:
            return {}
    if not isinstance(disagg_data, dict):
        return {}
    nested = disagg_data.get("values")
    if isinstance(nested, dict):
        return nested
    return disagg_data


def extract_numeric_from_formdata(
    value: Any,
    disagg_data: Any,
    *,
    row_label: Optional[str] = None,
    column: Optional[str] = None,
    matrix_row_filter: Optional[str] = None,
) -> Optional[float]:
    """Extract numeric value from FormData.value / disagg_data."""
    try:
        if row_label and column:
            payload = parse_matrix_disagg_payload(disagg_data)
            if not payload:
                return None
            key = f"{row_label}_{column}"
            val = payload.get(key)
            if val is None:
                return 0.0
            if isinstance(val, dict) and ("modified" in val or "original" in val):
                val = val.get("modified") if val.get("modified") is not None else val.get("original")
            try:
                return float(str(val).replace(",", "").strip() or 0)
            except (TypeError, ValueError):
                return 0.0

        if value is not None:
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                s = value.strip().replace(",", "").replace("\u00A0", " ").replace(" ", "")
                if s:
                    return float(s)

        if disagg_data:
            dd = disagg_data
            if isinstance(dd, str):
                try:
                    dd = json.loads(dd)
                except Exception:
                    dd = None
            if isinstance(dd, dict):
                payload = parse_matrix_disagg_payload(dd)
                total = 0.0
                found = False
                for k, v in payload.items():
                    if k.startswith("_"):
                        continue
                    if matrix_row_filter and matrix_row_filter not in str(k):
                        continue
                    if isinstance(v, dict) and ("modified" in v or "original" in v):
                        v = v.get("modified") if v.get("modified") is not None else v.get("original")
                    if isinstance(v, (int, float)):
                        total += float(v)
                        found = True
                    elif v is not None:
                        try:
                            total += float(str(v).replace(",", ""))
                            found = True
                        except (ValueError, TypeError):
                            pass
                if found:
                    return total
                vals = dd.get("values")
                if isinstance(vals, dict):
                    subtotal = sum(x for x in vals.values() if isinstance(x, (int, float)))
                    return float(subtotal) if subtotal else None
    except Exception as exc:
        logger.debug("extract_numeric_from_formdata failed: %s", exc)
        return None
    return None


def breakdown_from_disagg(
    disagg_data: Any,
    matrix_row_filter: Optional[str] = None,
) -> Dict[str, float]:
    """Return flat numeric breakdown dict from matrix disagg_data."""
    breakdown: Dict[str, float] = {}
    payload = parse_matrix_disagg_payload(disagg_data)
    if not payload:
        return breakdown
    for k, v in payload.items():
        if k.startswith("_"):
            continue
        if matrix_row_filter and matrix_row_filter not in str(k):
            continue
        if isinstance(v, dict) and ("modified" in v or "original" in v):
            v = v.get("modified") if v.get("modified") is not None else v.get("original")
        if v is None:
            continue
        try:
            n = float(str(v).replace(",", ""))
            breakdown[k] = breakdown.get(k, 0.0) + n
        except (TypeError, ValueError):
            pass
    return breakdown


def matrix_breakdown_key(row_label: str, column: Optional[str] = None) -> str:
    """Build the flat key used in matrix disagg breakdown dicts."""
    row = (row_label or "").strip()
    if column:
        return f"{row}_{column.strip()}"
    return row


def amount_from_breakdown(
    breakdown: Dict[str, float],
    row_label: str,
    column: Optional[str] = None,
) -> float:
    """Read a numeric amount for a matrix row (and optional column) from a flat breakdown."""
    if not breakdown:
        return 0.0
    key = matrix_breakdown_key(row_label, column)
    if key in breakdown:
        return float(breakdown.get(key) or 0)
    if column:
        return 0.0
    total = 0.0
    prefix = f"{row_label}_"
    for k, v in breakdown.items():
        if str(k).startswith("_"):
            continue
        if str(k) == row_label or str(k).startswith(prefix):
            total += float(v or 0)
    return total


def matrix_breakdown_sum(breakdown: Dict[str, float]) -> float:
    """Sum all numeric entries in a flat matrix breakdown (ignores underscore-prefixed keys)."""
    if not breakdown:
        return 0.0
    return sum(float(v or 0) for k, v in breakdown.items() if not str(k).startswith("_"))


def apply_matrix_share_analysis(
    rows: List[Dict[str, Any]],
    *,
    matrix_share_rows: List[str],
    matrix_share_column: Optional[str] = None,
    min_share_pct: Optional[float] = None,
    share_match: str = "any",
    share_threshold_rows: Optional[List[str]] = None,
    denominator_by_submission: Optional[Dict[int, float]] = None,
) -> List[Dict[str, Any]]:
    """
    Enrich cross-country matrix rows with per-row amounts and share percentages.

    Denominator: KPI-linked total for the submission when available, else matrix row sum.
    """
    if not matrix_share_rows:
        return rows

    share_match_norm = (share_match or "any").strip().lower()
    if share_match_norm not in {"any", "all"}:
        share_match_norm = "any"
    threshold_rows = share_threshold_rows or matrix_share_rows
    denom_map = denominator_by_submission or {}

    enriched: List[Dict[str, Any]] = []
    for row in rows:
        breakdown = row.get("breakdown") or {}
        share_breakdown: Dict[str, Dict[str, Any]] = {}
        amounts: Dict[str, float] = {}
        for label in matrix_share_rows:
            amt = amount_from_breakdown(breakdown, label, matrix_share_column)
            amounts[label] = amt
            share_breakdown[label] = {"amount": amt}

        if all(amounts.get(label, 0) == 0 for label in matrix_share_rows):
            continue

        sid = row.get("submission_id")
        kpi_denom = 0.0
        if sid is not None:
            try:
                kpi_denom = float(denom_map.get(int(sid), 0.0))
            except (TypeError, ValueError):
                kpi_denom = 0.0
        matrix_total = matrix_breakdown_sum(breakdown)
        if matrix_total <= 0:
            matrix_total = sum(amounts.values())
        denominator = kpi_denom if kpi_denom > 0 else matrix_total
        denom_source = "kpi" if kpi_denom > 0 else "matrix_sum"

        for label in matrix_share_rows:
            amt = amounts[label]
            pct = round((amt / denominator) * 100, 2) if denominator > 0 else None
            share_breakdown[label]["share_pct"] = pct

        enriched.append({
            **row,
            "share_breakdown": share_breakdown,
            "share_denominator": denominator,
            "share_denominator_source": denom_source,
        })

    if min_share_pct is not None:
        try:
            threshold = float(min_share_pct)
            filtered: List[Dict[str, Any]] = []
            for row in enriched:
                sbd = row.get("share_breakdown") or {}
                checks = []
                for label in threshold_rows:
                    pct = (sbd.get(label) or {}).get("share_pct")
                    checks.append(isinstance(pct, (int, float)) and float(pct) >= threshold)
                if not checks:
                    continue
                if share_match_norm == "all" and all(checks):
                    filtered.append(row)
                elif share_match_norm == "any" and any(checks):
                    filtered.append(row)
            enriched = filtered
        except (TypeError, ValueError):
            pass

    enriched.sort(
        key=lambda r: (
            -max(
                float((r.get("share_breakdown") or {}).get(label, {}).get("share_pct") or 0)
                for label in matrix_share_rows
            ),
            r.get("country_name") or "",
        )
    )
    return enriched


def slugify_matrix_row_label(label: str) -> str:
    """Stable snake_case key for a matrix row label."""
    import re
    slug = re.sub(r"[^a-z0-9]+", "_", (label or "").strip().lower())
    return slug.strip("_") or "row"


def enrich_matrix_share_display_rows(
    rows: List[Dict[str, Any]],
    matrix_share_rows: List[str],
    *,
    min_share_pct: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Add flat display fields (value, *_pct, matching_sources) for tables and summaries."""
    threshold = None
    if min_share_pct is not None:
        try:
            threshold = float(min_share_pct)
        except (TypeError, ValueError):
            threshold = None

    for row in rows:
        row["value"] = row.get("total")
        sb = row.get("share_breakdown") or {}
        matching: List[str] = []
        max_pct = 0.0
        for label in matrix_share_rows:
            entry = sb.get(label) or {}
            slug = slugify_matrix_row_label(label)
            pct = entry.get("share_pct")
            row[f"{slug}_amount"] = entry.get("amount")
            row[f"{slug}_pct"] = pct
            if isinstance(pct, (int, float)):
                max_pct = max(max_pct, float(pct))
                if threshold is not None and float(pct) >= threshold:
                    matching.append(label)
        row["matching_sources"] = matching
        row["max_share_pct"] = round(max_pct, 2) if max_pct else None
    return rows


def infer_matrix_share_denominator_kpi_code(
    *,
    field_label: str,
    template_name: Optional[str],
    template_identifier: Optional[Union[int, str]],
    matrix_share_rows: Optional[List[str]],
    explicit_kpi_code: Optional[str] = None,
) -> Optional[str]:
    """Best-effort KPI denominator when the LLM omits denominator_kpi_code."""
    if explicit_kpi_code and str(explicit_kpi_code).strip():
        return str(explicit_kpi_code).strip()
    if not matrix_share_rows:
        return None
    field = (field_label or "").strip().lower()
    tmpl = (template_name or "").strip().lower()
    tmpl_id = str(template_identifier or "").strip().lower()
    if "fdrs" not in tmpl and tmpl_id != "fdrs" and tmpl_id != "21":
        return None
    if "income" not in field:
        return None
    try:
        from app.services.data_quality.catalogs.fdrs_v1_catalog import FINANCE_TOTAL_INCOME
        return FINANCE_TOTAL_INCOME
    except Exception:
        return None


def load_submission_values_by_kpi_code(
    submission_ids: List[int],
    template_id: int,
    kpi_code: str,
) -> Dict[int, float]:
    """Load positive numeric FormData values keyed by submission id for a template KPI code."""
    from app.models import IndicatorBank

    if not submission_ids or not kpi_code or not template_id:
        return {}
    indicators = IndicatorBank.query.filter(IndicatorBank.fdrs_kpi_code == kpi_code).all()
    if not indicators:
        return {}
    item_ids = [
        int(fi.id)
        for fi in FormItem.query.filter(
            FormItem.template_id == int(template_id),
            FormItem.indicator_bank_id.in_([int(i.id) for i in indicators]),
            FormItem.archived.is_(False),
        ).all()
    ]
    if not item_ids:
        return {}
    q = (
        db.session.query(
            FormData.assignment_entity_status_id.label("aes_id"),
            FormData.value.label("value"),
            FormData.disagg_data.label("disagg_data"),
        )
        .filter(
            FormData.assignment_entity_status_id.in_(submission_ids),
            FormData.form_item_id.in_(item_ids),
            or_(FormData.data_not_available.is_(None), FormData.data_not_available.is_(False)),
            or_(FormData.not_applicable.is_(None), FormData.not_applicable.is_(False)),
        )
    )
    out: Dict[int, float] = {}
    for row in q.all():
        num = extract_numeric_from_formdata(row.value, row.disagg_data)
        if num is not None and num > 0:
            out[int(row.aes_id)] = float(num)
    return out


def formdata_has_value_filters():
    """Standard FormData quality filters (not N/A, has value or disagg)."""
    return and_(
        or_(FormData.data_not_available.is_(None), FormData.data_not_available.is_(False)),
        or_(FormData.not_applicable.is_(None), FormData.not_applicable.is_(False)),
        or_(FormData.value.isnot(None), FormData.disagg_data.isnot(None)),
    )


def resolve_bulk_allowed_country_ids(max_countries: int) -> Optional[List[int]]:
    allowed_country_ids_raw = user_allowed_country_ids()
    if allowed_country_ids_raw is None:
        return None
    allowed = [int(x) for x in allowed_country_ids_raw if x is not None]
    if len(allowed) > int(max_countries):
        allowed = allowed[: int(max_countries)]
    return allowed


def apply_bulk_rbac(q, can_see_ifrc: bool, allowed_country_ids: Optional[List[int]], *, join_form_item: bool = False):
    """Apply standard bulk-query RBAC/privacy filters to a query with AES in scope."""
    if join_form_item:
        q = q.join(FormItem, FormData.form_item_id == FormItem.id)
    if not can_see_ifrc:
        return q.filter(form_item_privacy_is_public_expr())
    if allowed_country_ids is not None:
        return q.filter(
            or_(
                form_item_privacy_is_public_expr(),
                AssignmentEntityStatus.entity_id.in_(allowed_country_ids),
            )
        )
    return q


def submission_recency_ts(entry: dict) -> _dt:
    try:
        t1 = entry.get("timestamp") if isinstance(entry.get("timestamp"), _dt) else _dt.min
        t2 = entry.get("assigned_at") if isinstance(entry.get("assigned_at"), _dt) else _dt.min
        return t1 if t1 >= t2 else t2
    except Exception:
        return _dt.min


def submission_sort_key(entry: dict) -> tuple:
    return (
        period_chronology_sort_key(
            entry.get("period_name"),
            period_start=entry.get("period_start"),
            period_end=entry.get("period_end"),
        ),
        submission_recency_ts(entry),
        int(entry.get("submission_id") or 0),
    )


def pick_most_recent_per_country(by_country_submissions: Dict[int, List[dict]]) -> Dict[int, dict]:
    """Pick the most recent submission entry per country."""
    result: Dict[int, dict] = {}
    for cid, entries in by_country_submissions.items():
        if not entries:
            continue
        candidates = [e for e in entries if e.get("has_data")]
        if not candidates:
            candidates = entries
        chosen = max(candidates, key=submission_sort_key)
        result[int(cid)] = chosen
    return result


def resolve_template_by_identifier(template_identifier: Union[int, str]) -> Optional[FormTemplate]:
    template = None
    if isinstance(template_identifier, int):
        template = db.session.get(FormTemplate, template_identifier)
    elif isinstance(template_identifier, str):
        ident = template_identifier.strip()
        if ident.isdigit():
            template = db.session.get(FormTemplate, int(ident))
        if not template and ident:
            template = (
                FormTemplate.query
                .join(FormTemplateVersion, FormTemplateVersion.template_id == FormTemplate.id)
                .filter(FormTemplateVersion.name.ilike(safe_ilike_pattern(ident)))
                .first()
            )
    return template


def resolve_form_items_by_label(
    field_label_or_name: str,
    *,
    template_id: Optional[int] = None,
    item_types: Optional[List[str]] = None,
) -> List[FormItem]:
    search_term = (field_label_or_name or "").strip()
    if not search_term:
        return []
    types = item_types or ["matrix", "indicator", "question"]
    search_pattern = safe_ilike_pattern(search_term)
    q = (
        FormItem.query
        .join(FormSection, FormItem.section_id == FormSection.id)
        .filter(
            FormItem.archived.is_(False),
            FormSection.archived.is_(False),
            FormItem.item_type.in_(types),
            or_(
                FormItem.label.ilike(search_pattern),
                FormSection.name.ilike(search_pattern),
            ),
        )
    )
    if template_id is not None:
        q = q.filter(FormItem.template_id == int(template_id))
    items = q.all()
    matrix_items = [i for i in items if (i.item_type or "").lower() == "matrix"]
    return matrix_items if matrix_items else items

