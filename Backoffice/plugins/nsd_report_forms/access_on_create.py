"""Give a newly created user country access for projects that name their email.

When a User row is inserted (Manage Users, or a first SSO sign-in), core ``project``
(and legacy profile assignments) are searched for that email in the focal /
project manager fields. The person then gets access to each matching country.
Access Group membership is not granted here: that is set on the user form or the
Access Groups screen. Nothing is ever removed. A failure here is logged and never
blocks the account creation.
"""
import logging

from sqlalchemy import bindparam, event, text

from app.models import User

log = logging.getLogger(__name__)

PROFILE_TEMPLATE = 'NSD Project profile - CBF'
CONTACT_LABELS = ('NS focal person email', 'IFRC project manager email')

_MATCHES_LEGACY = text("""
    SELECT DISTINCT aes.entity_id AS country_id
    FROM form_data fd
    JOIN form_item fi ON fi.id = fd.form_item_id
    JOIN form_template_version v ON v.id = fi.version_id AND v.status = 'published' AND v.name = :tpl
    JOIN assignment_entity_status aes ON aes.id = fd.assignment_entity_status_id
    WHERE aes.entity_type = 'country' AND fi.label IN :labels AND lower(trim(fd.value)) = :email
""").bindparams(bindparam('labels', expanding=True))

_MATCHES_REGISTRY = text("""
    SELECT DISTINCT country_id
    FROM project
    WHERE country_id IS NOT NULL
      AND (
        lower(trim(coalesce(focal_email, ''))) = :email
        OR lower(trim(coalesce(manager_email, ''))) = :email
      )
""")

_GRANT_COUNTRY = text("""
    INSERT INTO user_entity_permissions (user_id, entity_type, entity_id, created_at)
    SELECT :uid, 'country', :cid, now()
    WHERE NOT EXISTS (SELECT 1 FROM user_entity_permissions
                      WHERE user_id = :uid AND entity_type = 'country' AND entity_id = :cid)
""")


def grant_for_new_user(mapper, connection, user):
    email = (user.email or '').strip().lower()
    if not email:
        return
    try:
        with connection.begin_nested():  # savepoint: a problem here must not poison the user insert
            country_ids = set()
            try:
                for r in connection.execute(_MATCHES_REGISTRY, {'email': email}).all():
                    if r.country_id:
                        country_ids.add(r.country_id)
            except Exception:  # table may not exist yet during early migrate
                log.debug('NSD funds: project lookup skipped for %s', email, exc_info=True)
            for r in connection.execute(
                _MATCHES_LEGACY,
                {'tpl': PROFILE_TEMPLATE, 'labels': list(CONTACT_LABELS), 'email': email},
            ).all():
                if r.country_id:
                    country_ids.add(r.country_id)
            for country_id in country_ids:
                connection.execute(_GRANT_COUNTRY, {'uid': user.id, 'cid': country_id})
        if country_ids:
            log.info('NSD funds: new user %s got country access from project contacts', email)
    except Exception:  # noqa: BLE001
        log.exception('NSD funds: could not grant country access to new user %s', email)


if not event.contains(User, 'after_insert', grant_for_new_user):
    event.listen(User, 'after_insert', grant_for_new_user)
