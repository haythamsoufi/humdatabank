"""Assignment visibility policy: which assignments a user may see and work on.

Two independent restrictions are layered on top of the existing entity / RBAC checks.
A user reaches an assignment only when **both** allow it. Neither one widens the other:

1. *Personal scope* — ``User.assignment_access_mode``. ``all`` (default) adds no
   personal shortlist; ``selected`` limits the user to ``user_assignment_access``;
   ``templates`` limits them to current and future assignments of the templates in
   ``user_assignment_template_access``. This only narrows.
2. *Audience* — access groups on ``AssignedForm.allowed_roles`` (``RbacRole.kind == 'group'``).
   No groups means anyone who passes the personal scope. Otherwise the user must
   belong to at least one listed group. Permission roles never count, on either side.
   A personal scope of ``all`` does not bypass this.

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
from sqlalchemy.orm import aliased

from app import db
from app.models.assignments import (
    AssignedForm,
    assigned_form_allowed_role,
    user_assignment_access,
    user_assignment_template_access,
)

ACCESS_MODE_ALL = "all"
ACCESS_MODE_SELECTED = "selected"
ACCESS_MODE_TEMPLATES = "templates"
ACCESS_MODES = (ACCESS_MODE_ALL, ACCESS_MODE_SELECTED, ACCESS_MODE_TEMPLATES)

_CACHE_ATTR = "_assignment_access_cache"


@dataclass(frozen=True)
class AssignmentAccessScope:
    """What one user may reach, resolved once per request."""

    unrestricted: bool
    # None = every assignment passes the specific-assignment check.
    selected_ids: Optional[frozenset]
    role_ids: frozenset
    # None = not limited by template. Empty = templates mode with nothing ticked.
    template_ids: Optional[frozenset] = None
    mode: str = ACCESS_MODE_ALL


_UNRESTRICTED = AssignmentAccessScope(True, None, frozenset(), None, ACCESS_MODE_ALL)
_NO_ACCESS = AssignmentAccessScope(False, frozenset(), frozenset(), frozenset(), ACCESS_MODE_SELECTED)


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

    mode = normalize_access_mode(getattr(user, "assignment_access_mode", None))
    selected_ids: Optional[frozenset] = None
    template_ids: Optional[frozenset] = None
    if mode == ACCESS_MODE_SELECTED:
        rows = db.session.execute(
            select(user_assignment_access.c.assigned_form_id).where(
                user_assignment_access.c.user_id == uid
            )
        ).all()
        selected_ids = frozenset(int(r[0]) for r in rows)
    elif mode == ACCESS_MODE_TEMPLATES:
        rows = db.session.execute(
            select(user_assignment_template_access.c.template_id).where(
                user_assignment_template_access.c.user_id == uid
            )
        ).all()
        template_ids = frozenset(int(r[0]) for r in rows)

    role_ids = _group_ids_for_user(uid)
    scope = AssignmentAccessScope(False, selected_ids, role_ids, template_ids, mode)
    if cache is not None:
        cache["scope"][uid] = scope
    return scope


def _group_ids_for_user(user_id: int) -> frozenset:
    """Access Group ids this user belongs to. Permission roles are not included."""
    from app.models.rbac import ROLE_KIND_GROUP, RbacRole, RbacUserRole

    rows = db.session.execute(
        select(RbacUserRole.role_id)
        .join(RbacRole, RbacRole.id == RbacUserRole.role_id)
        .where(RbacUserRole.user_id == int(user_id), RbacRole.kind == ROLE_KIND_GROUP)
    ).all()
    return frozenset(int(r[0]) for r in rows)


def _group_audience_clause():
    """Link rows that are Access Groups. Permission roles on the link table are ignored."""
    from app.models.rbac import ROLE_KIND_GROUP, RbacRole

    return and_(
        assigned_form_allowed_role.c.role_id == RbacRole.id,
        RbacRole.kind == ROLE_KIND_GROUP,
    )


def allowed_role_ids_for_assignment(assigned_form_id: int) -> frozenset:
    """Access Group ids an assignment is restricted to (empty = no audience limit)."""
    from app.models.rbac import ROLE_KIND_GROUP, RbacRole

    aid = int(assigned_form_id)
    cache = _cache()
    if cache is not None and aid in cache["allowed_roles"]:
        return cache["allowed_roles"][aid]
    rows = db.session.execute(
        select(assigned_form_allowed_role.c.role_id)
        .join(RbacRole, RbacRole.id == assigned_form_allowed_role.c.role_id)
        .where(
            assigned_form_allowed_role.c.assigned_form_id == aid,
            RbacRole.kind == ROLE_KIND_GROUP,
        )
    ).all()
    result = frozenset(int(r[0]) for r in rows)
    if cache is not None:
        cache["allowed_roles"][aid] = result
    return result


def _template_id_for_assignment(assigned_form_id: int) -> Optional[int]:
    aid = int(assigned_form_id)
    cache = _cache()
    mapping = None
    if cache is not None:
        mapping = cache.setdefault("template_by_assignment", {})
        if aid in mapping:
            return mapping[aid]
    row = db.session.execute(
        select(AssignedForm.template_id).where(AssignedForm.id == aid)
    ).first()
    template_id = int(row[0]) if row and row[0] is not None else None
    if mapping is not None:
        mapping[aid] = template_id
    return template_id


def _passes_user_scope(scope: AssignmentAccessScope, assigned_form_id: int) -> bool:
    if scope.mode == ACCESS_MODE_SELECTED:
        return assigned_form_id in (scope.selected_ids or frozenset())
    if scope.mode == ACCESS_MODE_TEMPLATES:
        template_id = _template_id_for_assignment(assigned_form_id)
        return template_id is not None and template_id in (scope.template_ids or frozenset())
    return True


def user_can_access_assigned_form(user, assigned_form_id) -> bool:
    """Whether ``user`` passes both restrictions for this assignment."""
    if assigned_form_id is None:
        return False
    scope = get_access_scope(user)
    if scope.unrestricted:
        return True
    aid = int(assigned_form_id)
    if not _passes_user_scope(scope, aid):
        return False
    allowed = allowed_role_ids_for_assignment(aid)
    return not allowed or bool(allowed & scope.role_ids)


def filter_accessible_assigned_form_ids(user, assigned_form_ids: Iterable[int]) -> Set[int]:
    """Subset of ``assigned_form_ids`` the user may access (one query for the role check)."""
    ids = {int(i) for i in assigned_form_ids if i is not None}
    scope = get_access_scope(user)
    if scope.unrestricted or not ids:
        return ids if scope.unrestricted else set()
    if scope.mode == ACCESS_MODE_SELECTED:
        ids &= scope.selected_ids or frozenset()
    elif scope.mode == ACCESS_MODE_TEMPLATES:
        if not ids or not scope.template_ids:
            return set()
        rows = db.session.execute(
            select(AssignedForm.id).where(
                AssignedForm.id.in_(ids),
                AssignedForm.template_id.in_(sorted(scope.template_ids)),
            )
        ).all()
        ids = {int(r[0]) for r in rows}
    if not ids:
        return set()
    restricted = {}
    from app.models.rbac import ROLE_KIND_GROUP, RbacRole

    rows = db.session.execute(
        select(
            assigned_form_allowed_role.c.assigned_form_id,
            assigned_form_allowed_role.c.role_id,
        )
        .join(RbacRole, RbacRole.id == assigned_form_allowed_role.c.role_id)
        .where(
            assigned_form_allowed_role.c.assigned_form_id.in_(ids),
            RbacRole.kind == ROLE_KIND_GROUP,
        )
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
    if scope.mode == ACCESS_MODE_SELECTED:
        if not scope.selected_ids:
            return false()
        conditions.append(assigned_form_id_column.in_(sorted(scope.selected_ids)))
    elif scope.mode == ACCESS_MODE_TEMPLATES:
        if not scope.template_ids:
            return false()
        # Alias so this subquery is not auto-correlated away when the outer
        # query is already selecting from assigned_form.
        assignment_alias = aliased(AssignedForm)
        conditions.append(
            assigned_form_id_column.in_(
                select(assignment_alias.id).where(
                    assignment_alias.template_id.in_(sorted(scope.template_ids))
                )
            )
        )

    audience = _group_audience_clause()
    any_group = exists(
        select(1).where(
            and_(
                assigned_form_allowed_role.c.assigned_form_id == assigned_form_id_column,
                audience,
            )
        )
    )
    if scope.role_ids:
        matching_group = exists(
            select(1).where(
                and_(
                    assigned_form_allowed_role.c.assigned_form_id == assigned_form_id_column,
                    assigned_form_allowed_role.c.role_id.in_(sorted(scope.role_ids)),
                    audience,
                )
            )
        )
        conditions.append(or_(~any_group, matching_group))
    else:
        conditions.append(~any_group)

    return and_(*conditions)


def apply_assignment_access(query, user, assigned_form_id_column):
    """Filter ``query`` in place of the manual ``assignment_access_clause`` dance."""
    clause = assignment_access_clause(user, assigned_form_id_column)
    return query if clause is None else query.filter(clause)


def set_assignment_allowed_roles(assignment: AssignedForm, role_ids: Iterable[int]) -> bool:
    """Replace the access groups an assignment is restricted to. Returns True when it changed.

    Permission roles are dropped. An audience is groups only; a posted permission
    role must not lock the assignment or let that role's holders through.
    """
    from app.models.rbac import ROLE_KIND_GROUP, RbacRole

    wanted = {int(r) for r in role_ids if r is not None}
    roles = (
        RbacRole.query.filter(RbacRole.id.in_(wanted), RbacRole.kind == ROLE_KIND_GROUP).all()
        if wanted
        else []
    )
    new_ids = {int(r.id) for r in roles}
    old_ids = {int(r.id) for r in assignment.allowed_roles}
    if new_ids == old_ids:
        return False
    assignment.allowed_roles = sorted(roles, key=lambda r: (r.name or "").lower())
    invalidate_cache()
    return True


def set_user_assignment_access(
    user,
    mode: str,
    assigned_form_ids: Iterable[int],
    template_ids: Optional[Iterable[int]] = None,
) -> bool:
    """Set a user's assignment scope. Returns True when anything changed.

    Picks are kept when the mode changes so an admin can toggle between
    ``selected`` and ``templates`` without re-picking. Only the active mode is
    enforced. Pass ``template_ids=None`` to leave the saved templates untouched.
    """
    from app.models import FormTemplate

    mode = normalize_access_mode(mode)
    wanted = {int(i) for i in assigned_form_ids if i is not None}
    forms = AssignedForm.query.filter(AssignedForm.id.in_(wanted)).all() if wanted else []
    new_ids = {int(f.id) for f in forms}
    old_ids = {int(f.id) for f in user.selected_assignments}
    old_mode = normalize_access_mode(user.assignment_access_mode)

    templates_changed = False
    if template_ids is not None:
        wanted_templates = {int(i) for i in template_ids if i is not None}
        templates = (
            FormTemplate.query.filter(FormTemplate.id.in_(wanted_templates)).all()
            if wanted_templates
            else []
        )
        new_template_ids = {int(t.id) for t in templates}
        old_template_ids = {int(t.id) for t in user.selected_assignment_templates}
        if new_template_ids != old_template_ids:
            user.selected_assignment_templates = sorted(
                templates, key=lambda t: ((t.name or "").lower(), t.id)
            )
            templates_changed = True

    if mode == old_mode and new_ids == old_ids and not templates_changed:
        return False
    user.assignment_access_mode = mode
    if new_ids != old_ids:
        user.selected_assignments = sorted(forms, key=lambda f: f.id)
    invalidate_cache()
    if mode == ACCESS_MODE_SELECTED and not new_ids:
        current_app.logger.info(
            "User %s set to 'selected' assignment access with no assignments", _user_id(user)
        )
    if mode == ACCESS_MODE_TEMPLATES and template_ids is not None and not {
        int(t.id) for t in user.selected_assignment_templates
    }:
        current_app.logger.info(
            "User %s set to 'templates' assignment access with no templates", _user_id(user)
        )
    return True
