"""Shared filters and version scoping for /api/v1/data endpoints."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from app import db
from app.models import FormData, FormItem, FormTemplate
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


def build_data_api_scope_meta(
    *,
    template_id: Optional[int],
    published_version_id: Optional[int],
    version_scope: str,
    stable_key: Optional[str] = None,
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
    return meta
