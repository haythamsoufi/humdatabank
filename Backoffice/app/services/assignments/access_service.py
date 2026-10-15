"""Assignment visibility policy: which assignments a user may see and work on.

Two independent restrictions are layered on top of the existing entity / RBAC checks.
A user reaches an assignment only when **both** allow it:

1. *User scope* — ``User.assignment_access_mode``. ``all`` (default) leaves every
   assignment reachable; ``selected`` limits the user to the assignments in
   ``user_assignment_access``.
2. *Assignment roles* — ``AssignedForm.allowed_roles``. No roles (default) means open to
   everyone; otherwise only users holding at least one of the listed RBAC roles.

System Managers are never restricted, so a mistaken configuration cannot lock the
platform out of its own assignments. The policy hides assignments; it never grants
access. Entity scope and permission checks still apply afterwards.

Use :func:`user_can_access_assigned_form` for a single assignment and
:func:`assignment_access_clause` to filter queries so lists and detail routes agree.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Set

from flask import current_app, g, has_app_context
from sqlalchemy import and_, exists, false, or_, select

from app import db
from app.models.assignments import (
    AssignedForm,
    assigned_form_allowed_role,
    user_assignment_access,
)

ACCESS_MODE_ALL = "all"
ACCESS_MODE_SELECTED = "selected"
ACCESS_MODES = (ACCESS_MODE_ALL, ACCESS_MODE_SELECTED)

_CACHE_ATTR = "_assignment_access_cache"


@dataclass(frozen=True)
class AssignmentAccessScope:
    """What one user may reach, resolved once per request."""

    unrestricted: bool
    # None = every assignment passes the user-scope check.
    selected_ids: Optional[frozenset]
    role_ids: frozenset


_UNRESTRICTED = AssignmentAccessScope(True, None, frozenset())
_NO_ACCESS = AssignmentAccessScope(False, frozenset(), frozenset())


def normalize_access_mode(value) -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in ACCESS_MODES else ACCESS_MODE_ALL


def _cache() -> Optional[dict]:
    if not has_app_context():
        return None
    cache = getattr(g, _CACHE_ATTR, None)
    if cache is None:
        cache = {"scope": {}, "allowed_roles": {}}
        setattr(g, _CACHE_ATTR, cache)
    return cache


def invalidate_cache() -> None:
    if has_app_context() and hasattr(g, _CACHE_ATTR):
        delattr(g, _CACHE_ATTR)


def _user_id(user) -> int:
    try:
        return int(getattr(user, "id", 0) or 0)
    except (TypeError, ValueError):
        return 0


def get_access_scope(user) -> AssignmentAccessScope:
    """Resolve the assignment scope for ``user`` (cached for the request)."""
    if user is None or not getattr(user, "is_authenticated", False):
        return _NO_ACCESS

    from app.services.organization.authorization_service import AuthorizationService

    if AuthorizationService.is_system_manager(user):
        return _UNRESTRICTED

    uid = _user_id(user)
    cache = _cache()
    if cache is not None and uid in cache["scope"]:
        return cache["scope"][uid]

    selected_ids: Optional[frozenset] = None
    if normalize_access_mode(getattr(user, "assignment_access_mode", None)) == ACCESS_MODE_SELECTED:
        rows = db.session.execute(
            select(user_assignment_access.c.assigned_form_id).where(
                user_assignment_access.c.user_id == uid
            )
        ).all()
        selected_ids = frozenset(int(r[0]) for r in rows)

    role_ids = frozenset(int(r) for r in AuthorizationService._get_role_ids_for_user_id(uid))
    scope = AssignmentAccessScope(False, selected_ids, role_ids)
    if cache is not None:
        cache["scope"][uid] = scope
    return scope


def allowed_role_ids_for_assignment(assigned_form_id: int) -> frozenset:
    """RBAC role ids an assignment is restricted to (empty = open)."""
    aid = int(assigned_form_id)
    cache = _cache()
    if cache is not None and aid in cache["allowed_roles"]:
        return cache["allowed_roles"][aid]
    rows = db.session.execute(
        select(assigned_form_allowed_role.c.role_id).where(
            assigned_form_allowed_role.c.assigned_form_id == aid
        )
    ).all()
    result = frozenset(int(r[0]) for r in rows)
    if cache is not None:
        cache["allowed_roles"][aid] = result
    return result


def user_can_access_assigned_form(user, assigned_form_id) -> bool:
    """Whether ``user`` passes both restrictions for this assignment."""
    if assigned_form_id is None:
        return False
    scope = get_access_scope(user)
    if scope.unrestricted:
        return True
    aid = int(assigned_form_id)
    if scope.selected_ids is not None and aid not in scope.selected_ids:
        return False
    allowed = allowed_role_ids_for_assignment(aid)
    return not allowed or bool(allowed & scope.role_ids)


def filter_accessible_assigned_form_ids(user, assigned_form_ids: Iterable[int]) -> Set[int]:
    """Subset of ``assigned_form_ids`` the user may access (one query for the role check)."""
    ids = {int(i) for i in assigned_form_ids if i is not None}
    scope = get_access_scope(user)
    if scope.unrestricted or not ids:
        return ids if scope.unrestricted else set()
    if scope.selected_ids is not None:
        ids &= scope.selected_ids
    if not ids:
        return set()
    restricted = {}
    rows = db.session.execute(
        select(
            assigned_form_allowed_role.c.assigned_form_id,
            assigned_form_allowed_role.c.role_id,
        ).where(assigned_form_allowed_role.c.assigned_form_id.in_(ids))
    ).all()
    for aid, rid in rows:
        restricted.setdefault(int(aid), set()).add(int(rid))
    return {
        aid for aid in ids
        if aid not in restricted or (restricted[aid] & scope.role_ids)
    }


def assignment_access_clause(user, assigned_form_id_column):
    """SQL condition limiting ``assigned_form_id_column`` to assignments ``user`` may access.

    Returns ``None`` when the user is unrestricted, so callers can skip the filter:

        clause = assignment_access_clause(current_user, AssignedForm.id)
        if clause is not None:
            query = query.filter(clause)
    """
    scope = get_access_scope(user)
    if scope.unrestricted:
        return None

    conditions = []
    if scope.selected_ids is not None:
        if not scope.selected_ids:
            return false()
        conditions.append(assigned_form_id_column.in_(sorted(scope.selected_ids)))

    any_role = exists(
        select(1).where(assigned_form_allowed_role.c.assigned_form_id == assigned_form_id_column)
    )
    if scope.role_ids:
        matching_role = exists(
            select(1).where(
                and_(
                    assigned_form_allowed_role.c.assigned_form_id == assigned_form_id_column,
                    assigned_form_allowed_role.c.role_id.in_(sorted(scope.role_ids)),
                )
            )
        )
        conditions.append(or_(~any_role, matching_role))
    else:
        conditions.append(~any_role)

    return and_(*conditions)


def apply_assignment_access(query, user, assigned_form_id_column):
    """Filter ``query`` in place of the manual ``assignment_access_clause`` dance."""
    clause = assignment_access_clause(user, assigned_form_id_column)
    return query if clause is None else query.filter(clause)


def set_assignment_allowed_roles(assignment: AssignedForm, role_ids: Iterable[int]) -> bool:
    """Replace the roles an assignment is restricted to. Returns True when it changed."""
    from app.models.rbac import RbacRole

    wanted = {int(r) for r in role_ids if r is not None}
    roles = RbacRole.query.filter(RbacRole.id.in_(wanted)).all() if wanted else []
    new_ids = {int(r.id) for r in roles}
    old_ids = {int(r.id) for r in assignment.allowed_roles}
    if new_ids == old_ids:
        return False
    assignment.allowed_roles = sorted(roles, key=lambda r: (r.name or "").lower())
    invalidate_cache()
    return True


def set_user_assignment_access(user, mode: str, assigned_form_ids: Iterable[int]) -> bool:
    """Set a user's assignment scope. Returns True when anything changed.

    ``selected_assignments`` is kept even while the mode is ``all`` so an admin can
    toggle back to ``selected`` without re-picking; only ``selected`` mode enforces it.
    """
    mode = normalize_access_mode(mode)
    wanted = {int(i) for i in assigned_form_ids if i is not None}
    forms = AssignedForm.query.filter(AssignedForm.id.in_(wanted)).all() if wanted else []
    new_ids = {int(f.id) for f in forms}
    old_ids = {int(f.id) for f in user.selected_assignments}
    old_mode = normalize_access_mode(user.assignment_access_mode)
    if mode == old_mode and new_ids == old_ids:
        return False
    user.assignment_access_mode = mode
    if new_ids != old_ids:
        user.selected_assignments = sorted(forms, key=lambda f: f.id)
    invalidate_cache()
    if mode == ACCESS_MODE_SELECTED and not new_ids:
        current_app.logger.info(
            "User %s set to 'selected' assignment access with no assignments", _user_id(user)
        )
    return True
