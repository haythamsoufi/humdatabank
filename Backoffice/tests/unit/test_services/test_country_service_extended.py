"""
Extended coverage tests for country_service.py.

Supplements test_country_service.py to cover:
  - CountryService.get_all, get_all_with_national_societies, exists
  - fds_member_user_display_name
  - get_fds_member_user_options_for_country
  - parse_fds_member_user_id
  - resolve_fds_member_user_id_from_import
  - assign_country_fds_member_user
  - countries_with_fds_member_query
"""
import pytest
from unittest.mock import MagicMock, patch

from app.services.organization.country_service import (
    CountryService,
    assign_country_fds_member_user,
    countries_with_fds_member_query,
    fds_member_user_display_name,
    get_fds_member_filter_options,
    get_fds_member_user_options_for_country,
    parse_fds_member_user_id,
    resolve_fds_member_user_id_from_import,
    user_is_fds_member,
)
from tests.factories import (
    create_test_admin,
    create_test_country,
    create_test_user,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# CountryService — uncovered methods
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCountryServiceGetAll:
    def test_get_all_ordered(self, db_session, app):
        with app.app_context():
            create_test_country(db_session)
            query = CountryService.get_all(ordered=True)
            results = query.all()
            assert isinstance(results, list)
            assert len(results) >= 1

    def test_get_all_unordered(self, db_session, app):
        with app.app_context():
            query = CountryService.get_all(ordered=False)
            results = query.all()
            assert isinstance(results, list)


@pytest.mark.unit
class TestCountryServiceGetAllWithNationalSocieties:
    def test_returns_query(self, db_session, app):
        with app.app_context():
            create_test_country(db_session)
            query = CountryService.get_all_with_national_societies(ordered=True)
            results = query.all()
            assert isinstance(results, list)

    def test_unordered_variant(self, db_session, app):
        with app.app_context():
            query = CountryService.get_all_with_national_societies(ordered=False)
            assert query is not None


@pytest.mark.unit
class TestCountryServiceExists:
    def test_exists_when_present(self, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            assert CountryService.exists(country.id) is True

    def test_not_exists_when_absent(self, db_session, app):
        with app.app_context():
            assert CountryService.exists(9_999_999) is False


# ---------------------------------------------------------------------------
# fds_member_user_display_name
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFdsMemberUserDisplayName:
    def test_none_user_returns_empty_string(self):
        assert fds_member_user_display_name(None) == ""

    def test_user_with_name(self):
        user = MagicMock()
        user.name = "Alice Smith"
        user.email = "alice@example.com"
        user.id = 1
        assert fds_member_user_display_name(user) == "Alice Smith"

    def test_user_without_name_uses_email(self):
        user = MagicMock()
        user.name = ""
        user.email = "alice@example.com"
        user.id = 1
        assert fds_member_user_display_name(user) == "alice@example.com"

    def test_user_without_name_or_email_uses_id(self):
        user = MagicMock()
        user.name = ""
        user.email = ""
        user.id = 42
        assert fds_member_user_display_name(user) == "User 42"

    def test_user_with_none_name(self):
        user = MagicMock()
        user.name = None
        user.email = "bob@example.com"
        user.id = 2
        assert fds_member_user_display_name(user) == "bob@example.com"


# ---------------------------------------------------------------------------
# parse_fds_member_user_id
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestParseFdsMemberUserId:
    def test_none_returns_none(self):
        assert parse_fds_member_user_id(None) is None

    def test_empty_string_returns_none(self):
        assert parse_fds_member_user_id("") is None
        assert parse_fds_member_user_id("   ") is None

    def test_valid_integer_string(self):
        assert parse_fds_member_user_id("42") == 42

    def test_valid_float_string(self):
        assert parse_fds_member_user_id("42.0") == 42

    def test_invalid_string_returns_none(self):
        assert parse_fds_member_user_id("not-a-number") is None

    def test_zero_returns_none(self):
        assert parse_fds_member_user_id("0") is None

    def test_negative_returns_none(self):
        assert parse_fds_member_user_id("-5") is None

    def test_integer_input(self):
        assert parse_fds_member_user_id(7) == 7


# ---------------------------------------------------------------------------
# resolve_fds_member_user_id_from_import
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestResolveFdsMemberUserIdFromImport:
    def test_prefers_user_id_over_email(self, db_session, app):
        with app.app_context():
            user = create_test_user(db_session)
            result = resolve_fds_member_user_id_from_import(
                raw_user_id=str(user.id),
                raw_email="other@example.com",
            )
            assert result == user.id

    def test_falls_back_to_email(self, db_session, app):
        with app.app_context():
            user = create_test_user(db_session)
            result = resolve_fds_member_user_id_from_import(
                raw_user_id=None,
                raw_email=user.email,
            )
            assert result == user.id

    def test_email_case_insensitive(self, db_session, app):
        with app.app_context():
            user = create_test_user(db_session)
            result = resolve_fds_member_user_id_from_import(
                raw_user_id=None,
                raw_email=user.email.upper(),
            )
            assert result == user.id

    def test_no_user_id_no_email_returns_none(self, db_session, app):
        with app.app_context():
            result = resolve_fds_member_user_id_from_import(
                raw_user_id=None,
                raw_email=None,
            )
            assert result is None

    def test_empty_email_returns_none(self, db_session, app):
        with app.app_context():
            result = resolve_fds_member_user_id_from_import(
                raw_user_id=None,
                raw_email="",
            )
            assert result is None

    def test_unknown_email_raises_value_error(self, db_session, app):
        with app.app_context():
            with pytest.raises(ValueError, match="No active user found"):
                resolve_fds_member_user_id_from_import(
                    raw_user_id=None,
                    raw_email="absolutely.unknown.xyz@nonexistent.example.com",
                )


# ---------------------------------------------------------------------------
# get_fds_member_user_options_for_country
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetFdsMemberUserOptionsForCountry:
    def test_returns_list(self, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            result = get_fds_member_user_options_for_country(country.id)
            assert isinstance(result, list)

    def test_eligible_admin_appears_in_options(self, db_session, app):
        from app.models.core import UserEntityPermission
        from app.models.enums import EntityType
        from app import db

        with app.app_context():
            country = create_test_country(db_session)
            admin = create_test_admin(db_session)
            # Grant entity permission for this country
            db.session.add(
                UserEntityPermission(
                    user_id=admin.id,
                    entity_type=EntityType.country.value,
                    entity_id=country.id,
                )
            )
            db.session.commit()
            result = get_fds_member_user_options_for_country(country.id)
            ids = [opt["id"] for opt in result]
            assert admin.id in ids

    def test_result_has_expected_keys(self, db_session, app):
        from app.models.core import UserEntityPermission
        from app.models.enums import EntityType
        from app import db

        with app.app_context():
            country = create_test_country(db_session)
            admin = create_test_admin(db_session)
            db.session.add(
                UserEntityPermission(
                    user_id=admin.id,
                    entity_type=EntityType.country.value,
                    entity_id=country.id,
                )
            )
            db.session.commit()
            result = get_fds_member_user_options_for_country(country.id)
            for opt in result:
                assert "id" in opt
                assert "label" in opt
                assert "email" in opt


# ---------------------------------------------------------------------------
# assign_country_fds_member_user
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestAssignCountryFdsMemberUser:
    def test_set_to_none_clears_fds_member(self, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            country.fds_member_user_id = 99
            assign_country_fds_member_user(country, None)
            assert country.fds_member_user_id is None

    def test_ineligible_user_raises_value_error(self, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            user = create_test_user(db_session)
            # user is NOT an eligible admin for this country
            with pytest.raises(ValueError, match="org admin"):
                assign_country_fds_member_user(country, user.id)

    def test_eligible_user_is_assigned(self, db_session, app):
        from app.models.core import UserEntityPermission
        from app.models.enums import EntityType
        from app import db

        with app.app_context():
            country = create_test_country(db_session)
            admin = create_test_admin(db_session)
            db.session.add(
                UserEntityPermission(
                    user_id=admin.id,
                    entity_type=EntityType.country.value,
                    entity_id=country.id,
                )
            )
            db.session.commit()
            assign_country_fds_member_user(country, admin.id)
            assert country.fds_member_user_id == admin.id


# ---------------------------------------------------------------------------
# countries_with_fds_member_query
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCountriesWithFdsMemberQuery:
    def test_returns_query(self, db_session, app):
        with app.app_context():
            query = countries_with_fds_member_query()
            # Should be an executable SQLAlchemy query
            results = query.all()
            assert isinstance(results, list)


@pytest.mark.unit
class TestFdsMemberHelpers:
    def test_user_is_fds_member(self, db_session, app, admin_user):
        with app.app_context():
            country = create_test_country(db_session, iso3="FDS", iso2="FD")
            country.fds_member_user_id = admin_user.id
            db_session.commit()
            assert user_is_fds_member(admin_user.id) is True
            assert user_is_fds_member(None) is False

    def test_get_fds_member_filter_options(self, db_session, app, admin_user):
        with app.app_context():
            country = create_test_country(db_session, iso3="OPT", iso2="OP")
            country.fds_member_user_id = admin_user.id
            db_session.commit()
            options = get_fds_member_filter_options()
            ids = {opt['id'] for opt in options}
            assert admin_user.id in ids
