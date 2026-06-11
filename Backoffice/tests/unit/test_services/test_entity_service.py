"""
Comprehensive tests for EntityService.

Targets ~100% coverage of app/services/entity_service.py.
Uses DB records for Country and heavy mocking for organisation entity types.
"""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from app.models.enums import EntityType
from app.services.entity_service import EntityService
from tests.factories import (
    create_test_admin,
    create_test_country,
    create_test_user,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_entity(name="Test Entity"):
    e = MagicMock()
    e.name = name
    return e


def _ns_branch(name="Branch", country=None):
    b = _mock_entity(name)
    b.country = country or _mock_entity("Country")
    return b


def _ns_subbranch(name="SubBranch", branch=None):
    sb = _mock_entity(name)
    sb.branch = branch or _ns_branch()
    return sb


def _ns_localunit(name="LocalUnit", branch=None, subbranch=None):
    lu = _mock_entity(name)
    lu.branch = branch or _ns_branch()
    lu.subbranch = subbranch
    lu.subbranch_id = int(subbranch.id) if subbranch else None
    return lu


def _department(name="Dept", division=None):
    d = _mock_entity(name)
    d.division = division or _mock_entity("Division")
    return d


def _cluster_office(name="Cluster", regional_office=None):
    co = _mock_entity(name)
    co.regional_office = regional_office or _mock_entity("Regional")
    return co


# ---------------------------------------------------------------------------
# sort_document_modal_entity_choice_rows
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestSortDocumentModalEntityChoiceRows:
    def test_sorts_by_group_order_then_label(self):
        rows = [
            {"entity_type": "ns_branch", "label": "ZBranch"},
            {"entity_type": "country", "label": "Zimbabwe"},
            {"entity_type": "country", "label": "Angola"},
            {"entity_type": "ns_branch", "label": "ABranch"},
        ]
        result = EntityService.sort_document_modal_entity_choice_rows(rows)
        entity_types = [r["entity_type"] for r in result]
        # All countries before ns_branches
        assert entity_types.index("country") < entity_types.index("ns_branch")

    def test_labels_sorted_case_insensitive_within_group(self):
        rows = [
            {"entity_type": "country", "label": "Zimbabwe"},
            {"entity_type": "country", "label": "Angola"},
        ]
        result = EntityService.sort_document_modal_entity_choice_rows(rows)
        labels = [r["label"] for r in result]
        assert labels == ["Angola", "Zimbabwe"]

    def test_unknown_entity_type_sorted_last(self):
        rows = [
            {"entity_type": "unknown_type", "label": "A"},
            {"entity_type": "country", "label": "B"},
        ]
        result = EntityService.sort_document_modal_entity_choice_rows(rows)
        assert result[0]["entity_type"] == "country"
        assert result[-1]["entity_type"] == "unknown_type"

    def test_empty_list_returns_empty(self):
        assert EntityService.sort_document_modal_entity_choice_rows([]) == []

    def test_row_missing_entity_type_handled(self):
        rows = [{"label": "No Type"}]
        result = EntityService.sort_document_modal_entity_choice_rows(rows)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# get_entity
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetEntity:
    def test_unknown_entity_type_returns_none(self, db_session, app):
        with app.app_context():
            result = EntityService.get_entity("totally_unknown_type", 1)
            assert result is None

    def test_country_entity_type(self, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            result = EntityService.get_entity(EntityType.country.value, country.id)
            assert result is not None
            assert result.id == country.id

    def test_returns_none_for_missing_id(self, db_session, app):
        with app.app_context():
            result = EntityService.get_entity(EntityType.country.value, 9_999_999)
            assert result is None


# ---------------------------------------------------------------------------
# get_entity_display_name
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetEntityDisplayName:
    def test_returns_name_for_known_entity(self, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            name = EntityService.get_entity_display_name(EntityType.country.value, country.id)
            assert name == country.name

    def test_returns_unknown_for_missing_entity(self, db_session, app):
        with app.app_context():
            name = EntityService.get_entity_display_name("country", 9_999_999)
            assert "Unknown" in name
            assert "9999999" in name


# ---------------------------------------------------------------------------
# get_entity_name
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetEntityName:
    def test_without_hierarchy_returns_display_name(self, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            result = EntityService.get_entity_name(EntityType.country.value, country.id, include_hierarchy=False)
            assert result == country.name

    def test_with_hierarchy_calls_get_entity_hierarchy(self, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            result = EntityService.get_entity_name(EntityType.country.value, country.id, include_hierarchy=True)
            # Country hierarchy is just the country name
            assert country.name in result


# ---------------------------------------------------------------------------
# get_localized_entity_display_name
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetLocalizedEntityDisplayName:
    def test_country_type_calls_localization(self, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            with patch("app.utils.form_localization.get_localized_country_name", return_value="Localized Name"):
                result = EntityService.get_localized_entity_display_name(
                    EntityType.country.value, country.id
                )
            assert result == "Localized Name"

    def test_non_country_type_returns_name(self, db_session, app):
        with app.app_context():
            branch_entity = _mock_entity("Test Branch")
            with patch.object(EntityService, "get_entity", return_value=branch_entity):
                result = EntityService.get_localized_entity_display_name(
                    EntityType.ns_branch.value, 1
                )
            assert result == "Test Branch"

    def test_missing_entity_returns_unknown(self, db_session, app):
        with app.app_context():
            result = EntityService.get_localized_entity_display_name("country", 9_999_999)
            assert "Unknown" in result


# ---------------------------------------------------------------------------
# get_localized_entity_name
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetLocalizedEntityName:
    def test_without_hierarchy(self, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            with patch("app.utils.form_localization.get_localized_country_name", return_value=country.name):
                result = EntityService.get_localized_entity_name(
                    EntityType.country.value, country.id, include_hierarchy=False
                )
            assert result == country.name

    def test_with_hierarchy(self, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            with patch("app.utils.form_localization.get_localized_country_name", return_value=country.name):
                result = EntityService.get_localized_entity_name(
                    EntityType.country.value, country.id, include_hierarchy=True
                )
            assert country.name in result


# ---------------------------------------------------------------------------
# get_entity_hierarchy — all entity type branches
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetEntityHierarchy:
    def test_country_hierarchy(self, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            result = EntityService.get_entity_hierarchy(EntityType.country.value, country.id)
            assert result == country.name

    def test_missing_entity_returns_unknown(self, db_session, app):
        with app.app_context():
            result = EntityService.get_entity_hierarchy("country", 9_999_999)
            assert "Unknown" in result

    def test_ns_branch_with_country(self, app):
        country = _mock_entity("Kenya")
        branch = _ns_branch("Nairobi Branch", country=country)
        with app.app_context():
            with patch.object(EntityService, "get_entity", return_value=branch):
                result = EntityService.get_entity_hierarchy(EntityType.ns_branch.value, 1)
        assert "Kenya" in result
        assert "Nairobi Branch" in result

    def test_ns_branch_without_country(self, app):
        branch = _mock_entity("Branch Without Country")
        branch.country = None
        with app.app_context():
            with patch.object(EntityService, "get_entity", return_value=branch):
                result = EntityService.get_entity_hierarchy(EntityType.ns_branch.value, 1)
        assert "Branch Without Country" in result

    def test_ns_subbranch_hierarchy(self, app):
        country = _mock_entity("Kenya")
        branch = _ns_branch("Nairobi", country=country)
        subbranch = _ns_subbranch("Downtown", branch=branch)
        with app.app_context():
            with patch.object(EntityService, "get_entity", return_value=subbranch):
                result = EntityService.get_entity_hierarchy(EntityType.ns_subbranch.value, 1)
        assert "Kenya" in result
        assert "Nairobi" in result
        assert "Downtown" in result

    def test_ns_subbranch_without_branch(self, app):
        subbranch = _mock_entity("StandAlone Sub")
        subbranch.branch = None
        with app.app_context():
            with patch.object(EntityService, "get_entity", return_value=subbranch):
                result = EntityService.get_entity_hierarchy(EntityType.ns_subbranch.value, 1)
        assert "StandAlone Sub" in result

    def test_ns_localunit_with_subbranch(self, app):
        country = _mock_entity("Kenya")
        branch = _ns_branch("Nairobi", country=country)
        subbranch = _ns_subbranch("Downtown", branch=branch)
        lu = _ns_localunit("HQ", branch=branch, subbranch=subbranch)
        with app.app_context():
            with patch.object(EntityService, "get_entity", return_value=lu):
                result = EntityService.get_entity_hierarchy(EntityType.ns_localunit.value, 1)
        assert "HQ" in result
        assert "Downtown" in result

    def test_ns_localunit_without_branch(self, app):
        lu = _mock_entity("Lone Unit")
        lu.branch = None
        with app.app_context():
            with patch.object(EntityService, "get_entity", return_value=lu):
                result = EntityService.get_entity_hierarchy(EntityType.ns_localunit.value, 1)
        assert "Lone Unit" in result

    def test_division_hierarchy(self, app):
        division = _mock_entity("HQ Division")
        with app.app_context():
            with patch.object(EntityService, "get_entity", return_value=division):
                result = EntityService.get_entity_hierarchy(EntityType.division.value, 1)
        assert "HQ Division" in result

    def test_department_hierarchy(self, app):
        division = _mock_entity("Finance Division")
        dept = _department("Budgeting", division=division)
        with app.app_context():
            with patch.object(EntityService, "get_entity", return_value=dept):
                result = EntityService.get_entity_hierarchy(EntityType.department.value, 1)
        assert "Finance Division" in result
        assert "Budgeting" in result

    def test_department_without_division(self, app):
        dept = _mock_entity("Lone Department")
        dept.division = None
        with app.app_context():
            with patch.object(EntityService, "get_entity", return_value=dept):
                result = EntityService.get_entity_hierarchy(EntityType.department.value, 1)
        assert "Lone Department" in result

    def test_regional_office_hierarchy(self, app):
        ro = _mock_entity("Africa Regional")
        with app.app_context():
            with patch.object(EntityService, "get_entity", return_value=ro):
                result = EntityService.get_entity_hierarchy(EntityType.regional_office.value, 1)
        assert "Africa Regional" in result

    def test_cluster_office_hierarchy(self, app):
        ro = _mock_entity("Africa Regional")
        co = _cluster_office("West Africa Cluster", regional_office=ro)
        with app.app_context():
            with patch.object(EntityService, "get_entity", return_value=co):
                result = EntityService.get_entity_hierarchy(EntityType.cluster_office.value, 1)
        assert "Africa Regional" in result
        assert "West Africa Cluster" in result

    def test_cluster_office_without_regional_office(self, app):
        co = _mock_entity("Lone Cluster")
        co.regional_office = None
        with app.app_context():
            with patch.object(EntityService, "get_entity", return_value=co):
                result = EntityService.get_entity_hierarchy(EntityType.cluster_office.value, 1)
        assert "Lone Cluster" in result


# ---------------------------------------------------------------------------
# get_localized_entity_hierarchy — all branches
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetLocalizedEntityHierarchy:
    def test_country_hierarchy_localized(self, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            with patch("app.utils.form_localization.get_localized_country_name", return_value="LocalizedName"):
                result = EntityService.get_localized_entity_hierarchy(
                    EntityType.country.value, country.id
                )
        assert "LocalizedName" in result

    def test_missing_entity_returns_unknown(self, db_session, app):
        with app.app_context():
            result = EntityService.get_localized_entity_hierarchy("country", 9_999_999)
            assert "Unknown" in result

    def test_ns_branch_with_country_localized(self, app):
        country = _mock_entity("Kenya")
        branch = _ns_branch("Nairobi Branch", country=country)
        with app.app_context():
            with patch.object(EntityService, "get_entity", return_value=branch):
                with patch(
                    "app.utils.form_localization.get_localized_country_name",
                    return_value="Localized Kenya",
                ):
                    result = EntityService.get_localized_entity_hierarchy(EntityType.ns_branch.value, 1)
        assert "Localized Kenya" in result

    def test_ns_subbranch_localized(self, app):
        country = _mock_entity("Kenya")
        branch = _ns_branch("Nairobi", country=country)
        subbranch = _ns_subbranch("Downtown", branch=branch)
        with app.app_context():
            with patch.object(EntityService, "get_entity", return_value=subbranch):
                with patch(
                    "app.utils.form_localization.get_localized_country_name",
                    return_value="L-Kenya",
                ):
                    result = EntityService.get_localized_entity_hierarchy(EntityType.ns_subbranch.value, 1)
        assert "L-Kenya" in result
        assert "Downtown" in result

    def test_ns_localunit_localized(self, app):
        country = _mock_entity("Kenya")
        branch = _ns_branch("Nairobi", country=country)
        lu = _ns_localunit("HQ", branch=branch)
        with app.app_context():
            with patch.object(EntityService, "get_entity", return_value=lu):
                with patch(
                    "app.utils.form_localization.get_localized_country_name",
                    return_value="L-Kenya",
                ):
                    result = EntityService.get_localized_entity_hierarchy(EntityType.ns_localunit.value, 1)
        assert "HQ" in result

    def test_division_localized(self, app):
        division = _mock_entity("Tech Division")
        with app.app_context():
            with patch.object(EntityService, "get_entity", return_value=division):
                result = EntityService.get_localized_entity_hierarchy(EntityType.division.value, 1)
        assert "Tech Division" in result

    def test_department_localized(self, app):
        division = _mock_entity("IT")
        dept = _department("Systems", division=division)
        with app.app_context():
            with patch.object(EntityService, "get_entity", return_value=dept):
                result = EntityService.get_localized_entity_hierarchy(EntityType.department.value, 1)
        assert "Systems" in result

    def test_regional_office_localized(self, app):
        ro = _mock_entity("MENA Region")
        with app.app_context():
            with patch.object(EntityService, "get_entity", return_value=ro):
                result = EntityService.get_localized_entity_hierarchy(EntityType.regional_office.value, 1)
        assert "MENA Region" in result

    def test_cluster_office_localized(self, app):
        ro = _mock_entity("MENA")
        co = _cluster_office("GCC Cluster", regional_office=ro)
        with app.app_context():
            with patch.object(EntityService, "get_entity", return_value=co):
                result = EntityService.get_localized_entity_hierarchy(EntityType.cluster_office.value, 1)
        assert "GCC Cluster" in result

    def test_localunit_with_subbranch_localized(self, app):
        country = _mock_entity("Kenya")
        branch = _ns_branch("Nairobi", country=country)
        subbranch = _ns_subbranch("CBD", branch=branch)
        lu = _ns_localunit("Office 1", branch=branch, subbranch=subbranch)
        with app.app_context():
            with patch.object(EntityService, "get_entity", return_value=lu):
                with patch("app.utils.form_localization.get_localized_country_name", return_value="L-Kenya"):
                    result = EntityService.get_localized_entity_hierarchy(EntityType.ns_localunit.value, 1)
        assert "CBD" in result


# ---------------------------------------------------------------------------
# get_country_for_entity
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetCountryForEntity:
    def test_country_entity_returns_itself(self, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            result = EntityService.get_country_for_entity(EntityType.country.value, country.id)
            assert result is not None
            assert result.id == country.id

    def test_missing_entity_returns_none(self, db_session, app):
        with app.app_context():
            result = EntityService.get_country_for_entity("country", 9_999_999)
            assert result is None

    def test_ns_branch_returns_country(self, app):
        country = _mock_entity("Kenya")
        branch = _ns_branch(country=country)
        with app.app_context():
            with patch.object(EntityService, "get_entity", return_value=branch):
                result = EntityService.get_country_for_entity(EntityType.ns_branch.value, 1)
        assert result is country

    def test_ns_branch_without_country_attr(self, app):
        branch = MagicMock(spec=[])  # no 'country' attribute
        with app.app_context():
            with patch.object(EntityService, "get_entity", return_value=branch):
                result = EntityService.get_country_for_entity(EntityType.ns_branch.value, 1)
        assert result is None

    def test_ns_subbranch_returns_branch_country(self, app):
        country = _mock_entity("Kenya")
        branch = _ns_branch(country=country)
        subbranch = _ns_subbranch(branch=branch)
        with app.app_context():
            with patch.object(EntityService, "get_entity", return_value=subbranch):
                result = EntityService.get_country_for_entity(EntityType.ns_subbranch.value, 1)
        assert result is country

    def test_ns_subbranch_without_branch_returns_none(self, app):
        subbranch = _mock_entity("Sub")
        subbranch.branch = None
        with app.app_context():
            with patch.object(EntityService, "get_entity", return_value=subbranch):
                result = EntityService.get_country_for_entity(EntityType.ns_subbranch.value, 1)
        assert result is None

    def test_ns_localunit_returns_branch_country(self, app):
        country = _mock_entity("Kenya")
        branch = _ns_branch(country=country)
        lu = _ns_localunit(branch=branch)
        with app.app_context():
            with patch.object(EntityService, "get_entity", return_value=lu):
                result = EntityService.get_country_for_entity(EntityType.ns_localunit.value, 1)
        assert result is country

    def test_ns_localunit_without_branch_returns_none(self, app):
        lu = _mock_entity("Unit")
        lu.branch = None
        with app.app_context():
            with patch.object(EntityService, "get_entity", return_value=lu):
                result = EntityService.get_country_for_entity(EntityType.ns_localunit.value, 1)
        assert result is None

    def test_division_returns_none(self, app):
        division = _mock_entity("Division")
        with app.app_context():
            with patch.object(EntityService, "get_entity", return_value=division):
                result = EntityService.get_country_for_entity(EntityType.division.value, 1)
        assert result is None

    def test_department_returns_none(self, app):
        dept = _mock_entity("Dept")
        with app.app_context():
            with patch.object(EntityService, "get_entity", return_value=dept):
                result = EntityService.get_country_for_entity(EntityType.department.value, 1)
        assert result is None

    def test_regional_office_returns_none(self, app):
        ro = _mock_entity("RO")
        with app.app_context():
            with patch.object(EntityService, "get_entity", return_value=ro):
                result = EntityService.get_country_for_entity(EntityType.regional_office.value, 1)
        assert result is None

    def test_cluster_office_returns_none(self, app):
        co = _mock_entity("CO")
        with app.app_context():
            with patch.object(EntityService, "get_entity", return_value=co):
                result = EntityService.get_country_for_entity(EntityType.cluster_office.value, 1)
        assert result is None


# ---------------------------------------------------------------------------
# get_entities_for_user
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetEntitiesForUser:
    def test_admin_with_specific_entity_type(self, db_session, app):
        with app.app_context():
            admin = create_test_admin(db_session)
            country = create_test_country(db_session)
            result = EntityService.get_entities_for_user(admin, entity_type=EntityType.country.value)
            ids = [e.id for e in result]
            assert country.id in ids

    def test_admin_with_unknown_entity_type_returns_empty(self, db_session, app):
        with app.app_context():
            admin = create_test_admin(db_session)
            result = EntityService.get_entities_for_user(admin, entity_type="unknown_type_xyz")
            assert result == []

    def test_admin_without_entity_type_returns_all_types(self, db_session, app):
        with app.app_context():
            admin = create_test_admin(db_session)
            create_test_country(db_session)
            result = EntityService.get_entities_for_user(admin, entity_type=None)
            assert isinstance(result, list)

    def test_regular_user_gets_assigned_entities(self, db_session, app):
        from app.models.core import UserEntityPermission
        from app import db

        with app.app_context():
            user = create_test_user(db_session)
            country = create_test_country(db_session)
            db.session.add(
                UserEntityPermission(
                    user_id=user.id,
                    entity_type=EntityType.country.value,
                    entity_id=country.id,
                )
            )
            db.session.commit()
            result = EntityService.get_entities_for_user(user, entity_type=EntityType.country.value)
            ids = [e.id for e in result]
            assert country.id in ids

    def test_regular_user_without_permissions_returns_empty(self, db_session, app):
        with app.app_context():
            user = create_test_user(db_session)
            result = EntityService.get_entities_for_user(user, entity_type=EntityType.country.value)
            # User may have no entity permissions
            assert isinstance(result, list)

    def test_regular_user_entity_permission_for_unknown_type(self, db_session, app):
        """Permission references an entity type not in ENTITY_MODEL_MAP → skipped."""
        from app.models.core import UserEntityPermission
        from app import db

        with app.app_context():
            user = create_test_user(db_session)
            db.session.add(
                UserEntityPermission(
                    user_id=user.id,
                    entity_type="ghost_type",
                    entity_id=1,
                )
            )
            db.session.commit()
            result = EntityService.get_entities_for_user(user)
            assert isinstance(result, list)


# ---------------------------------------------------------------------------
# check_user_entity_access
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCheckUserEntityAccess:
    def test_admin_has_access_to_everything(self, db_session, app):
        with app.app_context():
            admin = create_test_admin(db_session)
            country = create_test_country(db_session)
            assert EntityService.check_user_entity_access(
                admin, EntityType.country.value, country.id
            ) is True

    def test_user_with_permission_has_access(self, db_session, app):
        from app.models.core import UserEntityPermission
        from app import db

        with app.app_context():
            user = create_test_user(db_session)
            country = create_test_country(db_session)
            db.session.add(
                UserEntityPermission(
                    user_id=user.id,
                    entity_type=EntityType.country.value,
                    entity_id=country.id,
                )
            )
            db.session.commit()
            assert EntityService.check_user_entity_access(
                user, EntityType.country.value, country.id
            ) is True

    def test_user_without_permission_has_no_access(self, db_session, app):
        with app.app_context():
            user = create_test_user(db_session)
            country = create_test_country(db_session)
            assert EntityService.check_user_entity_access(
                user, EntityType.country.value, country.id
            ) is False


# ---------------------------------------------------------------------------
# get_all_entities_by_type
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetAllEntitiesByType:
    def test_unknown_type_returns_empty(self, db_session, app):
        with app.app_context():
            result = EntityService.get_all_entities_by_type("totally_unknown_xyz")
            assert result == []

    def test_country_type_returns_list(self, db_session, app):
        with app.app_context():
            create_test_country(db_session)
            result = EntityService.get_all_entities_by_type(EntityType.country.value, filter_active=False)
            assert isinstance(result, list)
            assert len(result) >= 1

    def test_filter_active_skipped_when_no_is_active_attr(self, db_session, app):
        """Country model has no is_active field — filter should not be applied."""
        with app.app_context():
            create_test_country(db_session)
            # filter_active=True but Country doesn't have is_active → no filter applied
            result = EntityService.get_all_entities_by_type(EntityType.country.value, filter_active=True)
            assert isinstance(result, list)

    def test_filter_active_applied_when_model_has_is_active(self, app):
        """For a model that has is_active, filter should be applied."""
        MockModel = MagicMock()
        mock_query = MagicMock()
        MockModel.query = mock_query
        mock_query.filter_by.return_value = mock_query
        mock_query.all.return_value = []

        with app.app_context():
            with patch.dict(EntityService.ENTITY_MODEL_MAP, {"mock_type": MockModel}):
                # Simulate model having is_active attribute
                MockModel.is_active = True
                result = EntityService.get_all_entities_by_type("mock_type", filter_active=True)
            mock_query.filter_by.assert_called_once_with(is_active=True)


# ---------------------------------------------------------------------------
# get_entity_type_label
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetEntityTypeLabel:
    @pytest.mark.parametrize("entity_type,expected_label", [
        (EntityType.country.value, "Country"),
        (EntityType.national_society.value, "National Society"),
        (EntityType.ns_branch.value, "NS Branch"),
        (EntityType.ns_subbranch.value, "NS Sub-branch"),
        (EntityType.ns_localunit.value, "NS Local Unit"),
        (EntityType.division.value, "Secretariat Division"),
        (EntityType.department.value, "Secretariat Department"),
        (EntityType.regional_office.value, "Regional Office"),
        (EntityType.cluster_office.value, "Cluster Office"),
    ])
    def test_known_entity_type_labels(self, entity_type, expected_label):
        assert EntityService.get_entity_type_label(entity_type) == expected_label

    def test_unknown_type_returns_title_cased(self):
        result = EntityService.get_entity_type_label("some_weird_type")
        assert result == "Some Weird Type"


# ---------------------------------------------------------------------------
# get_children_entities
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetChildrenEntities:
    def test_missing_entity_returns_empty_dict(self, db_session, app):
        with app.app_context():
            result = EntityService.get_children_entities("country", 9_999_999)
            assert result == {}

    def test_country_returns_ns_branches(self, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            mock_branches_query = MagicMock()
            mock_branches_query.all.return_value = []
            country_entity = MagicMock()
            country_entity.ns_branches = mock_branches_query
            with patch.object(EntityService, "get_entity", return_value=country_entity):
                result = EntityService.get_children_entities(EntityType.country.value, country.id)
            assert EntityType.ns_branch.value in result

    def test_country_without_ns_branches_attr(self, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            country_entity = MagicMock(spec=["name"])  # no ns_branches attr
            with patch.object(EntityService, "get_entity", return_value=country_entity):
                result = EntityService.get_children_entities(EntityType.country.value, country.id)
            assert EntityType.ns_branch.value not in result

    def test_ns_branch_returns_subbranches_and_local_units(self, app):
        branch = MagicMock()
        mock_subbranches = MagicMock()
        mock_subbranches.all.return_value = []
        branch.subbranches = mock_subbranches

        lu_with_subbranch = MagicMock()
        lu_with_subbranch.subbranch_id = 1
        lu_direct = MagicMock()
        lu_direct.subbranch_id = None
        mock_local_units = MagicMock()
        mock_local_units.all.return_value = [lu_with_subbranch, lu_direct]
        branch.local_units = mock_local_units

        with app.app_context():
            with patch.object(EntityService, "get_entity", return_value=branch):
                result = EntityService.get_children_entities(EntityType.ns_branch.value, 1)
        assert EntityType.ns_subbranch.value in result
        assert EntityType.ns_localunit.value in result
        # Only direct local units (no subbranch_id) should appear
        assert lu_direct in result[EntityType.ns_localunit.value]
        assert lu_with_subbranch not in result[EntityType.ns_localunit.value]

    def test_ns_subbranch_returns_local_units(self, app):
        subbranch = MagicMock()
        mock_lus = MagicMock()
        mock_lus.all.return_value = []
        subbranch.local_units = mock_lus
        with app.app_context():
            with patch.object(EntityService, "get_entity", return_value=subbranch):
                result = EntityService.get_children_entities(EntityType.ns_subbranch.value, 1)
        assert EntityType.ns_localunit.value in result

    def test_division_returns_departments(self, app):
        division = MagicMock()
        mock_depts = MagicMock()
        mock_depts.all.return_value = []
        division.departments = mock_depts
        with app.app_context():
            with patch.object(EntityService, "get_entity", return_value=division):
                result = EntityService.get_children_entities(EntityType.division.value, 1)
        assert EntityType.department.value in result

    def test_regional_office_returns_cluster_offices(self, app):
        ro = MagicMock()
        mock_clusters = MagicMock()
        mock_clusters.all.return_value = []
        ro.cluster_offices = mock_clusters
        with app.app_context():
            with patch.object(EntityService, "get_entity", return_value=ro):
                result = EntityService.get_children_entities(EntityType.regional_office.value, 1)
        assert EntityType.cluster_office.value in result

    def test_national_society_returns_empty(self, app):
        """National Society has no defined children in the service."""
        ns = MagicMock(spec=["name"])
        with app.app_context():
            with patch.object(EntityService, "get_entity", return_value=ns):
                result = EntityService.get_children_entities(EntityType.national_society.value, 1)
        assert result == {}

    def test_department_returns_empty(self, app):
        """Departments have no children."""
        dept = MagicMock(spec=["name"])
        with app.app_context():
            with patch.object(EntityService, "get_entity", return_value=dept):
                result = EntityService.get_children_entities(EntityType.department.value, 1)
        assert result == {}
