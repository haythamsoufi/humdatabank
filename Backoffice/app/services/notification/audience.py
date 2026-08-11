"""
Shared helpers for admin-capable (RBAC) recipient lists used by notification emitters.

**Separate buckets**

- **Org admins** (``admin_users``): ``admin_core`` and ``admin_*`` roles **with**
  ``UserEntityPermission`` for the entity (country / branch / …). Does **not** include
  ``system_manager``.
- **System managers** (``system_managers``): users with the ``system_manager`` RBAC role
  (deployment-wide).

Audience toggles are enforced via ``audience_bucket_enabled`` in ``app_settings_service``.
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Set

from sqlalchemy import or_, select

from app.models import User
from app.models.rbac import RbacRole, RbacUserRole


def _admin_capable_role_ids_subquery():
    """system_manager OR admin_core OR admin_* (legacy global helper)."""
    return select(RbacRole.id).where(
        or_(
            RbacRole.code == "system_manager",
            RbacRole.code == "admin_core",
            RbacRole.code.like("admin\\_%", escape="\\"),
        )
    )


def _non_system_manager_admin_role_ids_subquery():
    """admin_core OR admin_* — excludes ``system_manager``."""
    return select(RbacRole.id).where(
        or_(
            RbacRole.code == "admin_core",
            RbacRole.code.like("admin\\_%", escape="\\"),
        )
    )


def _system_manager_role_ids_subquery():
    return select(RbacRole.id).where(RbacRole.code == "system_manager")


def get_admin_capable_user_ids(
    exclude_user_ids: Optional[Iterable[int]] = None,
) -> List[int]:
    """
    Distinct user IDs with admin-capable roles (deployment-wide):
    ``system_manager``, ``admin_core``, or ``admin_%``.
    """
    exclude: Set[int] = set(int(x) for x in (exclude_user_ids or []) if x is not None)

    rows = (
        User.query.join(RbacUserRole, User.id == RbacUserRole.user_id)
        .filter(RbacUserRole.role_id.in_(_admin_capable_role_ids_subquery()))
        .distinct()
        .all()
    )
    return [u.id for u in rows if u.id not in exclude]


def get_system_manager_user_ids(
    exclude_user_ids: Optional[Iterable[int]] = None,
) -> List[int]:
    """Active users with the ``system_manager`` RBAC role (deployment-wide)."""
    exclude: Set[int] = set(int(x) for x in (exclude_user_ids or []) if x is not None)
    rows = (
        User.query.filter(User.active.is_(True))
        .join(RbacUserRole, RbacUserRole.user_id == User.id)
        .filter(RbacUserRole.role_id.in_(_system_manager_role_ids_subquery()))
        .distinct()
        .all()
    )
    return [u.id for u in rows if u.id not in exclude]


def get_entity_scoped_non_system_manager_admin_user_ids(
    entity_type: Optional[str],
    entity_id: Optional[int],
    exclude_user_ids: Optional[Iterable[int]] = None,
) -> List[int]:
    """
    Org admins covering this entity: ``admin_core`` / ``admin_*`` plus ``UserEntityPermission``.

    Excludes ``system_manager`` — use :func:`get_system_manager_user_ids` for that bucket.
    """
    if entity_type is None or entity_id is None:
        return []
    try:
        eid = int(entity_id)
    except (TypeError, ValueError):
        return []
    et = str(entity_type).strip()
    if not et:
        return []

    exclude: Set[int] = set(int(x) for x in (exclude_user_ids or []) if x is not None)

    from app.models.core import UserEntityPermission

    rows = (
        User.query.filter(User.active.is_(True))
        .join(UserEntityPermission, UserEntityPermission.user_id == User.id)
        .join(RbacUserRole, RbacUserRole.user_id == User.id)
        .filter(
            UserEntityPermission.entity_type == et,
            UserEntityPermission.entity_id == int(eid),
            RbacUserRole.role_id.in_(_non_system_manager_admin_role_ids_subquery()),
        )
        .distinct()
        .all()
    )
    return sorted({u.id for u in rows if u.id not in exclude})


def _global_admin_type_role_ids_subquery():
    """
    Roles that classify a user as Admin in user_form.html (never focal for notifications).

    ``system_manager`` and ``assignment_approver`` are global; entity-scoped org admins
    are excluded separately via :func:`get_entity_scoped_non_system_manager_admin_user_ids`.
    """
    return select(RbacRole.id).where(
        or_(
            RbacRole.code == "system_manager",
            RbacRole.code == "assignment_approver",
        )
    )


def _entity_scoped_org_admin_user_ids_subquery(entity_type: str, entity_id: int):
    """User IDs with admin_core / admin_* plus permission on this entity."""
    from app.models.core import UserEntityPermission

    return (
        select(UserEntityPermission.user_id)
        .join(RbacUserRole, RbacUserRole.user_id == UserEntityPermission.user_id)
        .filter(
            UserEntityPermission.entity_type == entity_type,
            UserEntityPermission.entity_id == int(entity_id),
            RbacUserRole.role_id.in_(_non_system_manager_admin_role_ids_subquery()),
        )
    )


def collect_entity_admin_audience_recipient_ids(
    notification_type,
    entity_type: Optional[str],
    entity_id: Optional[int],
    exclude_user_ids: Optional[Iterable[int]] = None,
) -> List[int]:
    """
    Union recipients enabled by ``admin_users`` and ``system_managers`` toggles for ``notification_type``.
    """
    from app.services.platform.app_settings_service import audience_bucket_enabled

    if entity_type is None or entity_id is None:
        return []

    out: Set[int] = set()
    if audience_bucket_enabled(notification_type, "admin_users"):
        out.update(
            get_entity_scoped_non_system_manager_admin_user_ids(
                entity_type, entity_id, exclude_user_ids=exclude_user_ids
            )
        )
    if audience_bucket_enabled(notification_type, "system_managers"):
        out.update(get_system_manager_user_ids(exclude_user_ids=exclude_user_ids))

    ex = set(int(x) for x in (exclude_user_ids or []) if x is not None)
    return sorted(x for x in out if x not in ex)


def get_assignment_editor_submitter_user_ids_for_entity(
    entity_type: str,
    entity_id: int,
    exclude_user_ids: Optional[Iterable[int]] = None,
) -> List[int]:
    """
    Focal/editor recipients for this entity: ``assignment_editor_submitter`` with
    ``UserEntityPermission``, excluding users treated as Admin (org admin for this
    entity, or global ``system_manager`` / ``assignment_approver``).
    """
    exclude: Set[int] = set(int(x) for x in (exclude_user_ids or []) if x is not None)

    from app.models.core import UserEntityPermission

    global_admin_users = select(RbacUserRole.user_id).where(
        RbacUserRole.role_id.in_(_global_admin_type_role_ids_subquery())
    )
    entity_org_admins = _entity_scoped_org_admin_user_ids_subquery(entity_type, entity_id)

    permissions = (
        UserEntityPermission.query.filter_by(entity_type=entity_type, entity_id=int(entity_id))
        .join(User, UserEntityPermission.user_id == User.id)
        .filter(User.active.is_(True))
        .join(RbacUserRole, RbacUserRole.user_id == User.id)
        .join(RbacRole, RbacUserRole.role_id == RbacRole.id)
        .filter(RbacRole.code == "assignment_editor_submitter")
        .filter(~UserEntityPermission.user_id.in_(entity_org_admins))
        .filter(~User.id.in_(global_admin_users))
        .distinct()
        .all()
    )
    seen: Set[int] = set()
    out: List[int] = []
    for perm in permissions:
        uid = perm.user_id
        if uid is None or uid in exclude or uid in seen:
            continue
        seen.add(uid)
        out.append(uid)
    return out
