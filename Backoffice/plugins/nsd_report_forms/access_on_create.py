"""Give a newly created user access to the projects that name their email: country access and a role.

When a User row is inserted (Manage Users, or a first SSO sign-in), the project records are searched for that
email in the NS focal person / IFRC project manager fields. The person then gets access to each matching country
and the role that goes with the contact type (ROLE_BY_CONTACT). Same rule as the master import, which applies it to
users that already exist. Nothing is ever removed, and System Managers are not given extra roles.
A failure here is logged and never blocks the account creation.
"""
import logging

from sqlalchemy import bindparam, event, text

from app.models import User
from plugins.nsd_report_forms.plugin import GROUP_BY_ROLE, NSD_ROLE_FOCAL, NSD_ROLE_PM

log = logging.getLogger(__name__)

PROFILE_TEMPLATE = 'NSD Project profile - CBF'

# project-record field holding the email -> role given to that person (change here to change the policy)
ROLE_BY_CONTACT = {
    'NS focal person email': NSD_ROLE_FOCAL,
    'IFRC project manager email': NSD_ROLE_PM,
}
# the project manager role supersedes the focal point role: a person who is a PM never keeps the focal role

_MATCHES = text("""
    SELECT DISTINCT aes.entity_id AS country_id, fi.label AS label
    FROM form_data fd
    JOIN form_item fi ON fi.id = fd.form_item_id
    JOIN form_template_version v ON v.id = fi.version_id AND v.status = 'published' AND v.name = :tpl
    JOIN assignment_entity_status aes ON aes.id = fd.assignment_entity_status_id
    WHERE aes.entity_type = 'country' AND fi.label IN :labels AND lower(trim(fd.value)) = :email
""").bindparams(bindparam('labels', expanding=True))

_GRANT_COUNTRY = text("""
    INSERT INTO user_entity_permissions (user_id, entity_type, entity_id, created_at)
    SELECT :uid, 'country', :cid, now()
    WHERE NOT EXISTS (SELECT 1 FROM user_entity_permissions
                      WHERE user_id = :uid AND entity_type = 'country' AND entity_id = :cid)
""")

_GRANT_ROLE = text("""
    INSERT INTO rbac_user_role (user_id, role_id, created_at)
    SELECT :uid, r.id, now() FROM rbac_role r
    WHERE r.code = :code
      AND NOT EXISTS (SELECT 1 FROM rbac_user_role ur WHERE ur.user_id = :uid AND ur.role_id = r.id)
      AND NOT EXISTS (SELECT 1 FROM rbac_user_role ur2 JOIN rbac_role r2 ON r2.id = ur2.role_id
                      WHERE ur2.user_id = :uid AND r2.code = 'system_manager')
""")


def grant_for_new_user(mapper, connection, user):
    email = (user.email or '').strip().lower()
    if not email:
        return
    try:
        with connection.begin_nested():  # savepoint: a problem here must not poison the user insert
            rows = connection.execute(_MATCHES, {'tpl': PROFILE_TEMPLATE, 'labels': list(ROLE_BY_CONTACT),
                                                 'email': email}).all()
            for country_id in {r.country_id for r in rows}:
                connection.execute(_GRANT_COUNTRY, {'uid': user.id, 'cid': country_id})
            codes = {ROLE_BY_CONTACT[r.label] for r in rows}
            if NSD_ROLE_PM in codes:
                codes.discard(NSD_ROLE_FOCAL)
            # the permission role and its Access Group (the group is what lets the user reach the reports; it is
            # skipped quietly when the master import has not created it yet)
            for code in codes | {GROUP_BY_ROLE[c] for c in codes}:
                connection.execute(_GRANT_ROLE, {'uid': user.id, 'code': code})
        if rows:
            log.info('NSD funds: new user %s got project access from project contacts', email)
    except Exception:  # noqa: BLE001
        log.exception('NSD funds: could not grant project access to new user %s', email)


if not event.contains(User, 'after_insert', grant_for_new_user):
    event.listen(User, 'after_insert', grant_for_new_user)
