"""Give a newly created user access to the projects that name their email.

When a User row is inserted (Manage Users, or a first SSO sign-in), the project records are searched for that
email in the NS focal person / IFRC project manager fields. The person then gets access to each matching project
(initiative).
Access Group membership is not granted here: that is set on the user form or the Access Groups screen.
Nothing is ever removed. A failure here is logged and never blocks the account creation.
"""
import logging

from sqlalchemy import bindparam, event, text

from app.models import User

log = logging.getLogger(__name__)

PROFILE_TEMPLATE = 'NSD Project profile - CBF'
CONTACT_LABELS = ('NS focal person email', 'IFRC project manager email')

_MATCHES = text("""
    SELECT DISTINCT aes.entity_id AS initiative_id
    FROM form_data fd
    JOIN form_item fi ON fi.id = fd.form_item_id
    JOIN form_template_version v ON v.id = fi.version_id AND v.status = 'published' AND v.name = :tpl
    JOIN assignment_entity_status aes ON aes.id = fd.assignment_entity_status_id
    WHERE aes.entity_type = 'initiative' AND fi.label IN :labels AND lower(trim(fd.value)) = :email
""").bindparams(bindparam('labels', expanding=True))

_GRANT = text("""
    INSERT INTO user_entity_permissions (user_id, entity_type, entity_id, created_at)
    SELECT :uid, 'initiative', :iid, now()
    WHERE NOT EXISTS (SELECT 1 FROM user_entity_permissions
                      WHERE user_id = :uid AND entity_type = 'initiative' AND entity_id = :iid)
""")


def grant_for_new_user(mapper, connection, user):
    email = (user.email or '').strip().lower()
    if not email:
        return
    try:
        with connection.begin_nested():  # savepoint: a problem here must not poison the user insert
            rows = connection.execute(_MATCHES, {'tpl': PROFILE_TEMPLATE, 'labels': list(CONTACT_LABELS),
                                                 'email': email}).all()
            for initiative_id in {r.initiative_id for r in rows}:
                connection.execute(_GRANT, {'uid': user.id, 'iid': initiative_id})
        if rows:
            log.info('NSD funds: new user %s got project access from project contacts', email)
    except Exception:  # noqa: BLE001
        log.exception('NSD funds: could not grant project access to new user %s', email)


if not event.contains(User, 'after_insert', grant_for_new_user):
    event.listen(User, 'after_insert', grant_for_new_user)
