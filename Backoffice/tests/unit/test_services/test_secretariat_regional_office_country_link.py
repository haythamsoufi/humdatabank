"""Tests for linking countries to SecretariatRegionalOffice (IFRC regions)."""

from app.models.core import Country
from app.models.organization import SecretariatRegionalOffice
from app.services.organization.secretariat_regional_office_service import (
    assign_country_secretariat_regional_office,
    ensure_secretariat_regional_offices,
    normalize_region_label,
    resolve_secretariat_regional_office_by_label,
)
from tests.factories import create_test_country


class TestNormalizeRegionLabel:
    def test_legacy_europe_maps_to_europe_ca(self):
        assert normalize_region_label("Europe") == "Europe and Central Asia"

    def test_mena_long_form(self):
        assert normalize_region_label("Middle East and North Africa") == "MENA"

    def test_canonical_name_passthrough(self):
        assert normalize_region_label("Africa") == "Africa"


class TestEnsureSecretariatRegionalOffices:
    def test_creates_five_statutory_regions(self, db_session, app):
        with app.app_context():
            code_to_id = ensure_secretariat_regional_offices(db_session)
            assert len(code_to_id) == 5
            offices = (
                db_session.query(SecretariatRegionalOffice)
                .order_by(SecretariatRegionalOffice.display_order)
                .all()
            )
            assert [o.code for o in offices] == [
                "africa",
                "americas",
                "asia_pacific",
                "europe_ca",
                "mena",
            ]
            europe = next(o for o in offices if o.code == "europe_ca")
            assert europe.short_name == "Europe & CA"

    def test_idempotent(self, db_session, app):
        with app.app_context():
            ensure_secretariat_regional_offices(db_session)
            db_session.commit()
            count_before = db_session.query(SecretariatRegionalOffice).count()
            ensure_secretariat_regional_offices(db_session)
            assert db_session.query(SecretariatRegionalOffice).count() == count_before


class TestCountrySecretariatRegionalOfficeLink:
    def test_create_test_country_links_europe_legacy_label(self, db_session, app):
        with app.app_context():
            country = create_test_country(db_session, name="Link Test Country", region="Europe")
            assert country.secretariat_regional_office_id is not None
            assert country.secretariat_regional_office.code == "europe_ca"
            assert country.region == "Europe and Central Asia"

    def test_assign_country_from_label(self, db_session, app):
        with app.app_context():
            ensure_secretariat_regional_offices(db_session)
            country = Country(
                name="Manual Country",
                iso3="ZZZ",
                iso2="ZZ",
                region="",
            )
            assign_country_secretariat_regional_office(country, "MENA")
            db_session.add(country)
            db_session.commit()
            assert country.secretariat_regional_office_id is not None
            assert country.region == "MENA"

    def test_resolve_secretariat_regional_office_by_label(self, db_session, app):
        with app.app_context():
            office = resolve_secretariat_regional_office_by_label("Asia Pacific", session=db_session)
            assert office is not None
            assert office.code == "asia_pacific"
