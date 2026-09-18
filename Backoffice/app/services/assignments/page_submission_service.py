"""Helpers for optional per-page save/submit on an assignment."""
from __future__ import annotations

from typing import Any, Iterable

from app.extensions import db
from app.models.assignments import AssignmentEntityStatus, AssignmentPageStatus
from app.models.enums import AssignmentSectionStatusValue
from app.models.forms import FormPage, FormSection, FormTemplate
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
from app.services.assignments.section_submission_service import is_participating_section
from app.utils.datetime_helpers import utcnow

PAGE_ACTIONS = frozenset({'save_page', 'submit_page'})


def is_page_submission_enabled(assignment_entity_status) -> bool:
    assigned_form = getattr(assignment_entity_status, 'assigned_form', None)
    if assigned_form is None:
        return False
    return getattr(assigned_form, 'enable_page_submission', False) == True


def _section_id(section) -> int | None:
    sid = getattr(section, 'id', None)
    try:
        return int(sid) if sid is not None else None
    except (TypeError, ValueError):
        return None


def _page_id(raw) -> int | None:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _sections_by_id(all_sections: Iterable) -> dict[int, Any]:
    by_id: dict[int, Any] = {}
    for section in all_sections or []:
        sid = _section_id(section)
        if sid is not None:
            by_id[sid] = section
    return by_id


def _fallback_page_id(all_sections: Iterable) -> int | None:
    pages = []
    seen = set()
    for section in all_sections or []:
        page = getattr(section, 'page', None)
        pid = _page_id(getattr(page, 'id', None) or getattr(section, 'page_id', None))
        if pid is None or pid in seen:
            continue
        seen.add(pid)
        pages.append(page if page is not None else type('P', (), {'id': pid, 'order': 0})())
    if not pages:
        return None
    pages.sort(key=lambda page: (getattr(page, 'order', 0) or 0, int(getattr(page, 'id', 0) or 0)))
    return int(pages[0].id)


def resolved_page_id(section, all_sections: Iterable | None = None, fallback_page_id: int | None = None) -> int | None:
    """Nearest page_id on this section or its ancestors, else the first page."""
    by_id = _sections_by_id(all_sections) if all_sections is not None else None
    seen = set()
    current = section
    while current is not None:
        sid = _section_id(current)
        if sid is not None:
            if sid in seen:
                break
            seen.add(sid)
        pid = _page_id(getattr(current, 'page_id', None))
        if pid is not None:
            return pid
        parent_id = getattr(current, 'parent_section_id', None)
        if parent_id is None:
            break
        if by_id is not None:
            current = by_id.get(int(parent_id))
        else:
            current = db.session.get(FormSection, parent_id)
    if fallback_page_id is None and all_sections is not None:
        fallback_page_id = _fallback_page_id(all_sections)
    return _page_id(fallback_page_id)


def section_to_page_ids(all_sections: Iterable) -> dict[str, int]:
    fallback = _fallback_page_id(all_sections)
    mapping: dict[str, int] = {}
    for section in all_sections or []:
        sid = _section_id(section)
        if sid is None:
            continue
        pid = resolved_page_id(section, all_sections, fallback)
        if pid is not None:
            mapping[str(sid)] = pid
    return mapping


def participating_page_ids(all_sections: Iterable) -> list[int]:
    fallback = _fallback_page_id(all_sections)
    ordered: list[int] = []
    seen = set()
    for section in all_sections or []:
        if getattr(section, 'parent_section_id', None) is not None:
            continue
        if not is_participating_section(section):
            continue
        pid = resolved_page_id(section, all_sections, fallback)
        if pid is None or pid in seen:
            continue
        seen.add(pid)
        ordered.append(pid)
    return ordered


def resolve_page_scope(all_sections: Iterable, page_id: int) -> set[int]:
    try:
        page_id = int(page_id)
    except (TypeError, ValueError):
        return set()
    fallback = _fallback_page_id(all_sections)
    scope = set()
    for section in all_sections or []:
        sid = _section_id(section)
        if sid is None:
            continue
        if resolved_page_id(section, all_sections, fallback) == page_id:
            scope.add(sid)
    return scope


def resolve_requested_page(all_sections: Iterable, raw_page_id) -> tuple[int | None, set[int]]:
    page_id = _page_id(raw_page_id)
    if page_id is None:
        return None, set()
    if page_id not in set(participating_page_ids(all_sections)):
        return None, set()
    return page_id, resolve_page_scope(all_sections, page_id)


