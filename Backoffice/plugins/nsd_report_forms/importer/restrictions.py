"""NSD permission-role lookup for the importer.

Access Groups are not created or assigned here. Groups are managed under
User Management → Access Groups, membership is set on the user form or the
group's member list, and an assignment's "Who can access this assignment"
picker decides which groups may open it.
"""
from typing import Dict, List

from app.models.rbac import RbacRole

from ..plugin import NSD_ADMIN_ROLE


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
