"""Keep NSD reports away from everyone who is not an NSD user, with the platform's own assignment role restriction.

Access to a report comes from a role plus access to its country, so an ordinary focal point of Thailand (FDRS, UPR ...)
would otherwise see the NSD reports of Thailand. Core's "assignment access control" (``AssignedForm.allowed_roles``)
limits an assignment to users holding one of the listed roles; dashboards, APIs and direct links all honour it, and
System Managers are never restricted. The import sets, for every assignment it creates or updates:

  * quarterly reports: NSD NS focal point, NSD IFRC project manager, NSD funds admin
  * final reports:     NSD IFRC project manager, NSD funds admin   (NS focal points never see them)
  * project records:   NSD funds admin

Roles are only ever added, never removed, so a role an administrator adds by hand stays. Safe to run repeatedly.
"""
from typing import Dict, List

from app.models.rbac import RbacRole

from ..plugin import NSD_ADMIN_ROLE, NSD_ROLE_FOCAL, NSD_ROLE_PM

POLICY = {
    'profile': (NSD_ADMIN_ROLE,),
    'CBF quarter': (NSD_ROLE_FOCAL, NSD_ROLE_PM, NSD_ADMIN_ROLE),
    'CBF final report': (NSD_ROLE_PM, NSD_ADMIN_ROLE),
}


def load_roles() -> Dict[str, RbacRole]:
    codes = {c for roles in POLICY.values() for c in roles}
    return {r.code: r for r in RbacRole.query.filter(RbacRole.code.in_(codes)).all()}


def missing_roles(roles: Dict[str, RbacRole]) -> List[str]:
    wanted = {c for r in POLICY.values() for c in r}
    return sorted(wanted - set(roles))


def restrict(assigned_form, key: str, roles: Dict[str, RbacRole]) -> bool:
    """Make sure the assignment lists the roles the policy gives its report type. True when something was added."""
    held = {r.id for r in assigned_form.allowed_roles}
    added = False
    for code in POLICY.get(key, ()):
        role = roles.get(code)
        if role is not None and role.id not in held:
            assigned_form.allowed_roles.append(role)
            added = True
    return added