def page_boundary_section_ids(all_sections: Iterable) -> tuple[dict[str, int], dict[str, int]]:
    """First and last participating top-level section id per page."""
    fallback = _fallback_page_id(all_sections)
    first: dict[str, int] = {}
    last: dict[str, int] = {}
    for section in all_sections or []:
        if getattr(section, 'parent_section_id', None) is not None:
            continue
        if not is_participating_section(section):
            continue
        sid = _section_id(section)
        pid = resolved_page_id(section, all_sections, fallback)
        if sid is None or pid is None:
            continue
        key = str(pid)
        if key not in first:
            first[key] = sid
        last[key] = sid
    return first, last


def submitted_page_ids(assignment_entity_status_id: int) -> set[int]:
    if not assignment_entity_status_id:
        return set()
    rows = (
        db.session.query(AssignmentPageStatus.form_page_id)
        .filter(
            AssignmentPageStatus.assignment_entity_status_id == assignment_entity_status_id,
            AssignmentPageStatus.status.in_(list(COMPLETE_SCOPED_STATUSES)),
        )
        .all()
    )
    return {int(page_id) for (page_id,) in rows if page_id is not None}


def locked_page_ids(assignment_entity_status_id: int) -> set[int]:
    if not assignment_entity_status_id:
        return set()
    rows = (
        db.session.query(AssignmentPageStatus.form_page_id)
        .filter(
            AssignmentPageStatus.assignment_entity_status_id == assignment_entity_status_id,
            AssignmentPageStatus.status.in_(list(LOCKED_SCOPED_STATUSES)),
        )
        .all()
    )
    return {int(page_id) for (page_id,) in rows if page_id is not None}


def locked_section_ids(assignment_entity_status, all_sections: Iterable) -> set[int]:
    if not is_page_submission_enabled(assignment_entity_status):
        return set()
    aes_id = getattr(assignment_entity_status, 'id', None)
    if not aes_id:
        return set()
    locked = set()
    for page_id in locked_page_ids(aes_id):
        locked |= resolve_page_scope(all_sections, page_id)
    return locked


def get_or_create_row(assignment_entity_status_id: int, form_page_id: int) -> AssignmentPageStatus:
    row = AssignmentPageStatus.query.filter_by(
        assignment_entity_status_id=assignment_entity_status_id,
        form_page_id=form_page_id,
    ).first()
    if row:
        return row
    row = AssignmentPageStatus(
        assignment_entity_status_id=assignment_entity_status_id,
        form_page_id=form_page_id,
        status=AssignmentSectionStatusValue.not_started.value,
    )
    db.session.add(row)
    db.session.flush()
    return row


def _set_status(
    row: AssignmentPageStatus,
    new_status: AssignmentSectionStatusValue,
    user_id: int | None,
    *,
    now=None,
) -> AssignmentPageStatus:
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


def mark_page_in_progress(
    assignment_entity_status_id: int,
    form_page_id: int,
    user_id: int | None,
) -> AssignmentPageStatus:
    row = get_or_create_row(assignment_entity_status_id, form_page_id)
    if is_locked_status(row.status):
        return row
    return _set_status(row, AssignmentSectionStatusValue.in_progress, user_id)


def mark_page_submitted(
    assignment_entity_status_id: int,
    form_page_id: int,
    user_id: int | None,
    *,
    now=None,
) -> AssignmentPageStatus:
    row = get_or_create_row(assignment_entity_status_id, form_page_id)
    return _set_status(row, AssignmentSectionStatusValue.submitted, user_id, now=now)


def all_participating_pages_submitted(assignment_entity_status, all_sections: Iterable) -> bool:
    pages = participating_page_ids(all_sections)
    if not pages:
        return False
    submitted = submitted_page_ids(assignment_entity_status.id)
    return all(page_id in submitted for page_id in pages)


def reset_all_page_statuses(assignment_entity_status_id: int, user_id: int | None = None) -> int:
    rows = AssignmentPageStatus.query.filter_by(
        assignment_entity_status_id=assignment_entity_status_id,
    ).all()
    return apply_status_to_rows(
        rows,
        AssignmentSectionStatusValue.in_progress,
        user_id,
        REOPENABLE_SCOPED_STATUSES,
    )


def reset_page_status(
    assignment_entity_status_id: int,
    form_page_id: int,
    user_id: int | None = None,
) -> AssignmentPageStatus | None:
    row = AssignmentPageStatus.query.filter_by(
        assignment_entity_status_id=assignment_entity_status_id,
        form_page_id=form_page_id,
    ).first()
    if not row or not is_reopenable_status(row.status):
        return None
    return _set_status(row, AssignmentSectionStatusValue.in_progress, user_id)


def mark_page_requires_revision(
    assignment_entity_status_id: int,
    form_page_id: int,
    user_id: int | None = None,
) -> AssignmentPageStatus | None:
    row = AssignmentPageStatus.query.filter_by(
        assignment_entity_status_id=assignment_entity_status_id,
        form_page_id=form_page_id,
    ).first()
    if not row or status_value(row.status) not in REVISION_SOURCE_STATUSES:
        return None
    return _set_status(row, AssignmentSectionStatusValue.requires_revision, user_id)


