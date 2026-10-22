"""The initiative entity type (a funded project that reports on its own schedule)."""

from app.models.enums import EntityType
from app.models.initiatives import Initiative
from app.models.organization import NationalSociety
from app.services.organization.entity_service import EntityService
from app.utils.entity_groups import get_allowed_entity_type_codes
from tests.factories import create_test_country


def _initiative(db_session, ns=None):
    ini = Initiative(reference="CBF-XX-2401-001", title="Digital readiness",
                     national_society_id=ns.id if ns else None)
    db_session.add(ini)
    db_session.commit()
    return ini


def test_entity_service_resolves_an_initiative_and_its_country(db_session, app):
    country = create_test_country(db_session)
    ns = NationalSociety(name="Testland Red Cross", country_id=country.id, is_active=True)
    db_session.add(ns)
    db_session.commit()
    ini = _initiative(db_session, ns)

    assert EntityService.ENTITY_MODEL_MAP[EntityType.initiative.value] is Initiative
    assert EntityService.get_entity("initiative", ini.id).id == ini.id
    assert "CBF-XX-2401-001" in EntityService.get_entity_name("initiative", ini.id)
    assert EntityService.get_country_for_entity("initiative", ini.id).id == country.id
    assert EntityService.get_entity_type_label("initiative") == "Initiative"


def test_an_initiative_without_national_society_has_no_country(db_session, app):
    ini = _initiative(db_session)
    assert ini.country is None
    assert EntityService.get_country_for_entity("initiative", ini.id) is None


def test_initiatives_are_only_allowed_when_the_funds_group_is_enabled():
    assert "initiative" not in get_allowed_entity_type_codes(["countries", "ns_structure", "secretariat"])
    assert get_allowed_entity_type_codes(["countries", "funds"]) >= {"country", "initiative"}
