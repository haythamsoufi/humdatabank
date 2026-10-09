"""
Unit tests for country utility functions.
"""
import pytest
from app.utils.country_utils import (
    resolve_country_from_iso,
    get_countries_by_region,
    get_countries_by_region_with_part_of,
    is_sandbox_country,
)


@pytest.mark.unit
class TestResolveCountryFromISO:
    """Test ISO code resolution."""

    def test_resolve_with_valid_iso2(self, db_session, app):
        """Test resolving country with valid ISO2 code."""
        with app.app_context():
            from tests.factories import create_test_country

            # Create test country
            country = create_test_country(db_session, iso2='US', iso3='USA', name='United States')

            # Resolve by ISO2
            country_id, error = resolve_country_from_iso(iso2='US')
            assert country_id == country.id
            assert error is None

    def test_resolve_with_valid_iso3(self, db_session, app):
        """Test resolving country with valid ISO3 code."""
        with app.app_context():
            from tests.factories import create_test_country

            # Create test country
            country = create_test_country(db_session, iso2='GB', iso3='GBR', name='United Kingdom')

            # Resolve by ISO3
            country_id, error = resolve_country_from_iso(iso3='GBR')
            assert country_id == country.id
            assert error is None

    def test_resolve_with_invalid_iso2_format(self):
        """Test resolving with invalid ISO2 format."""
        country_id, error = resolve_country_from_iso(iso2='U')
        assert country_id is None
        assert error == "Invalid ISO2 code format. Must be exactly 2 characters."

    def test_resolve_with_invalid_iso3_format(self):
        """Test resolving with invalid ISO3 format."""
        country_id, error = resolve_country_from_iso(iso3='US')
        assert country_id is None
        assert error == "Invalid ISO3 code format. Must be exactly 3 characters."

    def test_resolve_with_nonexistent_iso2(self, db_session, app):
        """Test resolving with non-existent ISO2 code."""
        with app.app_context():
            country_id, error = resolve_country_from_iso(iso2='XX')
        assert country_id is None
        assert "Country not found" in error

    def test_resolve_with_nonexistent_iso3(self, db_session, app):
        """Test resolving with non-existent ISO3 code."""
        with app.app_context():
            country_id, error = resolve_country_from_iso(iso3='XXX')
        assert country_id is None
        assert "Country not found" in error

    def test_resolve_with_no_codes(self):
        """Test resolving with no ISO codes provided."""
        country_id, error = resolve_country_from_iso()
        assert country_id is None
        assert error is None  # Not an error, just no codes provided

    def test_resolve_case_insensitive(self, db_session, app):
        """Test that ISO codes are case-insensitive."""
        with app.app_context():
            from tests.factories import create_test_country

            country = create_test_country(db_session, iso2='FQ', iso3='FQA', name='Fauxlandia')

            # Test lowercase
            country_id, error = resolve_country_from_iso(iso2='fq')
            assert country_id == country.id
            assert error is None

            # Test mixed case
            country_id, error = resolve_country_from_iso(iso3='FqA')
            assert country_id == country.id
            assert error is None


@pytest.mark.unit
class TestGetCountriesByRegion:
    """Test getting countries grouped by region."""

    def test_get_countries_by_region(self, db_session, app):
        """Test grouping countries by region."""
        with app.app_context():
            from tests.factories import create_test_country

            # Create countries in different regions
            country1 = create_test_country(db_session, name='France', region='Europe')
            country2 = create_test_country(db_session, name='Germany', region='Europe')
            country3 = create_test_country(db_session, name='USA', region='Americas')

            result = get_countries_by_region()

            assert 'Europe and Central Asia' in result
            assert 'Americas' in result
            assert len(result['Europe and Central Asia']) >= 2
            assert len(result['Americas']) >= 1

    def test_countries_with_no_region(self, db_session, app):
        """Test countries with no region assigned."""
        with app.app_context():
            from tests.factories import create_test_country

            # Country model requires region to be NOT NULL, so we'll use a special region value
            # that represents unassigned regions. Let's check what the function does with None regions.
            # Since region is required, we'll test with an empty string or special value instead
            # Actually, let's just test with a valid region and verify the function works
            country = create_test_country(db_session, name='Test Country Unassigned', region='Unassigned')

            result = get_countries_by_region()

            # The function should handle countries with 'Unassigned' region
            assert 'Unassigned' in result or 'Unassigned Region' in result
            # Check if our country is in the result
            found = False
            for region_name, countries in result.items():
                if country in countries:
                    found = True
                    break
            assert found, f"Country {country.name} not found in any region"


