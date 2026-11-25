"""Create the users named in the Sectoral Interventions workbook and put them in the access group.

New users get no password and no welcome email: they sign in through the organisation's
single sign-on, or an admin sends the welcome email from Manage Users. Users that already
exist keep their roles and details; they are only added to the access group (and to the
countries they are a focal point for) and are listed in the report.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional, Set

from sqlalchemy import func

from app import db
from app.models import User
from app.models.core import UserEntityPermission
from app.models.enums import EntityType
from app.models.rbac import ROLE_KIND_GROUP, RbacRole, RbacUserRole

from plugins.global_award.constants import (
    ACCESS_GROUP_CODE,
    ACCESS_GROUP_NAME,
    DEFAULT_USER_ROLE_CODE,
)
from plugins.global_award.importer.contacts import PersonRecord

log = logging.getLogger(__name__)

_EMAIL_LIMIT = 120
_NAME_LIMIT = 100


def ensure_access_group() -> tuple[RbacRole, bool]:
    """The ``Global Award`` Access Group and whether this call created it."""
    group = (
        RbacRole.query.filter(RbacRole.kind == ROLE_KIND_GROUP, func.lower(RbacRole.name) == ACCESS_GROUP_NAME.casefold())
        .order_by(RbacRole.id)
        .first()
    )
    if group is None:
        group = RbacRole.query.filter_by(code=ACCESS_GROUP_CODE, kind=ROLE_KIND_GROUP).first()
    if group is not None:
        return group, False
    if RbacRole.query.filter_by(code=ACCESS_GROUP_CODE).first() is not None:
        raise ValueError(
            f"The role code {ACCESS_GROUP_CODE} is taken by something that is not an Access Group."
        )
    group = RbacRole(
        code=ACCESS_GROUP_CODE,
        name=ACCESS_GROUP_NAME,
        description="IFRC focal points and project managers of the Global Award.",
        kind=ROLE_KIND_GROUP,
    )
    db.session.add(group)
    db.session.flush()
    return group, True


def _member_ids(group: RbacRole) -> Set[int]:
    return {int(row.user_id) for row in RbacUserRole.query.filter_by(role_id=group.id).all()}


def _country_grants(user_ids: Iterable[int]) -> Dict[int, Set[int]]:
    ids = list(user_ids)
    if not ids:
        return {}
    out: Dict[int, Set[int]] = {}
    rows = UserEntityPermission.query.filter(
        UserEntityPermission.user_id.in_(ids),
        UserEntityPermission.entity_type == EntityType.country.value,
    ).all()
    for row in rows:
        out.setdefault(int(row.user_id), set()).add(int(row.entity_id))
    return out


def sync_users(
    people: Dict[str, PersonRecord],
    *,
    grant_country_ids: Optional[Set[int]] = None,
) -> Dict[str, Any]:
    """Create missing users, join everyone to the access group, grant country access.

    ``grant_country_ids`` limits country access to countries that have a Global Award project.
    Returns what happened so the caller can report it; nothing is committed here.
    """
    group, group_created = ensure_access_group()
    default_role = RbacRole.query.filter_by(code=DEFAULT_USER_ROLE_CODE).first()
    warnings: List[str] = []
    if default_role is None:
        warnings.append(
            f"Role {DEFAULT_USER_ROLE_CODE} was not found, so new users have no role. Run flask rbac seed."
        )

    emails = sorted(people)
    existing_rows = (
        User.query.filter(func.lower(User.email).in_(emails)).all() if emails else []
    )
    existing = {(user.email or "").strip().lower(): user for user in existing_rows}
    members = _member_ids(group)
    grants = _country_grants(user.id for user in existing_rows)

    created: List[Dict[str, Any]] = []
    already: List[Dict[str, Any]] = []
    skipped: List[str] = []
    access_added = 0
    group_added = 0

    for email in emails:
        person = people[email]
        if len(email) > _EMAIL_LIMIT:
            skipped.append(f"{email} (email longer than {_EMAIL_LIMIT} characters)")
            continue
        user = existing.get(email)
        is_new = user is None
        if is_new:
            user = User(email=email, name=(person.name or email)[:_NAME_LIMIT], active=True)
            db.session.add(user)
            db.session.flush()
            if default_role is not None:
                db.session.add(RbacUserRole(user_id=user.id, role_id=default_role.id))
            # The NSD projects plugin grants country access to a new user whose email is a
            # project contact, as the row is inserted. Read that back instead of assuming none.
            grants[user.id] = _country_grants([user.id]).get(user.id, set())

        joined = user.id not in members
        if joined:
            db.session.add(RbacUserRole(user_id=user.id, role_id=group.id))
            members.add(user.id)
            group_added += 1

        countries_added = 0
        for country_id in person.country_ids:
            if grant_country_ids is not None and country_id not in grant_country_ids:
                continue
            if country_id in grants.setdefault(user.id, set()):
                continue
            db.session.add(
                UserEntityPermission(
                    user_id=user.id,
                    entity_type=EntityType.country.value,
                    entity_id=country_id,
                )
            )
            grants[user.id].add(country_id)
            countries_added += 1
        access_added += countries_added

        row = {
            "email": email,
            "name": user.name or person.name,
            "roles": list(person.roles),
            "joined_group": joined,
            "countries_added": countries_added,
            "active": bool(user.active),
        }
        (created if is_new else already).append(row)
    db.session.flush()
    return {
        "group_name": group.name,
        "group_created": group_created,
        "created": created,
        "existing": already,
        "skipped": skipped,
        "group_added": group_added,
        "country_access_added": access_added,
        "warnings": warnings,
    }
