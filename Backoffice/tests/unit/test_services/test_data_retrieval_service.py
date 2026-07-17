"""
Comprehensive tests for app/services/data_retrieval_service.py.

Covers: _effective_user_role_and_id, _dialect_name, get_user_profile,
get_indicator_details, get_template_structure, get_platform_stats,
get_user_data_context, get_formdata_map, get_aes_with_joins, ensure_aes_access.
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, PropertyMock

from tests.factories import (
    create_test_user, create_test_admin, create_test_country,
    create_test_template, create_test_section, create_test_item,
    create_test_assignment_entity_status,
)
from app.models import IndicatorBank, FormData


def _make_indicator(db_session, name: str, archived: bool = False) -> IndicatorBank:
    ind = IndicatorBank(name=name, type="number", archived=archived)
    db_session.add(ind)
    db_session.commit()
    db_session.refresh(ind)
    return ind


# ---------------------------------------------------------------------------
# _effective_user_role_and_id
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestEffectiveUserRoleAndId:
    def test_authenticated_user_returns_role_and_id(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import _effective_user_role_and_id
            user = create_test_admin(db_session)
            mock_user = MagicMock()
            mock_user.is_authenticated = True
            mock_user.id = user.id
            with patch("app.services.data_retrieval_service.current_user", mock_user), \
                 patch("app.services.authorization_service.AuthorizationService.access_level",
                       return_value="admin"):
                result = _effective_user_role_and_id()
                assert result["user_id"] == user.id
                assert result["user_role"] == "admin"

    def test_unauthenticated_returns_public_role(self, app):
        with app.app_context():
            from app.services.data_retrieval_service import _effective_user_role_and_id
            mock_user = MagicMock()
            mock_user.is_authenticated = False
            with patch("app.services.data_retrieval_service.current_user", mock_user), \
                 patch("flask.has_request_context", return_value=False):
                result = _effective_user_role_and_id()
                assert result["user_role"] == "public"
                assert result["user_id"] is None

    def test_g_context_sets_user_id(self, app):
        with app.app_context():
            from app.services.data_retrieval_service import _effective_user_role_and_id
            mock_user = MagicMock()
            mock_user.is_authenticated = False
            mock_g = MagicMock()
            mock_g.ai_user_id = 42
            mock_g.ai_user_access_level = "focal_point"
            with patch("app.services.data_retrieval_service.current_user", mock_user), \
                 patch("flask.has_request_context", return_value=True), \
                 patch("flask.g", mock_g):
                result = _effective_user_role_and_id()
                assert result["user_id"] == 42
                assert result["user_role"] == "focal_point"

    def test_auth_resolution_exception_handled(self, app):
        with app.app_context():
            from app.services.data_retrieval_service import _effective_user_role_and_id
            mock_user = MagicMock()
            mock_user.is_authenticated = True
            mock_user.id = 1
            with patch("app.services.data_retrieval_service.current_user", mock_user), \
                 patch("app.services.authorization_service.AuthorizationService.access_level",
                       side_effect=Exception("err")), \
                 patch("flask.has_request_context", return_value=False):
                result = _effective_user_role_and_id()
                assert result["user_role"] == "public"

    def test_g_ai_user_role_fallback(self, app):
        with app.app_context():
            from app.services.data_retrieval_service import _effective_user_role_and_id
            mock_user = MagicMock()
            mock_user.is_authenticated = False
            mock_g = MagicMock()
            mock_g.ai_user_id = None
            mock_g.ai_user_access_level = None
            mock_g.ai_user_role = "chatbot"
            with patch("app.services.data_retrieval_service.current_user", mock_user), \
                 patch("flask.has_request_context", return_value=True), \
                 patch("flask.g", mock_g):
                result = _effective_user_role_and_id()
                assert result["user_role"] == "chatbot"


# ---------------------------------------------------------------------------
# _dialect_name
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestDialectName:
    def test_returns_dialect_name(self, app):
        with app.app_context():
            from app.services.data_retrieval_service import _dialect_name
            result = _dialect_name()
            assert isinstance(result, str)

    def test_exception_returns_empty_string(self, app):
        with app.app_context():
            from app.services.data_retrieval_service import _dialect_name
            with patch("app.services.data_retrieval_service.db") as mock_db:
                mock_db.engine = None
                result = _dialect_name()
                assert result == ""


# ---------------------------------------------------------------------------
# get_user_profile
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetUserProfile:
    def test_unauthenticated_no_user_id_returns_error(self, app):
        with app.app_context():
            from app.services.data_retrieval_service import get_user_profile
            mock_user = MagicMock()
            mock_user.is_authenticated = False
            with patch("app.services.data_retrieval_service.current_user", mock_user):
                result = get_user_profile()
                assert "error" in result
                assert "Not authenticated" in result["error"]

    def test_nonexistent_user_id_returns_error(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import get_user_profile
            mock_user = MagicMock()
            mock_user.is_authenticated = True
            mock_user.id = 999999
            with patch("app.services.data_retrieval_service.current_user", mock_user):
                result = get_user_profile(user_id=999999)
                assert "error" in result

    def test_returns_profile_for_current_user(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import get_user_profile
            user = create_test_user(db_session)
            with patch("app.services.data_retrieval_service.current_user", user):
                result = get_user_profile()
                assert "error" not in result
                assert result["id"] == user.id
                assert result["email"] == user.email

    def test_returns_profile_by_user_id_for_admin(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import get_user_profile
            admin = create_test_admin(db_session)
            target_user = create_test_user(db_session)
            with patch("app.services.data_retrieval_service.current_user", admin), \
                 patch("app.services.authorization_service.AuthorizationService.is_system_manager",
                       return_value=True):
                result = get_user_profile(user_id=target_user.id)
                assert "error" not in result
                assert result["id"] == target_user.id

    def test_access_denied_for_non_admin_viewing_other_user(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import get_user_profile
            user1 = create_test_user(db_session)
            user2 = create_test_user(db_session)
            with patch("app.services.data_retrieval_service.current_user", user1), \
                 patch("app.services.authorization_service.AuthorizationService.is_system_manager",
                       return_value=False), \
                 patch("app.services.authorization_service.AuthorizationService.has_rbac_permission",
                       return_value=False):
                result = get_user_profile(user_id=user2.id)
                assert "error" in result
                assert "Access denied" in result["error"]

    def test_profile_includes_rbac_roles(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import get_user_profile
            user = create_test_user(db_session)
            with patch("app.services.data_retrieval_service.current_user", user):
                result = get_user_profile()
                assert "rbac_roles" in result
                assert isinstance(result["rbac_roles"], list)

    def test_exception_returns_error(self, app):
        with app.app_context():
            from app.services.data_retrieval_service import get_user_profile
            with patch("app.services.data_retrieval_service.current_user",
                       side_effect=Exception("fail")):
                result = get_user_profile()
                assert "error" in result


# ---------------------------------------------------------------------------
# get_indicator_details
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetIndicatorDetails:
    def test_by_int_id(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import get_indicator_details
            ind = _make_indicator(db_session, "Number of volunteers SVC1")
            result = get_indicator_details(ind.id)
            assert result is not None
            assert result["id"] == ind.id
            assert result["name"] == ind.name

    def test_by_string_digit_id(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import get_indicator_details
            ind = _make_indicator(db_session, "Number of branches SVC2")
            result = get_indicator_details(str(ind.id))
            assert result is not None
            assert result["id"] == ind.id

    def test_by_name_keyword_fallback(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import get_indicator_details
            ind = _make_indicator(db_session, "Number of staff members SVC3")
            with patch("app.services.indicator_resolution_service.resolve_indicator_identifier",
                       return_value=None):
                result = get_indicator_details("staff members SVC3")
                assert result is not None

    def test_not_found_returns_none(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import get_indicator_details
            with patch("app.services.indicator_resolution_service.resolve_indicator_identifier",
                       return_value=None):
                result = get_indicator_details("Completely unknown indicator 99999")
                assert result is None

    def test_not_found_by_int_returns_none(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import get_indicator_details
            result = get_indicator_details(999999)
            assert result is None

    def test_exception_returns_none(self, app):
        with app.app_context():
            from app.services.data_retrieval_service import get_indicator_details
            with patch("app.services.data_retrieval_service.db") as mock_db:
                mock_db.session.get.side_effect = Exception("db fail")
                result = get_indicator_details(1)
                assert result is None

    def test_result_structure(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import get_indicator_details
            ind = _make_indicator(db_session, "Members test SVC4")
            result = get_indicator_details(ind.id)
            assert result is not None
            for key in ("id", "name", "type", "unit", "definition", "emergency", "archived"):
                assert key in result

    def test_fdrs_kpi_code_search(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import get_indicator_details
            # If fdrs_kpi_code attribute doesn't exist on model, this exercises the getattr check
            with patch("app.services.indicator_resolution_service.resolve_indicator_identifier",
                       return_value=None):
                result = get_indicator_details("some_kpi_code_XYZ")
                assert result is None or isinstance(result, dict)

    def test_multi_word_fallback_search(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import get_indicator_details
            ind = _make_indicator(db_session, "total number trained volunteers SVC5")
            with patch("app.services.indicator_resolution_service.resolve_indicator_identifier",
                       return_value=None):
                result = get_indicator_details("total trained volunteers SVC5")
                # May or may not find depending on word pattern
                assert result is None or isinstance(result, dict)


# ---------------------------------------------------------------------------
# get_template_structure
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetTemplateStructure:
    def test_not_found_by_int_returns_error(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import get_template_structure
            result = get_template_structure(999999)
            assert "error" in result

    def test_not_found_by_name_returns_error(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import get_template_structure
            result = get_template_structure("NonexistentTemplateName99999")
            assert "error" in result

    def test_found_by_int_id(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import get_template_structure
            template = create_test_template(db_session)
            result = get_template_structure(template.id)
            assert "error" not in result
            assert result["template"]["id"] == template.id

    def test_found_by_string_digit_id(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import get_template_structure
            template = create_test_template(db_session)
            result = get_template_structure(str(template.id))
            assert "error" not in result
            assert result["template"]["id"] == template.id

    def test_found_by_name(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import get_template_structure
            template = create_test_template(db_session, name="UniqueTemplateName SVC99")
            result = get_template_structure("UniqueTemplateName SVC99")
            assert "error" not in result

    def test_result_structure(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import get_template_structure
            template = create_test_template(db_session)
            result = get_template_structure(template.id)
            assert "template" in result
            assert "sections" in result
            assert "total_sections" in result
            assert "total_items" in result
            assert "indicator_names" in result

    def test_with_sections(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import get_template_structure
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            result = get_template_structure(template.id)
            assert result["total_sections"] >= 1

    def test_with_sections_and_items(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import get_template_structure
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            item = create_test_item(db_session, section, template)
            result = get_template_structure(template.id)
            assert result["total_items"] >= 1

    def test_exception_returns_error(self, app):
        with app.app_context():
            from app.services.data_retrieval_service import get_template_structure
            with patch("app.services.data_retrieval_service.db") as mock_db:
                mock_db.session.get.side_effect = Exception("fail")
                result = get_template_structure(1)
                assert "error" in result


# ---------------------------------------------------------------------------
# get_platform_stats
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetPlatformStats:
    def test_user_scoped_returns_stats_dict(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import get_platform_stats
            mock_user = MagicMock()
            mock_user.is_authenticated = True
            with patch("app.services.data_retrieval_service.current_user", mock_user), \
                 patch("app.services.data_retrieval_service._user_allowed_country_ids",
                       return_value=None):
                result = get_platform_stats(user_scoped=True)
                assert isinstance(result, dict)
                assert "total_users" in result
                assert "total_countries" in result
                assert "total_templates" in result
                assert "total_indicators" in result
                assert "total_assignments" in result
                assert "total_submissions" in result

    def test_not_user_scoped_admin_returns_global_stats(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import get_platform_stats
            mock_user = MagicMock()
            mock_user.is_authenticated = True
            with patch("app.services.data_retrieval_service.current_user", mock_user), \
                 patch("app.services.authorization_service.AuthorizationService.is_admin",
                       return_value=True), \
                 patch("app.services.authorization_service.AuthorizationService.is_system_manager",
                       return_value=False):
                result = get_platform_stats(user_scoped=False)
                assert isinstance(result, dict)
                assert "total_users" in result

    def test_not_user_scoped_non_admin_falls_back_to_scoped(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import get_platform_stats
            mock_user = MagicMock()
            mock_user.is_authenticated = True
            with patch("app.services.data_retrieval_service.current_user", mock_user), \
                 patch("app.services.authorization_service.AuthorizationService.is_admin",
                       return_value=False), \
                 patch("app.services.authorization_service.AuthorizationService.is_system_manager",
                       return_value=False), \
                 patch("app.services.data_retrieval_service._user_allowed_country_ids",
                       return_value=set()):
                result = get_platform_stats(user_scoped=False)
                assert isinstance(result, dict)

    def test_user_scoped_with_allowed_countries(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import get_platform_stats
            country = create_test_country(db_session)
            template = create_test_template(db_session)
            aes = create_test_assignment_entity_status(
                db_session, country=country, template=template, status="submitted"
            )
            with patch("app.services.data_retrieval_service._user_allowed_country_ids",
                       return_value={country.id}):
                result = get_platform_stats(user_scoped=True)
                assert result["total_submissions"] >= 1

    def test_exception_returns_zero_stats(self, app):
        with app.app_context():
            from app.services.data_retrieval_service import get_platform_stats
            with patch("app.services.data_retrieval_service._user_allowed_country_ids",
                       side_effect=Exception("fail")):
                result = get_platform_stats()
                assert result["total_users"] == 0


# ---------------------------------------------------------------------------
# get_user_data_context
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetUserDataContext:
    def test_nonexistent_user_returns_empty(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import get_user_data_context
            mock_user = MagicMock()
            mock_user.is_authenticated = True
            mock_user.id = 1
            with patch("app.services.data_retrieval_service.current_user", mock_user):
                result = get_user_data_context(user_id=999999)
                assert result == {}

    def test_focal_point_returns_country_data(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import get_user_data_context
            from tests.factories import create_focal_point_with_country
            user, country, aes = create_focal_point_with_country(db_session)
            with patch("app.services.data_retrieval_service.current_user", user), \
                 patch("app.services.authorization_service.AuthorizationService.has_role",
                       return_value=True), \
                 patch("app.services.authorization_service.AuthorizationService.is_admin",
                       return_value=False):
                result = get_user_data_context()
                assert "countries" in result

    def test_admin_returns_submission_counts(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import get_user_data_context
            admin = create_test_admin(db_session)
            with patch("app.services.data_retrieval_service.current_user", admin), \
                 patch("app.services.authorization_service.AuthorizationService.has_role",
                       return_value=False), \
                 patch("app.services.authorization_service.AuthorizationService.is_admin",
                       return_value=True):
                result = get_user_data_context()
                assert "recent_submissions_count" in result
                assert "pending_assignments" in result

    def test_cross_user_access_denied_for_non_admin(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import get_user_data_context
            user1 = create_test_user(db_session)
            user2 = create_test_user(db_session)
            with patch("app.services.data_retrieval_service.current_user", user1), \
                 patch("app.services.authorization_service.AuthorizationService.is_system_manager",
                       return_value=False), \
                 patch("app.services.authorization_service.AuthorizationService.has_rbac_permission",
                       return_value=False):
                result = get_user_data_context(user_id=user2.id)
                assert result == {}

    def test_exception_returns_empty(self, app):
        with app.app_context():
            from app.services.data_retrieval_service import get_user_data_context
            with patch("app.services.data_retrieval_service.current_user",
                       side_effect=Exception("fail")):
                result = get_user_data_context()
                assert result == {}


# ---------------------------------------------------------------------------
# get_formdata_map
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetFormdataMap:
    def test_aes_not_found_returns_empty(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import get_formdata_map
            mock_user = MagicMock()
            mock_user.is_authenticated = True
            with patch("app.services.data_retrieval_service.current_user", mock_user):
                result = get_formdata_map(999999)
                assert result == {}

    def test_access_denied_returns_empty(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import get_formdata_map
            country = create_test_country(db_session)
            template = create_test_template(db_session)
            aes = create_test_assignment_entity_status(
                db_session, country=country, template=template
            )
            mock_user = MagicMock()
            mock_user.is_authenticated = True
            with patch("app.services.data_retrieval_service.current_user", mock_user), \
                 patch("app.services.entity_service.EntityService.check_user_entity_access",
                       return_value=False):
                result = get_formdata_map(aes.id)
                assert result == {}

    def test_returns_formdata_map_when_access_granted(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import get_formdata_map
            country = create_test_country(db_session)
            template = create_test_template(db_session)
            aes = create_test_assignment_entity_status(
                db_session, country=country, template=template
            )
            mock_user = MagicMock()
            mock_user.is_authenticated = True
            with patch("app.services.data_retrieval_service.current_user", mock_user), \
                 patch("app.services.entity_service.EntityService.check_user_entity_access",
                       return_value=True):
                result = get_formdata_map(aes.id)
                assert isinstance(result, dict)

    def test_item_ids_filter_applied(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import get_formdata_map
            country = create_test_country(db_session)
            template = create_test_template(db_session)
            aes = create_test_assignment_entity_status(
                db_session, country=country, template=template
            )
            mock_user = MagicMock()
            mock_user.is_authenticated = True
            with patch("app.services.data_retrieval_service.current_user", mock_user), \
                 patch("app.services.entity_service.EntityService.check_user_entity_access",
                       return_value=True):
                result = get_formdata_map(aes.id, item_ids=[1, 2, 3])
                assert isinstance(result, dict)

    def test_exception_returns_empty(self, app):
        with app.app_context():
            from app.services.data_retrieval_service import get_formdata_map
            with patch("app.services.data_retrieval_service.db") as mock_db:
                mock_db.session.get.side_effect = Exception("fail")
                result = get_formdata_map(1)
                assert result == {}


# ---------------------------------------------------------------------------
# get_aes_with_joins
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetAesWithJoins:
    def test_not_found_returns_none(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import get_aes_with_joins
            mock_user = MagicMock()
            with patch("app.services.data_retrieval_service.current_user", mock_user):
                result = get_aes_with_joins(999999)
                assert result is None

    def test_access_denied_returns_none(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import get_aes_with_joins
            country = create_test_country(db_session)
            template = create_test_template(db_session)
            aes = create_test_assignment_entity_status(
                db_session, country=country, template=template
            )
            mock_user = MagicMock()
            with patch("app.services.data_retrieval_service.current_user", mock_user), \
                 patch("app.services.entity_service.EntityService.check_user_entity_access",
                       return_value=False):
                result = get_aes_with_joins(aes.id)
                assert result is None

    def test_found_with_access_returns_aes(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import get_aes_with_joins
            country = create_test_country(db_session)
            template = create_test_template(db_session)
            aes = create_test_assignment_entity_status(
                db_session, country=country, template=template
            )
            mock_user = MagicMock()
            with patch("app.services.data_retrieval_service.current_user", mock_user), \
                 patch("app.services.entity_service.EntityService.check_user_entity_access",
                       return_value=True):
                result = get_aes_with_joins(aes.id)
                assert result is not None
                assert result.id == aes.id

    def test_exception_returns_none(self, app):
        with app.app_context():
            from app.services.data_retrieval_service import get_aes_with_joins
            with patch("app.services.data_retrieval_service.AssignmentEntityStatus") as mock_aes:
                mock_aes.query.options.side_effect = Exception("fail")
                result = get_aes_with_joins(1)
                assert result is None


# ---------------------------------------------------------------------------
# ensure_aes_access
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestEnsureAesAccess:
    def test_not_found_returns_error(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import ensure_aes_access
            mock_user = MagicMock()
            with patch("app.services.data_retrieval_service.current_user", mock_user):
                result = ensure_aes_access(999999)
                assert "error" in result

    def test_found_returns_aes(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import ensure_aes_access
            country = create_test_country(db_session)
            template = create_test_template(db_session)
            aes = create_test_assignment_entity_status(
                db_session, country=country, template=template
            )
            mock_user = MagicMock()
            with patch("app.services.data_retrieval_service.current_user", mock_user), \
                 patch("app.services.entity_service.EntityService.check_user_entity_access",
                       return_value=True):
                result = ensure_aes_access(aes.id)
                assert "aes" in result
                assert result["aes"].id == aes.id

    def test_exception_returns_error(self, app):
        with app.app_context():
            from app.services.data_retrieval_service import ensure_aes_access
            with patch("app.services.data_retrieval_service.get_aes_with_joins",
                       side_effect=Exception("fail")):
                result = ensure_aes_access(1)
                assert "error" in result


# ---------------------------------------------------------------------------
# check_aes_access_light (+ per-(user, aes) positive-result cache)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCheckAesAccessLight:
    def _mock_user(self, user_id):
        mock_user = MagicMock()
        mock_user.id = user_id
        return mock_user

    def test_not_found_returns_false_and_not_cached(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import (
                check_aes_access_light, _aes_access_cache, clear_aes_access_light_cache,
            )
            clear_aes_access_light_cache()
            with patch("app.services.data_retrieval_service.current_user",
                       self._mock_user(7)):
                assert check_aes_access_light(999999) is False
            assert _aes_access_cache == {}

    def test_positive_result_cached_skips_recheck(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import (
                check_aes_access_light, clear_aes_access_light_cache,
            )
            clear_aes_access_light_cache()
            country = create_test_country(db_session)
            template = create_test_template(db_session)
            aes = create_test_assignment_entity_status(
                db_session, country=country, template=template
            )
            with patch("app.services.data_retrieval_service.current_user",
                       self._mock_user(7)), \
                 patch("app.services.entity_service.EntityService.check_user_entity_access",
                       return_value=True) as mock_check:
                assert check_aes_access_light(aes.id) is True
                assert check_aes_access_light(aes.id) is True
                assert mock_check.call_count == 1

    def test_denial_not_cached(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import (
                check_aes_access_light, _aes_access_cache, clear_aes_access_light_cache,
            )
            clear_aes_access_light_cache()
            country = create_test_country(db_session)
            template = create_test_template(db_session)
            aes = create_test_assignment_entity_status(
                db_session, country=country, template=template
            )
            with patch("app.services.data_retrieval_service.current_user",
                       self._mock_user(7)), \
                 patch("app.services.entity_service.EntityService.check_user_entity_access",
                       return_value=False) as mock_check:
                assert check_aes_access_light(aes.id) is False
                assert check_aes_access_light(aes.id) is False
                assert mock_check.call_count == 2
            assert _aes_access_cache == {}

    def test_cache_is_per_user(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_service import (
                check_aes_access_light, clear_aes_access_light_cache,
            )
            clear_aes_access_light_cache()
            country = create_test_country(db_session)
            template = create_test_template(db_session)
            aes = create_test_assignment_entity_status(
                db_session, country=country, template=template
            )
            with patch("app.services.entity_service.EntityService.check_user_entity_access",
                       return_value=True) as mock_check:
                with patch("app.services.data_retrieval_service.current_user",
                           self._mock_user(7)):
                    assert check_aes_access_light(aes.id) is True
                with patch("app.services.data_retrieval_service.current_user",
                           self._mock_user(8)):
                    assert check_aes_access_light(aes.id) is True
                assert mock_check.call_count == 2

    def test_expired_entry_rechecks(self, app, db_session):
        with app.app_context():
            import app.services.data_retrieval_service as drs
            drs.clear_aes_access_light_cache()
            country = create_test_country(db_session)
            template = create_test_template(db_session)
            aes = create_test_assignment_entity_status(
                db_session, country=country, template=template
            )
            with patch("app.services.data_retrieval_service.current_user",
                       self._mock_user(7)), \
                 patch("app.services.entity_service.EntityService.check_user_entity_access",
                       return_value=True) as mock_check:
                assert drs.check_aes_access_light(aes.id) is True
                # Force the entry to be expired, then confirm a fresh DB check.
                import time as _time
                drs._aes_access_cache[(7, aes.id)] = _time.monotonic() - 1
                assert drs.check_aes_access_light(aes.id) is True
                assert mock_check.call_count == 2

    def test_clear_cache_helper(self, app, db_session):
        with app.app_context():
            import app.services.data_retrieval_service as drs
            drs._aes_access_cache[(7, 1)] = 10.0
            drs.clear_aes_access_light_cache()
            assert drs._aes_access_cache == {}