def sync_page_statuses_for_entity_change(
    assignment_entity_status_id: int,
    previous_status,
    new_status,
    user_id: int | None = None,
) -> int:
    rows = AssignmentPageStatus.query.filter_by(
        assignment_entity_status_id=assignment_entity_status_id,
    ).all()
    return sync_scoped_rows_for_entity_change(rows, previous_status, new_status, user_id)


def page_workflow_statuses(assignment_entity_status_id: int, all_sections: Iterable) -> dict[str, str]:
    rows = AssignmentPageStatus.query.filter_by(
        assignment_entity_status_id=assignment_entity_status_id,
    ).all()
    by_page = {int(row.form_page_id): row.status for row in rows}
    return {
        str(page_id): by_page.get(page_id, AssignmentSectionStatusValue.not_started.value)
        for page_id in participating_page_ids(all_sections)
    }


def section_workflow_from_pages(assignment_entity_status_id: int, all_sections: Iterable) -> dict[str, str]:
    """Map every section to its page workflow status (for nav lock icons)."""
    page_statuses = page_workflow_statuses(assignment_entity_status_id, all_sections)
    mapping = section_to_page_ids(all_sections)
    return {
        section_id: page_statuses.get(str(page_id), AssignmentSectionStatusValue.not_started.value)
        for section_id, page_id in mapping.items()
    }


def page_progress_counts(assignment_entity_status_id: int, all_sections: Iterable) -> tuple[int, int]:
    pages = participating_page_ids(all_sections)
    total = len(pages)
    if total == 0:
        return 0, 0
    submitted = submitted_page_ids(assignment_entity_status_id)
    return sum(1 for page_id in pages if page_id in submitted), total


def prefetch_page_progress(assignment_entity_statuses: Iterable[AssignmentEntityStatus]) -> dict[int, dict]:
    result: dict[int, dict] = {}
    enabled_aes: list[AssignmentEntityStatus] = []
    for aes in assignment_entity_statuses or []:
        if not aes or not getattr(aes, 'id', None):
            continue
        if not is_page_submission_enabled(aes):
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
    pages_by_template: dict[int, list[int]] = {}
    if template_ids:
        rows = (
            db.session.query(FormPage.template_id, FormPage.id)
            .join(FormTemplate, FormTemplate.id == FormPage.template_id)
            .filter(
                FormPage.template_id.in_(list(template_ids)),
                FormPage.version_id == FormTemplate.published_version_id,
            )
            .order_by(FormPage.template_id, FormPage.order, FormPage.id)
            .all()
        )
        for template_id, page_id in rows:
            pages_by_template.setdefault(template_id, []).append(int(page_id))

        section_rows = (
            db.session.query(FormSection.template_id, FormSection.page_id)
            .join(FormTemplate, FormTemplate.id == FormSection.template_id)
            .filter(
                FormSection.template_id.in_(list(template_ids)),
                FormSection.version_id == FormTemplate.published_version_id,
                FormSection.parent_section_id.is_(None),
                FormSection.archived.is_(False),
                FormSection.section_type.in_(['standard', 'repeat', 'dynamic_indicators']),
            )
            .all()
        )
        pages_with_sections: dict[int, set[int]] = {}
        for template_id, page_id in section_rows:
            allowed = pages_by_template.get(template_id) or []
            resolved = int(page_id) if page_id else (allowed[0] if allowed else None)
            if resolved is None:
                continue
            pages_with_sections.setdefault(template_id, set()).add(resolved)
        pages_by_template = {
            tid: [pid for pid in pids if pid in pages_with_sections.get(tid, set())]
            for tid, pids in pages_by_template.items()
        }

    submitted_rows = (
        db.session.query(
            AssignmentPageStatus.assignment_entity_status_id,
            AssignmentPageStatus.form_page_id,
        )
        .filter(
            AssignmentPageStatus.assignment_entity_status_id.in_([aes.id for aes in enabled_aes]),
            AssignmentPageStatus.status.in_(list(COMPLETE_SCOPED_STATUSES)),
        )
        .all()
    )
    submitted_by_aes: dict[int, set[int]] = {}
    for aes_id, page_id in submitted_rows:
        submitted_by_aes.setdefault(int(aes_id), set()).add(int(page_id))

    for aes in enabled_aes:
        template_id = aes.assigned_form.template_id if aes.assigned_form else None
        allowed = set(pages_by_template.get(template_id or 0, []))
        submitted = submitted_by_aes.get(aes.id, set()) & allowed
        result[aes.id] = {
            'enabled': True,
            'submitted': len(submitted),
            'total': len(allowed),
        }
    return result
