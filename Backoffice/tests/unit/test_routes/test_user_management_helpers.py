"""Tests for admin user management helper functions.

Covers: app/routes/admin/user_management/helpers.py
"""

import pytest
from unittest.mock import patch, MagicMock
from tests.factories import create_test_user, create_test_country

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# _normalize_user_email_for_comparison
# ---------------------------------------------------------------------------

class TestNormalizeUserEmailForComparison:
    def test_none_returns_empty_string(self, app):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                _normalize_user_email_for_comparison,
            )
            assert _normalize_user_email_for_comparison(None) == ""

    def test_strips_and_lowercases(self, app):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                _normalize_user_email_for_comparison,
            )
            assert _normalize_user_email_for_comparison("  TEST@Example.COM  ") == "test@example.com"

    def test_already_lowercase(self, app):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                _normalize_user_email_for_comparison,
            )
            assert _normalize_user_email_for_comparison("user@test.com") == "user@test.com"

    def test_non_string_value(self, app):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                _normalize_user_email_for_comparison,
            )
            assert _normalize_user_email_for_comparison(123) == "123"


# ---------------------------------------------------------------------------
# _is_azure_sso_enabled
# ---------------------------------------------------------------------------

class TestIsAzureSsoEnabled:
    def test_returns_false_when_not_configured(self, app):
        with app.app_context():
            from app.routes.admin.user_management.helpers import _is_azure_sso_enabled
            with patch(
                "app.routes.admin.user_management.helpers.is_azure_b2c_configured",
                return_value=False,
            ):
                assert _is_azure_sso_enabled() is False

    def test_returns_true_when_configured(self, app):
        with app.app_context():
            from app.routes.admin.user_management.helpers import _is_azure_sso_enabled
            with patch(
                "app.routes.admin.user_management.helpers.is_azure_b2c_configured",
                return_value=True,
            ):
                assert _is_azure_sso_enabled() is True


# ---------------------------------------------------------------------------
# _get_allowed_non_country_entity_types
# ---------------------------------------------------------------------------

class TestGetAllowedNonCountryEntityTypes:
    def test_returns_list(self, app):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                _get_allowed_non_country_entity_types,
            )
            result = _get_allowed_non_country_entity_types()
            assert isinstance(result, list)

    def test_excludes_countries(self, app):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                _get_allowed_non_country_entity_types,
            )
            result = _get_allowed_non_country_entity_types()
            assert "countries" not in result


# ---------------------------------------------------------------------------
# _compute_role_type_for_user_id
# ---------------------------------------------------------------------------

class TestComputeRoleTypeForUserId:
    def test_focal_point_for_user_with_no_admin_roles(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                _compute_role_type_for_user_id,
            )
            user = create_test_user(
                db_session, email="crt_focal@example.com", role="focal_point"
            )
            result = _compute_role_type_for_user_id(user.id)
            assert result == "focal_point"

    def test_admin_for_user_with_admin_role(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                _compute_role_type_for_user_id,
            )
            user = create_test_user(
                db_session, email="crt_admin@example.com", role="admin"
            )
            result = _compute_role_type_for_user_id(user.id)
            assert result == "admin"

    def test_sys_mgr_returns_admin(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                _compute_role_type_for_user_id,
            )
            user = create_test_user(
                db_session, email="crt_sm@example.com", role="system_manager"
            )
            result = _compute_role_type_for_user_id(user.id)
            assert result == "admin"

    def test_exception_returns_admin_default(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                _compute_role_type_for_user_id,
            )
            with patch(
                "app.routes.admin.user_management.helpers.db.session",
                side_effect=Exception("db error"),
            ):
                result = _compute_role_type_for_user_id(999999)
            assert result == "admin"

    def test_approver_only_returns_admin(self, app, db_session):
        """Approver is admin-only in the UI, so approver-only users must load in Admin mode."""
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                _compute_role_type_for_user_id,
            )
            from app.models.rbac import RbacRole, RbacUserRole
            user = create_test_user(
                db_session, email="crt_approver@example.com", role="focal_point"
            )
            approver = db_session.query(RbacRole).filter_by(
                code="assignment_approver"
            ).first()
            if not approver:
                approver = RbacRole(code="assignment_approver", name="Assignment Approver")
                db_session.add(approver)
                db_session.flush()
            db_session.add(RbacUserRole(user_id=user.id, role_id=approver.id))
            db_session.commit()
            result = _compute_role_type_for_user_id(user.id)
            assert result == "admin"


