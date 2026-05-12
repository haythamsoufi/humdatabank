# ========== Data Retrieval: Form Domain ==========
"""
Form data queries, value breakdown, indicator values (single and all countries),
assignment indicator values, and form field value lookup.

Data source: Actual values always come from the form_data table (FormData model):
- FormData.value, FormData.disagg_data hold the stored values.
- FormData is linked to AssignmentEntityStatus (assignment + country + period) and
  to FormItem; FormItem.indicator_bank_id links to IndicatorBank.
- IndicatorBank is metadata only (indicator name, unit, definition); it does not
  store values. Value breakdown and indicator-value tools query FormData joined with
  AssignmentEntityStatus and FormItem to resolve indicator and period.
"""

import json
import logging
import math
import re
import unicodedata
from datetime import datetime as _dt
from typing import Callable, Dict, List, Optional, Union, Any

from sqlalchemy import and_, literal, func, or_
from sqlalchemy.orm import joinedload

from app.models import (
    Country, FormTemplate, FormTemplateVersion, FormSection, IndicatorBank,
    AssignedForm, FormData, FormItem, PublicSubmission,
)
from app.models.assignments import AssignmentEntityStatus
from app.extensions import db
from app.utils.api_helpers import service_error, GENERIC_ERROR_MESSAGE
from app.utils.constants import DEFAULT_LIMIT_PERIODS, MAX_LIMIT_PERIODS
from app.utils.datetime_helpers import utcnow
from app.utils.form_localization import get_localized_country_name, get_localized_indicator_name
from app.services.app_settings_service import get_organization_name
from app.utils.sql_utils import safe_ilike_pattern
from flask_babel import gettext as _

from .data_retrieval_shared import (
    get_effective_request_user,
    can_view_non_public_form_items,
    form_item_privacy_is_public_expr,
    user_allowed_country_ids,
    escape_like_pattern,
    get_indicator_candidates_by_keyword,
    score_indicator_relevance,
)
from .data_retrieval_country import (
    check_country_access,
    resolve_country,
    get_country_info,
)

logger = logging.getLogger(__name__)

