"""NSD master import: National Societies that are marked inactive are still found, but never beat an active one."""

from app.models.organization import NationalSociety
from plugins.nsd_report_forms.importer import apply
from tests.factories import create_test_country


def test_inactive_national_society_is_a_fallback_and_never_beats_an_active_one(db_session, app):
    active_country, inactive_country = create_test_country(db_session), create_test_country(db_session)
    both_country = create_test_country(db_session)
    active = NationalSociety(name="Alpha Red Cross", country_id=active_country.id, is_active=True)
    inactive = NationalSociety(name="Beta Red Cross", country_id=inactive_country.id, is_active=False)
    same_active = NationalSociety(name="Gamma Red Cross", country_id=both_country.id, is_active=True)
    same_inactive = NationalSociety(name="Gamma Old Red Cross", country_id=both_country.id, is_active=False)
    db_session.add_all([active, inactive, same_active, same_inactive])
    db_session.commit()

    by_name, by_country = apply.Lookups._ns_index()
    assert by_name[apply._norm_name("Alpha Red Cross")] == {active.id}
    assert by_name[apply._norm_name("Beta Red Cross")] == {inactive.id}          # only inactive: used
    assert by_country[inactive_country.iso3.upper()] == {inactive.id}
    assert by_country[both_country.iso3.upper()] == {same_active.id}             # the active one wins
    assert by_name[apply._norm_name("Gamma Old Red Cross")] == {same_inactive.id}  # still found by its own name
