"""Helpers for optional per-section save/submit on an assignment."""
from __future__ import annotations

from typing import Any, Iterable

from app.extensions import db
from app.models.assignments import AssignmentEntityStatus, AssignmentSectionStatus
from app.models.enums import AssignmentSectionStatusValue
from app.models.forms import FormSection, FormTemplate
from app.services.assignments.scoped_status import (
    COMPLETE_SCOPED_STATUSES,
    LOCKED_SCOPED_STATUSES,
    REOPENABLE_SCOPED_STATUSES,
    REVISION_SOURCE_STATUSES,
    apply_status_to_rows,
    is_locked_status,
    is_reopenable_status,
    status_value,
    sync_scoped_rows_for_entity_change,
)
from app.utils.datetime_helpers import utcnow

PARTICIPATING_SECTION_TYPES = frozenset({'standard', 'repeat', 'dynamic_indicators'})
SECTION_ACTIONS = frozenset({'save_section', 'submit_section'})


def is_section_submission_enabled(assignment_entity_status) -> bool:
    assigned_form = getattr(assignment_entity_status, 'assigned_form', None)
    if assigned_form is None:
        return False
    return getattr(assigned_form, 'enable_section_submission', False) == True


def is_participating_section(section) -> bool:
    section_type = getattr(section, 'section_type', None) or 'standard'
    if section_type == 'discussion':
        return False
    return section_type in PARTICIPATING_SECTION_TYPES


def _section_id(section) -> int | None:
    sid = getattr(section, 'id', None)
    try:
        return int(sid) if sid is not None else None
    except (TypeError, ValueError):
        return None


def _sections_by_id(all_sections: Iterable) -> dict[int, Any]:
    by_id: dict[int, Any] = {}
    for section in all_sections or []:
        sid = _section_id(section)
        if sid is not None:
            by_id[sid] = section
    return by_id


def top_level_section_id(section, all_sections: Iterable | None = None) -> int | None:
    """Return the nearest top-level ancestor id (or the section itself)."""
    sid = _section_id(section)
    if sid is None:
        return None
    parent_id = getattr(section, 'parent_section_id', None)
    if parent_id is None:
        return sid

    by_id = _sections_by_id(all_sections) if all_sections is not None else None
    seen = {sid}
    current = section
    while getattr(current, 'parent_section_id', None):
        pid = current.parent_section_id
        if pid in seen:
            break
        seen.add(pid)
        if by_id is not None:
            parent = by_id.get(pid)
        else:
            parent = db.session.get(FormSection, pid)
        if parent is None:
            return pid
        if getattr(parent, 'parent_section_id', None) is None:
            return int(parent.id)
        current = parent
    return sid


def resolve_section_scope(all_sections: Iterable, top_level_id: int) -> set[int]:
    """Top-level section plus every descendant (by parent_section_id)."""
    try:
        top_level_id = int(top_level_id)
    except (TypeError, ValueError):
        return set()

    by_parent: dict[int | None, list] = {}
    for section in all_sections or []:
        by_parent.setdefault(getattr(section, 'parent_section_id', None), []).append(section)

    scope = {top_level_id}
    stack = [top_level_id]
    while stack:
        parent_id = stack.pop()
        for child in by_parent.get(parent_id, []):
            child_id = _section_id(child)
            if child_id is None or child_id in scope:
                continue
            scope.add(child_id)
            stack.append(child_id)
    return scope


def participating_top_level_sections(all_sections: Iterable) -> list:
    return [
        section
        for section in (all_sections or [])
        if getattr(section, 'parent_section_id', None) is None
        and is_participating_section(section)
    ]


def _top_level_ids_with_status(assignment_entity_status_id: int, statuses) -> set[int]:
    if not assignment_entity_status_id:
        return set()
    rows = (
        db.session.query(AssignmentSectionStatus.form_section_id)
        .filter(
            AssignmentSectionStatus.assignment_entity_status_id == assignment_entity_status_id,
            AssignmentSectionStatus.status.in_(list(statuses)),
        )
        .all()
    )
    return {int(section_id) for (section_id,) in rows if section_id is not None}


def submitted_top_level_ids(assignment_entity_status_id: int) -> set[int]:
    return _top_level_ids_with_status(assignment_entity_status_id, COMPLETE_SCOPED_STATUSES)


def locked_top_level_ids(assignment_entity_status_id: int) -> set[int]:
    return _top_level_ids_with_status(assignment_entity_status_id, LOCKED_SCOPED_STATUSES)


