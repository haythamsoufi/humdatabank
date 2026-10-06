"""Utilities for template structure stable_key (cross-version field identity)."""

from __future__ import annotations

import uuid
from typing import Optional


def defer_stable_key_autogen(target) -> None:
    """Skip before_insert UUID generation (clone leaves NULL until deploy/backfill aligns)."""
    target._defer_stable_key_autogen = True


def generate_stable_key() -> str:
    """Return a new UUID string for a form item or section."""
    return str(uuid.uuid4())


# Template 22 matrices. These are the production keys (published version 22,
# items 1314 and 1303). Filled in only where stable_key is still null. Do not
# overwrite a key that is already set.
T22_STAFF_MATRIX_STABLE_KEY = "f4fa6b32-3141-4a15-a572-637e7d3f1f94"
T22_FUNDING_MATRIX_STABLE_KEY = "24b9438d-f937-4c99-802a-eccb1ffccc19"
T22_STAFF_MATRIX_COLUMN = "intl_delegates_hns"


def is_valid_stable_key(value: Optional[str]) -> bool:
    """Return True if value is a valid UUID string suitable for stable_key."""
    if not value or not isinstance(value, str):
        return False
    try:
        uuid.UUID(str(value).strip())
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def normalize_stable_key(value: Optional[str]) -> Optional[str]:
    """Return normalized UUID string or None if invalid/empty."""
    if not value or not isinstance(value, str):
        return None
    candidate = str(value).strip()
    if not candidate:
        return None
    if not is_valid_stable_key(candidate):
        return None
    return str(uuid.UUID(candidate))


def resolve_published_form_item_id(template_id: int, stable_key: str) -> Optional[int]:
    """Resolve a stable_key to the published-version form_item.id for submit/API clients."""
    key = normalize_stable_key(stable_key)
    if not key:
        return None
    from app.models import FormTemplate, FormItem

    template = FormTemplate.query.get(template_id)
    if not template or not template.published_version_id:
        return None
    item = FormItem.query.filter_by(
        template_id=template_id,
        version_id=template.published_version_id,
        stable_key=key,
        archived=False,
    ).first()
    return item.id if item else None


def resolve_published_form_section_id(template_id: int, stable_key: str) -> Optional[int]:
    """Resolve a stable_key to the published-version form_section.id."""
    key = normalize_stable_key(stable_key)
    if not key:
        return None
    from app.models import FormTemplate, FormSection

    template = FormTemplate.query.get(template_id)
    if not template or not template.published_version_id:
        return None
    section = FormSection.query.filter_by(
        template_id=template_id,
        version_id=template.published_version_id,
        stable_key=key,
        archived=False,
    ).first()
    return section.id if section else None


def resolve_form_item_refs(
    fields: list,
    template_id: int,
    *,
    id_key: str = 'form_item_id',
    stable_key_key: str = 'stable_key',
) -> tuple[list, list]:
    """Map optional stable_key entries to published form_item_id; return (resolved, errors)."""
    resolved = []
    errors = []
    for idx, field in enumerate(fields or []):
        if not isinstance(field, dict):
            errors.append(f'Field {idx}: expected object')
            continue
        item_id = field.get(id_key)
        stable = field.get(stable_key_key)
        if item_id is None and stable:
            item_id = resolve_published_form_item_id(template_id, stable)
            if item_id is None:
                errors.append(f'Field {idx}: unknown stable_key {stable!r}')
                continue
        if item_id is None:
            errors.append(f'Field {idx}: form_item_id or stable_key required')
            continue
        entry = dict(field)
        entry[id_key] = int(item_id)
        resolved.append(entry)
    return resolved, errors


def published_form_item_id_set(template_id: int) -> set[int]:
    """Return non-archived form_item ids for a template's published version."""
    from app.models import FormItem, FormTemplate
    from app.extensions import db

    template = FormTemplate.query.get(template_id)
    if not template or not template.published_version_id:
        return set()
    rows = (
        db.session.query(FormItem.id)
        .filter_by(
            template_id=template_id,
            version_id=template.published_version_id,
            archived=False,
        )
        .all()
    )
    return {int(row[0]) for row in rows}


def published_form_item_id_set_for_templates(template_ids: list[int]) -> set[int]:
    """Union of published-version form_item ids across templates."""
    out: set[int] = set()
    for template_id in template_ids or []:
        out |= published_form_item_id_set(int(template_id))
    return out
