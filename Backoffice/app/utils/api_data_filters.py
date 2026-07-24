"""Shared filters and version scoping for /api/v1/data endpoints."""

from __future__ import annotations

import re
from datetime import datetime as _dt
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, or_
from sqlalchemy.orm import joinedload

from app import db
from app.models import AssignedForm, FormData, FormItem, FormTemplate
from app.services.data_retrieval_shared import escape_like_pattern
from app.services.reporting_period_service import sort_period_names
from app.utils.stable_key import normalize_stable_key, resolve_published_form_item_id

VERSION_SCOPE_PUBLISHED = 'published'
VERSION_SCOPE_ALL = 'all'


def parse_version_scope(args) -> str:
    """Return ``published`` (default) or ``all`` from query args."""
    raw = str(args.get('version_scope', VERSION_SCOPE_PUBLISHED) or VERSION_SCOPE_PUBLISHED).strip().lower()
    if raw in (VERSION_SCOPE_PUBLISHED, VERSION_SCOPE_ALL):
        return raw
    return VERSION_SCOPE_PUBLISHED


def resolve_template_published_version_id(template_id: Optional[int]) -> Optional[int]:
    """Return published_version_id for a template, or None."""
    if template_id is None:
        return None
    try:
        tmpl = db.session.get(FormTemplate, int(template_id))
        if tmpl and getattr(tmpl, 'published_version_id', None):
            return int(tmpl.published_version_id)
    except Exception:
        return None
    return None


def parse_data_item_filters(
    args,
    *,
    template_id: Optional[int],
    item_id: Optional[int],
) -> Tuple[Optional[int], Optional[str], str, Optional[Dict[str, Any]]]:
    """
    Parse ``stable_key`` / ``item_id`` / ``version_scope`` query parameters.

    Returns ``(item_id, normalized_stable_key, version_scope, error_or_none)``.
    ``error_or_none`` is ``{'message': str, 'status': int}`` when the request is invalid.
    """
    version_scope = parse_version_scope(args)
    stable_key_raw = (args.get('stable_key') or '').strip()
    normalized_stable_key = normalize_stable_key(stable_key_raw) if stable_key_raw else None

    if stable_key_raw and normalized_stable_key is None:
        return item_id, None, version_scope, {
            'message': 'Invalid stable_key format (expected UUID).',
            'status': 400,
        }

    if normalized_stable_key and template_id is None:
        return item_id, normalized_stable_key, version_scope, {
            'message': 'stable_key filter requires template_id.',
            'status': 400,
        }

    if normalized_stable_key and item_id is not None:
        item_id = None

    if normalized_stable_key and version_scope == VERSION_SCOPE_PUBLISHED:
        resolved = resolve_published_form_item_id(int(template_id), normalized_stable_key)
        if resolved is None:
            return -1, normalized_stable_key, version_scope, None
        return int(resolved), normalized_stable_key, version_scope, None

    return item_id, normalized_stable_key, version_scope, None


def apply_form_data_version_scoping(
    assigned_query,
    public_query,
    *,
    template_id: Optional[int],
    published_version_id: Optional[int],
    version_scope: str,
    stable_key: Optional[str] = None,
):
    """Apply published-version and/or stable_key filters to FormData queries."""
    if assigned_query is None and public_query is None:
        return assigned_query, public_query

    apply_published = (
        template_id is not None
        and published_version_id is not None
        and version_scope == VERSION_SCOPE_PUBLISHED
    )
    apply_stable_key = bool(
        stable_key and template_id is not None and version_scope == VERSION_SCOPE_ALL
    )

    def _filter(q):
        if q is None:
            return q
        if apply_published:
            q = q.filter(FormData.form_item.has(FormItem.version_id == int(published_version_id)))
        if apply_stable_key:
            q = q.filter(
                FormData.form_item.has(
                    FormItem.template_id == int(template_id),
                    FormItem.stable_key == stable_key,
                )
            )
        return q

    return _filter(assigned_query), _filter(public_query)


def _assigned_form_period_name_filter(period_name: str):
    """Match AssignedForm.period_name using the same rules as /data period filters."""
    period = (period_name or '').strip()
    if not period:
        return None
    _pat = f"%{escape_like_pattern(period)}%"
    period_filter = AssignedForm.period_name.ilike(_pat, escape="\\")
    years = [int(y) for y in re.findall(r"\b(19\d{2}|20\d{2}|21\d{2})\b", str(period))]
    if years:
        start_year = min(years)
        end_year = max(years)
        period_start = _dt(start_year, 1, 1).date()
        period_end = _dt(end_year, 12, 31).date()
        period_filter = or_(
            period_filter,
            and_(
                AssignedForm.period_start.isnot(None),
                AssignedForm.period_end.isnot(None),
                AssignedForm.period_start <= period_end,
                AssignedForm.period_end >= period_start,
            ),
        )
    return period_filter


def _resolve_scope_template_names(template_id: Optional[int]) -> List[str]:
    if template_id is None:
        return []
    tmpl = (
        FormTemplate.query
        .options(joinedload(FormTemplate.published_version))
        .filter(FormTemplate.id == int(template_id))
        .first()
    )
    if not tmpl:
        return []
    name = (tmpl.name or '').strip()
    return [name] if name else []


def _resolve_scope_period_names(
    *,
    template_id: Optional[int],
    assignment_id: Optional[int],
    period_name: Optional[str],
) -> List[str]:
    if assignment_id is not None:
        af = db.session.get(AssignedForm, int(assignment_id))
        if af and (af.period_name or '').strip():
            return [af.period_name.strip()]
        return []

    period_filter_str = (period_name or '').strip()
    if not period_filter_str:
        return []

    q = db.session.query(AssignedForm.period_name).distinct()
    if template_id is not None:
        q = q.filter(AssignedForm.template_id == int(template_id))
    period_filter = _assigned_form_period_name_filter(period_filter_str)
    if period_filter is not None:
        q = q.filter(period_filter)
    names = [
        (pn or '').strip()
        for (pn,) in q.all()
        if (pn or '').strip()
    ]
    return sort_period_names(names)


def build_data_api_scope_meta(
    *,
    template_id: Optional[int],
    published_version_id: Optional[int],
    version_scope: str,
    stable_key: Optional[str] = None,
    assignment_id: Optional[int] = None,
    period_name: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Build optional ``scope`` object for data API responses when template_id is set."""
    if template_id is None:
        return None
    meta: Dict[str, Any] = {
        'template_id': int(template_id),
        'published_version_id': published_version_id,
        'version_scope': version_scope,
    }
    if stable_key:
        meta['stable_key'] = stable_key

    template_names = _resolve_scope_template_names(template_id)
    if template_names:
        meta['template_names'] = template_names

    period_names = _resolve_scope_period_names(
        template_id=template_id,
        assignment_id=assignment_id,
        period_name=period_name,
    )
    if period_names:
        meta['period_names'] = period_names

    return meta