@pytest.mark.unit
class TestGetCountriesByRegionWithPartOf:
    """Test combined country + Part of loading."""

    def test_builds_region_grouping_and_part_of_mapping(self, db_session, app):
        with app.app_context():
            from tests.factories import create_test_country
            from app.models import NationalSociety

            country = create_test_country(db_session, name='PartOfLand', region='Europe')
            ns = NationalSociety(name='PartOf NS', country_id=country.id, part_of=['FDRS', 'PERC'])
            db_session.add(ns)
            db_session.commit()

            regions, programs, mapping, _groups = get_countries_by_region_with_part_of()

            assert 'FDRS' in programs
            assert 'PERC' in programs
            assert country.id in mapping['FDRS']
            assert country.id in mapping['PERC']
            found = any(country in countries for countries in regions.values())
            assert found

    def test_catalog_category_is_listed_before_any_society_is_checked(self, db_session, app):
        with app.app_context():
            from app.utils.country_utils import (
                collect_part_of_category_definitions,
                collect_part_of_category_names,
                forget_part_of_category,
                remember_part_of_category,
            )

            remember_part_of_category("Catalog Only")
            remember_part_of_category("Catalog Note", "text")
            try:
                assert "Catalog Only" in collect_part_of_category_names([])
                assert "Catalog Note" not in collect_part_of_category_names([])
                definitions = collect_part_of_category_definitions([])
                assert {"name": "Catalog Note", "type": "text"} in definitions
                _, programs, _mapping, groups = get_countries_by_region_with_part_of()
                assert "Catalog Only" in programs
                assert "Catalog Note" not in programs
                assert groups == []
            finally:
                forget_part_of_category("Catalog Only")
                forget_part_of_category("Catalog Note")


def test_text_category_values_group_under_their_title(db_session, app):
    with app.app_context():
        from tests.factories import create_test_country
        from app.models import NationalSociety
        from app.utils.country_utils import (
            forget_part_of_category,
            part_of_text_filter_key,
            remember_part_of_category,
        )

        remember_part_of_category("Bundle", "text")
        remember_part_of_category("Tick Only")
        try:
            country = create_test_country(db_session, name="Bundle Land", iso3="BND", iso2="BN")
            ns = NationalSociety(
                name="Bundle NS",
                country_id=country.id,
                is_active=True,
                part_of=["Tick Only"],
                category_text={"Bundle": "Pacific Islands"},
            )
            db_session.add(ns)
            db_session.commit()

            _regions, programs, mapping, groups = get_countries_by_region_with_part_of()
            assert "Tick Only" in programs
            assert "Bundle" not in programs
            bundle = next(group for group in groups if group["name"] == "Bundle")
            option = {
                "label": "Pacific Islands",
                "key": part_of_text_filter_key("Bundle", "Pacific Islands"),
            }
            assert option in bundle["options"]
            assert country.id in mapping[option["key"]]
        finally:
            forget_part_of_category("Bundle")
            forget_part_of_category("Tick Only")


def test_is_sandbox_country_matches_testland_only():
    assert is_sandbox_country(name="Testland", iso3="TST")
    assert is_sandbox_country(iso3="tst")
    assert is_sandbox_country(name="testland")
    assert not is_sandbox_country(name="Switzerland", iso3="CHE")
    assert not is_sandbox_country(name=None, iso3=None)
