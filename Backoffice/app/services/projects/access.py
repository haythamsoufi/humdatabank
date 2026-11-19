"""Who may see and edit projects in the admin assignments UI."""

from __future__ import annotations

from app.models.projects import Project
from app.services.organization.authorization_service import AuthorizationService

PM_PERMISSION = "nsd_funds.pm_overview"
NSD_ADMIN_PERMISSION = "admin.nsd_funds.manage"


def can_manage_projects(user) -> bool:
    return AuthorizationService.is_system_manager(user) or AuthorizationService.has_rbac_permission(
        user, "admin.assignments.edit"
    )


def can_view_all_projects(user) -> bool:
    return (
        AuthorizationService.is_system_manager(user)
        or AuthorizationService.has_rbac_permission(user, "admin.assignments.view")
        or AuthorizationService.has_rbac_permission(user, "admin.assignments.edit")
        or AuthorizationService.has_rbac_permission(user, NSD_ADMIN_PERMISSION)
    )


def is_pm_viewer(user) -> bool:
    return AuthorizationService.has_rbac_permission(user, PM_PERMISSION)


def can_open_project_admin(user) -> bool:
    return can_view_all_projects(user) or is_pm_viewer(user)


def can_see_project(user, project: Project) -> bool:
    if can_view_all_projects(user):
        return True
    if not is_pm_viewer(user):
        return False
    return (project.manager_email or "").strip().casefold() == (getattr(user, "email", "") or "").strip().casefold()


def scope_manager(user, requested: str) -> tuple:
    """(manager email filter, scoped_to_self). PM-only viewers always see their own projects."""
    if can_view_all_projects(user):
        return requested, False
    return (getattr(user, "email", "") or "").strip(), True
