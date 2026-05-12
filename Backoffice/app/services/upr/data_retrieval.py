"""
upr.data_retrieval
──────────────────
SQL queries against ``AIDocumentChunk.extra_metadata["upr"]`` for structured
KPI values extracted from Unified Planning and Reporting documents.

Functions
---------
get_upr_kpi_value              – single country, best-match KPI
get_upr_kpi_timeseries         – single country, year-over-year series
get_upr_kpi_values_for_all_countries – all accessible countries, one metric
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Union

from flask_login import current_user
from sqlalchemy import desc, literal, text

from app.extensions import db
from app.models import AIDocument, AIDocumentChunk, Country
from app.utils.api_helpers import service_error, GENERIC_ERROR_MESSAGE
from app.utils.sql_utils import safe_ilike_pattern

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared helpers (imported from sibling modules)
# ---------------------------------------------------------------------------

def _effective_user_role_and_id() -> Dict[str, Any]:
    """Best-effort resolve user context for AI requests."""
    user_role = None
    user_id = None
    try:
        from app.services.authorization_service import AuthorizationService
        if getattr(current_user, "is_authenticated", False):
            user_role = AuthorizationService.access_level(current_user)
            user_id = int(getattr(current_user, "id", 0) or 0) or None
    except Exception as e:
        logger.debug("_effective_user_role_and_id: auth resolution failed: %s", e)
    try:
        from flask import g, has_request_context
        if has_request_context():
            if user_id is None:
                try:
                    user_id = int(getattr(g, "ai_user_id", None) or 0) or None
                except Exception:
                    user_id = None
            if user_role is None:
                user_role = getattr(g, "ai_user_access_level", None) or getattr(g, "ai_user_role", None) or user_role
    except Exception:
        pass
    if not user_role:
        user_role = "public"
    return {"user_role": user_role, "user_id": user_id}


def _dialect_name() -> str:
    try:
        return (getattr(db, "engine", None) and db.engine.dialect.name) or ""
    except Exception:
        return ""


def _user_allowed_country_ids():
    from app.services.data_retrieval_shared import user_allowed_country_ids
    return user_allowed_country_ids()


# ---------------------------------------------------------------------------
# Metric normalisation (shared across all three functions)
# ---------------------------------------------------------------------------

_METRIC_NORM = {
    "branch": "branches", "branches": "branches",
    "localunit": "local_units", "local_unit": "local_units",
    "local_units": "local_units", "local units": "local_units",
    "volunteer": "volunteers", "volunteers": "volunteers",
    "staff": "staff",
}
_VALID_METRICS = {"branches", "local_units", "volunteers", "staff"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_upr_kpi_value(
    *,
    country_identifier: Union[int, str],
    metric: str,
    prefer_year: Optional[int] = None,
) -> Dict[str, Any]:
    """Retrieve KPI values from UPR visual blocks in AI document chunk metadata."""
    try:
        m_raw = (metric or "").strip().lower()
        metric_norm = _METRIC_NORM.get(m_raw, m_raw)
        if metric_norm not in _VALID_METRICS:
            return service_error(f"Unsupported metric: {metric}", metric=metric)

        from app.services.data_retrieval_country import resolve_country
        country = resolve_country(country_identifier)
        if not country or not getattr(country, "id", None):
            return service_error(f"Country not found: {country_identifier}")

        ns_name = None
        try:
            ns = country.primary_national_society
            ns_name = (getattr(ns, "name", None) or "").strip() or None
        except Exception as e:
            logger.debug("get_upr_kpi_value: ns_name resolution failed for country %s: %s", country_identifier, e)
            ns_name = None

        ctx = _effective_user_role_and_id()
        user_role = ctx["user_role"]
        user_id = ctx["user_id"]

        dialect = _dialect_name().lower()

        q = (
            db.session.query(AIDocumentChunk, AIDocument)
            .join(AIDocument, AIDocumentChunk.document_id == AIDocument.id)
            .filter(
                AIDocument.searchable == True,  # noqa: E712
                AIDocument.processing_status == "completed",
                AIDocumentChunk.extra_metadata.isnot(None),
            )
        )

        if user_role not in ["admin", "system_manager"]:
            if user_id:
                q = q.filter(db.or_(AIDocument.is_public == True, AIDocument.user_id == user_id))  # noqa: E712
            else:
                q = q.filter(AIDocument.is_public == True)  # noqa: E712

            if dialect == "postgresql":
                role = (user_role or "public").strip().lower()
                role_json = json.dumps([role])
                q = q.filter(
                    db.or_(
                        AIDocument.is_public == True,  # noqa: E712
                        AIDocument.allowed_roles.is_(None),
                        text("(ai_documents.allowed_roles::jsonb @> CAST(:role_json AS jsonb))").bindparams(role_json=role_json),
                    )
                )

        if dialect == "postgresql":
            q = q.filter(
                AIDocumentChunk.extra_metadata["upr"].isnot(None),
                AIDocumentChunk.extra_metadata["upr"]["block"].as_string() == "in_support_kpis",
            )
            q = q.filter(
                db.or_(
                    AIDocument.country_id == int(country.id),
                    AIDocument.country_name.ilike(safe_ilike_pattern(country.name)),
                    AIDocumentChunk.extra_metadata["upr"]["society"].as_string().ilike(safe_ilike_pattern(ns_name)) if ns_name else literal(False),
                    AIDocumentChunk.extra_metadata["upr"]["society"].as_string().ilike(safe_ilike_pattern(country.name)),
                )
            )
        else:
            q = q.filter(
                db.or_(
                    AIDocument.country_id == int(country.id),
                    AIDocument.country_name.ilike(safe_ilike_pattern(country.name)),
                )
            )

        q = q.order_by(
            desc(AIDocument.processed_at),
            desc(AIDocument.created_at),
            AIDocumentChunk.page_number.asc().nullslast(),
        ).limit(200)
        rows = q.all()

        best = None
        best_key = None
        role_lc = (user_role or "public").strip().lower()
        for chunk, doc in rows:
            md = chunk.extra_metadata or {}
            upr = md.get("upr") if isinstance(md, dict) else None
            if not isinstance(upr, dict):
                continue
            if upr.get("block") != "in_support_kpis":
                continue

            if dialect != "postgresql" and user_role not in ["admin", "system_manager"]:
                if not getattr(doc, "is_public", False):
                    allowed_roles = getattr(doc, "allowed_roles", None)
                    if allowed_roles is not None:
                        try:
                            if role_lc not in [str(r).strip().lower() for r in (allowed_roles or [])]:
                                continue
                        except Exception:
                            continue

            kpis = upr.get("kpis") if isinstance(upr.get("kpis"), dict) else {}
            val = (kpis or {}).get(metric_norm)
            if val is None or str(val).strip() == "":
                continue
            conf = upr.get("confidence")
            try:
                conf_f = float(conf) if conf is not None else None
            except Exception:
                conf_f = None

            extraction = (upr.get("extraction") or "").strip() or None
            meta = _parse_upr_extraction_meta(extraction)
            yr = meta.get("year")
            year_match = bool(prefer_year and yr and int(yr) == int(prefer_year))
            try:
                processed_ts = getattr(doc, "processed_at", None) or getattr(doc, "created_at", None)
                processed_ord = processed_ts.timestamp() if processed_ts else 0.0
            except Exception:
                processed_ord = 0.0
            key = (
                1 if year_match else 0,
                float(conf_f) if conf_f is not None else -1.0,
                float(processed_ord),
            )
            candidate = {
                "value": str(val).strip(),
                "confidence": conf_f,
                "upr_society": (upr.get("society") or "").strip() or None,
                "extraction": extraction,
                "year": yr,
                "report_type": meta.get("report_type"),
                "chunk_id": int(chunk.id),
                "document_id": int(doc.id),
                "document_title": doc.title,
                "document_filename": doc.filename,
                "page_number": chunk.page_number,
                "document_url": f"/api/ai/documents/{int(doc.id)}/download",
            }
            if best is None or (best_key is not None and key > best_key) or best_key is None:
                best = candidate
                best_key = key

        if not best:
            return {
                "success": True,
                "country": {"id": int(country.id), "name": country.name, "iso3": getattr(country, "iso3", None)},
                "metric": metric_norm,
                "value": None,
                "notes": "No UPR KPI metadata found for this country/metric in accessible documents.",
                "records_count": 0,
            }
        return {
            "success": True,
            "country": {"id": int(country.id), "name": country.name, "iso3": getattr(country, "iso3", None)},
            "metric": metric_norm,
            "value": best["value"],
            "records_count": 1,
            "source": {
                "document_id": best["document_id"],
                "document_title": best["document_title"],
                "document_filename": best["document_filename"],
                "document_url": best["document_url"],
                "page_number": best["page_number"],
                "chunk_id": best["chunk_id"],
                "society": best["upr_society"],
                "extraction": best["extraction"],
                "year": best.get("year"),
                "report_type": best.get("report_type"),
                "confidence": best["confidence"],
            },
            "notes": None,
        }
    except Exception as e:
        logger.error("get_upr_kpi_value error: %s", e, exc_info=True)
        return service_error(f"Could not retrieve UPR KPI value: {e}")


def get_upr_kpi_timeseries(
    *,
    country_identifier: Union[int, str],
    metric: str,
) -> Dict[str, Any]:
    """Retrieve UPR KPI values as a time series across multiple documents for one country."""
    try:
        m_raw = (metric or "").strip().lower()
        metric_norm = _METRIC_NORM.get(m_raw, m_raw)
        if metric_norm not in _VALID_METRICS:
            return service_error(f"Unsupported metric: {metric}", series=[])

        metric_labels = {
            "branches": "Number of branches",
            "local_units": "Number of local units",
            "volunteers": "Number of volunteers",
            "staff": "Number of staff",
        }

        from app.services.data_retrieval_country import resolve_country
        country = resolve_country(country_identifier)
        if not country or not getattr(country, "id", None):
            return service_error(f"Country not found: {country_identifier}", series=[])

        ns_name = None
        try:
            ns = country.primary_national_society
            ns_name = (getattr(ns, "name", None) or "").strip() or None
        except Exception as e:
            logger.debug("get_upr_kpi_timeseries: ns_name resolution failed for country %s: %s", country_identifier, e)
            ns_name = None

        ctx = _effective_user_role_and_id()
        user_role = ctx["user_role"]
        user_id = ctx["user_id"]
        dialect = _dialect_name().lower()

        q = (
            db.session.query(AIDocumentChunk, AIDocument)
            .join(AIDocument, AIDocumentChunk.document_id == AIDocument.id)
            .filter(
                AIDocument.searchable == True,  # noqa: E712
                AIDocument.processing_status == "completed",
                AIDocumentChunk.extra_metadata.isnot(None),
            )
        )

        if user_role not in ["admin", "system_manager"]:
            if user_id:
                q = q.filter(db.or_(AIDocument.is_public == True, AIDocument.user_id == user_id))  # noqa: E712
            else:
                q = q.filter(AIDocument.is_public == True)  # noqa: E712
            if dialect == "postgresql":
                role = (user_role or "public").strip().lower()
                role_json = json.dumps([role])
                q = q.filter(
                    db.or_(
                        AIDocument.is_public == True,  # noqa: E712
                        AIDocument.allowed_roles.is_(None),
                        text("(ai_documents.allowed_roles::jsonb @> CAST(:role_json AS jsonb))").bindparams(role_json=role_json),
                    )
                )

        if dialect == "postgresql":
            q = q.filter(
                AIDocumentChunk.extra_metadata["upr"].isnot(None),
                AIDocumentChunk.extra_metadata["upr"]["block"].as_string() == "in_support_kpis",
            )
            q = q.filter(
                db.or_(
                    AIDocument.country_id == int(country.id),
                    AIDocument.country_name.ilike(safe_ilike_pattern(country.name)),
                    AIDocumentChunk.extra_metadata["upr"]["society"].as_string().ilike(safe_ilike_pattern(ns_name)) if ns_name else literal(False),
                    AIDocumentChunk.extra_metadata["upr"]["society"].as_string().ilike(safe_ilike_pattern(country.name)),
                )
            )
        else:
            q = q.filter(
                db.or_(
                    AIDocument.country_id == int(country.id),
                    AIDocument.country_name.ilike(safe_ilike_pattern(country.name)),
                )
            )

        q = q.order_by(
            desc(AIDocument.processed_at),
            desc(AIDocument.created_at),
        ).limit(500)
        rows = q.all()

        _doc_type_priority = {"annual_report": 3, "annual report": 3,
                              "midyear_report": 2, "mid-year report": 2, "midyear report": 2,
                              "plan": 1}

        year_points: Dict[int, Dict[str, Any]] = {}
        role_lc = (user_role or "public").strip().lower()

        for chunk, doc in rows:
            md = chunk.extra_metadata or {}
            upr = md.get("upr") if isinstance(md, dict) else None
            if not isinstance(upr, dict):
                continue
            if upr.get("block") != "in_support_kpis":
                continue

            if dialect != "postgresql" and user_role not in ["admin", "system_manager"]:
                if not getattr(doc, "is_public", False):
                    allowed_roles = getattr(doc, "allowed_roles", None)
                    if allowed_roles is not None:
                        try:
                            if role_lc not in [str(r).strip().lower() for r in (allowed_roles or [])]:
                                continue
                        except Exception:
                            continue

            kpis = upr.get("kpis") if isinstance(upr.get("kpis"), dict) else {}
            val_raw = (kpis or {}).get(metric_norm)
            if val_raw is None or str(val_raw).strip() == "":
                continue

            try:
                val_str = str(val_raw).strip().replace(",", "").replace("\u00a0", "").replace(" ", "")
                value = float(val_str)
            except (ValueError, TypeError):
                continue

            year = None
            fname_years = re.findall(r'\b(19\d{2}|20\d{2})\b', doc.filename or "")
            if fname_years:
                year = max(int(y) for y in fname_years)

            if not year:
                upr_ctx = upr.get("upr_context") if isinstance(upr.get("upr_context"), dict) else {}
                if upr_ctx.get("year"):
                    try:
                        year = int(upr_ctx["year"])
                    except (ValueError, TypeError):
                        pass

            if not year:
                extraction = (upr.get("extraction") or "").strip()
                m_yr = re.search(r'year\s*=\s*(\d{4})', extraction, re.IGNORECASE)
                if m_yr:
                    year = int(m_yr.group(1))

            if not year:
                try:
                    ts = getattr(doc, "processed_at", None) or getattr(doc, "created_at", None)
                    if ts:
                        year = ts.year
                except Exception:
                    pass

            if not year or year < 1900 or year > 2100:
                continue

            conf_f = 0.0
            try:
                if upr.get("confidence") is not None:
                    conf_f = float(upr["confidence"])
            except Exception:
                pass

            doc_type_str = ""
            upr_ctx = upr.get("upr_context") if isinstance(upr.get("upr_context"), dict) else {}
            doc_type_str = str(upr_ctx.get("doc_type") or "").strip().lower()
            if not doc_type_str:
                fname_lc = (doc.filename or "").lower()
                if "_ar_" in fname_lc or "annual" in fname_lc:
                    doc_type_str = "annual_report"
                elif "_myr_" in fname_lc or "mid" in fname_lc:
                    doc_type_str = "midyear_report"
                else:
                    doc_type_str = "plan"

            try:
                processed_ts = getattr(doc, "processed_at", None) or getattr(doc, "created_at", None)
                processed_ord = processed_ts.timestamp() if processed_ts else 0.0
            except Exception:
                processed_ord = 0.0

            rank_key = (_doc_type_priority.get(doc_type_str, 0), conf_f, processed_ord)

            existing = year_points.get(year)
            if existing is None or rank_key > existing["_rank"]:
                year_points[year] = {
                    "year": year,
                    "value": value,
                    "data_status": "document",
                    "period_name": str(year),
                    "source_document": doc.title or doc.filename,
                    "document_id": int(doc.id),
                    "_rank": rank_key,
                }

        series = []
        for yr in sorted(year_points.keys()):
            pt = year_points[yr]
            series.append({
                "year": pt["year"],
                "value": pt["value"],
                "data_status": pt["data_status"],
                "period_name": pt["period_name"],
            })

        return {
            "success": True,
            "country_id": int(country.id),
            "country_name": country.name,
            "iso3": getattr(country, "iso3", None),
            "indicator": {
                "name": metric_labels.get(metric_norm, metric_norm),
                "unit": metric_norm.replace("_", " ").title(),
            },
            "series": series,
            "count": len(series),
            "aggregation": "best_per_document_year",
            "source_type": "upr_documents",
        }
    except Exception as e:
        logger.error("get_upr_kpi_timeseries error: %s", e, exc_info=True)
        return service_error(f"Could not retrieve UPR KPI time series: {e}", series=[])


def get_upr_kpi_values_for_all_countries(metric: str) -> Dict[str, Any]:
    """Retrieve UPR KPI values for all user-accessible countries."""
    try:
        m_raw = (metric or "").strip().lower()
        metric_norm = _METRIC_NORM.get(m_raw, m_raw)
        if metric_norm not in _VALID_METRICS:
            return service_error(f"Unsupported metric: {metric}", rows=[], count=0)

        ctx = _effective_user_role_and_id()
        user_role = ctx["user_role"]
        user_id = ctx["user_id"]
        dialect = _dialect_name().lower()

        allowed_country_ids = _user_allowed_country_ids()

        q = (
            db.session.query(AIDocumentChunk, AIDocument)
            .join(AIDocument, AIDocumentChunk.document_id == AIDocument.id)
            .filter(
                AIDocument.searchable == True,  # noqa: E712
                AIDocument.processing_status == "completed",
                AIDocumentChunk.extra_metadata.isnot(None),
            )
        )
        if allowed_country_ids is not None:
            q = q.filter(
                db.or_(
                    AIDocument.is_public == True,  # noqa: E712
                    AIDocument.country_id.in_(allowed_country_ids),
                )
            )
        if user_role not in ["admin", "system_manager"]:
            if user_id:
                q = q.filter(db.or_(AIDocument.is_public == True, AIDocument.user_id == user_id))  # noqa: E712
            else:
                q = q.filter(AIDocument.is_public == True)  # noqa: E712
            if dialect == "postgresql":
                role = (user_role or "public").strip().lower()
                role_json = json.dumps([role])
                q = q.filter(
                    db.or_(
                        AIDocument.is_public == True,  # noqa: E712
                        AIDocument.allowed_roles.is_(None),
                        text("(ai_documents.allowed_roles::jsonb @> CAST(:role_json AS jsonb))").bindparams(role_json=role_json),
                    )
                )
        if dialect == "postgresql":
            q = q.filter(
                AIDocumentChunk.extra_metadata["upr"].isnot(None),
                AIDocumentChunk.extra_metadata["upr"]["block"].as_string() == "in_support_kpis",
            )
        q = q.order_by(desc(AIDocument.processed_at), desc(AIDocument.created_at), AIDocumentChunk.page_number.asc().nullslast())

        batch_size = 2000
        max_batches = 5
        rows: List[Any] = []
        for i in range(max_batches):
            batch = q.limit(batch_size).offset(i * batch_size).all()
            if not batch:
                break
            rows.extend(batch)
            if len(batch) < batch_size:
                break

        by_country: Dict[int, Dict[str, Any]] = {}
        role_lc = (user_role or "public").strip().lower()
        for chunk, doc in rows:
            country_id = getattr(doc, "country_id", None)
            if country_id is None:
                continue
            if (
                allowed_country_ids is not None
                and int(country_id) not in allowed_country_ids
                and not getattr(doc, "is_public", False)
            ):
                continue
            md = chunk.extra_metadata or {}
            upr = md.get("upr") if isinstance(md, dict) else None
            if not isinstance(upr, dict):
                continue
            if upr.get("block") != "in_support_kpis":
                continue

            if dialect != "postgresql" and user_role not in ["admin", "system_manager"]:
                if not getattr(doc, "is_public", False):
                    allowed_roles = getattr(doc, "allowed_roles", None)
                    if allowed_roles is not None:
                        try:
                            if role_lc not in [str(r).strip().lower() for r in (allowed_roles or [])]:
                                continue
                        except Exception:
                            continue

            kpis = upr.get("kpis") if isinstance(upr.get("kpis"), dict) else {}
            val = (kpis or {}).get(metric_norm)
            if val is None or str(val).strip() == "":
                continue
            conf = upr.get("confidence")
            try:
                conf_f = float(conf) if conf is not None else None
            except Exception:
                conf_f = None
            try:
                processed_ts = getattr(doc, "processed_at", None) or getattr(doc, "created_at", None)
                processed_ord = processed_ts.timestamp() if processed_ts else 0.0
            except Exception:
                processed_ord = 0.0
            candidate = {
                "value": str(val).strip(),
                "confidence": conf_f,
                "processed_ord": float(processed_ord),
                "document_id": int(doc.id),
                "document_title": getattr(doc, "title", None),
                "page_number": chunk.page_number,
            }
            existing = by_country.get(int(country_id))
            if existing is None:
                by_country[int(country_id)] = candidate
            else:
                ex_conf = existing.get("confidence")
                ex_ts = float(existing.get("processed_ord") or 0.0)
                new_conf = conf_f if conf_f is not None else -1.0
                old_conf = ex_conf if ex_conf is not None else -1.0
                if (new_conf, candidate["processed_ord"]) > (old_conf, ex_ts):
                    by_country[int(country_id)] = candidate

        country_ids = list(by_country.keys())
        if not country_ids:
            return {"success": True, "metric": metric_norm, "rows": [], "count": 0}
        countries = {c.id: c for c in Country.query.filter(Country.id.in_(country_ids)).all()}
        out_rows = []
        for cid in sorted(country_ids):
            c = countries.get(cid)
            name = c.name if c else str(cid)
            iso3 = getattr(c, "iso3", None) or ""
            rec = by_country[cid]
            doc_id = rec["document_id"]
            out_rows.append({
                "country_id": cid,
                "country_name": name,
                "iso3": iso3,
                "region": getattr(c, "region", None) or "",
                "value": rec["value"],
                "source": {
                    "document_id": doc_id,
                    "document_title": rec["document_title"],
                    "page_number": rec["page_number"],
                    "document_url": f"/api/ai/documents/{doc_id}/download",
                },
            })
        return {"success": True, "metric": metric_norm, "rows": out_rows, "count": len(out_rows)}
    except Exception as e:
        logger.error("get_upr_kpi_values_for_all_countries error: %s", e, exc_info=True)
        return service_error(GENERIC_ERROR_MESSAGE, rows=[], count=0)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_upr_extraction_meta(extraction: Optional[str]) -> Dict[str, Any]:
    """Parse strings like ``'pe=midyear_report; year=2024 - ...'`` into
    ``{year: int|None, report_type: str|None}``.
    """
    out: Dict[str, Any] = {"year": None, "report_type": None}
    s = (extraction or "").strip()
    if not s:
        return out
    s_low = s.lower()
    if ("year=" not in s_low) and ("pe=" not in s_low) and ("ype=" not in s_low):
        return out
    try:
        left, _, _right = s.replace("\r", " ").replace("\n", " ").partition("-")
        meta: Dict[str, str] = {}
        for part in re.split(r"[;,\|]\s*", left):
            if "=" in part:
                k, v = part.split("=", 1)
                meta[k.strip().lower()] = v.strip()
        year = meta.get("year")
        if year and str(year).strip().isdigit():
            out["year"] = int(str(year).strip())
        rtype = meta.get("ype") or meta.get("pe") or meta.get("type")
        if rtype:
            rt = str(rtype).strip().replace("_", " ").strip().lower()
            if rt in ("midyear report", "mid year report"):
                out["report_type"] = "Mid-year Report"
            elif rt == "annual report":
                out["report_type"] = "Annual Report"
            else:
                out["report_type"] = " ".join(w.capitalize() for w in rt.split())
    except Exception as e:
        logger.debug("_parse_upr_extraction_meta failed: %s", e)
        return out
    return out