def get_indicator_timeseries(
    *,
    country_id: int,
    indicator_identifier: str,
    limit_periods: int = 12,
    include_saved: bool = True,
    on_progress: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """
    Return a per-country time series for an indicator across assignment periods.

    This is designed for "over time / trend / by year" questions. It returns one point per year
    (best available submission for that year) so the UI can render a line chart.

    Behavior:
    - Resolves indicator name to a primary IndicatorBank id (same resolver as bulk queries).
    - Treats "Number of ..." and common count units as point-in-time indicators:
      chooses ONE value per period/year (not summed across years).
    - Includes submitted/approved values; optionally includes saved/draft values (default True)
      so recent cycles are visible even if not submitted yet (flagged via data_status).
    """
    def _progress(msg: str) -> None:
        if on_progress:
            try:
                on_progress(msg)
            except Exception as e:
                logger.debug("_progress callback failed: %s", e)

    try:
        country_id = int(country_id)
        ident = (indicator_identifier or "").strip()
        if not ident:
            return service_error("indicator_identifier is required", series=[])

        primary_id = resolve_indicator_to_primary_id(ident, country_id=country_id)
        if not primary_id:
            return service_error("Indicator not found", series=[])
        indicator = db.session.get(IndicatorBank, int(primary_id))
        if not indicator:
            return service_error("Indicator not found", series=[])

        ind_display = get_localized_indicator_name(indicator)
        _disp_progress = ind_display.strip() or str(primary_id)
        if len(_disp_progress) > 200:
            _disp_progress = _disp_progress[:197] + "…"
        _progress(_("Selected indicator: %(name)s", name=_disp_progress))

        # RBAC: ensure the caller can access this country (same rule as other tools)
        try:
            check_country_access(int(country_id))
        except Exception as e_access:
            return service_error(str(e_access), series=[])

        country = db.session.get(Country, int(country_id))
        country_display = get_localized_country_name(country) if country else ""

        def _timeseries_common_fields() -> Dict[str, Any]:
            return {
                "country_name": (country.name if country else str(country_id)),
                "country_display_name": country_display,
                "indicator": {
                    "id": int(indicator.id),
                    "name": indicator.name,
                    "display_name": ind_display,
                    "unit": getattr(indicator, "unit", None),
                },
                "indicator_display_name": ind_display,
            }

        # Determine point-indicator behavior
        is_point_indicator = False
        try:
            nm = (indicator.name or "").strip().lower()
            unit = (getattr(indicator, "unit", None) or "").strip().lower()
            if nm.startswith("number of"):
                is_point_indicator = True
            if unit in {"branch", "branches", "count", "number"}:
                is_point_indicator = True
        except Exception as e:
            logger.debug("get_indicator_timeseries: is_point_indicator heuristic failed: %s", e)
            is_point_indicator = False

        _progress(_("Querying form data…"))
        item_ids = [int(fi.id) for fi in FormItem.query.filter(FormItem.indicator_bank_id == int(primary_id)).all()]
        if not item_ids:
            return {
                "success": True,
                "country_id": country_id,
                **_timeseries_common_fields(),
                "series": [],
                "count": 0,
            }

        q = (
            db.session.query(
                AssignmentEntityStatus.id.label("submission_id"),
                AssignmentEntityStatus.status.label("status"),
                AssignmentEntityStatus.status_timestamp.label("status_timestamp"),
                AssignedForm.period_name.label("period_name"),
                FormData.value.label("value"),
                FormData.disagg_data.label("disagg_data"),
            )
            .join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
            .join(FormData, FormData.assignment_entity_status_id == AssignmentEntityStatus.id)
            .filter(
                AssignmentEntityStatus.entity_type == "country",
                AssignmentEntityStatus.entity_id == int(country_id),
                FormData.form_item_id.in_(item_ids),
                or_(FormData.data_not_available.is_(None), FormData.data_not_available.is_(False)),
                or_(FormData.not_applicable.is_(None), FormData.not_applicable.is_(False)),
                or_(FormData.value.isnot(None), FormData.disagg_data.isnot(None)),
            )
        )
        if not include_saved:
            q = q.filter(AssignmentEntityStatus.status.in_(["Submitted", "Approved"]))

        rows = q.all()
        if not rows:
            return {
                "success": True,
                "country_id": country_id,
                **_timeseries_common_fields(),
                "series": [],
                "count": 0,
            }

        def _ascii_digits(text: str) -> str:
            """
            Normalize unicode digits (e.g. Arabic-Indic) to ASCII digits.
            Keeps all other characters unchanged.
            """
            out = []
            for ch in str(text):
                try:
                    if ch.isdigit() and ch not in "0123456789":
                        out.append(str(unicodedata.digit(ch)))
                    else:
                        out.append(ch)
                except Exception as e:
                    logger.debug("_ascii_digits: unicode digit conversion failed for %r: %s", ch, e)
                    out.append(ch)
            return "".join(out)

        def _parse_year(s: Optional[str]) -> Optional[int]:
            """
            Parse the year represented by AssignedForm.period_name.

            Supported period formats (project contract):
            - Single year: "2024"
            - Year range: "2023-2024" (use the most recent year, i.e. 2024)
            - Month range: "Jan 2024 - Dec 2024" or "Oct 2023 - Mar 2024" (use the most recent year)

            Implementation:
            - Extract all 4-digit years and return max(years).
            - Additionally support compact ranges like "2011-12" by interpreting the end year as 2012.
            - Never fall back to timestamps; if parsing fails, the submission is skipped (with a warning log).
            """
            if not s:
                return None
            txt = _ascii_digits(str(s)).strip()

            # Prefer 4-digit years anywhere in the string.
            m4 = re.findall(r"\b(19\d{2}|20\d{2})\b", txt)
            if m4:
                try:
                    return max(int(x) for x in m4)
                except Exception as e:
                    logger.debug("_parse_year: max year parse failed %r: %s", m4, e)
                    return None

            # Support "YYYY-YY" / "YYYY/YY" (e.g. "2011-12" -> 2012).
            m2 = re.search(r"\b(19\d{2}|20\d{2})\s*[-/]\s*(\d{2})\b", txt)
            if m2:
                try:
                    start_year = int(m2.group(1))
                    end_yy = int(m2.group(2))
                    century = (start_year // 100) * 100
                    end_year = century + end_yy
                    if end_year < start_year:
                        end_year += 100
                    return end_year
                except Exception as e:
                    logger.debug("_parse_year: YYYY-YY parse failed: %s", e)
                    return None

            return None

        def _numeric(value: Any, disagg_data: Any) -> Optional[float]:
            def _parse_numeric_str(s: str) -> Optional[float]:
                try:
                    t = (s or "").strip()
                    if not t:
                        return None
                    # common formatting: "14,098" or "8 000" or "8 000"
                    t = t.replace(",", "").replace("\u00A0", " ").replace(" ", "")
                    if not t:
                        return None
                    return float(t)
                except Exception as e:
                    logger.debug("_parse_numeric_str failed for %r: %s", s, e)
                    return None

            def _sum_numeric_leaves(obj: Any) -> tuple[float, int]:
                """
                Recursively sum numeric leaves in nested dict/list structures.

                Supports common matrix/disagg shapes, including:
                - {"values": {"direct": {"unknown_unknown": 7786}, "indirect": null}}
                - leaf cells like {"modified": 1, "original": 2}

                Returns:
                  (subtotal, found_count) where found_count counts numeric leaves found.
                """
                subtotal = 0.0
                found = 0

                if obj is None:
                    return subtotal, found

                # Unwrap modified/original cell dicts
                if isinstance(obj, dict) and ("modified" in obj or "original" in obj):
                    v = obj.get("modified") if obj.get("modified") is not None else obj.get("original")
                    return _sum_numeric_leaves(v)

                if isinstance(obj, (int, float)):
                    return float(obj), 1

                if isinstance(obj, str):
                    n = _parse_numeric_str(obj)
                    if n is None:
                        return subtotal, found
                    return float(n), 1

                if isinstance(obj, dict):
                    for k, v in obj.items():
                        try:
                            if isinstance(k, str) and k.startswith("_"):
                                continue
                        except Exception as e:
                            logger.debug("_sum_numeric_leaves: skip key check failed: %s", e)
                        s, c = _sum_numeric_leaves(v)
                        subtotal += float(s)
                        found += int(c)
                    return subtotal, found

                if isinstance(obj, list):
                    for v in obj:
                        s, c = _sum_numeric_leaves(v)
                        subtotal += float(s)
                        found += int(c)
                    return subtotal, found

                return subtotal, found

            try:
                # Prefer the main field value when present.
                # Rationale: most indicator queries ask for the total, and many forms store totals in FormData.value.
                # Use disaggregation only as fallback when the main value is missing/unparseable.
                if value is not None:
                    if isinstance(value, (int, float)):
                        return float(value)
                    if isinstance(value, str):
                        n = _parse_numeric_str(value)
                        if n is not None:
                            return float(n)

                if disagg_data:
                    dd = disagg_data
                    if isinstance(dd, str):
                        try:
                            dd = json.loads(dd)
                        except Exception as exc:
                            logger.debug("_numeric: disagg_data json.loads failed: %s", exc)
                            dd = None
                    if isinstance(dd, dict):
                        # Common disagg format: {"values": {...}}
                        vals = dd.get("values", None)
                        if isinstance(vals, dict):
                            subtotal, found = _sum_numeric_leaves(vals)
                            return float(subtotal) if found > 0 else None

                        # Fallback: matrix-style / flat dict with numeric leaves (exclude metadata keys).
                        subtotal, found = _sum_numeric_leaves(dd)
                        return float(subtotal) if found > 0 else None
            except Exception as e:
                logger.debug("_numeric: parse/aggregation failed: %s", e)
                return None
            return None

        # Aggregate within a submission (avoid double counting duplicate fields)
        by_submission: Dict[int, Dict[str, Any]] = {}
        for r in rows:
            sid = int(r.submission_id)
            entry = by_submission.get(sid)
            if entry is None:
                entry = {
                    "submission_id": sid,
                    "period_name": getattr(r, "period_name", None),
                    "timestamp": getattr(r, "status_timestamp", None),
                    "status": getattr(r, "status", None),
                    "total": 0.0,
                    "has_numeric": False,
                }
                by_submission[sid] = entry
            n = _numeric(getattr(r, "value", None), getattr(r, "disagg_data", None))
            if n is None:
                continue
            entry["has_numeric"] = True
            if is_point_indicator:
                if float(n) > float(entry.get("total") or 0.0):
                    entry["total"] = float(n)
            else:
                entry["total"] = float(entry.get("total") or 0.0) + float(n)

        def _status_rank(status: Any) -> int:
            s = str(status or "").strip()
            if s in ("Approved", "Submitted"):
                return 2
            if s:
                return 1
            return 0

        # Choose best submission per year (year derived ONLY from period_name)
        best_by_year: Dict[int, Dict[str, Any]] = {}
        for e in by_submission.values():
            if not bool(e.get("has_numeric")):
                # Avoid emitting misleading 0.0 points when the period exists but no numeric value was found.
                period_name_raw = str(e.get("period_name") or "").strip() or None
                parsed = _parse_year(period_name_raw) if period_name_raw else None
                if parsed is not None:
                    try:
                        escaped = (period_name_raw or "").encode("unicode_escape").decode("ascii")
                    except Exception as exc:
                        logger.debug("unicode_escape failed: %s", exc)
                        escaped = repr(period_name_raw)
                    logger.warning(
                        "get_indicator_timeseries no_numeric_for_period country_id=%s indicator_id=%s submission_id=%s period_name=%r escaped=%s status=%r",
                        country_id,
                        getattr(indicator, "id", None),
                        e.get("submission_id"),
                        period_name_raw,
                        escaped,
                        e.get("status"),
                    )
                continue
            period_name = str(e.get("period_name") or "").strip() or None
            parsed_year = _parse_year(period_name) if period_name else None
            year = parsed_year
            if year is None:
                # No timestamp fallback: if parsing fails, skip (but log loudly so we can fix period formats).
                try:
                    escaped = (period_name or "").encode("unicode_escape").decode("ascii")
                except Exception as exc:
                    logger.debug("unicode_escape failed: %s", exc)
                    escaped = repr(period_name)
                logger.warning(
                    "get_indicator_timeseries year_parse_failed country_id=%s indicator_id=%s submission_id=%s period_name=%r escaped=%s status=%r status_timestamp=%r",
                    country_id,
                    getattr(indicator, "id", None),
                    e.get("submission_id"),
                    period_name,
                    escaped,
                    e.get("status"),
                    e.get("timestamp"),
                )

            # Attach debug metadata (kept internal; may be surfaced in logs later)
            try:
                e["_year_debug"] = {
                    "parsed_year": parsed_year,
                    "used_year": year,
                    "source": ("period_name" if parsed_year is not None else "none"),
                }
            except Exception as exc:
                logger.debug("_year_debug attach failed: %s", exc)
            if year is None:
                continue
            key = int(year)
            cur = best_by_year.get(key)
            if cur is None:
                best_by_year[key] = e
                continue
            cur_rank = _status_rank(cur.get("status"))
            new_rank = _status_rank(e.get("status"))
            if new_rank != cur_rank:
                if new_rank > cur_rank:
                    best_by_year[key] = e
                    logger.debug(
                        "get_indicator_timeseries choose_for_year year=%s reason=status_rank country_id=%s indicator_id=%s prev_submission_id=%s new_submission_id=%s prev_status=%r new_status=%r",
                        key,
                        country_id,
                        getattr(indicator, "id", None),
                        cur.get("submission_id"),
                        e.get("submission_id"),
                        cur.get("status"),
                        e.get("status"),
                    )
                continue
            # same status rank: prefer latest timestamp, then higher submission_id
            cur_ts = cur.get("timestamp")
            new_ts = e.get("timestamp")
            try:
                if new_ts and cur_ts and new_ts > cur_ts:
                    best_by_year[key] = e
                    logger.debug(
                        "get_indicator_timeseries choose_for_year year=%s reason=timestamp country_id=%s indicator_id=%s prev_submission_id=%s new_submission_id=%s prev_ts=%r new_ts=%r",
                        key,
                        country_id,
                        getattr(indicator, "id", None),
                        cur.get("submission_id"),
                        e.get("submission_id"),
                        cur_ts,
                        new_ts,
                    )
                    continue
            except Exception as exc:
                logger.debug("timestamp comparison failed: %s", exc)
            try:
                if int(e.get("submission_id") or 0) > int(cur.get("submission_id") or 0):
                    best_by_year[key] = e
                    logger.debug(
                        "get_indicator_timeseries choose_for_year year=%s reason=submission_id country_id=%s indicator_id=%s prev_submission_id=%s new_submission_id=%s",
                        key,
                        country_id,
                        getattr(indicator, "id", None),
                        cur.get("submission_id"),
                        e.get("submission_id"),
                    )
            except Exception as exc:
                logger.debug("submission_id comparison failed: %s", exc)

        series = []
        for y in sorted(best_by_year.keys()):
            e = best_by_year[y]
            total = float(e.get("total") or 0.0)
            period_name = str(e.get("period_name") or "").strip() or None
            st = str(e.get("status") or "").strip()
            # Keep a compact status for the UI (used for chart legend / highlighting).
            # Historically we collapsed Approved → submitted, but charts benefit from
            # showing Approved distinctly.
            if st == "Approved":
                data_status = "approved"
            elif st == "Submitted":
                data_status = "submitted"
            else:
                data_status = "saved"
            series.append(
                {
                    "year": int(y),
                    "value": total,
                    "period_name": period_name,
                    "data_status": data_status,
                }
            )

        # Limit to the last N periods (by year)
        try:
            limit_n = max(1, min(int(limit_periods or DEFAULT_LIMIT_PERIODS), MAX_LIMIT_PERIODS))
        except Exception as e:
            logger.debug("get_indicator_timeseries: limit_periods parse failed: %s", e)
            limit_n = DEFAULT_LIMIT_PERIODS
        if len(series) > limit_n:
            series = series[-limit_n:]

        return {
            "success": True,
            "country_id": int(country_id),
            **_timeseries_common_fields(),
            "iso3": (getattr(country, "iso3", None) or "") if country else "",
            "series": series,
            "count": len(series),
            "aggregation": ("point_latest_per_year" if is_point_indicator else "sum_per_year"),
        }
    except Exception as e:
        logger.exception("get_indicator_timeseries error")
        return service_error(GENERIC_ERROR_MESSAGE, series=[], count=0)

def query_form_data(
    *,
    template_id: Optional[int] = None,
    submission_id: Optional[int] = None,
    item_id: Optional[int] = None,
    item_type: Optional[str] = None,
    country_id: Optional[int] = None,
    period_name: Optional[str] = None,
    indicator_bank_id: Optional[int] = None,
    submission_type: Optional[str] = None,
    preload: bool = False,
) -> Dict[str, Any]:
    """
    Centralized FormData query builder for API usage. Does not enforce RBAC (API uses API key),
    but encapsulates join shapes and filters consistently for assigned and public data.

    Returns a dict with two query objects: 'assigned' and 'public'. Callers may further iterate .all().
    """
    try:
        assigned_q = FormData.query
        public_q = FormData.query.join(AssignmentEntityStatus).join(
            PublicSubmission,
            and_(
                AssignmentEntityStatus.assigned_form_id == PublicSubmission.assigned_form_id,
                AssignmentEntityStatus.entity_id == PublicSubmission.country_id,
                AssignmentEntityStatus.entity_type == 'country',
            ),
        ).join(AssignedForm, PublicSubmission.assigned_form_id == AssignedForm.id)

        # Assigned path joins lazily: add joins only when needed to avoid ambiguous columns
        if template_id or country_id or period_name:
            assigned_q = assigned_q.join(AssignmentEntityStatus).join(AssignedForm)

        if template_id:
            assigned_q = assigned_q.filter(AssignedForm.template_id == template_id)
            public_q = public_q.filter(AssignedForm.template_id == template_id)
        if country_id:
            assigned_q = assigned_q.filter(
                AssignmentEntityStatus.entity_id == country_id,
                AssignmentEntityStatus.entity_type == 'country'
            )
            public_q = public_q.filter(PublicSubmission.country_id == country_id)
        if period_name:
            _pat = f"%{escape_like_pattern(period_name)}%"
            assigned_q = assigned_q.filter(AssignedForm.period_name.ilike(_pat, escape="\\"))
            public_q = public_q.filter(AssignedForm.period_name.ilike(_pat, escape="\\"))

        if submission_id:
            # For assigned path, ensure ACStatus join exists
            if not (template_id or country_id or period_name):
                assigned_q = assigned_q.join(AssignmentEntityStatus)
            assigned_q = assigned_q.filter(AssignmentEntityStatus.id == submission_id)
            public_q = public_q.filter(PublicSubmission.id == submission_id)

        if item_id:
            assigned_q = assigned_q.filter(FormData.form_item_id == item_id)
            public_q = public_q.filter(FormData.form_item_id == item_id)

        if item_type:
            assigned_q = assigned_q.join(FormItem, FormData.form_item).filter(FormItem.item_type == item_type)
            public_q = public_q.join(FormItem, FormData.form_item).filter(FormItem.item_type == item_type)

        if indicator_bank_id:
            assigned_q = assigned_q.join(FormItem, FormData.form_item).join(IndicatorBank, FormItem.indicator_bank).filter(IndicatorBank.id == indicator_bank_id)
            public_q = public_q.join(FormItem, FormData.form_item).join(IndicatorBank, FormItem.indicator_bank).filter(IndicatorBank.id == indicator_bank_id)

        if preload:
            # Eager-load common relationships to avoid N+1 during serialization
            # Note: AssignedForm.template and PublicSubmission.country are backrefs,
            # so we can't use joinedload on them. They'll be loaded when accessed.
            assigned_q = assigned_q.options(
                joinedload(FormData.form_item).joinedload(FormItem.form_section).joinedload(FormSection.template),
                joinedload(FormData.form_item).joinedload(FormItem.indicator_bank),
                joinedload(FormData.assignment_entity_status).joinedload(AssignmentEntityStatus.assigned_form),
            )
            public_q = public_q.options(
                joinedload(FormData.form_item).joinedload(FormItem.form_section).joinedload(FormSection.template),
                joinedload(FormData.form_item).joinedload(FormItem.indicator_bank),
                joinedload(FormData.public_submission).joinedload(PublicSubmission.assigned_form),
            )

        # ---------- Privacy gating ----------
        # Public callers (including API key / website / mobile) should see ONLY FormItem privacy='public'.
        # Non-public form items require RBAC.
        viewer = get_effective_request_user()

        if not can_view_non_public_form_items(viewer):
            # Avoid join duplication by using relationship .has() (EXISTS).
            public_only = form_item_privacy_is_public_expr()
            assigned_q = assigned_q.filter(FormData.form_item.has(public_only))
            public_q = public_q.filter(FormData.form_item.has(public_only))

        # Respect submission_type if provided by caller
        return {
            'assigned': None if submission_type == 'public' else assigned_q,
            'public': None if submission_type == 'assigned' else public_q,
        }
    except Exception as e:
        logger.error(f"Error building form data query: {e}", exc_info=True)
        return {'assigned': FormData.query.filter(literal(False)), 'public': FormData.query.filter(literal(False))}


def get_form_data_queries(queries_dict):
    """
    Extract assigned and public queries from query_form_data result with safe fallbacks.

    Args:
        queries_dict: Dictionary returned by query_form_data() with 'assigned' and 'public' keys

    Returns:
        tuple: (assigned_query, public_query) - Both are always valid query objects (never None)
    """
    assigned_q = queries_dict.get('assigned')
    public_q = queries_dict.get('public')

    # Provide empty query fallback if None
    if assigned_q is None:
        assigned_q = FormData.query.filter(literal(False))
    if public_q is None:
        public_q = FormData.query.filter(literal(False))

    return assigned_q, public_q


def get_value_breakdown(
    country_id: int,
    indicator_identifier: Union[int, str],
    period: Optional[str] = None,
    filters: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Compute value breakdown for an indicator in a country (RBAC enforced).

    Values are read from the form_data table (FormData.value, FormData.disagg_data),
    linked via FormItem.indicator_bank_id to IndicatorBank (metadata only). Data is
    scoped by AssignmentEntityStatus (country + assignment + period).

    This provides explainability for questions like "why is value 20 not 10?"
    by showing the contributing records, aggregation method, and filters applied.

    Period matching: period is matched by substring (ilike) on AssignedForm.period_name, so
    single year (2024), year range (2023-2024), fiscal (FY2024), or month range all work.

    Args:
        country_id: Country ID
        indicator_identifier: Indicator ID (int) or name (str) — used to find FormItems and thus FormData
        period: Optional period filter (e.g. "2023", "2023-2024", "FY2023") — substring match
        filters: Additional filters dict (future use)

    Returns:
        Dict with: total, records_count, included_examples, mode, notes, indicator, provenance
    """
    query_start_time = utcnow()

    has_assigned_access = bool(check_country_access(country_id))
    alternative_indicators_result: List[Dict[str, Any]] = []

    # Resolve indicator
    try:
        indicator = None
        if isinstance(indicator_identifier, int) or (isinstance(indicator_identifier, str) and indicator_identifier.isdigit()):
            indicator = db.session.get(IndicatorBank, int(indicator_identifier))
        else:
            ident = (indicator_identifier or "").strip()
            # Try semantic/LLM resolution first when configured (vector or vector_then_llm)
            try:
                from app.services.indicator_resolution_service import resolve_indicator_identifier
                indicator = resolve_indicator_identifier(indicator_identifier, user_query=None)
                if indicator is not None:
                    logger.debug(
                        "get_value_breakdown indicator resolution (vector/LLM) country_id=%s ident=%r chosen=%s (id=%s)",
                        country_id, indicator_identifier, indicator.name, indicator.id,
                    )
            except Exception as e:
                logger.debug("Indicator vector resolution failed: %s", e)
            if indicator is None and ident:
                # If the identifier looks like a form template name, return hint immediately (do not look up as indicator).
                template = (
                    FormTemplate.query
                    .join(FormTemplateVersion, FormTemplateVersion.template_id == FormTemplate.id)
                    .filter(FormTemplateVersion.name.ilike(safe_ilike_pattern(ident)))
                    .first()
                )
                if template:
                    return {
                        'error': 'Indicator not found',
                        'hint': f'"{ident}" is a form template, not an indicator. Use get_template_details("{template.name}") for form structure and get_assignment_indicator_values(country, "{template.name}", period) for reported values.',
                        'suggestion_tool': 'get_template_details',
                        'suggestion_arg': template.name,
                    }
                # Keyword fallback: prefer an indicator that has submitted data for the requested country/period.
            # This avoids returning an arbitrary first match for generic terms like "volunteers".
            candidates = get_indicator_candidates_by_keyword(ident)
            if not candidates:
                indicator = None
            elif len(candidates) == 1:
                indicator = candidates[0]
                logger.debug(
                    "get_value_breakdown indicator resolution country_id=%s ident=%r single_candidate chosen=%s (id=%s)",
                    country_id,
                    indicator_identifier,
                    indicator.name,
                    indicator.id,
                )
            else:
                candidate_ids = [c.id for c in candidates]

                # Score all candidates by relevance (prefer more general indicators)
                scored_candidates = []
                for c in candidates:
                    relevance_score = score_indicator_relevance(c.name, ident)
                    scored_candidates.append((c, relevance_score))

                # Sort by relevance score (descending)
                scored_candidates.sort(key=lambda x: x[1], reverse=True)

                # Count records per indicator for this country (+ optional period).
                # Count BOTH submitted and saved so an indicator with saved data (e.g. 2024 FDRS 14,098)
                # can be chosen over another that also has only saved data (e.g. 2018 with 0). When both
                # are saved, both get a count and relevance (e.g. "Number of people volunteering") decides.
                cnt_q_submitted = (
                    db.session.query(
                        IndicatorBank.id.label("indicator_id"),
                        func.count(FormData.id).label("records"),
                    )
                    .join(FormItem, FormItem.indicator_bank_id == IndicatorBank.id)
                    .join(FormData, FormData.form_item_id == FormItem.id)
                    .join(AssignmentEntityStatus, FormData.assignment_entity_status_id == AssignmentEntityStatus.id)
                    .filter(
                        IndicatorBank.id.in_(candidate_ids),
                        AssignmentEntityStatus.entity_type == "country",
                        AssignmentEntityStatus.entity_id == country_id,
                        AssignmentEntityStatus.status.in_(['Submitted', 'Approved']),
                        or_(FormData.data_not_available.is_(None), FormData.data_not_available.is_(False)),
                        or_(FormData.not_applicable.is_(None), FormData.not_applicable.is_(False)),
                        or_(FormData.value.isnot(None), FormData.disagg_data.isnot(None)),
                    )
                )
                if period:
                    _pat = f"%{escape_like_pattern(period)}%"
                    cnt_q_submitted = cnt_q_submitted.join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id).filter(
                        AssignedForm.period_name.ilike(_pat, escape="\\")
                    )
                ranked_submitted = cnt_q_submitted.group_by(IndicatorBank.id).all()

                cnt_q_saved = (
                    db.session.query(
                        IndicatorBank.id.label("indicator_id"),
                        func.count(FormData.id).label("records"),
                    )
                    .join(FormItem, FormItem.indicator_bank_id == IndicatorBank.id)
                    .join(FormData, FormData.form_item_id == FormItem.id)
                    .join(AssignmentEntityStatus, FormData.assignment_entity_status_id == AssignmentEntityStatus.id)
                    .filter(
                        IndicatorBank.id.in_(candidate_ids),
                        AssignmentEntityStatus.entity_type == "country",
                        AssignmentEntityStatus.entity_id == country_id,
                        ~AssignmentEntityStatus.status.in_(['Submitted', 'Approved']),
                        or_(FormData.data_not_available.is_(None), FormData.data_not_available.is_(False)),
                        or_(FormData.not_applicable.is_(None), FormData.not_applicable.is_(False)),
                        or_(FormData.value.isnot(None), FormData.disagg_data.isnot(None)),
                    )
                )
                if period:
                    _pat = f"%{escape_like_pattern(period)}%"
                    cnt_q_saved = cnt_q_saved.join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id).filter(
                        AssignedForm.period_name.ilike(_pat, escape="\\")
                    )
                ranked_saved = cnt_q_saved.group_by(IndicatorBank.id).all()

                # Merge: each indicator gets submitted_count + saved_count so saved-only data is visible
                data_count_map = {}
                for row in ranked_submitted:
                    data_count_map[int(row.indicator_id)] = data_count_map.get(int(row.indicator_id), 0) + int(row.records or 0)
                for row in ranked_saved:
                    data_count_map[int(row.indicator_id)] = data_count_map.get(int(row.indicator_id), 0) + int(row.records or 0)

                # Max year per indicator for this country: prefer indicator with more recent data
                # (e.g. Syria: "Number of volunteers" has 2024/14k, "Number of people volunteering" has 2018/0)
                max_year_map: Dict[int, int] = {}
                try:
                    recency_q = (
                        db.session.query(
                            IndicatorBank.id.label("indicator_id"),
                            AssignedForm.period_name,
                            AssignmentEntityStatus.status_timestamp,
                        )
                        .join(FormItem, FormItem.indicator_bank_id == IndicatorBank.id)
                        .join(FormData, FormData.form_item_id == FormItem.id)
                        .join(AssignmentEntityStatus, FormData.assignment_entity_status_id == AssignmentEntityStatus.id)
                        .join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
                        .filter(
                            IndicatorBank.id.in_(candidate_ids),
                            AssignmentEntityStatus.entity_type == "country",
                            AssignmentEntityStatus.entity_id == country_id,
                            or_(FormData.value.isnot(None), FormData.disagg_data.isnot(None)),
                        )
                    )
                    for row in recency_q.all():
                        y = None
                        if getattr(row, "period_name", None):
                            m = re.findall(r"\b(19\d{2}|20\d{2})\b", str(row.period_name))
                            if m:
                                y = max(int(x) for x in m)
                        if y is None and getattr(row, "status_timestamp", None):
                            y = getattr(row.status_timestamp, "year", None)
                        if y is not None:
                            iid = int(row.indicator_id)
                            max_year_map[iid] = max(max_year_map.get(iid, 0), y)
                except Exception as recency_err:
                    logger.debug("get_value_breakdown recency query failed: %s", recency_err)

                # Combine relevance score with data availability and recency
                # Prefer high relevance, then recency (so 2024 beats 2018), then data count
                final_scores = []
                for c, relevance_score in scored_candidates:
                    data_count = data_count_map.get(c.id, 0)
                    max_year = max_year_map.get(c.id, 0)
                    combined_score = relevance_score
                    if data_count > 0:
                        combined_score += min(0.8, data_count / 100.0)  # Cap bonus at 0.8
                    # Recency: (year - 2000) * 0.1 so 2024 adds 2.4, 2018 adds 1.8 — prefer indicator with latest data
                    if max_year >= 2000:
                        combined_score += (max_year - 2000) * 0.1
                    final_scores.append((c, combined_score, relevance_score, data_count))

                # Sort by combined score
                final_scores.sort(key=lambda x: x[1], reverse=True)

                # Build alternatives list (all indicators with data, sorted by relevance)
                alternatives = []
                for c, combined_score, relevance_score, data_count in final_scores[:10]:
                    if data_count > 0:
                        alternatives.append(
                            {
                                "id": c.id,
                                "name": c.name,
                                "records_count": data_count,
                                "relevance_score": round(relevance_score, 2)
                            }
                        )

                # Select the best indicator (highest combined score)
                alternative_indicators_result = alternatives
                if final_scores:
                    indicator = final_scores[0][0]
                    logger.debug(
                        "get_value_breakdown indicator resolution country_id=%s ident=%r candidates=%s chosen=%s (id=%s)",
                        country_id,
                        indicator_identifier,
                        [
                            (c.name, c.id, round(rel, 2), data_count, round(comb, 2))
                            for c, comb, rel, data_count in final_scores[:5]
                        ],
                        indicator.name,
                        indicator.id,
                    )
                else:
                    # Fallback to first match if scoring fails
                    indicator = candidates[0]
                    logger.debug(
                        "get_value_breakdown indicator fallback country_id=%s ident=%r chosen=%s (id=%s)",
                        country_id,
                        indicator_identifier,
                        indicator.name,
                        indicator.id,
                    )

        if not indicator:
            return {'error': 'Indicator not found'}

        # Get country name for provenance
        country = db.session.get(Country, country_id)
        country_name = country.name if country else f"Country ID {country_id}"

        # Get form items linked to this indicator and to any other indicator that matched the name,
        # so we don't miss form_data (e.g. 47087) stored under a different indicator label (e.g. "People volunteering")
        candidate_indicator_ids = [indicator.id]
        if alternative_indicators_result:
            for alt in alternative_indicators_result:
                aid = alt.get("id")
                if aid is not None and int(aid) not in candidate_indicator_ids:
                    candidate_indicator_ids.append(int(aid))
        # When resolved by name, include form items from all indicators matching that name
        # (e.g. "Volunteers" should also match "Number of people volunteering" -> add "volunteering" variant)
        ident = (indicator_identifier or "").strip() if isinstance(indicator_identifier, str) else ""
        if ident and (not ident.isdigit()):
            name_patterns = [safe_ilike_pattern(ident)]
            if ident.endswith("s") and len(ident) > 3:
                name_patterns.append(safe_ilike_pattern(ident[:-1] + "ing"))  # volunteers -> volunteering
                name_patterns.append(safe_ilike_pattern(ident[:-1]))  # volunteers -> volunteer
            name_matches = IndicatorBank.query.filter(
                or_(*[IndicatorBank.name.ilike(p) for p in name_patterns])
            ).limit(25).all()
            for ind_m in name_matches:
                iid = getattr(ind_m, "id", None)
                if iid is not None and int(iid) not in candidate_indicator_ids:
                    candidate_indicator_ids.append(int(iid))
        item_q = FormItem.query.filter(FormItem.indicator_bank_id.in_(candidate_indicator_ids))
        items = item_q.all()
        item_ids = [fi.id for fi in items]
        if not item_ids:
            return {
                'total': 0,
                'records_count': 0,
                'included_examples': [],
                'notes': 'No form items linked to indicator.',
                'indicator': {'id': indicator.id, 'name': indicator.name, 'unit': indicator.unit},
                'provenance': {
                    'source': get_organization_name(),
                    'query_time': query_start_time.isoformat(),
                    'filters': {'country': country_name, 'indicator': indicator.name},
                    'record_count': 0,
                    'aggregation': 'None (no linked form items)',
                    'exclusions': 'No form items found for this indicator'
                }
            }

        # Build query:
        # - Assigned path (requires country access): FormData → AssignmentEntityStatus → AssignedForm
        # - No assigned access: same join (AssignmentEntityStatus); visibility is by FormItem.privacy only.
        records: list[FormData] = []
        data_status = 'submitted'  # 'submitted' | 'saved'
        # Visibility: FormItem.privacy 'public' → everyone; 'ifrc_network' → same-org / RBAC only.
        viewer = get_effective_request_user()
        if can_view_non_public_form_items(viewer):
            visible_item_ids = item_ids
        else:
            visible_item_ids = [fi.id for fi in items if (getattr(fi, "privacy", None) or "").strip().lower() == "public"]
        data_scope = "assigned" if has_assigned_access else "public"

        # Track applied filters for provenance
        applied_filters = {'country': country_name, 'indicator': indicator.name}

        if has_assigned_access:
            base_q = FormData.query.join(AssignmentEntityStatus)
            base_q = base_q.filter(
                AssignmentEntityStatus.entity_id == country_id,
                AssignmentEntityStatus.entity_type == 'country'
            )

            # Apply period filter if provided
            if period:
                _pat = f"%{escape_like_pattern(period)}%"
                base_q = base_q.join(AssignedForm).filter(AssignedForm.period_name.ilike(_pat, escape="\\"))
                applied_filters['period'] = period

            # Filter by form item IDs
            base_q = base_q.filter(FormData.form_item_id.in_(item_ids))

            # Apply additional filters if provided (but do not change data scope)
            if filters:
                applied_filters.update(filters)

            # Load both submitted and saved/draft data so we have all periods per country+indicator.
            # Otherwise we only get one status (e.g. submitted 2018 with 0) and never see saved 2024 with 14k.
            submitted_q = base_q.filter(AssignmentEntityStatus.status.in_(['Submitted', 'Approved']))
            submitted_records = submitted_q.all()
            saved_q = base_q.filter(~AssignmentEntityStatus.status.in_(['Submitted', 'Approved']))
            saved_records = saved_q.all()
            # Include saved records that have any value (including 0) or disagg_data, so latest period
            # is visible. Excluding value=0 with (r.value or r.disagg_data) dropped 2024 and left only 2018.
            saved_records_with_data = [
                r for r in saved_records
                if not (r.data_not_available or r.not_applicable)
                and (r.value is not None or r.disagg_data)
            ]
            # Merge so by_submission gets every period (then point-indicator logic picks latest / first non-zero).
            records = list(submitted_records) + list(saved_records_with_data)
            if not submitted_records and saved_records_with_data:
                data_status = 'saved'
            logger.debug(
                "get_value_breakdown records (assigned) country_id=%s indicator=%s submitted=%s saved_total=%s saved_with_data=%s records=%s",
                country_id,
                indicator.name if indicator else None,
                len(submitted_records),
                len(saved_records),
                len(saved_records_with_data),
                len(records),
            )
        else:
            # No assigned country access: visibility by FormItem.privacy only (public or IFRC if same-org).
            # Only show submitted/approved values (no drafts/saved).
            if not visible_item_ids:
                return {
                    'indicator': {'id': indicator.id, 'name': indicator.name, 'unit': indicator.unit, 'definition': indicator.definition},
                    'alternative_indicators': alternative_indicators_result,
                    'total': 0,
                    'records_count': 0,
                    'included_examples': [],
                    'mode': 'total',
                    'period': period,
                    'data_status': 'submitted',
                    'filters_applied': {'country_id': country_id, 'period': period, 'custom_filters': filters or {}},
                    'notes': 'No data visible for this indicator (form items are IFRC-only and you are not in the same organization).',
                    'provenance': {
                        'source': get_organization_name(),
                        'query_time': query_start_time.isoformat(),
                        'filters': applied_filters,
                        'data_status': 'submitted',
                        'data_scope': 'public',
                        'record_count': 0,
                        'total_records_found': 0,
                        'aggregation': 'None (restricted by FormItem.privacy)',
                        'time_period': period or 'All periods',
                        'exclusions': 'Restricted by FormItem.privacy',
                    },
                }

            base_q = FormData.query.join(AssignmentEntityStatus).join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
            base_q = base_q.filter(
                AssignmentEntityStatus.entity_id == country_id,
                AssignmentEntityStatus.entity_type == 'country',
                AssignmentEntityStatus.status.in_(['Submitted', 'Approved']),
                FormData.form_item_id.in_(visible_item_ids),
            )
            if period:
                _pat = f"%{escape_like_pattern(period)}%"
                base_q = base_q.filter(AssignedForm.period_name.ilike(_pat, escape="\\"))
                applied_filters['period'] = period
            # Exclude N/A flags and empty entries
            base_q = base_q.filter(
                or_(FormData.data_not_available.is_(None), FormData.data_not_available.is_(False)),
                or_(FormData.not_applicable.is_(None), FormData.not_applicable.is_(False)),
                or_(FormData.value.isnot(None), FormData.disagg_data.isnot(None)),
            )
            records = base_q.all()
        # ==================== Aggregation ====================
        #
        # IMPORTANT:
        # For "Number of ..." indicators (counts like branches, volunteers, etc.), values are typically
        # point-in-time per submission/assignment. Summing across multiple submissions double-counts.
        #
        # We therefore treat "Number of ..." (and common count units) as "point indicators":
        # - Group FormData by submission (AssignmentEntityStatus / PublicSubmission)
        # - Compute a per-submission total (summing across linked form items only)
        # - If multiple submissions exist, pick the latest submission's value (and expose a summary in provenance)
        #
        is_point_indicator = False
        try:
            nm = (indicator.name or "").strip().lower()
            unit = (indicator.unit or "").strip().lower()
            if nm.startswith("number of"):
                is_point_indicator = True
            if unit in {"branch", "branches", "count", "number"}:
                is_point_indicator = True
        except Exception as exc:
            logger.debug("get_value_breakdown: is_point_indicator heuristic failed: %s", exc)
            is_point_indicator = False

        total = 0.0
        count = 0
        examples: list[int] = []
        mode = None
        disagg_modes = set()

        def _numeric_from_record(fd: FormData) -> float | None:
            nonlocal mode
            try:
                # Use model's total_value when available (value or sum of disagg_data.values) so we match form storage
                tv = getattr(fd, "total_value", None)
                if tv is not None:
                    if isinstance(tv, (int, float)):
                        return float(tv)
                    s = str(tv).strip().replace(",", "").replace("\u00A0", " ")
                    if s:
                        return float(s)
                if fd.disagg_data and isinstance(fd.disagg_data, dict):
                    vals = fd.disagg_data.get("values", {})
                    if isinstance(vals, dict):
                        subtotal = sum(v for v in vals.values() if isinstance(v, (int, float)))
                        mode = fd.disagg_data.get("mode") or mode
                        if mode:
                            disagg_modes.add(mode)
                        return float(subtotal) if subtotal else None
                v = fd.get_effective_value()
                if v is not None:
                    if isinstance(v, (int, float)):
                        return float(v)
                    s = str(v).strip().replace(",", "").replace("\u00A0", " ")
                    if s:
                        return float(s)
            except Exception as exc:
                logger.debug("_numeric_from_record failed: %s", exc)
            return None

        # For point indicators, only count form_data from the chosen indicator per submission
        # (we still fetch with wide item_ids so we don't miss data under alternate labels)
        form_item_ids_chosen = [fi.id for fi in items if getattr(fi, "indicator_bank_id", None) == indicator.id]

        # Group by submission id (avoids double counting across assignments/submissions)
        by_submission: dict[int, dict] = {}
        if records:
            for r in records:
                # Group by submission: use whichever link this FormData has
                sub_id = getattr(r, "assignment_entity_status_id", None) or getattr(r, "public_submission_id", None)
                if sub_id is None:
                    sub_id = -int(getattr(r, "id", 0) or 0)

                entry = by_submission.get(int(sub_id))
                if entry is None:
                    entry = {
                        "submission_id": int(sub_id),
                        "total": 0.0,
                        "formdata_ids": [],
                        "period_name": None,
                        "template_name": None,
                        "status": None,
                        "timestamp": None,
                    }
                    # Attach period/assignment/status metadata from whichever link this FormData has.
                    # Visibility is determined by FormItem.privacy only; metadata comes from the submission.
                    try:
                        aes = getattr(r, "assignment_entity_status", None)
                        if aes is not None:
                            entry["status"] = getattr(aes, "status", None)
                            entry["timestamp"] = getattr(aes, "status_timestamp", None)
                            af = getattr(aes, "assigned_form", None)
                            if af is not None:
                                entry["period_name"] = getattr(af, "period_name", None)
                                tpl = getattr(af, "template", None)
                                entry["template_name"] = getattr(tpl, "name", None) if tpl is not None else None
                        else:
                            ps = getattr(r, "public_submission", None)
                            if ps is not None:
                                entry["status"] = getattr(ps, "status", None)
                                entry["timestamp"] = getattr(ps, "approved_at", None) or getattr(ps, "updated_at", None)
                                af = getattr(ps, "assigned_form", None)
                                if af is not None:
                                    entry["period_name"] = getattr(af, "period_name", None)
                                    tpl = getattr(af, "template", None)
                                    entry["template_name"] = getattr(tpl, "name", None) if tpl is not None else None
                    except Exception as exc:
                        logger.debug("get_value_breakdown: entry metadata attach failed: %s", exc)
                    by_submission[int(sub_id)] = entry

                # Point indicators: only count records from the chosen indicator, and take one value per submission
                # (avoid double-count when form has two fields for same indicator, e.g. form_item 916 and 1201 both → indicator 724)
                if is_point_indicator and form_item_ids_chosen and getattr(r, "form_item_id", None) not in form_item_ids_chosen:
                    continue
                num = _numeric_from_record(r)
                if isinstance(num, (int, float)):
                    n = float(num)
                    if is_point_indicator:
                        # One value per submission: use max so duplicate form fields don't sum (e.g. 14098+14098 → 14098)
                        if (entry["total"] or 0) < n:
                            entry["total"] = n
                            entry["formdata_ids"] = [int(r.id)]
                        elif (entry["total"] or 0) == 0:
                            entry["total"] = n
                            try:
                                entry["formdata_ids"] = [int(r.id)]
                            except Exception as exc:
                                logger.debug("formdata_ids assign failed: %s", exc)
                    else:
                        entry["total"] += n
                        try:
                            entry["formdata_ids"].append(int(r.id))
                        except Exception as exc:
                            logger.debug("formdata_ids append failed: %s", exc)

        def _parse_year(s: str | None) -> int | None:
            if not s:
                return None
            m = re.findall(r"\b(19\d{2}|20\d{2})\b", str(s))
            try:
                return max(int(x) for x in m) if m else None
            except Exception as exc:
                logger.debug("_parse_year failed for %r: %s", s, exc)
                return None

        def _ts(v) -> _dt:
            try:
                return v if isinstance(v, _dt) else _dt.min
            except Exception as exc:
                logger.debug("_ts failed: %s", exc)
                return _dt.min

        def _year_for_sort(e: dict) -> int:
            """Year for ordering: period_name first, then timestamp year, else -1 so unknown sorts last."""
            y = _parse_year(e.get("period_name"))
            if y is not None:
                return y
            ts = e.get("timestamp")
            if ts and hasattr(ts, "year"):
                return ts.year
            return -1

        # Point indicators: use latest submission value instead of summing submissions.
        assignment_name: Optional[str] = None
        period_used: Optional[str] = None
        if is_point_indicator and by_submission:
            # Prioritize latest period first: sort by (year in period_name or timestamp, timestamp, submission_id) descending.
            # So 2024 is always chosen over 2018 when both exist in by_submission.
            ordered = sorted(
                by_submission.values(),
                key=lambda e: (
                    _year_for_sort(e),
                    _ts(e.get("timestamp")),
                    int(e.get("submission_id") or 0),
                ),
                reverse=True,
            )
            chosen = ordered[0]
            total = float(chosen.get("total") or 0.0)
            # Only if the latest-period submission has value 0, use the next latest non-zero (same order).
            # We never prefer an older period over a newer one when the newer has a value.
            used_fallback = False
            if total == 0.0 and len(ordered) > 1:
                for candidate in ordered[1:]:
                    cand_total = float(candidate.get("total") or 0.0)
                    if cand_total != 0.0:
                        chosen = candidate
                        total = cand_total
                        used_fallback = True
                        break
            logger.debug(
                "get_value_breakdown point indicator country_id=%s indicator=%s by_submission=%s ordered=(period,total,year)=%s chosen_period=%s chosen_total=%s used_fallback=%s",
                country_id,
                indicator.name if indicator else None,
                len(by_submission),
                [
                        (e.get("period_name"), e.get("total"), _year_for_sort(e))
                        for e in ordered[:10]
                ],
                chosen.get("period_name"),
                total,
                used_fallback,
            )
            examples = [int(x) for x in (chosen.get("formdata_ids") or [])[:5] if x is not None]
            # records_count: number of contributing FormData rows in the chosen submission
            count = len(chosen.get("formdata_ids") or [])
            assignment_name = chosen.get("template_name")
            period_used = chosen.get("period_name")
            # Reflect status of the submission we actually used (submitted vs saved/draft).
            chosen_status = (chosen.get("status") or "").strip()
            data_status = 'submitted' if chosen_status in ('Submitted', 'Approved') else 'saved'
        else:
            # Non-point indicators: preserve legacy behavior (sum across all records)
            for r in records:
                num = _numeric_from_record(r)
                if isinstance(num, (int, float)):
                    total += float(num)
                    count += 1
                    if len(examples) < 5:
                        try:
                            examples.append(int(r.id))
                        except Exception as exc:
                            logger.debug("examples.append failed: %s", exc)
            if by_submission:
                first_entry = next(iter(by_submission.values()), None)
                if first_entry:
                    assignment_name = first_entry.get("template_name")
                    period_used = first_entry.get("period_name")

        # Determine final mode for display
        if len(disagg_modes) > 1:
            mode = f"mixed ({', '.join(sorted(disagg_modes))})"
        elif mode is None:
            mode = 'total'

        # Build provenance information
        query_end_time = utcnow()
        query_duration = (query_end_time - query_start_time).total_seconds()

        aggregation_method = 'Sum of values'
        if is_point_indicator and by_submission:
            aggregation_method = 'Latest submission value (point-in-time indicator)'
        if len(disagg_modes) > 1:
            aggregation_method = f"Mixed aggregation: {', '.join(sorted(disagg_modes))}"
        elif mode == 'total':
            aggregation_method = 'Sum of disaggregation totals'

        exclusions = []
        if count < len(records):
            exclusions.append(f"{len(records) - count} records with non-numeric values")

        # Build notes with data status information
        notes = 'Sum of effective values across linked form items; disaggregation totals when present.'
        if is_point_indicator and by_submission and len(by_submission) > 1 and not period:
            # Keep this short; details go in provenance.
            notes += ' (Multiple submissions found; using latest submission value.)'
        if data_status == 'saved':
            notes += ' **Note: This data is from saved/draft entries and has not been submitted. Values may change before final submission.**'
        if data_scope == "public":
            notes += ' (Public submissions only.)'

        return {
            'indicator': {
                'id': indicator.id,
                'name': indicator.name,
                'unit': indicator.unit,
                'definition': indicator.definition
            },
            # Optional: present when the original identifier was ambiguous and we found multiple matches with data.
            'alternative_indicators': alternative_indicators_result,
            'total': total,
            'records_count': count,
            'included_examples': examples,
            'mode': mode,
            'period': period,
            'data_status': data_status,  # 'submitted' or 'saved'
            'assignment_name': assignment_name,
            'period_used': period_used,
            'filters_applied': {
                'country_id': country_id,
                'period': period,
                'custom_filters': filters or {}
            },
            'notes': notes,
            'provenance': {
                'source': get_organization_name(),
                'query_time': query_start_time.isoformat(),
                'query_duration_seconds': round(query_duration, 3),
                'filters': applied_filters,
                'data_status': data_status,
                'data_scope': data_scope,
                'record_count': count,
                'total_records_found': len(records),
                'aggregation': aggregation_method,
                'time_period': period or 'All periods',
                'exclusions': '; '.join(exclusions) if exclusions else 'None',
                'submissions_found': len(by_submission) if by_submission else 0,
                'submissions_summary': (
                    [
                        {
                            'submission_id': int(e.get('submission_id') or 0),
                            'period_name': e.get('period_name'),
                            'status': e.get('status'),
                            'total': float(e.get('total') or 0.0),
                        }
                        for e in sorted(
                            by_submission.values(),
                            key=lambda x: (
                                _parse_year(x.get("period_name")) or -1,
                                _ts(x.get("timestamp")),
                                int(x.get("submission_id") or 0),
                            ),
                            reverse=True,
                        )[:5]
                    ]
                    if (is_point_indicator and by_submission and len(by_submission) > 1)
                    else []
                ),
            }
        }
    except Exception as e:
        logger.error(f"Error computing value breakdown: {e}", exc_info=True)
        return {'error': 'Failed to compute value breakdown'}



def resolve_indicator_to_primary_id(
    indicator_name: str,
    *,
    country_id: Optional[int] = None,
) -> Optional[int]:
    """
    Resolve an indicator name to a single primary IndicatorBank id.

    Resolution layers (in order):
    1. Vector similarity (when indicator embeddings exist and method != keyword).
    2. Keyword ILIKE fallback (stem-aware).
    3. Merge both candidate sets (vector candidates + keyword candidates) so
       a correct indicator found only by one path is not missed.
    4. Score candidates by: vector similarity + keyword relevance + data availability
       (when country_id is provided) + recency.
    """
    ident = (indicator_name or "").strip()
    if not ident:
        return None
    if ident.isdigit():
        ind = db.session.get(IndicatorBank, int(ident))
        return int(ind.id) if ind else None

    # --- Layer 1: Vector candidates ---
    vector_pairs: List[tuple] = []
    try:
        from app.services.indicator_resolution_service import get_indicator_candidates
        vector_pairs = get_indicator_candidates(indicator_name, top_k=10)
    except Exception as e:
        logger.debug("resolve_indicator_to_primary_id: vector candidates failed for %r: %s", indicator_name, e)

    similarity_map: Dict[int, float] = {int(c.id): float(s) for c, s in vector_pairs}
    has_vector_scores = bool(similarity_map)

    # --- Layer 2: Keyword candidates (always run to catch what vector missed) ---
    keyword_candidates = get_indicator_candidates_by_keyword(ident)

    # --- Merge: union of both sets, preserving order ---
    seen_ids: set[int] = set()
    candidates: list[IndicatorBank] = []
    vector_only_ids: list[int] = []
    keyword_only_ids: list[int] = []
    both_ids: list[int] = []
    kw_id_set = {c.id for c in keyword_candidates}
    vec_id_set = {c.id for c, _ in vector_pairs}
    for c, _ in vector_pairs:
        if c.id not in seen_ids:
            seen_ids.add(c.id)
            candidates.append(c)
            if c.id in kw_id_set:
                both_ids.append(c.id)
            else:
                vector_only_ids.append(c.id)
    for c in keyword_candidates:
        if c.id not in seen_ids:
            seen_ids.add(c.id)
            candidates.append(c)
            keyword_only_ids.append(c.id)

    logger.info(
        "resolve_indicator_to_primary_id: ident=%r country_id=%s | "
        "vector=%d keyword=%d merged=%d (vector_only=%s keyword_only=%s both=%s)",
        indicator_name, country_id,
        len(vector_pairs), len(keyword_candidates), len(candidates),
        vector_only_ids[:5], keyword_only_ids[:5], both_ids[:5],
    )

    if not candidates:
        logger.info("resolve_indicator_to_primary_id: no candidates found for %r", indicator_name)
        return None

    # --- Layer 3: Data-availability + recency (when country_id is known) ---
    data_count_map: Dict[int, int] = {}
    max_year_map: Dict[int, int] = {}
    if country_id is not None and len(candidates) > 1:
        candidate_ids = [c.id for c in candidates]
        try:
            from app.models import FormData
            from app.models.assignments import AssignmentEntityStatus as AES
            cnt_q = (
                db.session.query(
                    IndicatorBank.id.label("indicator_id"),
                    func.count(FormData.id).label("records"),
                )
                .join(FormItem, FormItem.indicator_bank_id == IndicatorBank.id)
                .join(FormData, FormData.form_item_id == FormItem.id)
                .join(AES, FormData.assignment_entity_status_id == AES.id)
                .filter(
                    IndicatorBank.id.in_(candidate_ids),
                    AES.entity_type == "country",
                    AES.entity_id == int(country_id),
                    or_(FormData.data_not_available.is_(None), FormData.data_not_available.is_(False)),
                    or_(FormData.not_applicable.is_(None), FormData.not_applicable.is_(False)),
                    or_(FormData.value.isnot(None), FormData.disagg_data.isnot(None)),
                )
                .group_by(IndicatorBank.id)
            )
            for row in cnt_q.all():
                data_count_map[int(row.indicator_id)] = int(row.records or 0)

            recency_q = (
                db.session.query(
                    IndicatorBank.id.label("indicator_id"),
                    AssignedForm.period_name,
                )
                .join(FormItem, FormItem.indicator_bank_id == IndicatorBank.id)
                .join(FormData, FormData.form_item_id == FormItem.id)
                .join(AES, FormData.assignment_entity_status_id == AES.id)
                .join(AssignedForm, AES.assigned_form_id == AssignedForm.id)
                .filter(
                    IndicatorBank.id.in_(candidate_ids),
                    AES.entity_type == "country",
                    AES.entity_id == int(country_id),
                    or_(FormData.value.isnot(None), FormData.disagg_data.isnot(None)),
                )
            )
            for row in recency_q.all():
                y = None
                if getattr(row, "period_name", None):
                    m = re.findall(r"\b(19\d{2}|20\d{2})\b", str(row.period_name))
                    if m:
                        y = max(int(x) for x in m)
                if y is not None:
                    iid = int(row.indicator_id)
                    max_year_map[iid] = max(max_year_map.get(iid, 0), y)

            logger.info(
                "resolve_indicator_to_primary_id: data_counts=%s max_years=%s",
                {k: v for k, v in sorted(data_count_map.items(), key=lambda x: -x[1])[:5]},
                {k: v for k, v in sorted(max_year_map.items(), key=lambda x: -x[1])[:5]},
            )
        except Exception as e:
            logger.warning("resolve_indicator_to_primary_id: data-availability query failed: %s", e)

    # --- Layer 4: Combined scoring ---
    def _combined_score(c: IndicatorBank) -> tuple:
        """Returns (final_score, score_breakdown_dict)."""
        vec_sim = similarity_map.get(int(c.id), 0.0)
        kw_rel = score_indicator_relevance(c.name, ident)
        if has_vector_scores:
            base = vec_sim * 5.0 + kw_rel * 0.3
        else:
            base = kw_rel

        data_bonus = 0.0
        recency_bonus = 0.0
        data_count = data_count_map.get(c.id, 0)
        max_year = max_year_map.get(c.id, 0)
        if data_count > 0:
            data_bonus = min(1.0, data_count / 50.0)
        if max_year >= 2000:
            recency_bonus = (max_year - 2000) * 0.1

        final = base + data_bonus + recency_bonus
        breakdown = {
            "vec_sim": round(vec_sim, 4),
            "kw_rel": round(kw_rel, 2),
            "base": round(base, 2),
            "data_count": data_count,
            "data_bonus": round(data_bonus, 2),
            "max_year": max_year,
            "recency_bonus": round(recency_bonus, 2),
            "final": round(final, 2),
        }
        return final, breakdown

    scored = []
    for c in candidates:
        final, breakdown = _combined_score(c)
        scored.append((c, final, breakdown))
    scored.sort(key=lambda item: (item[1], (item[0].name or "").strip().lower()), reverse=True)

    logger.info(
        "resolve_indicator_to_primary_id: WINNER=%r (id=%s) | top5 scoring:\n%s",
        scored[0][0].name, scored[0][0].id,
        "\n".join(
            f"  #{i+1} id={c.id} score={round(s, 2)} {bd} name={c.name!r}"
            for i, (c, s, bd) in enumerate(scored[:5])
        ),
    )

    return int(scored[0][0].id)


def get_indicator_values_for_all_countries(
    indicator_name: str,
    period: Optional[str] = None,
    max_countries: int = 250,
    min_value: Optional[float] = None,
    on_progress: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """
    Get indicator values for all user-accessible countries in one call.
    Use for "volunteers for all countries", "list indicator X by country", etc.
    Prefer this over calling get_indicator_value 192 times.

    Values are read from the form_data table (FormData joined with AssignmentEntityStatus
    and FormItem/IndicatorBank). IndicatorBank is metadata only; actual data is in FormData.

    RBAC applies: only countries the user can access are included.
    Returns one row per country with a value (countries with no data are omitted).

    Args:
        indicator_name: Name of the indicator (same as get_indicator_value)
        period: Optional period filter (e.g. "2023", "FY2023")
        max_countries: Cap number of countries queried (default 250) to avoid timeouts
        min_value: Optional. If set, return only rows where value >= min_value (e.g. 10001 for
            "more than 10000"). Use for threshold queries so the backend does the filter and
            the response contains only qualifying countries (no omission risk in the model).

    Returns:
        Dict with success, indicator_name, period, rows (list of {country_id, country_name, iso3, value, data_status, optional assignment_name, optional period_used}), count
    """
    def _progress(msg: str) -> None:
        if on_progress:
            try:
                on_progress(msg)
            except Exception as e:
                logger.debug("_progress callback failed: %s", e)

    try:
        # Normalize period: treat "" / whitespace as not provided.
        period = ((period or "").strip() or None)

        viewer = get_effective_request_user()
        can_see_ifrc = can_view_non_public_form_items(viewer)

        _progress("Loading countries…")
        allowed_country_ids_raw = user_allowed_country_ids()
        # allowed_country_ids semantics:
        # - None: unrestricted (admin/system manager/country managers)
        # - []: no entity scope (public data should still be visible)
        # - [ids...]: non-public data is allowed only for these countries
        allowed_country_ids: Optional[List[int]]
        if allowed_country_ids_raw is None:
            allowed_country_ids = None
        else:
            allowed_country_ids = [int(x) for x in allowed_country_ids_raw if x is not None]
            if len(allowed_country_ids) > int(max_countries):
                allowed_country_ids = allowed_country_ids[: int(max_countries)]

        ident = (indicator_name or "").strip()
        if not ident:
            return service_error("Indicator name is required", rows=[], count=0)

        # -------- Resolve candidate indicators (vector + keyword merged) --------
        candidates: List[IndicatorBank] = []
        similarity_map: Dict[int, float] = {}
        if ident.isdigit():
            ind = db.session.get(IndicatorBank, int(ident))
            if ind:
                candidates = [ind]
                similarity_map[int(ind.id)] = 1.0
        else:
            # Vector candidates
            try:
                from app.services.indicator_resolution_service import get_indicator_candidates
                vector_pairs = get_indicator_candidates(indicator_name, top_k=10)
                candidates = [c for c, _ in vector_pairs]
                similarity_map = {int(c.id): float(s) for c, s in vector_pairs}
            except Exception as e:
                logger.debug("get_indicator_values_for_all_countries: get_indicator_candidates failed: %s", e)
            # Always merge keyword candidates so stem variants are found
            keyword_candidates = get_indicator_candidates_by_keyword(ident)
            seen_ids = {int(c.id) for c in candidates}
            for c in keyword_candidates:
                if int(c.id) not in seen_ids:
                    seen_ids.add(int(c.id))
                    candidates.append(c)
        if not candidates:
            return service_error("Indicator not found", rows=[], count=0)

        has_vector_scores = bool(similarity_map)
        candidate_ids = [int(c.id) for c in candidates]

        # Compute a combined relevance score per candidate.  When vector
        # similarity is available it dominates; keyword relevance is a
        # lightweight secondary signal (tiebreaker / fallback).
        def _relevance(c: IndicatorBank) -> float:
            vec_sim = similarity_map.get(int(c.id), 0.0)
            kw_rel = score_indicator_relevance(c.name, ident)
            if has_vector_scores:
                return vec_sim * 5.0 + kw_rel * 0.3
            return kw_rel

        scored_candidates = [(c, _relevance(c)) for c in candidates]
        scored_candidates.sort(
            key=lambda item: (item[1], (item[0].name or "").strip().lower()),
            reverse=True,
        )

        # Default resolved indicator: top relevance candidate (may be overridden by coverage-based scoring below).
        resolved_indicator_id: int = int(scored_candidates[0][0].id)
        resolved_indicator_name: str = str(scored_candidates[0][0].name or "").strip()

        alternatives: List[Dict[str, Any]] = []
        global_counts: Dict[int, int] = {}
        if len(candidates) > 1:
            # Counts per (country, indicator), including both submitted+saved data
            count_q = (
                db.session.query(
                    AssignmentEntityStatus.entity_id.label("country_id"),
                    IndicatorBank.id.label("indicator_id"),
                    func.count(FormData.id).label("records"),
                )
                .join(FormItem, FormItem.indicator_bank_id == IndicatorBank.id)
                .join(FormData, FormData.form_item_id == FormItem.id)
                .join(AssignmentEntityStatus, FormData.assignment_entity_status_id == AssignmentEntityStatus.id)
                .filter(
                    IndicatorBank.id.in_(candidate_ids),
                    AssignmentEntityStatus.entity_type == "country",
                    or_(FormData.data_not_available.is_(None), FormData.data_not_available.is_(False)),
                    or_(FormData.not_applicable.is_(None), FormData.not_applicable.is_(False)),
                    or_(FormData.value.isnot(None), FormData.disagg_data.isnot(None)),
                )
            )
            if not can_see_ifrc:
                count_q = count_q.filter(form_item_privacy_is_public_expr())
            elif allowed_country_ids is not None:
                count_q = count_q.filter(
                    or_(
                        form_item_privacy_is_public_expr(),
                        AssignmentEntityStatus.entity_id.in_(allowed_country_ids),
                    )
                )
            if period:
                _pat = f"%{escape_like_pattern(period)}%"
                count_q = count_q.join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id).filter(
                    AssignedForm.period_name.ilike(_pat, escape="\\")
                )
            count_rows = count_q.group_by(AssignmentEntityStatus.entity_id, IndicatorBank.id).all()
            data_count_map: Dict[tuple[int, int], int] = {
                (int(r.country_id), int(r.indicator_id)): int(r.records or 0)
                for r in count_rows
            }

            # Build global alternatives list (still useful for the AI to disambiguate).
            for (cid, iid), cnt in data_count_map.items():
                global_counts[iid] = global_counts.get(iid, 0) + int(cnt)
            for c, rel in scored_candidates[:10]:
                cnt = int(global_counts.get(int(c.id), 0))
                if cnt > 0:
                    vec_sim = similarity_map.get(int(c.id))
                    alternatives.append(
                        {"id": int(c.id), "name": c.name, "records_count": cnt,
                         "relevance_score": round(float(rel), 2),
                         **({"vector_similarity": round(float(vec_sim), 4)} if vec_sim is not None else {})}
                    )

            # Resolve ONE indicator id for the whole response (never mix indicators across countries).
            # Combined score: vector similarity (primary) + keyword relevance (secondary) + coverage.
            ident_lower = ident.strip().lower()
            query_terms = set(re.findall(r"[a-z]+", ident_lower))
            avoid_terms = {"death", "deaths", "fatal", "fatality", "fatalities", "mortality", "killed", "injury", "injuries"}
            wants_avoid_topic = bool(query_terms & avoid_terms)

            best_id = resolved_indicator_id
            best_score = float("-inf")
            for c, rel in scored_candidates:
                iid = int(c.id)
                nm = (c.name or "").strip().lower()
                cnt = int(global_counts.get(iid, 0))
                score = float(rel) + (1.5 * math.log10(cnt + 1))
                if (("death" in nm) or ("deaths" in nm) or ("fatal" in nm) or ("mortality" in nm)) and not wants_avoid_topic:
                    score -= 3.0
                if score > best_score:
                    best_score = score
                    best_id = iid
            resolved_indicator_id = int(best_id)
            try:
                resolved_indicator_name = str(next((c.name for c in candidates if int(c.id) == resolved_indicator_id), resolved_indicator_name))
            except Exception as exc:
                logger.debug("resolved_indicator_name fallback failed: %s", exc)

        _ri_name = (resolved_indicator_name or "").strip() or str(resolved_indicator_id)
        if len(_ri_name) > 200:
            _ri_name = _ri_name[:197] + "…"
        _progress(_("Selected indicator: %(name)s", name=_ri_name))

        # Determine point-indicator behavior for the resolved indicator.
        try:
            resolved_obj = next((c for c in candidates if int(c.id) == int(resolved_indicator_id)), scored_candidates[0][0])
            nm = (resolved_obj.name or "").strip().lower()
            unit = (getattr(resolved_obj, "unit", None) or "").strip().lower()
            resolved_is_point_indicator = bool(nm.startswith("number of") or unit in {"branch", "branches", "count", "number"})
        except Exception as exc:
            logger.debug("resolved_is_point_indicator heuristic failed: %s", exc)
            resolved_is_point_indicator = False

        # Form items for the resolved indicator ONLY (never mix across indicators)
        item_pairs_q = db.session.query(FormItem.id, FormItem.indicator_bank_id).filter(
            FormItem.indicator_bank_id == int(resolved_indicator_id)
        )
        if not can_see_ifrc:
            item_pairs_q = item_pairs_q.filter(form_item_privacy_is_public_expr())
        item_pairs = item_pairs_q.all()
        item_ids = [int(fid) for fid, _ in item_pairs]
        if not item_ids:
            return {"success": True, "indicator_name": indicator_name, "period": period, "rows": [], "count": 0}

        # -------- Fetch all relevant records in one query --------
        _progress("Querying form data…")
        q = (
            db.session.query(
                AssignmentEntityStatus.entity_id.label("country_id"),
                FormItem.indicator_bank_id.label("indicator_id"),
                AssignmentEntityStatus.id.label("submission_id"),
                AssignmentEntityStatus.status.label("status"),
                AssignmentEntityStatus.status_timestamp.label("status_timestamp"),
                AssignedForm.period_name.label("period_name"),
                AssignedForm.assigned_at.label("assigned_at"),
                AssignedForm.template_id.label("template_id"),
                FormData.id.label("formdata_id"),
                FormData.value.label("value"),
                FormData.disagg_data.label("disagg_data"),
            )
            .join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
            .join(FormData, FormData.assignment_entity_status_id == AssignmentEntityStatus.id)
            .join(FormItem, FormData.form_item_id == FormItem.id)
            .filter(
                AssignmentEntityStatus.entity_type == "country",
                FormItem.indicator_bank_id == int(resolved_indicator_id),
                FormData.form_item_id.in_(item_ids),
                or_(FormData.data_not_available.is_(None), FormData.data_not_available.is_(False)),
                or_(FormData.not_applicable.is_(None), FormData.not_applicable.is_(False)),
                or_(FormData.value.isnot(None), FormData.disagg_data.isnot(None)),
            )
        )
        if not can_see_ifrc:
            q = q.filter(form_item_privacy_is_public_expr())
        elif allowed_country_ids is not None:
            q = q.filter(
                or_(
                    form_item_privacy_is_public_expr(),
                    AssignmentEntityStatus.entity_id.in_(allowed_country_ids),
                )
            )
        if period:
            _pat = f"%{escape_like_pattern(period)}%"
            q = q.filter(AssignedForm.period_name.ilike(_pat, escape="\\"))
        rows = q.all()

        if not rows:
            return {"success": True, "indicator_name": indicator_name, "period": period, "rows": [], "count": 0}

        _progress("Building results…")
        # Country metadata (avoid per-row db lookups)
        country_ids_with_data = sorted({int(r.country_id) for r in rows if getattr(r, "country_id", None) is not None})
        countries = Country.query.filter(Country.id.in_(country_ids_with_data)).all() if country_ids_with_data else []
        country_map = {int(c.id): c for c in countries}

        def _parse_year(s: str | None) -> int | None:
            if not s:
                return None
            m = re.findall(r"\b(19\d{2}|20\d{2})\b", str(s))
            try:
                return max(int(x) for x in m) if m else None
            except Exception as exc:
                logger.debug("_parse_year failed for %r: %s", s, exc)
                return None

        def _ts(v) -> _dt:
            try:
                return v if isinstance(v, _dt) else _dt.min
            except Exception as exc:
                logger.debug("_ts failed: %s", exc)
                return _dt.min

        def _recency_ts(e: dict) -> _dt:
            """
            Prefer real timestamps over parsing year from period_name.
            - status_timestamp updates when the submission status changes (most relevant).
            - assigned_at is a stable fallback when period_name lacks a year.
            """
            try:
                t1 = _ts(e.get("timestamp"))
                t2 = _ts(e.get("assigned_at"))
                return t1 if t1 >= t2 else t2
            except Exception as exc:
                logger.debug("_recency_ts failed: %s", exc)
                return _dt.min

        def _year_for_sort(e: dict) -> int:
            y = _parse_year(e.get("period_name"))
            if y is not None:
                return y
            ts = e.get("timestamp")
            if ts and hasattr(ts, "year"):
                return ts.year
            at = e.get("assigned_at")
            if at and hasattr(at, "year"):
                return at.year
            return -1

        def _numeric_from_row(value: Any, disagg_data: Any) -> float | None:
            try:
                # Prefer the main value when present; use disaggregation as fallback.
                v = value
                if v is not None:
                    if isinstance(v, (int, float)):
                        return float(v)
                    if isinstance(v, str):
                        s = v.strip()
                        if s:
                            s = s.replace(",", "").replace("\u00A0", " ").replace(" ", "")
                            if s:
                                return float(s)

                if disagg_data:
                    dd = disagg_data
                    if isinstance(dd, str):
                        try:
                            dd = json.loads(dd)
                        except Exception as exc:
                            logger.debug("_numeric_from_row: disagg json.loads failed: %s", exc)
                            dd = None
                    if isinstance(dd, dict):
                        vals = dd.get("values", {}) or {}
                        if isinstance(vals, dict):
                            subtotal = sum(x for x in vals.values() if isinstance(x, (int, float)))
                            return float(subtotal) if subtotal != 0 else None
            except Exception as exc:
                logger.debug("_numeric_from_row failed: %s", exc)
                return None
            return None

        # Aggregate by (country, indicator, submission) (indicator is effectively constant here)
        by_country_indicator: Dict[int, Dict[int, Dict[int, dict]]] = {}
        for r in rows:
            cid = int(r.country_id)
            iid = int(r.indicator_id) if getattr(r, "indicator_id", None) is not None else 0
            sid = int(r.submission_id)
            country_inds = by_country_indicator.setdefault(cid, {})
            subs = country_inds.setdefault(iid, {})
            entry = subs.get(sid)
            if entry is None:
                entry = {
                    "submission_id": sid,
                    "total": 0.0,
                    "has_numeric": False,
                    "formdata_ids": [],
                    "period_name": r.period_name,
                    "template_id": int(r.template_id) if r.template_id is not None else None,
                    "status": r.status,
                    "timestamp": r.status_timestamp,
                    "assigned_at": getattr(r, "assigned_at", None),
                }
                subs[sid] = entry

            num = _numeric_from_row(r.value, r.disagg_data)
            if isinstance(num, (int, float)):
                entry["has_numeric"] = True
                n = float(num)
                if resolved_is_point_indicator:
                    if (entry["total"] or 0) < n:
                        entry["total"] = n
                        try:
                            entry["formdata_ids"] = [int(r.formdata_id)]
                        except Exception as exc:
                            logger.debug("formdata_ids assign (formdata_id) failed: %s", exc)
                    elif (entry["total"] or 0) == 0:
                        entry["total"] = n
                        try:
                            entry["formdata_ids"] = [int(r.formdata_id)]
                        except Exception as exc:
                            logger.debug("formdata_ids assign (formdata_id) failed: %s", exc)
                else:
                    entry["total"] += n
                    try:
                        entry["formdata_ids"].append(int(r.formdata_id))
                    except Exception as exc:
                        logger.debug("formdata_ids append (formdata_id) failed: %s", exc)

        # Template name mapping
        template_ids_seen = sorted(
            {int(e.get("template_id")) for cinds in by_country_indicator.values() for subs in cinds.values() for e in subs.values() if e.get("template_id")}
        )
        templates = FormTemplate.query.filter(FormTemplate.id.in_(template_ids_seen)).all() if template_ids_seen else []
        template_map = {int(t.id): t for t in templates}

        # Indicator name map
        indicator_map = {int(c.id): c for c in candidates}

        rows_out: List[Dict[str, Any]] = []
        for cid, inds in by_country_indicator.items():
            subs = (inds or {}).get(int(resolved_indicator_id), {}) or {}
            if not subs:
                continue

            value_out: Optional[float] = None
            period_used: Optional[str] = None
            assignment_name: Optional[str] = None
            data_status: str = "submitted"

            # Always choose ONE submission per country, regardless of indicator type.
            # When no explicit period filter is supplied, choose the most recent *period with data*:
            # - Prefer the highest year parsed from period_name (e.g. "2023-2024" -> 2024, "FY2024" -> 2024)
            # - Use status/assignment timestamps as a tie-breaker within the same year
            # - Ignore submissions that have no parsable numeric values (e.g. empty/unparseable fields)
            candidates = [e for e in subs.values() if bool(e.get("has_numeric"))]
            if not candidates:
                continue
            ordered = sorted(
                candidates,
                key=lambda e: (
                    _year_for_sort(e),
                    _recency_ts(e),
                    int(e.get("submission_id") or 0),
                ),
                reverse=True,
            )
            chosen = ordered[0]
            total = float(chosen.get("total") or 0.0)
            value_out = float(total)
            period_used = chosen.get("period_name")
            tmpl_id = chosen.get("template_id")
            if tmpl_id:
                tpl = template_map.get(int(tmpl_id))
                if tpl is not None:
                    assignment_name = tpl.name
            chosen_status = (chosen.get("status") or "").strip()
            data_status = 'submitted' if chosen_status in ('Submitted', 'Approved') else 'saved'

            if value_out is None:
                continue

            c = country_map.get(int(cid))
            ind_obj = indicator_map.get(int(resolved_indicator_id))
            row = {
                "country_id": int(cid),
                "country_name": c.name if c else str(cid),
                "iso3": (getattr(c, "iso3", None) or "") if c else "",
                "region": (getattr(c, "region", None) or "") if c else "",
                "value": float(value_out),
                "data_status": data_status,
                # Non-breaking additions for debugging/disambiguation:
                "indicator_id": int(resolved_indicator_id),
                "indicator_name_resolved": ind_obj.name if ind_obj else None,
            }
            if assignment_name is not None:
                row["assignment_name"] = assignment_name
            if period_used is not None:
                row["period_used"] = period_used
            rows_out.append(row)

        # Sort by value descending so high-value countries appear first.
        rows_out.sort(key=lambda r: (-(r.get("value") or 0), (r.get("country_name") or "")))

        # Optional threshold filter: backend does the filter so the model only displays rows (no omission risk).
        if min_value is not None:
            try:
                threshold = float(min_value)
                rows_out = [r for r in rows_out if (r.get("value") or 0) >= threshold]
            except (TypeError, ValueError):
                pass

        try:
            resolved_obj = indicator_map.get(int(resolved_indicator_id))
            resolved_indicator = {
                "id": int(resolved_indicator_id),
                "name": (resolved_obj.name if resolved_obj else None) or resolved_indicator_name or str(resolved_indicator_id),
            }
        except Exception as exc:
            logger.debug("resolved_indicator fallback: %s", exc)
            resolved_indicator = {"id": int(resolved_indicator_id), "name": resolved_indicator_name or str(resolved_indicator_id)}

        return {
            "success": True,
            "indicator_name": indicator_name,
            "period": period,
            "rows": rows_out,
            "rows_sorted_by_value_desc": True,
            "count": len(rows_out),
            "alternative_indicators": alternatives,
            "resolved_indicator": resolved_indicator,
            "note_platform_region": "Use each row's 'region' for the Operational region column (platform data). When the user asks for continent, that means operational region — use this field; do not add a separate continent column or use model knowledge. Allowed values: Asia Pacific, MENA, Europe & CA, Africa, Americas.",
        }
    except Exception as e:
        logger.error("get_indicator_values_for_all_countries error: %s", e, exc_info=True)
        return service_error(GENERIC_ERROR_MESSAGE, rows=[], count=0)


def _numeric_from_formdata_value(value: Any, disagg_data: Any) -> Optional[float]:
    """Extract a single numeric from FormData.value or disagg_data (for assignment list)."""
    try:
        if disagg_data and isinstance(disagg_data, dict):
            vals = disagg_data.get("values")
            if isinstance(vals, dict):
                subtotal = sum(v for v in vals.values() if isinstance(v, (int, float)))
                return float(subtotal) if subtotal else None
            # Flat matrix-style keys with numeric values
            total = 0.0
            for k, v in disagg_data.items():
                if k.startswith("_"):
                    continue
                if isinstance(v, dict) and ("modified" in v or "original" in v):
                    v = v.get("modified") if v.get("modified") is not None else v.get("original")
                if isinstance(v, (int, float)):
                    total += float(v)
                elif v is not None:
                    try:
                        total += float(str(v).replace(",", ""))
                    except (ValueError, TypeError):
                        pass
            return total if total else None
        if value is not None:
            if isinstance(value, (int, float)):
                return float(value)
            s = str(value).strip().replace(",", "")
            if s:
                return float(s)
    except Exception as exc:
        logger.debug("_numeric_from_formdata_value failed: %s", exc)
    return None

def get_assignment_indicator_values(
    country_identifier: Union[int, str],
    template_identifier: Union[int, str],
    period: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get reported indicator values for a specific assignment (country + template + period).

    Use for questions like "FDRS 2024 Syria indicators" or "what values did Syria report for FDRS 2024".
    Returns form-submitted (or saved) values per indicator for that assignment.

    Period matching: assignment period is matched by substring (ilike). Supported formats include
    single year (2024), year range (2023-2024), fiscal (FY2024), month range (Jan 2024 - Dec 2024), etc.

    Args:
        country_identifier: Country name, ISO3, or ID
        template_identifier: Template name (e.g. "FDRS") or ID
        period: Optional period filter; any period_name containing this string matches (e.g. "2024", "2023-2024")

    Returns:
        Dict with assignment_info, indicator_values (list of {indicator_name, value, unit, data_status}), data_status
    """
    try:
        country = resolve_country(country_identifier)
        if not country or not getattr(country, "id", None):
            return {"error": "Country not found", "indicator_values": []}
        country_id = int(country.id)

        if not check_country_access(country_id):
            return {"error": "Access denied for this country", "indicator_values": []}

        # Resolve template (FormTemplate.name is a @property; filter via FormTemplateVersion.name)
        template = None
        if isinstance(template_identifier, int):
            template = db.session.get(FormTemplate, template_identifier)
        elif isinstance(template_identifier, str):
            if template_identifier.strip().isdigit():
                template = db.session.get(FormTemplate, int(template_identifier.strip()))
            if not template:
                template = (
                    FormTemplate.query
                    .join(FormTemplateVersion, FormTemplateVersion.template_id == FormTemplate.id)
                    .filter(FormTemplateVersion.name.ilike(safe_ilike_pattern(template_identifier.strip())))
                    .first()
                )
        if not template:
            return {"error": "Template not found", "indicator_values": []}

        # Find assignment(s): AssignedForm + AssignmentEntityStatus for this country and template
        q = (
            db.session.query(AssignmentEntityStatus, AssignedForm)
            .join(AssignedForm, AssignedForm.id == AssignmentEntityStatus.assigned_form_id)
            .filter(
                AssignmentEntityStatus.entity_id == country_id,
                AssignmentEntityStatus.entity_type == "country",
                AssignedForm.template_id == template.id,
            )
        )
        if period:
            _pat = f"%{escape_like_pattern(period)}%"
            q = q.filter(AssignedForm.period_name.ilike(_pat, escape="\\"))
        rows = q.all()
        if not rows:
            return {
                "assignment_info": {
                    "country_id": country_id,
                    "country_name": getattr(country, "name", None),
                    "template_name": template.name,
                    "period_filter": period,
                },
                "indicator_values": [],
                "data_status": "submitted",
                "notes": "No assignment found for this country, template, and period.",
            }

        # Use the first matching assignment (e.g. FDRS 2024)
        aes, assigned_form = rows[0]
        aes_id = int(aes.id)
        data_status = "submitted" if aes.status in ("Submitted", "Approved") else "saved"

        # FormData for this assignment, only for form items that are indicators
        fd_q = (
            db.session.query(FormData, FormItem, IndicatorBank)
            .join(FormItem, FormData.form_item_id == FormItem.id)
            .join(IndicatorBank, FormItem.indicator_bank_id == IndicatorBank.id)
            .filter(
                FormData.assignment_entity_status_id == aes_id,
                FormItem.indicator_bank_id.isnot(None),
            )
        )
        # Exclude N/A or data_not_available
        fd_q = fd_q.filter(
            or_(FormData.data_not_available.is_(None), FormData.data_not_available.is_(False)),
            or_(FormData.not_applicable.is_(None), FormData.not_applicable.is_(False)),
        )
        fd_rows = fd_q.all()

        indicator_values = []
        seen_indicator_ids = set()
        for fd, fi, ind in fd_rows:
            if ind.id in seen_indicator_ids:
                continue
            seen_indicator_ids.add(ind.id)
            val = fd.value
            disagg = getattr(fd, "disagg_data", None)
            # Sum disagg_data when value is None so we return a numeric for disaggregated indicators
            num = _numeric_from_formdata_value(val, disagg)
            if num is not None:
                val = num
            elif disagg and not val:
                val = "(disaggregated)"
            indicator_values.append({
                "indicator_name": ind.name,
                "value": val,
                "unit": getattr(ind, "unit", None) or "",
            })
        indicator_values.sort(key=lambda x: (x["indicator_name"] or "").lower())

        return {
            "assignment_info": {
                "country_id": country_id,
                "country_name": getattr(country, "name", None),
                "template_name": template.name,
                "period_name": getattr(assigned_form, "period_name", None),
                "assignment_id": assigned_form.id,
                "status": aes.status,
            },
            "indicator_values": indicator_values,
            "data_status": data_status,
            "notes": f"Found {len(indicator_values)} indicator(s) with values." if indicator_values else "No indicator values recorded for this assignment.",
        }
    except Exception as e:
        logger.exception("get_assignment_indicator_values failed: %s", e)
        return {"error": "An error occurred.", "indicator_values": []}


# ==================== Form Field / Matrix Value (for Chatbot) ====================

def get_form_field_value(
    country_identifier: str,
    field_label_or_name: str,
    period: Optional[str] = None,
    assignment_period: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get value(s) for a form field (section or matrix item) for a country.

    Used by the chatbot for questions like "People to be reached by Bangladesh in 2027".
    - Matches form items by ITEM LABEL (e.g. "Longer term programmes") OR SECTION LABEL (e.g. "People to be reached").
    - Supports item types: indicator (with disaggregation), question (numeric or text), matrix (JSON/flat keys).
    - Matrix data is in FormData.disagg_data as nested (values dict) or flat (e.g. {"2025_SP1": 75000});
      period filters matrix ROW/KEY (e.g. "2027" → keys containing "2027"). assignment_period filters
      which assignment (single year, year range, or month range — matched by substring in period_name).
    - period: filters MATRIX ROW/KEY only; assignment_period: which assignment (e.g. "2025", "2023-2024").

    Args:
        country_identifier: Country name, ISO3 code, or ID
        field_label_or_name: Section name or form item label (e.g. "people to be reached", "Longer term programmes")
        period: Optional matrix row/key filter (e.g. "2027") — filters disagg_data keys, not assignment period
        assignment_period: Optional assignment period (e.g. "2025", "2023-2024", "FY2024") — substring match

    Returns:
        Dict with: field_label, section_label, total, breakdown, text_values (if any non-numeric), period, data_status, notes
    """
    try:
        # Debug: log incoming parameters
        logger.info(
            "get_form_field_value called: country_identifier=%r, field_label_or_name=%r, period=%r, assignment_period=%r",
            country_identifier,
            field_label_or_name,
            period,
            assignment_period,
        )

        country_info = get_country_info(country_identifier)
        if 'error' in country_info:
            logger.warning("get_form_field_value: country not found: %s", country_identifier)
            return service_error(country_info['error'])
        country_id = country_info['country']['id']
        country_name = country_info['country'].get('name') or country_identifier

        search_term = (field_label_or_name or '').strip()
        if not search_term:
            return service_error('Field label or name is required.')

        # Find form items by ITEM LABEL or SECTION NAME (join FormSection)
        # Section "People to be reached" contains matrix "Longer term programmes" — match either
        search_pattern = safe_ilike_pattern(search_term)
        items = (
            FormItem.query
            .join(FormSection, FormItem.section_id == FormSection.id)
            .filter(
                FormItem.archived.is_(False),
                FormSection.archived.is_(False),
                FormItem.item_type.in_(['matrix', 'indicator', 'question']),
                or_(
                    FormItem.label.ilike(search_pattern),
                    FormSection.name.ilike(search_pattern),
                ),
            )
            .all()
        )

        logger.debug(
            "get_form_field_value: found %d form item(s) for search_term=%r: item_ids=%s, labels=%s, section_names=%s",
            len(items),
            search_term,
            [i.id for i in items],
            [i.label for i in items],
            [i.form_section.name if i.form_section else None for i in items],
        )

        if not items:
            return {
                'error': f'No form field found matching "{field_label_or_name}".',
                'success': False,
                'field_label_or_name': field_label_or_name,
                'debug': {'search_term': search_term, 'searched': 'item label and section name'},
            }

        # Prefer matrix items for "people to be reached" style queries
        matrix_items = [i for i in items if (i.item_type or '').lower() == 'matrix']
        chosen = matrix_items if matrix_items else items
        has_country_access = bool(check_country_access(country_id))
        # Without country access: visibility by FormItem.privacy (public or IFRC if same-org).
        if not has_country_access:
            viewer = get_effective_request_user()
            can_see_ifrc = can_view_non_public_form_items(viewer)
            chosen = [
                i for i in chosen
                if (getattr(i, "privacy", None) or "").strip().lower() == "public" or can_see_ifrc
            ]
            if not chosen:
                return service_error('Access denied: the requested field is not visible (public or same-org).')
        item_ids = [i.id for i in chosen]
        effective_label = chosen[0].label
        section_label = chosen[0].form_section.name if chosen[0].form_section else None

        # FormData for this country and these items.
        # Do NOT filter by AssignedForm.period_name using period — period is the matrix ROW (e.g. 2027).
        base_q = (
            FormData.query
            .join(AssignmentEntityStatus, FormData.assignment_entity_status_id == AssignmentEntityStatus.id)
            .filter(
                AssignmentEntityStatus.entity_type == 'country',
                AssignmentEntityStatus.entity_id == country_id,
                FormData.form_item_id.in_(item_ids),
                or_(FormData.data_not_available.is_(None), FormData.data_not_available.is_(False)),
                or_(FormData.not_applicable.is_(None), FormData.not_applicable.is_(False)),
                or_(FormData.value.isnot(None), FormData.disagg_data.isnot(None)),
            )
        )
        if assignment_period:
            _pat = f"%{escape_like_pattern(assignment_period)}%"
            base_q = base_q.join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id).filter(
                AssignedForm.period_name.ilike(_pat, escape="\\")
            )

        # Prefer submitted/approved.
        # Public callers should never see draft/saved values; RBAC users may.
        submitted_q = base_q.filter(AssignmentEntityStatus.status.in_(['Submitted', 'Approved']))
        records = submitted_q.all()
        data_status = 'submitted'
        if has_country_access:
            if not records or all(not r.value and not r.disagg_data for r in records):
                saved_q = base_q.filter(~AssignmentEntityStatus.status.in_(['Submitted', 'Approved']))
                saved = saved_q.all()
                saved_with_data = [r for r in saved if r.value or r.disagg_data]
                if saved_with_data:
                    records = saved_with_data
                    data_status = 'saved'

        logger.debug(
            "get_form_field_value: country_id=%s, item_ids=%s, period (matrix key filter)=%r, assignment_period=%r, records_count=%s",
            country_id,
            item_ids,
            period,
            assignment_period,
            len(records),
        )

        total = 0
        breakdown = {}
        text_values: List[str] = []  # non-numeric question values (e.g. text answers)
        period_str = period or 'all'

        for r in records:
            # Parse disagg_data if stored as JSON string (e.g. from some imports)
            disagg = r.disagg_data
            if disagg is not None and isinstance(disagg, str):
                try:
                    disagg = json.loads(disagg) if disagg.strip() else None
                except Exception as exc:
                    logger.debug("disagg json.loads failed: %s", exc)
                    disagg = None

            if disagg and isinstance(disagg, dict):
                # Nested format: disagg_data.values
                vals = disagg.get('values')
                if isinstance(vals, dict):
                    if period:
                        vals = {k: v for k, v in vals.items() if period in str(k)}
                    for k, v in vals.items():
                        if isinstance(v, (int, float)):
                            breakdown[k] = breakdown.get(k, 0) + v
                            total += v
                else:
                    # Flat matrix format: {"2025_SP1": 75000, "2027_SP3": 2500000} or variable-column
                    # format: {"101_SP1": {"original": "...", "modified": "...", "isModified": bool}}
                    flat = disagg
                    if period:
                        flat = {k: v for k, v in flat.items() if period in str(k)}
                    for k, v in flat.items():
                        if k.startswith('_'):
                            continue
                        # Use effective value (modified if present, else original) for variable-column format
                        if isinstance(v, dict) and ('modified' in v or 'original' in v):
                            v = v.get('modified') if v.get('modified') is not None else v.get('original')
                        if v is not None:
                            try:
                                n = float(str(v).replace(',', ''))
                                breakdown[k] = breakdown.get(k, 0) + n
                                total += n
                            except (ValueError, TypeError):
                                pass
            elif r.value is not None:
                try:
                    v = float(r.value)
                    total += v
                    breakdown['value'] = breakdown.get('value', 0) + v
                except (TypeError, ValueError):
                    # Question with text or other non-numeric value: keep for display
                    text_val = str(r.value).strip()
                    if text_val and text_val not in text_values:
                        text_values.append(text_val)

        if records and breakdown:
            logger.debug(
                "get_form_field_value: total=%s, breakdown_keys=%s, sample=%s",
                total,
                list(breakdown.keys())[:15],
                dict(list(breakdown.items())[:5]),
            )

        # Resolve variables in labels (e.g. [entity_name] -> "Bangladesh") for display
        field_label_display = effective_label
        section_label_display = section_label
        if records:
            try:
                from app.services.variable_resolution_service import VariableResolutionService
                aes = records[0].assignment_entity_status
                assigned_form = getattr(aes, 'assigned_form', None) if aes else None
                form_template = getattr(assigned_form, 'template', None) if assigned_form else None
                template_version = getattr(form_template, 'published_version', None) if form_template else None
                if template_version and aes:
                    resolved_variables = VariableResolutionService.resolve_variables(
                        template_version, aes
                    )
                    if resolved_variables:
                        field_label_display = VariableResolutionService.replace_variables_in_text(
                            effective_label, resolved_variables
                        )
                        if section_label:
                            section_label_display = VariableResolutionService.replace_variables_in_text(
                                section_label, resolved_variables
                            )
                        logger.debug(
                            "get_form_field_value: resolved labels: field %r -> %r, section %r -> %r",
                            effective_label, field_label_display, section_label, section_label_display,
                        )
                else:
                    # Fallback: at least substitute entity_name from country we already have
                    resolved_variables = {
                        'entity_name': country_name,
                        'entity_id': country_id,
                        'entity_type': 'country',
                    }
                    field_label_display = VariableResolutionService.replace_variables_in_text(
                        effective_label, resolved_variables
                    )
                    if section_label:
                        section_label_display = VariableResolutionService.replace_variables_in_text(
                            section_label, resolved_variables
                        )
            except Exception as e:
                logger.warning("get_form_field_value: variable resolution failed, using raw labels: %s", e)

        notes = 'Sum of values from form submissions.'
        if data_status == 'saved':
            notes += ' Data is from saved/draft entries and has not been submitted.'

        out = {
            'success': True,
            'field_label': field_label_display,
            'section_label': section_label_display,
            'country': country_name,
            'period': period_str,
            'total': total,
            'breakdown': breakdown,
            'data_status': data_status,
            'notes': notes,
            'records_count': len(records),
            'debug': {
                'search_term': search_term,
                'item_ids': item_ids,
                'period_used_for_matrix_keys': period,
                'assignment_period_filter': assignment_period,
            },
        }
        if text_values:
            out['text_values'] = text_values
        return out
    except Exception as e:
        logger.exception("get_form_field_value failed: %s", e)
        return {
            'success': False,
            'error': 'An error occurred.',
            'field_label_or_name': field_label_or_name,
        }