# ---------------------------------------------------------------------------
# _get_countries_by_region
# ---------------------------------------------------------------------------

class TestGetCountriesByRegion:
    def test_returns_defaultdict(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import _get_countries_by_region
            result = _get_countries_by_region()
            assert isinstance(result, dict)

    def test_groups_countries_by_region(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import _get_countries_by_region
            create_test_country(db_session, name="Alpha Land", region="Region A")
            create_test_country(db_session, name="Beta Land", region="Region A")
            result = _get_countries_by_region()
            assert "Region A" in result
            assert len(result["Region A"]) >= 2

    def test_none_region_grouped_as_unassigned(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import _get_countries_by_region
            from app.models import Country
            c = Country(name="NoRegionCnt", iso2="NZ", iso3="NZZ")
            db_session.add(c)
            db_session.commit()
            result = _get_countries_by_region()
            assert "Unassigned Region" in result


# ---------------------------------------------------------------------------
# _set_user_rbac_roles
# ---------------------------------------------------------------------------

class TestSetUserRbacRoles:
    def test_replaces_existing_roles(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import _set_user_rbac_roles
            from app.models.rbac import RbacRole, RbacUserRole
            user = create_test_user(db_session, email="set_roles@example.com")
            role = db_session.query(RbacRole).filter_by(code="assignment_viewer").first()
            if not role:
                role = RbacRole(code="assignment_viewer", name="AV")
                db_session.add(role)
                db_session.flush()
            _set_user_rbac_roles(user, [role.id])
            roles = RbacUserRole.query.filter_by(user_id=user.id).all()
            assert len(roles) == 1
            assert roles[0].role_id == role.id

    def test_empty_role_list_removes_all(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import _set_user_rbac_roles
            from app.models.rbac import RbacUserRole
            user = create_test_user(db_session, email="empty_roles@example.com")
            _set_user_rbac_roles(user, [])
            roles = RbacUserRole.query.filter_by(user_id=user.id).all()
            assert roles == []

    def test_deduplicates_role_ids(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import _set_user_rbac_roles
            from app.models.rbac import RbacRole, RbacUserRole
            user = create_test_user(db_session, email="dedup_roles@example.com")
            role = db_session.query(RbacRole).filter_by(code="assignment_viewer").first()
            if not role:
                role = RbacRole(code="assignment_viewer", name="AV")
                db_session.add(role)
                db_session.flush()
            _set_user_rbac_roles(user, [role.id, role.id])
            roles = RbacUserRole.query.filter_by(user_id=user.id).all()
            role_ids = [r.role_id for r in roles]
            assert role_ids.count(role.id) == 1

    def test_ignores_none_ids(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import _set_user_rbac_roles
            from app.models.rbac import RbacUserRole
            user = create_test_user(db_session, email="none_role@example.com")
            _set_user_rbac_roles(user, [None, None])
            roles = RbacUserRole.query.filter_by(user_id=user.id).all()
            assert roles == []

    def test_no_op_for_user_with_no_id(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import _set_user_rbac_roles
            mock_user = MagicMock()
            mock_user.id = None
            _set_user_rbac_roles(mock_user, [1, 2])


# ---------------------------------------------------------------------------
# _ensure_user_has_default_rbac_role
# ---------------------------------------------------------------------------

class TestEnsureUserHasDefaultRbacRole:
    def test_adds_default_role_if_none(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                _ensure_user_has_default_rbac_role,
            )
            from app.models.rbac import RbacUserRole
            user = create_test_user(db_session, email="ensure_role@example.com")
            # Clear existing roles
            RbacUserRole.query.filter_by(user_id=user.id).delete()
            db_session.commit()
            _ensure_user_has_default_rbac_role(user)
            roles = RbacUserRole.query.filter_by(user_id=user.id).all()
            assert len(roles) >= 1

    def test_no_op_if_already_has_role(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                _ensure_user_has_default_rbac_role,
            )
            from app.models.rbac import RbacUserRole
            user = create_test_user(db_session, email="already_has_role@example.com")
            initial_count = RbacUserRole.query.filter_by(user_id=user.id).count()
            _ensure_user_has_default_rbac_role(user)
            final_count = RbacUserRole.query.filter_by(user_id=user.id).count()
            assert final_count == initial_count

    def test_creates_role_if_missing(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                _ensure_user_has_default_rbac_role,
            )
            from app.models.rbac import RbacRole, RbacUserRole
            user = create_test_user(db_session, email="create_role@example.com")
            # Remove existing roles and the default role
            RbacUserRole.query.filter_by(user_id=user.id).delete()
            role = RbacRole.query.filter_by(code="assignment_viewer").first()
            if role:
                RbacUserRole.query.filter_by(role_id=role.id).delete()
                db_session.delete(role)
            db_session.commit()
            _ensure_user_has_default_rbac_role(user, default_role_code="assignment_viewer")
            roles = RbacUserRole.query.filter_by(user_id=user.id).all()
            assert len(roles) == 1

    def test_no_op_for_user_with_no_id(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                _ensure_user_has_default_rbac_role,
            )
            mock_user = MagicMock()
            mock_user.id = None
            _ensure_user_has_default_rbac_role(mock_user)


# ---------------------------------------------------------------------------
# _filter_requested_admin_roles_for_actor
# ---------------------------------------------------------------------------

class TestFilterRequestedAdminRolesForActor:
    def test_empty_list_returns_empty(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                _filter_requested_admin_roles_for_actor,
            )
            actor = create_test_user(db_session, email="actor_empty@example.com")
            kept, dropped = _filter_requested_admin_roles_for_actor([], actor)
            assert kept == []
            assert dropped == []

    def test_non_admin_roles_are_kept(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                _filter_requested_admin_roles_for_actor,
            )
            from app.models.rbac import RbacRole
            actor = create_test_user(db_session, email="actor_keep@example.com")
            role = db_session.query(RbacRole).filter_by(code="assignment_viewer").first()
            if not role:
                role = RbacRole(code="assignment_viewer", name="AV")
                db_session.add(role)
                db_session.flush()
            kept, dropped = _filter_requested_admin_roles_for_actor([role.id], actor)
            assert role.id in kept
            assert role.id not in dropped

    def test_admin_role_dropped_if_actor_lacks_it(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                _filter_requested_admin_roles_for_actor,
            )
            from app.models.rbac import RbacRole
            actor = create_test_user(db_session, email="actor_no_adm@example.com")
            # Create admin role that actor doesn't have
            adm_role = db_session.query(RbacRole).filter_by(code="admin_other").first()
            if not adm_role:
                adm_role = RbacRole(code="admin_other", name="Admin Other")
                db_session.add(adm_role)
                db_session.flush()
            kept, dropped = _filter_requested_admin_roles_for_actor([adm_role.id], actor)
            assert adm_role.id in dropped
            assert adm_role.id not in kept

    def test_admin_role_kept_if_actor_has_it(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                _filter_requested_admin_roles_for_actor,
            )
            from app.models.rbac import RbacRole, RbacUserRole
            actor = create_test_user(db_session, email="actor_has_adm@example.com")
            adm_role = db_session.query(RbacRole).filter_by(code="admin_core").first()
            if not adm_role:
                adm_role = RbacRole(code="admin_core", name="Admin Core")
                db_session.add(adm_role)
                db_session.flush()
            # Grant actor the admin role
            existing = RbacUserRole.query.filter_by(
                user_id=actor.id, role_id=adm_role.id
            ).first()
            if not existing:
                db_session.add(RbacUserRole(user_id=actor.id, role_id=adm_role.id))
                db_session.commit()
            kept, dropped = _filter_requested_admin_roles_for_actor([adm_role.id], actor)
            assert adm_role.id in kept
            assert adm_role.id not in dropped


# ---------------------------------------------------------------------------
# _filter_role_choices_for_actor
# ---------------------------------------------------------------------------

class TestFilterRoleChoicesForActor:
    def test_empty_choices_returns_empty(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                _filter_role_choices_for_actor,
            )
            actor = create_test_user(db_session, email="choices_empty@example.com")
            result = _filter_role_choices_for_actor([], actor)
            assert result == []

    def test_non_admin_choices_kept(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                _filter_role_choices_for_actor,
            )
            from app.models.rbac import RbacRole
            actor = create_test_user(db_session, email="choices_keep@example.com")
            role = db_session.query(RbacRole).filter_by(code="assignment_viewer").first()
            if not role:
                role = RbacRole(code="assignment_viewer", name="AV")
                db_session.add(role)
                db_session.flush()
            choices = [(role.id, "Assignment Viewer")]
            result = _filter_role_choices_for_actor(choices, actor)
            assert any(r[0] == role.id for r in result)

    def test_admin_choice_dropped_if_actor_lacks(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                _filter_role_choices_for_actor,
            )
            from app.models.rbac import RbacRole
            actor = create_test_user(db_session, email="choices_drop@example.com")
            adm_role = db_session.query(RbacRole).filter_by(code="admin_special").first()
            if not adm_role:
                adm_role = RbacRole(code="admin_special", name="Admin Special")
                db_session.add(adm_role)
                db_session.flush()
            choices = [(adm_role.id, "Admin Special")]
            result = _filter_role_choices_for_actor(choices, actor)
            assert not any(r[0] == adm_role.id for r in result)

    def test_invalid_rid_in_choices_skipped(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                _filter_role_choices_for_actor,
            )
            actor = create_test_user(db_session, email="choices_inv@example.com")
            choices = [("not-an-int", "Bad")]
            result = _filter_role_choices_for_actor(choices, actor)
            assert result == []


# ---------------------------------------------------------------------------
# _apply_role_type_and_implications
# ---------------------------------------------------------------------------

class TestApplyRoleTypeAndImplications:
    def test_empty_list_returns_empty(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                _apply_role_type_and_implications,
            )
            result = _apply_role_type_and_implications([], role_type=None)
            assert result == []

    def test_deduplicates(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                _apply_role_type_and_implications,
            )
            result = _apply_role_type_and_implications([1, 1, 2, 2], role_type=None)
            assert result.count(1) == 1
            assert result.count(2) == 1

    def test_focal_point_strips_admin_roles(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                _apply_role_type_and_implications,
            )
            from app.models.rbac import RbacRole
            admin_role = db_session.query(RbacRole).filter_by(code="admin_core").first()
            if not admin_role:
                admin_role = RbacRole(code="admin_core", name="Admin Core")
                db_session.add(admin_role)
                db_session.flush()
            result = _apply_role_type_and_implications(
                [admin_role.id], role_type="focal_point"
            )
            assert admin_role.id not in result

    def test_focal_point_strips_approver_role(self, app, db_session):
        """Approver is admin-only in the UI; saving as Focal Point must drop it."""
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                _apply_role_type_and_implications,
            )
            from app.models.rbac import RbacRole
            approver = db_session.query(RbacRole).filter_by(
                code="assignment_approver"
            ).first()
            if not approver:
                approver = RbacRole(code="assignment_approver", name="Assignment Approver")
                db_session.add(approver)
                db_session.flush()
            editor = db_session.query(RbacRole).filter_by(
                code="assignment_editor_submitter"
            ).first()
            if not editor:
                editor = RbacRole(code="assignment_editor_submitter", name="AES")
                db_session.add(editor)
                db_session.flush()
            db_session.commit()
            result = _apply_role_type_and_implications(
                [approver.id, editor.id], role_type="focal_point"
            )
            assert approver.id not in result
            assert editor.id in result

    def test_focal_point_adds_viewer_when_no_assignment_roles(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                _apply_role_type_and_implications,
            )
            from app.models.rbac import RbacRole
            viewer_role = db_session.query(RbacRole).filter_by(
                code="assignment_viewer"
            ).first()
            if not viewer_role:
                viewer_role = RbacRole(code="assignment_viewer", name="AV")
                db_session.add(viewer_role)
                db_session.flush()
            editor_role = db_session.query(RbacRole).filter_by(
                code="assignment_editor_submitter"
            ).first()
            if not editor_role:
                editor_role = RbacRole(
                    code="assignment_editor_submitter", name="AES"
                )
                db_session.add(editor_role)
                db_session.flush()
            db_session.commit()
            result = _apply_role_type_and_implications([], role_type="focal_point")
            assert viewer_role.id in result
            assert editor_role.id not in result

    def test_focal_point_viewer_only_does_not_add_editor(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                _apply_role_type_and_implications,
            )
            from app.models.rbac import RbacRole
            viewer_role = db_session.query(RbacRole).filter_by(
                code="assignment_viewer"
            ).first()
            if not viewer_role:
                viewer_role = RbacRole(code="assignment_viewer", name="AV")
                db_session.add(viewer_role)
                db_session.flush()
            editor_role = db_session.query(RbacRole).filter_by(
                code="assignment_editor_submitter"
            ).first()
            if not editor_role:
                editor_role = RbacRole(
                    code="assignment_editor_submitter", name="AES"
                )
                db_session.add(editor_role)
                db_session.flush()
            db_session.commit()
            result = _apply_role_type_and_implications(
                [viewer_role.id], role_type="focal_point"
            )
            assert viewer_role.id in result
            assert editor_role.id not in result

    def test_drops_deprecated_role(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                _apply_role_type_and_implications,
            )
            from app.models.rbac import RbacRole
            deprecated = db_session.query(RbacRole).filter_by(
                code="assignment_documents_uploader"
            ).first()
            if not deprecated:
                deprecated = RbacRole(
                    code="assignment_documents_uploader", name="Upload Only"
                )
                db_session.add(deprecated)
                db_session.flush()
                db_session.commit()
            result = _apply_role_type_and_implications(
                [deprecated.id],
                role_type=None,
                drop_role_codes={"assignment_documents_uploader"},
            )
            assert deprecated.id not in result

    def test_admin_auto_downgraded_to_focal_point(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                _apply_role_type_and_implications,
            )
            from app.models.rbac import RbacRole
            viewer = db_session.query(RbacRole).filter_by(
                code="assignment_viewer"
            ).first()
            if not viewer:
                viewer = RbacRole(code="assignment_viewer", name="AV")
                db_session.add(viewer)
                db_session.flush()
            editor = db_session.query(RbacRole).filter_by(
                code="assignment_editor_submitter"
            ).first()
            if not editor:
                editor = RbacRole(code="assignment_editor_submitter", name="AES")
                db_session.add(editor)
                db_session.flush()
            db_session.commit()
            result = _apply_role_type_and_implications(
                [viewer.id], role_type="admin"
            )
            assert viewer.id in result

    def test_none_in_role_ids_skipped(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                _apply_role_type_and_implications,
            )
            result = _apply_role_type_and_implications(
                [None, 1, None, 2], role_type=None
            )
            assert None not in result


# ---------------------------------------------------------------------------
# _country_access_request_to_dict
# ---------------------------------------------------------------------------

class TestCountryAccessRequestToDict:
    def test_serializes_full_request(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                _country_access_request_to_dict,
            )
            user = create_test_user(db_session, email="car_user@example.com")
            country = create_test_country(db_session)
            from app.models import CountryAccessRequest
            req = CountryAccessRequest(
                user_id=user.id,
                country_id=country.id,
                status="pending",
            )
            db_session.add(req)
            db_session.commit()
            db_session.refresh(req)
            result = _country_access_request_to_dict(req)
            assert result["id"] == req.id
            assert result["status"] == "pending"
            assert result["user"]["email"] == user.email
            assert result["country"]["id"] == country.id

    def test_handles_no_processed_by(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                _country_access_request_to_dict,
            )
            user = create_test_user(db_session, email="car_noproc@example.com")
            country = create_test_country(db_session)
            from app.models import CountryAccessRequest
            req = CountryAccessRequest(
                user_id=user.id,
                country_id=country.id,
                status="pending",
            )
            db_session.add(req)
            db_session.commit()
            result = _country_access_request_to_dict(req)
            assert result["processed_by"] is None


# ---------------------------------------------------------------------------
# _get_user_deletion_preview
# ---------------------------------------------------------------------------

class TestGetUserDeletionPreview:
    def test_returns_will_delete_and_will_unassign(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                _get_user_deletion_preview,
            )
            user = create_test_user(db_session, email="del_prev@example.com")
            from app.models import User as UserModel
            u = UserModel.query.get(user.id)
            preview = _get_user_deletion_preview(u)
            assert "will_delete" in preview
            assert "will_unassign" in preview
            assert "notifications" in preview["will_delete"]

    def test_counts_are_integers(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                _get_user_deletion_preview,
            )
            user = create_test_user(db_session, email="del_prev2@example.com")
            from app.models import User as UserModel
            u = UserModel.query.get(user.id)
            preview = _get_user_deletion_preview(u)
            for key, val in preview["will_delete"].items():
                assert isinstance(val, int), f"{key} should be int"


# ---------------------------------------------------------------------------
# _cascade_delete_user_related
# ---------------------------------------------------------------------------

class TestCascadeDeleteUserRelated:
    def test_deletes_user(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                _cascade_delete_user_related,
            )
            from app.models import User as UserModel
            user = create_test_user(db_session, email="cascade_del@example.com")
            uid = user.id
            u = UserModel.query.get(uid)
            _cascade_delete_user_related(u)
            db_session.commit()
            assert UserModel.query.get(uid) is None

    def test_deletes_entity_permissions(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                _cascade_delete_user_related,
            )
            from app.models import User as UserModel
            from app.models.core import UserEntityPermission
            user = create_test_user(db_session, email="cascade_perm@example.com")
            country = create_test_country(db_session)
            perm = UserEntityPermission(
                user_id=user.id, entity_type="country", entity_id=country.id
            )
            db_session.add(perm)
            db_session.commit()
            uid = user.id
            u = UserModel.query.get(uid)
            _cascade_delete_user_related(u)
            db_session.commit()
            remaining = UserEntityPermission.query.filter_by(user_id=uid).all()
            assert remaining == []


# ---------------------------------------------------------------------------
# build_admin_user_list_rows
# ---------------------------------------------------------------------------

class TestBuildAdminUserListRows:
    def test_empty_list_returns_empty(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                build_admin_user_list_rows,
            )
            result = build_admin_user_list_rows([])
            assert result == []

    def test_returns_row_for_each_user(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                build_admin_user_list_rows,
            )
            from app.models import User as UserModel
            user1 = create_test_user(db_session, email="bl1@example.com")
            user2 = create_test_user(db_session, email="bl2@example.com")
            users = UserModel.query.filter(
                UserModel.id.in_([user1.id, user2.id])
            ).all()
            result = build_admin_user_list_rows(users)
            assert len(result) == 2

    def test_row_has_expected_fields(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                build_admin_user_list_rows,
            )
            from app.models import User as UserModel
            user = create_test_user(db_session, email="bl_fields@example.com")
            u = UserModel.query.get(user.id)
            result = build_admin_user_list_rows([u])
            assert len(result) == 1
            row = result[0]
            assert "id" in row
            assert "email" in row
            assert "rbac_roles" in row

    def test_includes_country_data(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                build_admin_user_list_rows,
            )
            from app.models import User as UserModel
            from app.models.core import UserEntityPermission
            user = create_test_user(db_session, email="bl_country@example.com")
            country = create_test_country(db_session)
            perm = UserEntityPermission(
                user_id=user.id, entity_type="country", entity_id=country.id
            )
            db_session.add(perm)
            db_session.commit()
            u = UserModel.query.get(user.id)
            result = build_admin_user_list_rows([u])
            assert result[0]["country_ids"] == [country.id]


# ---------------------------------------------------------------------------
# build_admin_user_detail_dict
# ---------------------------------------------------------------------------

class TestBuildAdminUserDetailDict:
    def test_returns_none_for_nonexistent_user(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                build_admin_user_detail_dict,
            )
            result = build_admin_user_detail_dict(999999)
            assert result is None

    def test_returns_dict_for_user(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                build_admin_user_detail_dict,
            )
            user = create_test_user(db_session, email="detail_dict@example.com")
            result = build_admin_user_detail_dict(user.id)
            assert result is not None
            assert result["id"] == user.id
            assert result["email"] == user.email

    def test_includes_rbac_roles(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                build_admin_user_detail_dict,
            )
            user = create_test_user(
                db_session, email="detail_roles@example.com", role="admin"
            )
            result = build_admin_user_detail_dict(user.id)
            assert "rbac_roles" in result
            assert isinstance(result["rbac_roles"], list)

    def test_includes_entity_permissions(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                build_admin_user_detail_dict,
            )
            from app.models.core import UserEntityPermission
            user = create_test_user(db_session, email="detail_perms@example.com")
            country = create_test_country(db_session)
            perm = UserEntityPermission(
                user_id=user.id, entity_type="country", entity_id=country.id
            )
            db_session.add(perm)
            db_session.commit()
            result = build_admin_user_detail_dict(user.id)
            assert "entity_permissions" in result
            assert any(
                ep["entity_type"] == "country"
                for ep in result["entity_permissions"]
            )

    def test_computed_role_type_field(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                build_admin_user_detail_dict,
            )
            user = create_test_user(db_session, email="crt_field@example.com")
            result = build_admin_user_detail_dict(user.id)
            assert "computed_role_type" in result
            assert result["computed_role_type"] in ("admin", "focal_point")

    def test_is_system_manager_field(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                build_admin_user_detail_dict,
            )
            sm_user = create_test_user(
                db_session, email="sm_det@example.com", role="system_manager"
            )
            result = build_admin_user_detail_dict(sm_user.id)
            assert result["is_system_manager"] is True

    def test_effective_permissions_aggregated(self, app, db_session):
        with app.app_context():
            from app.routes.admin.user_management.helpers import (
                build_admin_user_detail_dict,
            )
            user = create_test_user(
                db_session, email="eff_perms@example.com", role="admin"
            )
            result = build_admin_user_detail_dict(user.id)
            assert "effective_permissions" in result
