"""Copy one project's assignment settings onto each of its report cycles.

The entry form, emails, and mobile API keep reading ``AssignedForm``. This module
is the only writer of those shared options for ``scope=project_cycle`` rows.
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence

from flask import current_app

from app import db
from app.models.assignments import (
    SUBMISSION_REVIEW_RECIPIENT_FDS,
    SUBMISSION_REVIEW_RECIPIENT_SPECIFIC,
)
from app.models.projects import Project, ProjectAssignment
from app.services.projects.service import list_project_cycle_assignments, parse_cycle_slot

# Options stored once on ProjectAssignment and copied onto every report.
SHARED_FLAG_FIELDS = (
    "enable_export_pdf",
    "enable_export_excel",
    "enable_import_excel",
    "email_attach_pdf",
    "email_attach_excel",
    "enable_page_submission",
    "enable_offline_download",
    "requires_delegation_review",
    "submission_review_recipient_mode",
    "data_owner_id",
)

_TEMPLATE_SEED_FLAGS = ("enable_export_pdf", "enable_export_excel", "enable_import_excel")


def _plugin_manager():
    return getattr(current_app, "plugin_manager", None)


def plugin_report_types(project: Project) -> list:
    manager = _plugin_manager()
    if manager is None or not hasattr(manager, "project_report_types"):
        return []
    try:
        return list(manager.project_report_types(project) or [])
    except Exception as exc:
        current_app.logger.warning("project_report_types failed: %s", exc)
        return []


def plugin_audience_role_ids(project: Project, slot: str) -> list:
    manager = _plugin_manager()
    if manager is None or not hasattr(manager, "project_report_audience_ids"):
        return []
    try:
        return [int(role_id) for role_id in (manager.project_report_audience_ids(project, slot) or [])]
    except Exception as exc:
        current_app.logger.warning("project_report_audience failed: %s", exc)
        return []


def _majority_bool(values: Sequence[bool]) -> bool:
    if not values:
        return False
    trues = sum(1 for value in values if value)
    return trues > (len(values) - trues)


def _majority_value(values: Iterable, default):
    counts = {}
    for value in values:
        if value in (None, ""):
            continue
        counts[value] = counts.get(value, 0) + 1
    if not counts:
        return default
    return max(counts.items(), key=lambda item: (item[1], str(item[0])))[0]


def _ids_on_majority(groups: Sequence[Sequence[int]]) -> list:
    if not groups:
        return []
    need = len(groups) / 2
    counts = {}
    for group in groups:
        for role_id in {int(v) for v in group if v is not None}:
            counts[role_id] = counts.get(role_id, 0) + 1
    return sorted(role_id for role_id, count in counts.items() if count > need)


def _seed_from_reports(settings: ProjectAssignment, reports: Sequence) -> None:
    """Fill a new settings row from the reports that already exist."""
    settings.data_owner_id = _majority_value((af.data_owner_id for af in reports), None)
    settings.submission_review_recipient_mode = _majority_value(
        (af.submission_review_recipient_mode for af in reports),
        SUBMISSION_REVIEW_RECIPIENT_FDS,
    ) or SUBMISSION_REVIEW_RECIPIENT_FDS
    settings.allowed_role_ids = _ids_on_majority(
        [list(getattr(af, "allowed_role_ids", []) or []) for af in reports]
    ) or None
    settings.review_recipient_user_ids = _ids_on_majority(
        [
            [int(user.id) for user in (af.submission_review_recipient_users or [])]
            for af in reports
        ]
    ) or None
    for name in SHARED_FLAG_FIELDS:
        if name in ("data_owner_id", "submission_review_recipient_mode"):
            continue
        chosen = _majority_bool([bool(getattr(af, name, False)) for af in reports])
        if (
            not chosen
            and name in _TEMPLATE_SEED_FLAGS
            and not any(bool(getattr(af, name, False)) for af in reports)
        ):
            chosen = any(
                bool(getattr(getattr(af, "template", None), name, False)) for af in reports
            )
        setattr(settings, name, bool(chosen))


def _seed_export_flags_from_template(assignment) -> None:
    """Turn on export flags a brand-new report inherits when no project settings exist yet."""
    template = getattr(assignment, "template", None)
    if template is None:
        return
    for name in _TEMPLATE_SEED_FLAGS:
        if not bool(getattr(assignment, name, False)) and bool(getattr(template, name, False)):
            setattr(assignment, name, True)


def get_or_create_project_assignment(project: Project) -> ProjectAssignment:
    row = ProjectAssignment.query.filter_by(project_id=project.id).first()
    if row is not None:
        return row
    row = ProjectAssignment(project_id=project.id)
    reports = list_project_cycle_assignments(project)
    if reports:
        _seed_from_reports(row, reports)
    db.session.add(row)
    db.session.flush()
    return row


def _wanted_role_ids(settings: ProjectAssignment, project: Project, assignment) -> set:
    slot = parse_cycle_slot(assignment.period_name) or ""
    return set(settings.role_id_list()) | set(plugin_audience_role_ids(project, slot))


def _reviewer_ids(assignment) -> set:
    return {int(user.id) for user in (assignment.submission_review_recipient_users or [])}


def report_settings_differ(settings: ProjectAssignment, assignment, project: Project) -> bool:
    for name in SHARED_FLAG_FIELDS:
        left = getattr(settings, name)
        right = getattr(assignment, name)
        if name == "data_owner_id":
            if (left or None) != (right or None):
                return True
            continue
        if name == "submission_review_recipient_mode":
            if (left or SUBMISSION_REVIEW_RECIPIENT_FDS) != (right or SUBMISSION_REVIEW_RECIPIENT_FDS):
                return True
            continue
        if bool(left) != bool(right):
            return True
    if _wanted_role_ids(settings, project, assignment) != set(assignment.allowed_role_ids or []):
        return True
    if settings.submission_review_recipient_mode == SUBMISSION_REVIEW_RECIPIENT_SPECIFIC:
        if set(settings.reviewer_id_list()) != _reviewer_ids(assignment):
            return True
    elif _reviewer_ids(assignment):
        return True
    return False


def settings_drift(project: Project) -> List:
    """Report assignments whose shared options differ from the project settings."""
    settings = ProjectAssignment.query.filter_by(project_id=project.id).first()
    if settings is None:
        return []
    return [
        assignment
        for assignment in list_project_cycle_assignments(project)
        if report_settings_differ(settings, assignment, project)
    ]


def _apply_reviewers(settings: ProjectAssignment, assignment) -> bool:
    from app.models.core import User

    if settings.submission_review_recipient_mode == SUBMISSION_REVIEW_RECIPIENT_SPECIFIC:
        wanted = settings.reviewer_id_list()
        if set(wanted) == _reviewer_ids(assignment):
            return False
        users = User.query.filter(User.id.in_(wanted)).all() if wanted else []
        by_id = {int(user.id): user for user in users}
        assignment.submission_review_recipient_users = [by_id[uid] for uid in wanted if uid in by_id]
        return True
    if _reviewer_ids(assignment):
        assignment.submission_review_recipient_users = []
        return True
    return False


def _apply_one(settings: ProjectAssignment, project: Project, assignment, *, user_id: Optional[int]) -> bool:
    """Copy shared options onto one report. Returns True when something changed."""
    from app.services.assignments.access_service import set_assignment_allowed_roles
    from app.services.assignments.page_submission_service import apply_page_submission_mode_change
    from app.services.imports.assignment_excel_access import sync_assignment_custom_excel_flags

    touched = False
    page_before = bool(assignment.enable_page_submission)
    for name in SHARED_FLAG_FIELDS:
        new_value = getattr(settings, name)
        if name in ("data_owner_id", "submission_review_recipient_mode"):
            if name == "data_owner_id":
                new_value = new_value or None
            else:
                new_value = new_value or SUBMISSION_REVIEW_RECIPIENT_FDS
            if getattr(assignment, name) != new_value:
                setattr(assignment, name, new_value)
                touched = True
            continue
        new_value = bool(new_value)
        if bool(getattr(assignment, name)) != new_value:
            setattr(assignment, name, new_value)
            touched = True

    wanted_roles = _wanted_role_ids(settings, project, assignment)
    if wanted_roles != set(assignment.allowed_role_ids or []):
        set_assignment_allowed_roles(assignment, wanted_roles)
        touched = True
    if _apply_reviewers(settings, assignment):
        touched = True

    page_after = bool(assignment.enable_page_submission)
    if page_before != page_after:
        apply_page_submission_mode_change(assignment, page_after, user_id)
        touched = True
    sync_assignment_custom_excel_flags(assignment)
    return touched


def apply_to_report(project: Project, assignment, *, user_id: Optional[int] = None) -> bool:
    """Copy the project's saved settings onto one report. No-op when settings do not exist yet."""
    settings = ProjectAssignment.query.filter_by(project_id=project.id).first()
    if settings is None:
        return False
    return _apply_one(settings, project, assignment, user_id=user_id)


def apply_to_reports(project: Project, *, user_id: Optional[int] = None) -> int:
    """Copy settings onto every report of the project. Returns how many reports changed."""
    settings = ProjectAssignment.query.filter_by(project_id=project.id).one()
    changed = 0
    for assignment in list_project_cycle_assignments(project):
        if _apply_one(settings, project, assignment, user_id=user_id):
            changed += 1
    return changed


def inherit_on_new_report(project: Project, assignment) -> None:
    """Give a newly created report the project settings, or the template export defaults.

    Existing reports are left alone so a re-import does not overwrite an admin's choices.
    """
    settings = ProjectAssignment.query.filter_by(project_id=project.id).first()
    if settings is None:
        _seed_export_flags_from_template(assignment)
        return
    _apply_one(settings, project, assignment, user_id=None)
