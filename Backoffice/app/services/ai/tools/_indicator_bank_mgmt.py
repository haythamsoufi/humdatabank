"""
Indicator Bank management data helpers for AI tools.

Read-only queries for usage stats, catalog browsing, aggregate stats,
change history, and suggestion queue. Used by AIToolsRegistry management tools.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import (
    AssignmentEntityStatus,
    FormData,
    FormItem,
    FormTemplate,
    FormTemplateVersion,
    IndicatorBank,
    IndicatorBankHistory,
    IndicatorSuggestion,
    Sector,
)
from app.utils.sql_utils import safe_ilike_pattern

logger = logging.getLogger(__name__)


def resolve_indicator_by_name(identifier: str) -> Optional[IndicatorBank]:
    """Resolve an indicator by id or name (delegates to data retrieval layer)."""
    from app.services.data_retrieval.service import get_indicator_details

    ident = (identifier or "").strip()
    if not ident:
        return None
    if ident.isdigit():
        ind = db.session.get(IndicatorBank, int(ident))
        if ind:
            return ind
    details = get_indicator_details(ident)
    if not details or not details.get("id"):
        return None
    return db.session.get(IndicatorBank, int(details["id"]))


def get_indicator_usage_details(indicator_bank_id: int) -> Dict[str, Any]:
    """
    Form/template usage and reporting reach for one indicator.

    usage_count: FormItem rows referencing this indicator (matches admin list).
    template_count: distinct form templates that include it.
    templates: per-template breakdown with form_item_count.
    countries_with_data: distinct countries with FormData for those form items.
    dynamic_usage_count: DynamicIndicatorData rows (runtime-added indicators).
    """
    ind = db.session.get(IndicatorBank, indicator_bank_id)
    if not ind:
        return {}

    form_items = (
        FormItem.query.filter(
            FormItem.indicator_bank_id == indicator_bank_id,
            FormItem.item_type == "indicator",
            FormItem.archived == False,  # noqa: E712
        )
        .all()
    )
    usage_count = len(form_items)
    form_item_ids = [fi.id for fi in form_items]

    templates_map: Dict[int, Dict[str, Any]] = {}
    for fi in form_items:
        tid = fi.template_id
        if tid is None:
            continue
        if tid not in templates_map:
            template = fi.template or db.session.get(FormTemplate, tid)
            version = fi.version_id and db.session.get(FormTemplateVersion, fi.version_id)
            version_name = (getattr(version, "name", None) or "") if version else ""
            template_name = template.name if template else f"Template {tid}"
            templates_map[tid] = {
                "template_id": int(tid),
                "name": version_name or template_name,
                "version_id": int(fi.version_id) if fi.version_id else None,
                "form_item_count": 0,
            }
        templates_map[tid]["form_item_count"] += 1

    countries_with_data = 0
    if form_item_ids:
        countries_with_data = (
            db.session.query(func.count(func.distinct(AssignmentEntityStatus.entity_id)))
            .join(FormData, FormData.assignment_entity_status_id == AssignmentEntityStatus.id)
            .filter(
                FormData.form_item_id.in_(form_item_ids),
                AssignmentEntityStatus.entity_type == "country",
                or_(
                    FormData.value.isnot(None),
                    FormData.disagg_data.isnot(None),
                    FormData.prefilled_value.isnot(None),
                    FormData.imputed_value.isnot(None),
                ),
                or_(FormData.data_not_available == False, FormData.data_not_available.is_(None)),  # noqa: E712
                or_(FormData.not_applicable == False, FormData.not_applicable.is_(None)),  # noqa: E712
            )
            .scalar()
            or 0
        )

    try:
        from app.models.forms import DynamicIndicatorData

        dynamic_usage_count = (
            DynamicIndicatorData.query.filter(
                DynamicIndicatorData.indicator_bank_id == indicator_bank_id
            ).count()
        )
    except Exception as exc:
        logger.debug("dynamic_usage_count failed: %s", exc)
        dynamic_usage_count = 0

    return {
        "indicator_id": int(ind.id),
        "indicator": ind.name or "",
        "usage_count": usage_count,
        "template_count": len(templates_map),
        "templates": sorted(templates_map.values(), key=lambda t: str(t.get("name") or "")),
        "countries_with_data": int(countries_with_data),
        "dynamic_usage_count": int(dynamic_usage_count),
    }


def query_indicators_filtered(
    *,
    sector: Optional[str] = None,
    type_: Optional[str] = None,
    archived: Optional[bool] = False,
    has_no_usage: bool = False,
    has_no_definition: bool = False,
    search: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> Dict[str, Any]:
    """Browse indicator catalog with optional filters."""
    limit = max(1, min(int(limit or 20), 100))
    offset = max(0, int(offset or 0))

    usage_subq = (
        db.session.query(
            FormItem.indicator_bank_id.label("indicator_bank_id"),
            func.count(FormItem.id).label("usage_count"),
        )
        .filter(FormItem.indicator_bank_id.isnot(None))
        .group_by(FormItem.indicator_bank_id)
        .subquery()
    )

    q = (
        db.session.query(
            IndicatorBank,
            func.coalesce(usage_subq.c.usage_count, 0).label("usage_count"),
        )
        .outerjoin(usage_subq, IndicatorBank.id == usage_subq.c.indicator_bank_id)
        .options(
            joinedload(IndicatorBank.measurement_type),
            joinedload(IndicatorBank.measurement_unit),
        )
    )

    if archived is not None:
        q = q.filter(IndicatorBank.archived == bool(archived))

    if type_:
        q = q.filter(IndicatorBank.type == str(type_).strip().lower())

    if sector:
        sector_str = str(sector).strip()
        sector_row = Sector.query.filter(Sector.name.ilike(safe_ilike_pattern(sector_str))).first()
        if sector_row:
            q = q.filter(IndicatorBank.sector.contains(str(sector_row.id)))
        else:
            q = q.filter(IndicatorBank.sector.contains(sector_str))

    if search:
        pattern = safe_ilike_pattern(search)
        q = q.filter(
            or_(
                IndicatorBank.name.ilike(pattern),
                IndicatorBank.definition.ilike(pattern),
            )
        )

    if has_no_usage:
        q = q.filter(func.coalesce(usage_subq.c.usage_count, 0) == 0)

    if has_no_definition:
        q = q.filter(
            or_(
                IndicatorBank.definition.is_(None),
                func.trim(IndicatorBank.definition) == "",
            )
        )

    total_count = q.count()
    rows = (
        q.order_by(IndicatorBank.name)
        .offset(offset)
        .limit(limit)
        .all()
    )

    indicators: List[Dict[str, Any]] = []
    for ind, usage_count in rows:
        indicators.append(
            {
                "id": int(ind.id),
                "name": ind.name or "",
                "type": ind.type or "",
                "unit": ind.unit or "",
                "sector_names": ind.get_all_sector_names(),
                "usage_count": int(usage_count or 0),
                "has_definition": bool((ind.definition or "").strip()),
                "archived": bool(ind.archived),
            }
        )

    return {
        "indicators": indicators,
        "total_count": int(total_count),
        "limit": limit,
        "offset": offset,
    }


def get_indicator_bank_aggregate_stats() -> Dict[str, Any]:
    """High-level indicator bank health / catalog statistics."""
    usage_subq = (
        db.session.query(
            FormItem.indicator_bank_id.label("indicator_bank_id"),
            func.count(FormItem.id).label("usage_count"),
        )
        .filter(FormItem.indicator_bank_id.isnot(None))
        .group_by(FormItem.indicator_bank_id)
        .subquery()
    )

    total = IndicatorBank.query.count()
    archived = IndicatorBank.query.filter(IndicatorBank.archived == True).count()  # noqa: E712
    no_definition = (
        IndicatorBank.query.filter(
            or_(
                IndicatorBank.definition.is_(None),
                func.trim(IndicatorBank.definition) == "",
            ),
            IndicatorBank.archived == False,  # noqa: E712
        ).count()
    )

    zero_usage = (
        db.session.query(IndicatorBank)
        .outerjoin(usage_subq, IndicatorBank.id == usage_subq.c.indicator_bank_id)
        .filter(
            IndicatorBank.archived == False,  # noqa: E712
            func.coalesce(usage_subq.c.usage_count, 0) == 0,
        )
        .count()
    )

    by_type_rows = (
        db.session.query(IndicatorBank.type, func.count(IndicatorBank.id))
        .filter(IndicatorBank.archived == False)  # noqa: E712
        .group_by(IndicatorBank.type)
        .order_by(func.count(IndicatorBank.id).desc())
        .all()
    )
    by_type = {str(t or "unknown"): int(c) for t, c in by_type_rows}

    # Top sectors by primary sector id in JSONB
    sector_counts: Dict[int, int] = {}
    for ind in IndicatorBank.query.filter(IndicatorBank.archived == False).all():  # noqa: E712
        if not ind.sector or not isinstance(ind.sector, dict):
            continue
        primary = ind.sector.get("primary")
        if primary:
            sector_counts[int(primary)] = sector_counts.get(int(primary), 0) + 1

    sector_names: Dict[int, str] = {}
    if sector_counts:
        for s in Sector.query.filter(Sector.id.in_(list(sector_counts.keys()))).all():
            sector_names[s.id] = s.name

    top_sectors = sorted(
        [
            {"sector": sector_names.get(sid, f"Sector {sid}"), "count": cnt}
            for sid, cnt in sector_counts.items()
        ],
        key=lambda x: (-x["count"], x["sector"]),
    )[:10]

    recent = (
        IndicatorBank.query.filter(IndicatorBank.archived == False)  # noqa: E712
        .order_by(IndicatorBank.created_at.desc())
        .limit(5)
        .all()
    )
    recently_added = [
        {
            "id": int(r.id),
            "name": r.name or "",
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in recent
    ]

    pending_suggestions = (
        IndicatorSuggestion.query.filter(
            func.lower(IndicatorSuggestion.status) == "pending"
        ).count()
    )

    return {
        "total": int(total),
        "archived": int(archived),
        "active": int(total - archived),
        "no_definition": int(no_definition),
        "zero_usage": int(zero_usage),
        "by_type": by_type,
        "top_sectors_by_count": top_sectors,
        "recently_added": recently_added,
        "pending_suggestions": int(pending_suggestions),
    }


def get_indicator_change_history_rows(
    indicator_bank_id: int,
    *,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Audit trail rows for one indicator."""
    limit = max(1, min(int(limit or 10), 50))
    rows = (
        IndicatorBankHistory.query.filter(
            IndicatorBankHistory.indicator_bank_id == indicator_bank_id
        )
        .options(joinedload(IndicatorBankHistory.user))
        .order_by(IndicatorBankHistory.created_at.desc())
        .limit(limit)
        .all()
    )
    out: List[Dict[str, Any]] = []
    for row in rows:
        user = row.user
        changed_by = ""
        if user:
            changed_by = (getattr(user, "name", None) or getattr(user, "email", None) or "").strip()
        out.append(
            {
                "change_type": row.change_type or "",
                "change_description": row.change_description or "",
                "changed_by": changed_by or "Unknown",
                "changed_at": row.created_at.isoformat() if row.created_at else None,
            }
        )
    return out