def locked_section_ids(assignment_entity_status, all_sections: Iterable) -> set[int]:
    """Section ids (top-level + descendants) whose data must not be overwritten."""
    if not is_section_submission_enabled(assignment_entity_status):
        return set()
    aes_id = getattr(assignment_entity_status, 'id', None)
    if not aes_id:
        return set()
    locked = set()
    for top_id in locked_top_level_ids(aes_id):
        locked |= resolve_section_scope(all_sections, top_id)
    return locked


def get_or_create_row(assignment_entity_status_id: int, form_section_id: int) -> AssignmentSectionStatus:
    row = AssignmentSectionStatus.query.filter_by(
        assignment_entity_status_id=assignment_entity_status_id,
        form_section_id=form_section_id,
    ).first()
    if row:
        return row
    row = AssignmentSectionStatus(
        assignment_entity_status_id=assignment_entity_status_id,
        form_section_id=form_section_id,
        status=AssignmentSectionStatusValue.not_started.value,
    )
    db.session.add(row)
    db.session.flush()
    return row


def _set_status(
    row: AssignmentSectionStatus,
    new_status: AssignmentSectionStatusValue,
    user_id: int | None,
    *,
    now=None,
) -> AssignmentSectionStatus:
    stamp = now or utcnow()
    row.status = new_status.value
    row.status_timestamp = stamp
    if user_id is not None:
        row.status_changed_by_user_id = user_id
    if new_status == AssignmentSectionStatusValue.submitted:
        if user_id is not None:
            row.submitted_by_user_id = user_id
        row.submitted_at = stamp
    return row


def mark_section_in_progress(
    assignment_entity_status_id: int,
    form_section_id: int,
    user_id: int | None,
) -> AssignmentSectionStatus:
    row = get_or_create_row(assignment_entity_status_id, form_section_id)
    if is_locked_status(row.status):
        return row
    return _set_status(row, AssignmentSectionStatusValue.in_progress, user_id)


def mark_section_submitted(
    assignment_entity_status_id: int,
    form_section_id: int,
    user_id: int | None,
    *,
    now=None,
) -> AssignmentSectionStatus:
    row = get_or_create_row(assignment_entity_status_id, form_section_id)
    return _set_status(row, AssignmentSectionStatusValue.submitted, user_id, now=now)


def all_participating_sections_submitted(assignment_entity_status, all_sections: Iterable) -> bool:
    participating = participating_top_level_sections(all_sections)
    if not participating:
        return False
    submitted = submitted_top_level_ids(assignment_entity_status.id)
    return all(_section_id(section) in submitted for section in participating)


def reset_all_section_statuses(assignment_entity_status_id: int, user_id: int | None = None) -> int:
    rows = AssignmentSectionStatus.query.filter_by(
        assignment_entity_status_id=assignment_entity_status_id,
    ).all()
    return apply_status_to_rows(
        rows,
        AssignmentSectionStatusValue.in_progress,
        user_id,
        REOPENABLE_SCOPED_STATUSES,
    )


def reset_section_status(
    assignment_entity_status_id: int,
    form_section_id: int,
    user_id: int | None = None,
) -> AssignmentSectionStatus | None:
    row = AssignmentSectionStatus.query.filter_by(
        assignment_entity_status_id=assignment_entity_status_id,
        form_section_id=form_section_id,
    ).first()
    if not row or not is_reopenable_status(row.status):
        return None
    return _set_status(row, AssignmentSectionStatusValue.in_progress, user_id)


def mark_section_requires_revision(
    assignment_entity_status_id: int,
    form_section_id: int,
    user_id: int | None = None,
) -> AssignmentSectionStatus | None:
    row = AssignmentSectionStatus.query.filter_by(
        assignment_entity_status_id=assignment_entity_status_id,
        form_section_id=form_section_id,
    ).first()
    if not row or status_value(row.status) not in REVISION_SOURCE_STATUSES:
        return None
    return _set_status(row, AssignmentSectionStatusValue.requires_revision, user_id)


def sync_section_statuses_for_entity_change(
    assignment_entity_status_id: int,
    previous_status,
    new_status,
    user_id: int | None = None,
) -> int:
    rows = AssignmentSectionStatus.query.filter_by(
        assignment_entity_status_id=assignment_entity_status_id,
    ).all()
    return sync_scoped_rows_for_entity_change(rows, previous_status, new_status, user_id)


