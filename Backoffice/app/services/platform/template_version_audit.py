"""Read-only integrity audit for form template versions.

Finds the states that make version deploys ambiguous or unsafe before they are hit in
production, and that a future database constraint would reject:

* more than one draft for a template
* more than one published version, or ``published_version_id`` not matching the published one
* the same ``stable_key`` on several items or sections of one version
* items/sections with no ``stable_key`` in templates that have more than one version
  (deploy backfills these by position; running ``backfill_stable_keys.py`` makes it explicit)

Nothing here writes to the database.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import func

from app.extensions import db
from app.models import FormItem, FormSection, FormTemplate, FormTemplateVersion


def _scoped(query, column, template_id: Optional[int]):
    return query.filter(column == template_id) if template_id is not None else query


def _multiple_drafts(template_id: Optional[int]) -> List[Dict[str, Any]]:
    query = (
        db.session.query(
            FormTemplateVersion.template_id,
            func.count(FormTemplateVersion.id),
            func.array_agg(FormTemplateVersion.id),
        )
        .filter(FormTemplateVersion.status == 'draft')
        .group_by(FormTemplateVersion.template_id)
        .having(func.count(FormTemplateVersion.id) > 1)
    )
    query = _scoped(query, FormTemplateVersion.template_id, template_id)
    return [
        {'template_id': tid, 'draft_count': count, 'version_ids': sorted(ids)}
        for tid, count, ids in query.all()
    ]


def _published_inconsistencies(template_id: Optional[int]) -> List[Dict[str, Any]]:
    published_by_template: Dict[int, List[int]] = {}
    version_query = _scoped(
        db.session.query(FormTemplateVersion.template_id, FormTemplateVersion.id)
        .filter(FormTemplateVersion.status == 'published'),
        FormTemplateVersion.template_id,
        template_id,
    )
    for tid, vid in version_query.all():
        published_by_template.setdefault(tid, []).append(vid)

    findings: List[Dict[str, Any]] = []
    template_query = _scoped(
        db.session.query(FormTemplate.id, FormTemplate.published_version_id), FormTemplate.id, template_id
    )
    for tid, pointer in template_query.all():
        published_ids = sorted(published_by_template.get(tid, []))
        if len(published_ids) > 1:
            findings.append({
                'template_id': tid, 'problem': 'multiple_published_versions',
                'published_version_ids': published_ids, 'published_version_id': pointer,
            })
        elif published_ids and pointer != published_ids[0]:
            findings.append({
                'template_id': tid, 'problem': 'pointer_mismatch',
                'published_version_ids': published_ids, 'published_version_id': pointer,
            })
        elif not published_ids and pointer is not None:
            findings.append({
                'template_id': tid, 'problem': 'pointer_to_unpublished_version',
                'published_version_ids': [], 'published_version_id': pointer,
            })
    return findings


def _duplicate_keys(model, template_id: Optional[int]) -> List[Dict[str, Any]]:
    query = (
        db.session.query(
            model.template_id,
            model.version_id,
            model.stable_key,
            func.count(model.id),
            func.array_agg(model.id),
        )
        .filter(model.stable_key.isnot(None))
        .group_by(model.template_id, model.version_id, model.stable_key)
        .having(func.count(model.id) > 1)
    )
    query = _scoped(query, model.template_id, template_id)
    return [
        {
            'template_id': tid, 'version_id': vid, 'stable_key': key,
            'row_count': count, 'row_ids': sorted(ids),
        }
        for tid, vid, key, count, ids in query.all()
    ]


def _null_keys(model, template_id: Optional[int]) -> List[Dict[str, Any]]:
    multi_version = (
        db.session.query(FormTemplateVersion.template_id)
        .group_by(FormTemplateVersion.template_id)
        .having(func.count(FormTemplateVersion.id) > 1)
        .subquery()
    )
    query = (
        db.session.query(model.template_id, model.version_id, func.count(model.id))
        .filter(model.stable_key.is_(None), model.template_id.in_(db.session.query(multi_version.c.template_id)))
        .group_by(model.template_id, model.version_id)
    )
    query = _scoped(query, model.template_id, template_id)
    return [
        {'template_id': tid, 'version_id': vid, 'row_count': count}
        for tid, vid, count in query.all()
    ]


def audit_template_versions(template_id: Optional[int] = None) -> Dict[str, Any]:
    """Return findings per check; an empty list means that check is clean."""
    findings = {
        'multiple_drafts': _multiple_drafts(template_id),
        'published_inconsistencies': _published_inconsistencies(template_id),
        'duplicate_item_keys': _duplicate_keys(FormItem, template_id),
        'duplicate_section_keys': _duplicate_keys(FormSection, template_id),
        'items_without_key': _null_keys(FormItem, template_id),
        'sections_without_key': _null_keys(FormSection, template_id),
    }
    # Missing keys are repaired automatically at deploy, so they are advisory; the rest block
    # or corrupt a deploy and must be fixed first.
    blocking = (
        'multiple_drafts', 'published_inconsistencies', 'duplicate_item_keys', 'duplicate_section_keys',
    )
    findings['has_blocking_issues'] = any(findings[name] for name in blocking)
    return findings