def list_indicator_suggestion_rows(
    *,
    status: str = "pending",
    limit: int = 20,
    offset: int = 0,
) -> Dict[str, Any]:
    """Paginated suggestion queue for reviewers."""
    limit = max(1, min(int(limit or 20), 100))
    offset = max(0, int(offset or 0))
    status_norm = (status or "pending").strip().lower()

    q = IndicatorSuggestion.query
    if status_norm and status_norm != "all":
        q = q.filter(func.lower(IndicatorSuggestion.status) == status_norm)

    total = q.count()
    rows = (
        q.order_by(IndicatorSuggestion.submitted_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    suggestions: List[Dict[str, Any]] = []
    for s in rows:
        reason = (s.reason or "").strip()
        if len(reason) > 300:
            reason = reason[:300] + "…"
        suggestions.append(
            {
                "id": int(s.id),
                "indicator_name": s.indicator_name or "",
                "suggestion_type": s.suggestion_type or "",
                "status": s.status or "",
                "submitter_name": s.submitter_name or "",
                "submitter_email": s.submitter_email or "",
                "submitted_at": s.submitted_at.isoformat() if s.submitted_at else None,
                "reason": reason,
                "indicator_id": int(s.indicator_id) if s.indicator_id else None,
            }
        )

    return {
        "suggestions": suggestions,
        "total_count": int(total),
        "status_filter": status_norm,
        "limit": limit,
        "offset": offset,
    }