def section_workflow_statuses(assignment_entity_status_id: int, all_sections: Iterable) -> dict[str, str]:
    """Map every section id to its top-level workflow status."""
    rows = AssignmentSectionStatus.query.filter_by(
        assignment_entity_status_id=assignment_entity_status_id,
    ).all()
    by_top = {int(row.form_section_id): row.status for row in rows}
    statuses: dict[str, str] = {}
    for section in all_sections or []:
        sid = _section_id(section)
        if sid is None:
            continue
        top_id = top_level_section_id(section, all_sections)
        statuses[str(sid)] = by_top.get(top_id or sid, AssignmentSectionStatusValue.not_started.value)
    return statuses


def section_progress_counts(assignment_entity_status_id: int, all_sections: Iterable) -> tuple[int, int]:
    participating = participating_top_level_sections(all_sections)
    total = len(participating)
    if total == 0:
        return 0, 0
    submitted = submitted_top_level_ids(assignment_entity_status_id)
    count = sum(1 for section in participating if _section_id(section) in submitted)
    return count, total


def parse_section_id(raw) -> int | None:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def resolve_requested_section(all_sections: Iterable, raw_section_id) -> tuple[int | None, set[int]]:
    """Return (top_level_id, scope_ids) for a posted section_id, or (None, empty)."""
    requested_id = parse_section_id(raw_section_id)
    if requested_id is None:
        return None, set()
    by_id = _sections_by_id(all_sections)
    section = by_id.get(requested_id)
    if section is None:
        return None, set()
    top_id = top_level_section_id(section, all_sections)
    if top_id is None:
        return None, set()
    top_section = by_id.get(top_id)
    if top_section is None or not is_participating_section(top_section):
        return None, set()
    return top_id, resolve_section_scope(all_sections, top_id)


def prefetch_section_progress(assignment_entity_statuses: Iterable[AssignmentEntityStatus]) -> dict[int, dict]:
    """Batch {aes_id: {enabled, submitted, total}} for dashboard cards."""
    result: dict[int, dict] = {}
    enabled_aes: list[AssignmentEntityStatus] = []
    for aes in assignment_entity_statuses or []:
        if not aes or not getattr(aes, 'id', None):
            continue
        enabled = is_section_submission_enabled(aes)
        if not enabled:
            result[aes.id] = {'enabled': False, 'submitted': 0, 'total': 0}
            continue
        enabled_aes.append(aes)

    if not enabled_aes:
        return result

    template_ids = {
        aes.assigned_form.template_id
        for aes in enabled_aes
        if aes.assigned_form and aes.assigned_form.template_id
    }
    totals_by_template: dict[int, int] = {}
    section_ids_by_template: dict[int, set[int]] = {}
    if template_ids:
        rows = (
            db.session.query(
                FormSection.template_id,
                FormSection.id,
            )
            .join(FormTemplate, FormTemplate.id == FormSection.template_id)
            .filter(
                FormSection.template_id.in_(list(template_ids)),
                FormSection.version_id == FormTemplate.published_version_id,
                FormSection.parent_section_id.is_(None),
                FormSection.archived.is_(False),
                FormSection.section_type.in_(list(PARTICIPATING_SECTION_TYPES)),
            )
            .all()
        )
        for template_id, section_id in rows:
            section_ids_by_template.setdefault(template_id, set()).add(int(section_id))
        totals_by_template = {
            tid: len(sids) for tid, sids in section_ids_by_template.items()
        }

    aes_ids = [aes.id for aes in enabled_aes]
    submitted_rows = (
        db.session.query(
            AssignmentSectionStatus.assignment_entity_status_id,
            AssignmentSectionStatus.form_section_id,
        )
        .filter(
            AssignmentSectionStatus.assignment_entity_status_id.in_(aes_ids),
            AssignmentSectionStatus.status.in_(list(COMPLETE_SCOPED_STATUSES)),
        )
        .all()
    )
    submitted_by_aes: dict[int, set[int]] = {}
    for aes_id, section_id in submitted_rows:
        submitted_by_aes.setdefault(int(aes_id), set()).add(int(section_id))

    for aes in enabled_aes:
        template_id = aes.assigned_form.template_id if aes.assigned_form else None
        allowed = section_ids_by_template.get(template_id or 0, set())
        submitted = submitted_by_aes.get(aes.id, set()) & allowed
        result[aes.id] = {
            'enabled': True,
            'submitted': len(submitted),
            'total': totals_by_template.get(template_id or 0, 0),
        }
    return result
