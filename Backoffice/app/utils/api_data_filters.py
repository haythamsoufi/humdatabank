"""Shared filters and version scoping for /api/v1/data endpoints."""

from __future__ import annotations

import re
from datetime import datetime as _dt
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, or_
from sqlalchemy.orm import joinedload

from app import db
from app.models import AssignedForm, FormData, FormItem, FormTemplate
from app.services.data_retrieval.shared import escape_like_pattern
from app.services.forms.reporting_period_service import sort_period_names
from app.utils.stable_key import normalize_stable_key, resolve_published_form_item_id

VERSION_SCOPE_PUBLISHED = 'published'
VERSION_SCOPE_ALL = 'all'


def parse_assignment_id_filters(args) -> Optional[List[int]]:
    """
    Parse ``assignment_id`` / ``assigned_form_id`` query parameters.

    Supports a single id, comma-separated lists (``123,456``), and repeated
    query params (``assignment_id=123&assignment_id=456``).
    """
    tokens: List[str] = []
    for key in ('assignment_id', 'assigned_form_id'):
        values: List[Any] = []
        getlist = getattr(args, 'getlist', None)
        if callable(getlist):
            values = list(getlist(key) or [])
        if not values:
            raw = args.get(key)
            if raw is None:
                continue
            if isinstance(raw, (list, tuple)):
                values = list(raw)
            else:
                values = [raw]
        for value in values:
            part = str(value or '').strip()
            if not part:
                continue
            tokens.extend(p.strip() for p in part.split(',') if p.strip())

    if not tokens:
        return None

    ids: List[int] = []
    seen = set()
    for token in tokens:
        if not token.lstrip('-').isdigit():
            continue
        val = int(token)
        if val <= 0 or val in seen:
            continue
        seen.add(val)
        ids.append(val)
    return ids or None


def _assignment_template_conflict_message(rows) -> str:
    """Human-readable detail when assignment scope does not match ``template_id``."""
    parts = []
    for row in rows or []:
        if not row or row.id is None:
            continue
        template_name = None
        template = getattr(row, 'template', None)
        if template and getattr(template, 'name', None):
            template_name = str(template.name).strip()
        tid = getattr(row, 'template_id', None)
        if template_name and tid is not None:
            parts.append(f'{int(row.id)} → template {int(tid)} ({template_name})')
        elif tid is not None:
            parts.append(f'{int(row.id)} → template {int(tid)}')
        else:
            parts.append(str(int(row.id)))
    detail = '; '.join(parts)
    if detail:
        return f'assignment_id does not match template_id ({detail})'
    return 'assignment_id does not match template_id'


def resolve_assignment_scope(
    assignment_ids: Optional[List[int]],
    *,
    template_id: Optional[int] = None,
) -> Tuple[Optional[int], List[int], Optional[Dict[str, Any]]]:
    """
    Validate assignment scope and resolve template ids.

    Returns ``(template_id, template_ids, error_or_none)``.

    ``template_id`` is set when exactly one template is in scope (backward
    compatible single-template callers). When multiple templates are requested,
    ``template_id`` is ``None`` and ``template_ids`` lists them all.
    """
    if not assignment_ids:
        scoped = [int(template_id)] if template_id is not None else []
        single = scoped[0] if len(scoped) == 1 else None
        return single, scoped, None

    rows = (
        AssignedForm.query
        .options(joinedload(AssignedForm.template))
        .filter(AssignedForm.id.in_([int(x) for x in assignment_ids]))
        .all()
    )
    found = {int(row.id) for row in rows if row and row.id is not None}
    missing = [int(x) for x in assignment_ids if int(x) not in found]
    if missing:
        label = missing[0] if len(missing) == 1 else ', '.join(str(x) for x in missing)
        return None, [], {
            'message': (
                f'Assignment not found: {label}. assignment_id expects an AssignedForm id. '
                'If this id came from assignment_statuses[] or a workflow/status view, it is '
                'likely an AssignmentEntityStatus id instead — pass it as submission_id.'
            ),
            'status': 404,
        }

    template_ids = sorted({
        int(row.template_id)
        for row in rows
        if row and row.template_id is not None
    })

    if template_id is not None:
        expected = int(template_id)
        mismatched = [
            row for row in rows
            if row and row.template_id is not None and int(row.template_id) != expected
        ]
        if mismatched:
            return None, template_ids, {
                'message': _assignment_template_conflict_message(mismatched),
                'status': 400,
            }
        return expected, template_ids or [expected], None

    if len(template_ids) == 1:
        return template_ids[0], template_ids, None
    return None, template_ids, None


def resolve_assignment_entity_status_fallback(
    assignment_ids: Optional[List[int]],
) -> Optional[Tuple[int, Optional[int]]]:
    """
    Check whether a single, otherwise-unresolved ``assignment_id`` is actually an
    ``AssignmentEntityStatus`` id (a common mix-up: assignment_statuses[] / workflow
    and status views are keyed by AssignmentEntityStatus.id, not AssignedForm.id —
    e.g. a request like ``assignment_id=1610`` where 1610 is really a submission_id).

    Only handles the unambiguous single-id case; multi-id requests where one or more
    ids fail to resolve as AssignedForm keep the normal 404 (mixing AssignedForm and
    AssignmentEntityStatus ids in one call is inherently ambiguous to auto-resolve).

    Returns ``(submission_id, template_id)`` on a match — callers should then treat
    the request as if ``submission_id`` had been passed instead of ``assignment_id``
    — or ``None`` when there is no match (caller should fall back to the normal
    "not found" error).
    """
    if not assignment_ids or len(assignment_ids) != 1:
        return None
    from app.models.assignments import AssignmentEntityStatus

    aes = (
        AssignmentEntityStatus.query
        .options(joinedload(AssignmentEntityStatus.assigned_form))
        .filter(AssignmentEntityStatus.id == int(assignment_ids[0]))
        .first()
    )
    if not aes:
        return None
    template_id = (
        int(aes.assigned_form.template_id)
        if aes.assigned_form and aes.assigned_form.template_id is not None
        else None
    )
    return int(aes.id), template_id


