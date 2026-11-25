"""The Emergency Operations access group is who may open a reporting assignment.

The group is organizational membership (``RbacRole.kind == 'group'``), not a
permission role. System managers stay unrestricted by the assignment audience
check. Everyone else must belong to this group.
"""

from __future__ import annotations

import logging

from flask import has_request_context
from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.rbac import ROLE_KIND_GROUP, RbacRole

log = logging.getLogger(__name__)

GROUP_CODE = "group_emergency_operations"
GROUP_NAME = "Emergency Operations"

_backfilled_for = None


def ensure_dref_access_group() -> RbacRole | None:
    """Return the Emergency Operations access group, creating it when neither the code nor the name exists."""
    group = RbacRole.query.filter_by(code=GROUP_CODE).first()
    if group is not None and group.kind != ROLE_KIND_GROUP:
        group = None
    if group is None:
        group = (
            RbacRole.query.filter(
                RbacRole.kind == ROLE_KIND_GROUP,
                db.func.lower(RbacRole.name) == GROUP_NAME.lower(),
            )
            .order_by(RbacRole.id.asc())
            .first()
        )
    if group is not None:
        return group
    group = RbacRole(
        code=GROUP_CODE,
        name=GROUP_NAME,
        description="People who may open and file Emergency Operations assignments.",
        kind=ROLE_KIND_GROUP,
    )
    db.session.add(group)
    nested = db.session.begin_nested()
    try:
        db.session.flush()
        nested.commit()
    except IntegrityError:
        nested.rollback()
        db.session.expunge(group)
        group = RbacRole.query.filter(
            or_(
                RbacRole.code == GROUP_CODE,
                and_(RbacRole.kind == ROLE_KIND_GROUP, db.func.lower(RbacRole.name) == GROUP_NAME.lower()),
            )
        ).first()
        if group is None or group.kind != ROLE_KIND_GROUP:
            log.warning("Emergency Operations access group could not be created", exc_info=True)
            return None
    else:
        log.info("Created access group %s (%s)", GROUP_NAME, GROUP_CODE)
    return group


def attach_dref_audience(assignment) -> bool:
    """Require the Emergency Operations access group on this assignment. Other groups stay."""
    if assignment is None:
        return False
    group = ensure_dref_access_group()
    if group is None:
        return False
    current = {int(role.id) for role in (assignment.allowed_roles or [])}
    if int(group.id) in current:
        return False
    from app.services.assignments.access_service import set_assignment_allowed_roles

    set_assignment_allowed_roles(assignment, current | {int(group.id)})
    return True


def restrict_dref_assignments() -> int:
    """Add the Emergency Operations access group to every reporting assignment that does not have it yet."""
    from app.models.assignments import AssignedForm
    from plugins.emergency_operations_monitoring.models import DrefPeriod

    group = ensure_dref_access_group()
    if group is None:
        return 0
    ids = [
        row[0]
        for row in db.session.query(DrefPeriod.assigned_form_id)
        .filter(DrefPeriod.assigned_form_id.isnot(None))
        .all()
    ]
    if not ids:
        return 0
    changed = 0
    for assignment in AssignedForm.query.filter(AssignedForm.id.in_(ids)).all():
        if attach_dref_audience(assignment):
            changed += 1
    return changed


def ensure_dref_assignment_access() -> None:
    """Create the group if needed, then restrict existing assignments once per group id."""
    global _backfilled_for
    group = ensure_dref_access_group()
    if group is None:
        return
    if _backfilled_for == int(group.id):
        return
    restrict_dref_assignments()
    _backfilled_for = int(group.id)
    if not has_request_context():
        db.session.commit()
