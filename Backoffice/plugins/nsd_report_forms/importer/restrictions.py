"""NSD Access Groups and permission-role helpers for the importer.

Access Groups (``RbacRole.kind == 'group'``) decide who may open an NSD
assignment when the slot's audience is restricted. Permission roles still
answer what a user can do (enter/submit). The importer:

- ensures the ``NSD Focal Points`` and ``NSD PMs`` Access Groups exist
- creates missing contact users and adds them to the right group
- grants country entity access and the Assignment Editor/Submitter role
- grants the NSD PM overview permission role to IFRC project managers
"""
from __future__ import annotations

import logging
import secrets
from typing import Dict, List, Optional, Tuple

from app import db
from app.models import User
from app.models.rbac import ROLE_KIND_GROUP, RbacRole, RbacUserRole

from ..plugin import NSD_ADMIN_ROLE, NSD_PM_PERMISSION

log = logging.getLogger(__name__)

# Access Groups (kind=group) — display names match User Management → Access Groups
FOCAL_GROUP_CODE = "group_nsd_focal_points"
FOCAL_GROUP_NAME = "NSD Focal Points"
PM_GROUP_CODE = "group_nsd_pms"
PM_GROUP_NAME = "NSD PMs"

# Permission role so PMs can open Explore Data → NSD funds / My projects
PM_OVERVIEW_ROLE_CODE = "nsd_pm_overview"
PM_OVERVIEW_ROLE_NAME = "NSD funds: my projects"

EDITOR_ROLE_CODE = "assignment_editor_submitter"


def load_roles() -> Dict[str, RbacRole]:
    """The NSD admin permission role, if it has been seeded."""
    return {
        r.code: r
        for r in RbacRole.query.filter(RbacRole.code == NSD_ADMIN_ROLE).all()
    }


def missing_roles(roles: Dict[str, RbacRole]) -> List[str]:
    """Seeded permission roles the importer expects and that are not in ``roles``."""
    if NSD_ADMIN_ROLE in roles:
        return []
    return [NSD_ADMIN_ROLE]


def _slug_ok(code: str) -> str:
    return (code or "").strip().lower()


def ensure_access_group(code: str, name: str, description: str = "") -> RbacRole:
    """Return the Access Group, creating it when missing (matched by code or name)."""
    code = _slug_ok(code)
    group = RbacRole.query.filter_by(code=code).first()
    if group is None:
        group = (
            RbacRole.query.filter(
                RbacRole.kind == ROLE_KIND_GROUP,
                RbacRole.name == name,
            ).first()
        )
    if group is None:
        # Tolerate "NSD PM" vs "NSD PMs"
        group = (
            RbacRole.query.filter(
                RbacRole.kind == ROLE_KIND_GROUP,
                RbacRole.name.ilike(name.rstrip("s") + "%"),
            ).first()
        )
    if group is None:
        group = RbacRole(
            code=code,
            name=name,
            description=description
            or f"NSD CBF contacts ({name}). Membership is set by the master import.",
            kind=ROLE_KIND_GROUP,
        )
        db.session.add(group)
        db.session.flush()
        log.info("NSD import: created Access Group %r (%s)", name, code)
        return group

    if group.kind != ROLE_KIND_GROUP:
        group.kind = ROLE_KIND_GROUP
    if (group.name or "").strip() != name:
        # Keep the admin-facing name stable when we created an alternate spelling
        if not group.name:
            group.name = name
    return group


def ensure_nsd_access_groups() -> Dict[str, RbacRole]:
    """Ensure both NSD contact Access Groups exist. Keys: ``focal``, ``pm``."""
    return {
        "focal": ensure_access_group(
            FOCAL_GROUP_CODE,
            FOCAL_GROUP_NAME,
            "National Society focal persons for NSD CBF projects. Audience: Final reports only.",
        ),
        "pm": ensure_access_group(
            PM_GROUP_CODE,
            PM_GROUP_NAME,
            "IFRC project managers for NSD CBF projects. Audience: all report slots (quarters + Final).",
        ),
    }


def _ensure_permission_role(code: str, name: str, permission_codes: List[str]) -> RbacRole:
    from app.models.rbac import ROLE_KIND_PERMISSION, RbacPermission, RbacRolePermission

    role = RbacRole.query.filter_by(code=code).first()
    if role is None:
        role = RbacRole(
            code=code,
            name=name,
            description=name,
            kind=ROLE_KIND_PERMISSION,
        )
        db.session.add(role)
        db.session.flush()
    elif role.kind == ROLE_KIND_GROUP:
        # Never overwrite an Access Group with the same code
        raise RuntimeError(f"RBAC code {code!r} is an Access Group; cannot attach permissions")

    for perm_code in permission_codes:
        perm = RbacPermission.query.filter_by(code=perm_code).first()
        if perm is None:
            perm = RbacPermission(code=perm_code, name=perm_code, description=perm_code)
            db.session.add(perm)
            db.session.flush()
        link = RbacRolePermission.query.filter_by(role_id=role.id, permission_id=perm.id).first()
        if link is None:
            db.session.add(RbacRolePermission(role_id=role.id, permission_id=perm.id))
    return role