def resolve_template_id_from_assignment_ids(
    assignment_ids: Optional[List[int]],
    *,
    template_id: Optional[int] = None,
) -> Tuple[Optional[int], Optional[Dict[str, Any]]]:
    """Backward-compatible wrapper around :func:`resolve_assignment_scope`."""
    resolved_template_id, _template_ids, error = resolve_assignment_scope(
        assignment_ids,
        template_id=template_id,
    )
    return resolved_template_id, error


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
    template_ids: Optional[List[int]] = None,
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
    scoped_template_ids = list(template_ids or [])
    if template_id is not None and int(template_id) not in scoped_template_ids:
        scoped_template_ids.append(int(template_id))

    if stable_key_raw and normalized_stable_key is None:
        return item_id, None, version_scope, {
            'message': 'Invalid stable_key format (expected UUID).',
            'status': 400,
        }

    if normalized_stable_key and len(scoped_template_ids) > 1:
        return item_id, normalized_stable_key, version_scope, {
            'message': (
                'stable_key filter requires a single template. '
                'Pass template_id or use assignments from one template only.'
            ),
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
    template_ids: Optional[List[int]] = None,
):
    """Apply published-version and/or stable_key filters to FormData queries."""
    if assigned_query is None and public_query is None:
        return assigned_query, public_query

    multi_template = bool(template_ids and len(template_ids) > 1)
    apply_published_single = (
        not multi_template
        and template_id is not None
        and published_version_id is not None
        and version_scope == VERSION_SCOPE_PUBLISHED
    )
    apply_published_multi = (
        multi_template
        and version_scope == VERSION_SCOPE_PUBLISHED
    )
    apply_stable_key = bool(
        stable_key and template_id is not None and version_scope == VERSION_SCOPE_ALL
    )

    def _filter(q):
        if q is None:
            return q
        if apply_published_single:
            q = q.filter(FormData.form_item.has(FormItem.version_id == int(published_version_id)))
        elif apply_published_multi:
            q = (
                q.join(FormItem, FormData.form_item_id == FormItem.id)
                .join(FormTemplate, FormItem.template_id == FormTemplate.id)
                .filter(
                    FormTemplate.published_version_id.isnot(None),
                    FormItem.version_id == FormTemplate.published_version_id,
                )
            )
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


def _resolve_scope_template_names_for_ids(template_ids: Optional[List[int]]) -> List[str]:
    ids = [int(x) for x in (template_ids or []) if x is not None]
    if not ids:
        return []
    rows = (
        FormTemplate.query
        .filter(FormTemplate.id.in_(ids))
        .all()
    )
    by_id = {
        int(row.id): (row.name or '').strip()
        for row in rows
        if row and row.id is not None and (row.name or '').strip()
    }
    return [by_id[tid] for tid in sorted(ids) if tid in by_id]


def _resolve_scope_period_names(
    *,
    template_id: Optional[int],
    assignment_ids: Optional[List[int]] = None,
    period_name: Optional[str] = None,
) -> List[str]:
    if assignment_ids:
        rows = (
            db.session.query(AssignedForm.period_name)
            .filter(AssignedForm.id.in_([int(x) for x in assignment_ids]))
            .distinct()
            .all()
        )
        names = [
            (pn or '').strip()
            for (pn,) in rows
            if (pn or '').strip()
        ]
        return sort_period_names(names)

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
    assignment_ids: Optional[List[int]] = None,
    period_name: Optional[str] = None,
    template_ids: Optional[List[int]] = None,
) -> Optional[Dict[str, Any]]:
    """Build optional ``scope`` object for data API responses."""
    scoped_template_ids = sorted({
        int(x) for x in (template_ids or [])
        if x is not None
    })
    if template_id is not None:
        scoped_template_ids = sorted(set(scoped_template_ids + [int(template_id)]))

    if not scoped_template_ids and not assignment_ids:
        return None

    meta: Dict[str, Any] = {
        'version_scope': version_scope,
    }
    if stable_key:
        meta['stable_key'] = stable_key
    if assignment_ids:
        meta['assignment_ids'] = [int(x) for x in assignment_ids]

    if len(scoped_template_ids) == 1:
        single_template_id = scoped_template_ids[0]
        meta['template_id'] = single_template_id
        meta['published_version_id'] = (
            published_version_id
            if published_version_id is not None
            else resolve_template_published_version_id(single_template_id)
        )
        template_names = _resolve_scope_template_names(single_template_id)
    else:
        meta['template_ids'] = scoped_template_ids
        published_map = {
            str(tid): resolve_template_published_version_id(tid)
            for tid in scoped_template_ids
        }
        meta['published_version_ids'] = {
            key: value for key, value in published_map.items() if value is not None
        }
        template_names = _resolve_scope_template_names_for_ids(scoped_template_ids)

    if template_names:
        meta['template_names'] = template_names

    period_names = _resolve_scope_period_names(
        template_id=template_id if len(scoped_template_ids) == 1 else None,
        assignment_ids=assignment_ids,
        period_name=period_name,
    )
    if period_names:
        meta['period_names'] = period_names

    return meta
