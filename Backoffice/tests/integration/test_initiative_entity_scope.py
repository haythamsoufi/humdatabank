"""Initiatives follow their country for delegation and in the data API, and stay out of admin lists unless enabled."""

from app.models.core import UserEntityPermission
from app.models.initiatives import Initiative
from app.models.organization import NationalSociety
from app.services.organization.authorization_service import AuthorizationService
from app.services.organization.entity_service import EntityService
from app.utils.api_serialization import batch_countries_for_aes_list
from tests.factories import create_test_country, create_test_user


def _initiative(db_session, country, reference):
    ns = NationalSociety(name=f"{reference} Red Cross", country_id=country.id, is_active=True)
    db_session.add(ns)
    db_session.flush()
    ini = Initiative(reference=reference, title="Digital readiness", national_society_id=ns.id)
    db_session.add(ini)
    db_session.commit()
    return ini


def test_a_country_holder_may_delegate_access_to_initiatives_of_that_country_only(db_session, app):
    mine, other = create_test_country(db_session), create_test_country(db_session)
    ini_mine, ini_other = _initiative(db_session, mine, "CBF-S1-2401-001"), _initiative(db_session, other, "CBF-S2-2401-001")
    actor = create_test_user(db_session, role="user")
    db_session.add(UserEntityPermission(user_id=actor.id, entity_type="country", entity_id=mine.id))
    db_session.commit()

    assert AuthorizationService.can_delegate_entity_access(actor, "initiative", ini_mine.id)
    assert not AuthorizationService.can_delegate_entity_access(actor, "initiative", ini_other.id)


def test_the_data_api_resolves_the_country_of_an_initiative_row(db_session, app):
    country = create_test_country(db_session)
    ini = _initiative(db_session, country, "CBF-S3-2401-001")
    row = type("Row", (), {"entity_type": "initiative", "entity_id": ini.id})()
    assert batch_countries_for_aes_list([row])[("initiative", ini.id)].id == country.id


def test_admin_entity_lists_include_initiatives_only_when_the_funds_group_is_enabled(db_session, app):
    country = create_test_country(db_session)
    ini = _initiative(db_session, country, "CBF-S4-2401-001")
    admin = create_test_user(db_session, role="admin")

    def initiatives():
        return [e for e in EntityService.get_entities_for_user(admin) if isinstance(e, Initiative)]

    app.config["ENABLED_ENTITY_TYPES"] = ["countries", "ns_structure", "secretariat"]
    assert initiatives() == []
    app.config["ENABLED_ENTITY_TYPES"] = ["countries", "funds"]
    assert [i.id for i in initiatives()] == [ini.id]
