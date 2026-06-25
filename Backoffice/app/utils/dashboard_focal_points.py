"""Shared helpers for dashboard focal-point contact lists."""

from __future__ import annotations

from sqlalchemy import or_

from app import db
from app.models import User
from app.models.core import UserEntityPermission
from app.models.rbac import RbacRole, RbacUserRole


def _serialize_focal_point(user: User) -> dict:
    return {
        'id': user.id,
        'name': (user.name or '').strip() or None,
        'title': (user.title or '').strip() or None,
        'email': user.email,
    }


def get_focal_points_for_country(country_id: int) -> tuple[list[dict], list[dict]]:
    """
    Return (national_society_focal_points, organization_focal_points) for a country.

    Mirrors main.dashboard categorization: assignment_editor_submitter users with
    country permission, split by org email domain and excluding admin/system_manager roles.
    """
    from app.utils.organization_helpers import is_org_email

    all_focal_points_for_country = (
        User.query
        .join(UserEntityPermission, User.id == UserEntityPermission.user_id)
        .join(RbacUserRole, User.id == RbacUserRole.user_id)
        .join(RbacRole, RbacUserRole.role_id == RbacRole.id)
        .filter(
            RbacRole.code == 'assignment_editor_submitter',
            UserEntityPermission.entity_type == 'country',
            UserEntityPermission.entity_id == country_id,
        )
        .distinct()
        .order_by(User.name)
        .all()
    )

    admin_role_user_ids = set(
        uid for (uid,) in db.session.query(RbacUserRole.user_id)
        .join(RbacRole, RbacUserRole.role_id == RbacRole.id)
        .filter(or_(
            RbacRole.code == 'system_manager',
            RbacRole.code.like('admin_%'),
        ))
        .all()
    )

    ns_focal_points = [
        _serialize_focal_point(fp)
        for fp in all_focal_points_for_country
        if not is_org_email(fp.email)
    ]
    org_focal_points = [
        _serialize_focal_point(fp)
        for fp in all_focal_points_for_country
        if is_org_email(fp.email) and fp.id not in admin_role_user_ids
    ]
    return ns_focal_points, org_focal_points