def _ensure_user_in_role(user_id: int, role: RbacRole) -> bool:
    existing = RbacUserRole.query.filter_by(user_id=user_id, role_id=role.id).first()
    if existing:
        return False
    db.session.add(RbacUserRole(user_id=user_id, role_id=role.id))
    return True


def ensure_contact_user(
    *,
    email: str,
    name: str = "",
    group: RbacRole,
    also_roles: Optional[List[RbacRole]] = None,
) -> Tuple[User, bool]:
    """Get or create a user for an NSD contact email and put them in ``group``.

    Returns ``(user, created)``. New users are active with a random unusable
    password (SSO accounts); existing users are left as-is aside from group/role links.
    """
    email_clean = (email or "").strip()
    if not email_clean or "@" not in email_clean:
        raise ValueError("email required")

    user = User.query.filter(User.email.ilike(email_clean)).first()
    created = False
    if user is None:
        display = (name or "").strip() or email_clean.split("@", 1)[0]
        user = User(email=email_clean, name=display[:100], active=True)
        # Random password so the account is not blank-loginable; SSO/invite still works.
        user.set_password(secrets.token_urlsafe(32))
        db.session.add(user)
        db.session.flush()
        created = True
        log.info("NSD import: created user %s", email_clean)
    else:
        if not (user.name or "").strip() and (name or "").strip():
            user.name = name.strip()[:100]
        if not user.active:
            user.active = True

    _ensure_user_in_role(user.id, group)
    for role in also_roles or []:
        _ensure_user_in_role(user.id, role)
    return user, created


def ensure_editor_role() -> RbacRole:
    role = RbacRole.query.filter_by(code=EDITOR_ROLE_CODE).first()
    if role is None:
        role = RbacRole(
            code=EDITOR_ROLE_CODE,
            name="Assignment Editor/Submitter",
            description="Enter/edit/submit assignments for assigned entities",
            kind="permission",
        )
        db.session.add(role)
        db.session.flush()
    return role


def ensure_pm_overview_role() -> RbacRole:
    return _ensure_permission_role(
        PM_OVERVIEW_ROLE_CODE,
        PM_OVERVIEW_ROLE_NAME,
        [NSD_PM_PERMISSION],
    )


def attach_groups_to_assignment(assigned_form_id: int, groups: List[RbacRole]) -> None:
    """Ensure each Access Group is listed on the assignment audience (idempotent add)."""
    from app.models.assignments import assigned_form_allowed_role
    from app.utils.datetime_helpers import utcnow

    if not groups:
        return
    existing = {
        int(r[0])
        for r in db.session.execute(
            db.select(assigned_form_allowed_role.c.role_id).where(
                assigned_form_allowed_role.c.assigned_form_id == int(assigned_form_id)
            )
        ).all()
    }
    for group in groups:
        if int(group.id) in existing:
            continue
        db.session.execute(
            assigned_form_allowed_role.insert().values(
                assigned_form_id=int(assigned_form_id),
                role_id=int(group.id),
                created_at=utcnow(),
            )
        )


def sync_nsd_audience_on_assignment(
    assigned_form_id: int,
    *,
    allow_focal: bool,
    allow_pm: bool = True,
) -> None:
    """Set NSD Access Group audience for a shared slot.

    Only the two NSD groups are managed; any other audience groups are left alone.
    - Final slots: Focal Points + PMs
    - Quarter slots: PMs only
    """
    from app.models.assignments import assigned_form_allowed_role
    from app.utils.datetime_helpers import utcnow

    groups = ensure_nsd_access_groups()
    managed = {int(groups["focal"].id), int(groups["pm"].id)}
    desired = set()
    if allow_focal:
        desired.add(int(groups["focal"].id))
    if allow_pm:
        desired.add(int(groups["pm"].id))

    existing = {
        int(r[0])
        for r in db.session.execute(
            db.select(assigned_form_allowed_role.c.role_id).where(
                assigned_form_allowed_role.c.assigned_form_id == int(assigned_form_id)
            )
        ).all()
    }

    for role_id in sorted(desired - existing):
        db.session.execute(
            assigned_form_allowed_role.insert().values(
                assigned_form_id=int(assigned_form_id),
                role_id=role_id,
                created_at=utcnow(),
            )
        )

    stale = (existing & managed) - desired
    if stale:
        db.session.execute(
            assigned_form_allowed_role.delete().where(
                assigned_form_allowed_role.c.assigned_form_id == int(assigned_form_id),
                assigned_form_allowed_role.c.role_id.in_(sorted(stale)),
            )
        )
