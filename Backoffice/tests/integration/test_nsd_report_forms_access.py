"""NSD funds plugin does not create Access Groups or put users in them.

Groups are managed in the admin UI. The importer only checks that its admin
permission role exists, and a new account only receives country access.
"""

from app.models.rbac import RbacRole, RbacUserRole
from plugins.nsd_report_forms.importer import restrictions
from plugins.nsd_report_forms.plugin import NSD_ADMIN_ROLE
from tests.factories import create_test_user


def test_missing_roles_is_only_the_admin_permission_role():
    assert restrictions.missing_roles({}) == [NSD_ADMIN_ROLE]
    assert not hasattr(restrictions, "ensure_groups")
    assert not hasattr(restrictions, "restrict")


def test_new_user_is_not_placed_in_an_access_group(db_session, app):
    group = RbacRole(code="group_nsd_should_not_be_granted", name="NSD should not be granted", kind="group")
    db_session.add(group)
    db_session.commit()
    user = create_test_user(db_session, role="user")
    held = {
        code
        for (code,) in db_session.query(RbacRole.code)
        .join(RbacUserRole, RbacUserRole.role_id == RbacRole.id)
        .filter(RbacUserRole.user_id == user.id)
    }
    assert group.code not in held
