"""
Unit tests for country service.
"""
import pytest
from app.services.country_service import CountryService
from tests.factories import create_test_country


@pytest.mark.unit
class TestCountryService:
    """Test country service methods."""

    def test_get_by_id_exists(self, db_session, app):
        """Test getting country by ID when it exists."""
        with app.app_context():
            country = create_test_country(db_session)
            result = CountryService.get_by_id(country.id)
            assert result is not None
            assert result.id == country.id
            assert result.name == country.name

    def test_get_by_id_not_exists(self, app):
        """Test getting country by ID when it doesn't exist."""
        with app.app_context():
            result = CountryService.get_by_id(99999)
            assert result is None

    def test_get_by_iso2_exists(self, db_session, app):
        """Test getting country by ISO2 when it exists."""
        with app.app_context():
            country = create_test_country(db_session, iso2='US', iso3='USA')
            result = CountryService.get_by_iso2('US')
            assert result is not None
            assert result.id == country.id

    def test_get_by_iso2_case_insensitive(self, db_session, app):
        """Test that ISO2 lookup is case-insensitive."""
        with app.app_context():
            country = create_test_country(db_session, iso2='FR', iso3='FRA')
            result = CountryService.get_by_iso2('fr')
            assert result is not None
            assert result.id == country.id

    def test_get_by_iso2_not_exists(self, app):
        """Test getting country by ISO2 when it doesn't exist."""
        with app.app_context():
            result = CountryService.get_by_iso2('XX')
            assert result is None

    def test_get_by_iso3_exists(self, db_session, app):
        """Test getting country by ISO3 when it exists."""
        with app.app_context():
            country = create_test_country(db_session, iso2='GB', iso3='GBR')
            result = CountryService.get_by_iso3('GBR')
            assert result is not None
            assert result.id == country.id

    def test_get_by_iso3_case_insensitive(self, db_session, app):
        """Test that ISO3 lookup is case-insensitive."""
        with app.app_context():
            country = create_test_country(db_session, iso2='DE', iso3='DEU')
            result = CountryService.get_by_iso3('deu')
            assert result is not None
            assert result.id == country.id

    def test_get_by_iso3_not_exists(self, app):
        """Test getting country by ISO3 when it doesn't exist."""
        with app.app_context():
            result = CountryService.get_by_iso3('XXX')
            assert result is None
