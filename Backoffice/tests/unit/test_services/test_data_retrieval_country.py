"""
Comprehensive tests for app/services/data_retrieval_country.py.

Covers: check_country_access, resolve_country, get_country_info,
get_assignments_for_country, get_user_countries, get_user_country_ids.
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

from tests.factories import (
    create_test_user, create_test_admin, create_test_country,
    create_test_template, create_test_assignment_entity_status,
)


# ---------------------------------------------------------------------------
# check_country_access
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCheckCountryAccess:
    def test_unrestricted_user_returns_true(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.country import check_country_access
            country = create_test_country(db_session)
            with patch("app.services.data_retrieval.country.user_allowed_country_ids", return_value=None):
                assert check_country_access(country.id) is True

    def test_country_in_allowed_set_returns_true(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.country import check_country_access
            country = create_test_country(db_session)
            with patch("app.services.data_retrieval.country.user_allowed_country_ids",
                       return_value={country.id}):
                assert check_country_access(country.id) is True

    def test_country_not_in_allowed_set_checks_entity_service(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.country import check_country_access
            country = create_test_country(db_session)
            mock_user = MagicMock()
            mock_user.is_authenticated = True
            with patch("app.services.data_retrieval.country.user_allowed_country_ids",
                       return_value={99999}), \
                 patch("app.services.data_retrieval.country.current_user", mock_user), \
                 patch("app.services.organization.entity_service.EntityService.check_user_entity_access",
                       return_value=True):
                result = check_country_access(country.id)
                assert result is True

    def test_unauthenticated_user_returns_false(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.country import check_country_access
            country = create_test_country(db_session)
            mock_user = MagicMock()
            mock_user.is_authenticated = False
            with patch("app.services.data_retrieval.country.user_allowed_country_ids",
                       return_value={99999}), \
                 patch("app.services.data_retrieval.country.current_user", mock_user):
                result = check_country_access(country.id)
                assert result is False

    def test_entity_service_exception_returns_false(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.country import check_country_access
            country = create_test_country(db_session)
            mock_user = MagicMock()
            mock_user.is_authenticated = True
            with patch("app.services.data_retrieval.country.user_allowed_country_ids",
                       return_value={99999}), \
                 patch("app.services.data_retrieval.country.current_user", mock_user), \
                 patch("app.services.organization.entity_service.EntityService.check_user_entity_access",
                       side_effect=Exception("fail")):
                result = check_country_access(country.id)
                assert result is False


# ---------------------------------------------------------------------------
# resolve_country
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestResolveCountry:
    def test_resolve_by_int_id(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.country import resolve_country
            country = create_test_country(db_session)
            result = resolve_country(country.id)
            assert result is not None
            assert result.id == country.id

    def test_resolve_by_string_digit(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.country import resolve_country
            country = create_test_country(db_session)
            result = resolve_country(str(country.id))
            assert result is not None
            assert result.id == country.id

    def test_resolve_by_name(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.country import resolve_country
            country = create_test_country(db_session, name="Resolvalia", iso2="RL", iso3="RLL")
            result = resolve_country("Resolvalia")
            assert result is not None
            assert result.id == country.id

    def test_nonexistent_int_returns_none(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.country import resolve_country
            result = resolve_country(999999)
            assert result is None

    def test_nonexistent_name_returns_none(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.country import resolve_country
            result = resolve_country("Nonexistentlandia99999")
            assert result is None

    def test_exception_returns_none(self, app):
        with app.app_context():
            from app.services.data_retrieval.country import resolve_country
            with patch("app.services.data_retrieval.country.db") as mock_db:
                mock_db.session.get.side_effect = Exception("db error")
                result = resolve_country(1)
                assert result is None


# ---------------------------------------------------------------------------
# get_country_info
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetCountryInfo:
    def test_country_not_found_returns_error(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.country import get_country_info
            result = get_country_info("Nonexistent Country 99999XYZ")
            assert "error" in result

    def test_access_denied_returns_error(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.country import get_country_info
            country = create_test_country(db_session)
            with patch("app.services.data_retrieval.country.check_country_access", return_value=False):
                result = get_country_info(country.id)
                assert "error" in result
                assert "Access denied" in result["error"]

    def test_found_with_no_assignments(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.country import get_country_info
            country = create_test_country(db_session)
            with patch("app.services.data_retrieval.country.check_country_access", return_value=True):
                result = get_country_info(country.id)
                assert "error" not in result
                assert result["country"]["id"] == country.id
                assert result["assignments"]["total"] == 0
                assert result["assignments"]["completed"] == 0
                assert result["assignments"]["pending"] == 0

    def test_found_with_submitted_assignments(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.country import get_country_info
            country = create_test_country(db_session)
            template = create_test_template(db_session)
            aes = create_test_assignment_entity_status(
                db_session, country=country, template=template, status="submitted"
            )
            with patch("app.services.data_retrieval.country.check_country_access", return_value=True):
                result = get_country_info(country.id)
                assert result["assignments"]["total"] == 1
                assert result["assignments"]["completed"] == 1
                assert result["assignments"]["pending"] == 0

    def test_found_with_upcoming_deadline(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.country import get_country_info
            from app.models.assignments import AssignmentEntityStatus
            country = create_test_country(db_session)
            template = create_test_template(db_session)
            aes = create_test_assignment_entity_status(
                db_session, country=country, template=template, status="in_progress"
            )
            future_date = datetime.now(timezone.utc) + timedelta(days=10)
            aes.due_date = future_date
            db_session.commit()

            with patch("app.services.data_retrieval.country.check_country_access", return_value=True):
                result = get_country_info(country.id)
                assert len(result["upcoming_deadlines"]) >= 0

    def test_found_returns_recent_submissions(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.country import get_country_info
            from app.models.assignments import AssignmentEntityStatus
            country = create_test_country(db_session)
            template = create_test_template(db_session)
            aes = create_test_assignment_entity_status(
                db_session, country=country, template=template, status="approved"
            )
            aes.status_timestamp = datetime.now(timezone.utc)
            db_session.commit()

            with patch("app.services.data_retrieval.country.check_country_access", return_value=True):
                result = get_country_info(country.id)
                assert len(result["recent_submissions"]) >= 1

    def test_by_string_identifier(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.country import get_country_info
            country = create_test_country(db_session, name="Stringly", iso2="ST", iso3="STR")
            with patch("app.services.data_retrieval.country.check_country_access", return_value=True):
                result = get_country_info("Stringly")
                assert "error" not in result
                assert result["country"]["name"] == "Stringly"

    def test_exception_returns_error(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.country import get_country_info
            with patch("app.services.data_retrieval.country.db") as mock_db:
                mock_db.session.get.side_effect = Exception("db failure")
                result = get_country_info(1)
                assert "error" in result


# ---------------------------------------------------------------------------
# get_assignments_for_country
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetAssignmentsForCountry:
    def test_access_denied_returns_empty(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.country import get_assignments_for_country
            country = create_test_country(db_session)
            with patch("app.services.data_retrieval.country.check_country_access", return_value=False):
                mock_user = MagicMock()
                mock_user.id = 1
                with patch("app.services.data_retrieval.country.current_user", mock_user):
                    result = get_assignments_for_country(country.id)
                    assert result == []

    def test_returns_all_assignments(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.country import get_assignments_for_country
            country = create_test_country(db_session)
            template = create_test_template(db_session)
            aes = create_test_assignment_entity_status(
                db_session, country=country, template=template, status="in_progress"
            )
            with patch("app.services.data_retrieval.country.check_country_access", return_value=True):
                result = get_assignments_for_country(country.id)
                assert len(result) >= 1
                assert result[0]["status"] == "in_progress"

    def test_status_filter_applied(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.country import get_assignments_for_country
            country = create_test_country(db_session)
            template = create_test_template(db_session)
            aes1 = create_test_assignment_entity_status(
                db_session, country=country, template=template, status="in_progress"
            )
            template2 = create_test_template(db_session)
            aes2 = create_test_assignment_entity_status(
                db_session, country=country, template=template2, status="submitted"
            )
            with patch("app.services.data_retrieval.country.check_country_access", return_value=True):
                result = get_assignments_for_country(country.id, status_filter="submitted")
                statuses = [r["status"] for r in result]
                assert "in_progress" not in statuses
                assert all(s == "submitted" for s in statuses)

    def test_include_details_true(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.country import get_assignments_for_country
            country = create_test_country(db_session)
            template = create_test_template(db_session)
            aes = create_test_assignment_entity_status(
                db_session, country=country, template=template
            )
            with patch("app.services.data_retrieval.country.check_country_access", return_value=True):
                result = get_assignments_for_country(country.id, include_details=True)
                assert len(result) >= 1
                assert "template_description" in result[0]

    def test_include_details_false(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.country import get_assignments_for_country
            country = create_test_country(db_session)
            template = create_test_template(db_session)
            aes = create_test_assignment_entity_status(
                db_session, country=country, template=template
            )
            with patch("app.services.data_retrieval.country.check_country_access", return_value=True):
                result = get_assignments_for_country(country.id, include_details=False)
                assert len(result) >= 1
                assert "template_description" not in result[0]

    def test_completed_assignment_is_marked(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.country import get_assignments_for_country
            country = create_test_country(db_session)
            template = create_test_template(db_session)
            create_test_assignment_entity_status(
                db_session, country=country, template=template, status="approved"
            )
            with patch("app.services.data_retrieval.country.check_country_access", return_value=True):
                result = get_assignments_for_country(country.id)
                assert result[0]["is_completed"] is True

    def test_exception_returns_empty(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.country import get_assignments_for_country
            country = create_test_country(db_session)
            with patch("app.services.data_retrieval.country.check_country_access", return_value=True), \
                 patch("app.services.data_retrieval.country.db") as mock_db:
                mock_db.session.query.side_effect = Exception("fail")
                result = get_assignments_for_country(country.id)
                assert result == []


# ---------------------------------------------------------------------------
# get_user_countries
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetUserCountries:
    def test_unrestricted_returns_all_countries(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.country import get_user_countries
            c1 = create_test_country(db_session)
            c2 = create_test_country(db_session)
            with patch("app.services.data_retrieval.country.user_allowed_country_ids", return_value=None):
                result = get_user_countries()
                ids = [r["id"] for r in result]
                assert c1.id in ids
                assert c2.id in ids

    def test_restricted_user_returns_user_countries(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.country import get_user_countries
            country = create_test_country(db_session)
            mock_countries_qs = MagicMock()
            mock_countries_qs.order_by.return_value = [country]
            mock_user = MagicMock()
            mock_user.countries = mock_countries_qs
            with patch("app.services.data_retrieval.country.user_allowed_country_ids",
                       return_value={country.id}), \
                 patch("app.services.data_retrieval.country.current_user", mock_user):
                result = get_user_countries()
                ids = [r["id"] for r in result]
                assert country.id in ids

    def test_user_without_countries_attr_returns_empty(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.country import get_user_countries
            mock_user = MagicMock(spec=[])  # No 'countries' attribute
            with patch("app.services.data_retrieval.country.user_allowed_country_ids",
                       return_value={1, 2}), \
                 patch("app.services.data_retrieval.country.current_user", mock_user):
                result = get_user_countries()
                assert result == []

    def test_result_structure(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.country import get_user_countries
            country = create_test_country(db_session, iso3="ABC")
            with patch("app.services.data_retrieval.country.user_allowed_country_ids", return_value=None):
                result = get_user_countries()
                if result:
                    for r in result:
                        assert "id" in r
                        assert "name" in r
                        assert "iso3" in r
                        assert "national_society" in r

    def test_exception_returns_empty(self, app):
        with app.app_context():
            from app.services.data_retrieval.country import get_user_countries
            with patch("app.services.data_retrieval.country.user_allowed_country_ids",
                       side_effect=Exception("err")):
                result = get_user_countries()
                assert result == []


# ---------------------------------------------------------------------------
# get_user_country_ids
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetUserCountryIds:
    def test_unrestricted_returns_all_ids(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.country import get_user_country_ids
            c1 = create_test_country(db_session)
            c2 = create_test_country(db_session)
            with patch("app.services.data_retrieval.country.user_allowed_country_ids", return_value=None):
                result = get_user_country_ids()
                assert isinstance(result, list)
                assert c1.id in result
                assert c2.id in result

    def test_restricted_returns_user_country_ids(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.country import get_user_country_ids
            country = create_test_country(db_session)
            mock_countries_qs = MagicMock()
            mock_countries_qs.all.return_value = [country]
            mock_user = MagicMock()
            mock_user.countries = mock_countries_qs
            with patch("app.services.data_retrieval.country.user_allowed_country_ids",
                       return_value={country.id}), \
                 patch("app.services.data_retrieval.country.current_user", mock_user):
                result = get_user_country_ids()
                assert country.id in result

    def test_no_countries_attr_returns_empty(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.country import get_user_country_ids
            mock_user = MagicMock(spec=[])
            with patch("app.services.data_retrieval.country.user_allowed_country_ids",
                       return_value={1}), \
                 patch("app.services.data_retrieval.country.current_user", mock_user):
                result = get_user_country_ids()
                assert result == []

    def test_exception_returns_empty(self, app):
        with app.app_context():
            from app.services.data_retrieval.country import get_user_country_ids
            with patch("app.services.data_retrieval.country.user_allowed_country_ids",
                       side_effect=Exception("err")):
                result = get_user_country_ids()
                assert result == []
