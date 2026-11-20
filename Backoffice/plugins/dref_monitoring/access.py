"""Who can see an operation, and which tier they act at.

A Backoffice role is the capability. Country access or an operation membership
is the scope. A membership tier can narrow a higher role on that operation.
Portfolio permission and system managers see every operation.
"""

from __future__ import annotations

from dataclasses import dataclass

from flask_login import current_user

from app.models.core import UserEntityPermission
from app.services.organization.authorization_service import AuthorizationService
from plugins.dref_monitoring.constants import (
    ENTER_PERMISSION,
    MANAGE_PERMISSION,
    PORTFOLIO_PERMISSION,
    REVIEW_PERMISSION,
    VALIDATE_PERMISSION,
)
from plugins.dref_monitoring.models import DrefMember, DrefOperation

_RANK = {"enter": 1, "validate": 2, "review": 3, "portfolio": 4}
_ACTION = {"view": 1, "enter": 1, "validate": 2, "review": 3, "portfolio": 4, "manage": 4}


@dataclass(frozen=True)
class Actor:
    user_id: int | None
    is_manager: bool
    permissions: frozenset[str]
    country_ids: frozenset[int]
    memberships: dict[int, str]

    def rbac_rank(self) -> int:
        if PORTFOLIO_PERMISSION in self.permissions:
            return 4
        if REVIEW_PERMISSION in self.permissions:
            return 3
        if VALIDATE_PERMISSION in self.permissions:
            return 2
        if ENTER_PERMISSION in self.permissions:
            return 1
        return 0

    def rank_on(self, operation: DrefOperation) -> int:
        if self.is_manager or PORTFOLIO_PERMISSION in self.permissions:
            return 4
        capability = self.rbac_rank()
        rank = 0
        if operation.country_id and operation.country_id in self.country_ids:
            rank = capability
        tier = self.memberships.get(operation.id)
        if tier and capability:
            rank = max(rank, min(capability, _RANK.get(tier, 0)))
        return rank

    def allows(self, operation: DrefOperation, action: str) -> bool:
        needed = _ACTION.get(action, 99)
        if action == "view":
            return self.rank_on(operation) >= 1
        return self.rank_on(operation) >= needed


def actor_for_user(user) -> Actor:
    if user is None or not getattr(user, "is_authenticated", False):
        return Actor(None, False, frozenset(), frozenset(), {})
    user_id = int(user.id)
    is_manager = AuthorizationService.is_system_manager(user) or AuthorizationService.has_rbac_permission(
        user, MANAGE_PERMISSION
    )
    permissions = frozenset(
        code
        for code in (
            ENTER_PERMISSION,
            VALIDATE_PERMISSION,
            REVIEW_PERMISSION,
            PORTFOLIO_PERMISSION,
            MANAGE_PERMISSION,
        )
        if AuthorizationService.has_rbac_permission(user, code)
    )
    country_ids = frozenset(
        row.entity_id
        for row in UserEntityPermission.query.filter_by(user_id=user_id, entity_type="country").all()
    )
    memberships = {
        row.operation_id: row.tier
        for row in DrefMember.query.filter_by(user_id=user_id).all()
    }
    return Actor(user_id, bool(is_manager), permissions, country_ids, memberships)


def current_actor() -> Actor:
    return actor_for_user(current_user)


_CAPABILITY_CODES = (
    ENTER_PERMISSION,
    VALIDATE_PERMISSION,
    REVIEW_PERMISSION,
    PORTFOLIO_PERMISSION,
    MANAGE_PERMISSION,
)


def capable_users_query():
    """Active users who hold a DREF monitoring permission through a role.

    A membership only narrows a role, so these are the only people it can help.
    System managers already see every operation and are left out.
    """
    from app.extensions import db
    from app.models.core import User
    from app.models.rbac import RbacPermission, RbacRolePermission, RbacUserRole

    holders = (
        db.session.query(RbacUserRole.user_id)
        .join(RbacRolePermission, RbacRolePermission.role_id == RbacUserRole.role_id)
        .join(RbacPermission, RbacPermission.id == RbacRolePermission.permission_id)
        .filter(RbacPermission.code.in_(_CAPABILITY_CODES))
    )
    return User.query.filter(User.active.is_(True), User.id.in_(holders))


def user_is_capable(user_id: int) -> bool:
    return capable_users_query().filter_by(id=user_id).first() is not None


def operations_for(actor: Actor):
    query = DrefOperation.query
    if actor.is_manager or PORTFOLIO_PERMISSION in actor.permissions:
        return query
    clauses = []
    if actor.country_ids and actor.rbac_rank():
        clauses.append(DrefOperation.country_id.in_(list(actor.country_ids)))
    member_ids = [op_id for op_id, tier in actor.memberships.items() if _RANK.get(tier, 0) and actor.rbac_rank()]
    if member_ids:
        clauses.append(DrefOperation.id.in_(member_ids))
    if not clauses:
        return query.filter(DrefOperation.id == -1)
    if len(clauses) == 1:
        return query.filter(clauses[0])
    from app.extensions import db

    return query.filter(db.or_(*clauses))
