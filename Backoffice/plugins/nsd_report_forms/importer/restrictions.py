"""Keep NSD reports away from everyone who is not an NSD user, with the platform's Access Groups.

Access to a report comes from a role plus access to its country, so an ordinary focal point of Thailand (FDRS, UPR ...)
would otherwise see the NSD reports of Thailand. Core's "assignment access control" (``AssignedForm.allowed_roles``)
limits an assignment to users who hold one of the listed roles or Access Groups; dashboards, APIs and direct links all
honour it, and System Managers are never restricted. The import sets, for every assignment it creates or updates:

  * quarterly reports: NSD NS focal point group, NSD IFRC project manager group, NSD funds admin role
  * final reports:     NSD IFRC project manager group, NSD funds admin role   (NS focal points never see them)
  * project records:   NSD funds admin role

Access Groups (``rbac_role.kind = 'group'``) hold no permissions, so they only scope; the NSD roles give the
permissions. The groups are created here when they do not exist. Entries are only ever added, never removed, so a
group an administrator adds by hand stays. Safe to run repeatedly.
"""
from typing import Dict, List

from app import db
from app.models.rbac import RbacRole

from ..plugin import NSD_ADMIN_ROLE, NSD_GROUP_FOCAL, NSD_GROUP_PM, NSD_GROUPS

POLICY = {
    'profile': (NSD_ADMIN_ROLE,),
    'CBF quarter': (NSD_GROUP_FOCAL, NSD_GROUP_PM, NSD_ADMIN_ROLE),
    'CBF final report': (NSD_GROUP_PM, NSD_ADMIN_ROLE),
}


def load_roles() -> Dict[str, RbacRole]:
    codes = {c for roles in POLICY.values() for c in roles}
    return {r.code: r for r in RbacRole.query.filter(RbacRole.code.in_(codes)).all()}


def missing_roles(roles: Dict[str, RbacRole]) -> List[str]:
    """Seeded roles that do not exist yet (the groups are not listed: ``ensure_groups`` creates them)."""
    wanted = {c for r in POLICY.values() for c in r} - set(NSD_GROUPS)
    return sorted(wanted - set(roles))


def ensure_groups(roles: Dict[str, RbacRole]) -> int:
    """Create the NSD Access Groups that are missing and add them to ``roles``. Returns how many were created.

    Needs core's ``rbac_role.kind`` column (Access Groups). Without it the groups are created as plain roles, which
    restrict assignments the same way.
    """
    made = 0
    has_kind = hasattr(RbacRole, 'kind')
    for code, (name, description) in NSD_GROUPS.items():
        if code in roles:
            continue
        extra = {'kind': 'group'} if has_kind else {}
        role = RbacRole(code=code, name=name, description=description, **extra)
        db.session.add(role)
        roles[code] = role
        made += 1
    if made:
        db.session.flush()
    return made


def restrict(assigned_form, key: str, roles: Dict[str, RbacRole]) -> bool:
    """Make sure the assignment lists the roles and groups the policy gives its report type. True when added."""
    held = {r.id for r in assigned_form.allowed_roles}
    added = False
    for code in POLICY.get(key, ()):
        role = roles.get(code)
        if role is not None and role.id not in held:
            assigned_form.allowed_roles.append(role)
            added = True
    return added
