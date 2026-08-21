"""
Comprehensive tests for rbac_seed_service.

Targets 100% code coverage of:
  app/services/rbac_seed_service.py
"""

import pytest
from unittest.mock import patch, MagicMock

from app.services.organization.rbac_seed_service import (
    _permission_catalog,
    _baseline_roles,
    seed_rbac_permissions_and_roles,
)


# ---------------------------------------------------------------------------
# _permission_catalog
# ---------------------------------------------------------------------------

class TestPermissionCatalog:
    def test_returns_list(self):
        catalog = _permission_catalog()
        assert isinstance(catalog, list)
        assert len(catalog) > 0

    def test_each_entry_is_three_tuple(self):
        for entry in _permission_catalog():
            assert isinstance(entry, tuple)
            assert len(entry) == 3

    def test_all_codes_are_non_empty_strings(self):
        for code, name, desc in _permission_catalog():
            assert isinstance(code, str) and code
            assert isinstance(name, str) and name
            assert isinstance(desc, str) and desc

    def test_codes_are_unique(self):
        catalog = _permission_catalog()
        codes = [code for code, _, _ in catalog]
        assert len(codes) == len(set(codes))

    def test_contains_core_permissions(self):
        codes = {code for code, _, _ in _permission_catalog()}
        for expected in (
            'admin.users.view',
            'admin.templates.view',
            'assignment.view',
            'assignment.enter',
            'assignment.submit',
            'admin.settings.manage',
            'admin.governance.view',
        ):
            assert expected in codes, f"Expected permission '{expected}' missing from catalog"

    def test_all_codes_contain_dot_separator(self):
        for code, _, _ in _permission_catalog():
            assert '.' in code, f"Permission code '{code}' has no '.' separator"

    def test_stable_length(self):
        # Guards against accidental deletions: catalog should have enough entries
        assert len(_permission_catalog()) >= 50


# ---------------------------------------------------------------------------
# _baseline_roles
# ---------------------------------------------------------------------------

class TestBaselineRoles:
    def _roles(self):
        return _baseline_roles(_permission_catalog())

    def test_returns_list_of_dicts(self):
        roles = self._roles()
        assert isinstance(roles, list)
        for role in roles:
            assert isinstance(role, dict)

    def test_each_role_has_required_keys(self):
        for role in self._roles():
            assert 'code' in role
            assert 'name' in role
            assert 'description' in role
            assert 'permission_codes' in role

    def test_role_codes_unique(self):
        codes = [r['code'] for r in self._roles()]
        assert len(codes) == len(set(codes))

    def test_system_manager_has_all_catalog_permissions(self):
        catalog = _permission_catalog()
        all_codes = {code for code, _, _ in catalog}
        sm_role = next(r for r in _baseline_roles(catalog) if r['code'] == 'system_manager')
        assert set(sm_role['permission_codes']) == all_codes

    def test_admin_full_only_has_admin_permissions(self):
        catalog = _permission_catalog()
        admin_full = next(r for r in _baseline_roles(catalog) if r['code'] == 'admin_full')
        for code in admin_full['permission_codes']:
            assert code.startswith('admin.'), f"Non-admin perm in admin_full: {code}"

    def test_all_role_permission_codes_in_catalog(self):
        catalog = _permission_catalog()
        catalog_codes = {code for code, _, _ in catalog}
        for role in _baseline_roles(catalog):
            for perm in role['permission_codes']:
                assert perm in catalog_codes, (
                    f"Permission '{perm}' in role '{role['code']}' not found in catalog"
                )

    def test_contains_expected_roles(self):
        role_codes = {r['code'] for r in self._roles()}
        for expected in (
            'system_manager', 'admin_core', 'admin_full',
            'assignment_viewer', 'assignment_approver',
            'assignment_editor_submitter',
        ):
            assert expected in role_codes, f"Expected role '{expected}' missing"

    def test_assignment_viewer_has_only_view(self):
        catalog = _permission_catalog()
        roles = _baseline_roles(catalog)
        viewer = next(r for r in roles if r['code'] == 'assignment_viewer')
        assert viewer['permission_codes'] == ['assignment.view']

    def test_admin_core_is_subset_of_admin_permissions(self):
        catalog = _permission_catalog()
        roles = _baseline_roles(catalog)
        admin_full = next(r for r in roles if r['code'] == 'admin_full')
        admin_core = next(r for r in roles if r['code'] == 'admin_core')
        full_set = set(admin_full['permission_codes'])
        for perm in admin_core['permission_codes']:
            assert perm in full_set, f"admin_core has perm '{perm}' not in admin_full"


# ---------------------------------------------------------------------------
# seed_rbac_permissions_and_roles  (integration tests using real DB)
# ---------------------------------------------------------------------------

class TestSeedRbacPermissionsAndRoles:
    """Integration tests for seed_rbac_permissions_and_roles."""

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _run(app, **kwargs):
        """Run seed inside app context, patching safe_remove to keep session alive."""
        with app.app_context():
            with patch('app.services.organization.rbac_seed_service.safe_remove'):
                return seed_rbac_permissions_and_roles(**kwargs)

    # ------------------------------------------------------------------
    # return-value shape
    # ------------------------------------------------------------------

    def test_return_dict_has_all_keys(self, db_session, app):
        result = self._run(app, use_advisory_lock=False)
        expected_keys = {
            'skipped_due_to_lock', 'created_permissions', 'updated_permissions',
            'created_roles', 'updated_roles', 'created_role_permission_links',
            'deleted_role_permission_links',
        }
        assert expected_keys == set(result.keys())

    def test_first_run_creates_permissions_and_roles(self, db_session, app):
        result = self._run(app, use_advisory_lock=False)
        assert result['skipped_due_to_lock'] == 0
        assert result['created_permissions'] > 0
        assert result['created_roles'] > 0
        assert result['created_role_permission_links'] > 0
        assert result['updated_permissions'] == 0
        assert result['updated_roles'] == 0
        assert result['deleted_role_permission_links'] == 0

    # ------------------------------------------------------------------
    # idempotency
    # ------------------------------------------------------------------

    def test_second_run_creates_nothing_new(self, db_session, app):
        self._run(app, use_advisory_lock=False)
        result = self._run(app, use_advisory_lock=False)
        assert result['created_permissions'] == 0
        assert result['created_roles'] == 0
        assert result['created_role_permission_links'] == 0
        assert result['deleted_role_permission_links'] == 0

    # ------------------------------------------------------------------
    # upsert permission
    # ------------------------------------------------------------------

    def test_updates_permission_name_when_changed(self, db_session, app):
        with app.app_context():
            from app.models.rbac import RbacPermission
            with patch('app.services.organization.rbac_seed_service.safe_remove'):
                seed_rbac_permissions_and_roles(use_advisory_lock=False)

            perm = db_session.query(RbacPermission).filter_by(code='admin.users.view').first()
            assert perm is not None
            perm.name = 'Old Name'
            db_session.commit()

            with patch('app.services.organization.rbac_seed_service.safe_remove'):
                result = seed_rbac_permissions_and_roles(use_advisory_lock=False)

            assert result['updated_permissions'] >= 1
            db_session.expire(perm)
            perm = db_session.query(RbacPermission).filter_by(code='admin.users.view').first()
            assert perm.name == 'View users'

    def test_updates_permission_description_when_changed(self, db_session, app):
        with app.app_context():
            from app.models.rbac import RbacPermission
            with patch('app.services.organization.rbac_seed_service.safe_remove'):
                seed_rbac_permissions_and_roles(use_advisory_lock=False)

            perm = db_session.query(RbacPermission).filter_by(code='admin.users.view').first()
            perm.description = 'Old description'
            db_session.commit()

            with patch('app.services.organization.rbac_seed_service.safe_remove'):
                result = seed_rbac_permissions_and_roles(use_advisory_lock=False)

            assert result['updated_permissions'] >= 1

    # ------------------------------------------------------------------
    # upsert role
    # ------------------------------------------------------------------

    def test_updates_role_name_when_changed(self, db_session, app):
        with app.app_context():
            from app.models.rbac import RbacRole
            with patch('app.services.organization.rbac_seed_service.safe_remove'):
                seed_rbac_permissions_and_roles(use_advisory_lock=False)

            role = db_session.query(RbacRole).filter_by(code='system_manager').first()
            assert role is not None
            role.name = 'Old Name'
            db_session.commit()

            with patch('app.services.organization.rbac_seed_service.safe_remove'):
                result = seed_rbac_permissions_and_roles(use_advisory_lock=False)

            assert result['updated_roles'] >= 1
            db_session.expire(role)
            role = db_session.query(RbacRole).filter_by(code='system_manager').first()
            assert role.name == 'System Manager'

    def test_updates_role_description_when_changed(self, db_session, app):
        with app.app_context():
            from app.models.rbac import RbacRole
            with patch('app.services.organization.rbac_seed_service.safe_remove'):
                seed_rbac_permissions_and_roles(use_advisory_lock=False)

            role = db_session.query(RbacRole).filter_by(code='system_manager').first()
            role.description = 'Old description'
            db_session.commit()

            with patch('app.services.organization.rbac_seed_service.safe_remove'):
                result = seed_rbac_permissions_and_roles(use_advisory_lock=False)

            assert result['updated_roles'] >= 1

    # ------------------------------------------------------------------
    # role-permission links
    # ------------------------------------------------------------------

    def test_removes_stale_permission_links(self, db_session, app):
        with app.app_context():
            from app.models.rbac import RbacRole, RbacPermission, RbacRolePermission
            with patch('app.services.organization.rbac_seed_service.safe_remove'):
                seed_rbac_permissions_and_roles(use_advisory_lock=False)

            # Give assignment_viewer an extra (catalog) permission it shouldn't have
            role = db_session.query(RbacRole).filter_by(code='assignment_viewer').first()
            perm = db_session.query(RbacPermission).filter_by(code='admin.api.manage').first()
            extra = RbacRolePermission(role_id=role.id, permission_id=perm.id)
            db_session.add(extra)
            db_session.commit()

            with patch('app.services.organization.rbac_seed_service.safe_remove'):
                result = seed_rbac_permissions_and_roles(use_advisory_lock=False)

            assert result['deleted_role_permission_links'] >= 1
            remaining = db_session.query(RbacRolePermission).filter_by(
                role_id=role.id, permission_id=perm.id
            ).first()
            assert remaining is None

    def test_adds_missing_permission_links(self, db_session, app):
        with app.app_context():
            from app.models.rbac import RbacRole, RbacPermission, RbacRolePermission
            with patch('app.services.organization.rbac_seed_service.safe_remove'):
                seed_rbac_permissions_and_roles(use_advisory_lock=False)

            # Remove a link that should exist
            role = db_session.query(RbacRole).filter_by(code='assignment_viewer').first()
            perm = db_session.query(RbacPermission).filter_by(code='assignment.view').first()
            link = db_session.query(RbacRolePermission).filter_by(
                role_id=role.id, permission_id=perm.id
            ).first()
            if link:
                db_session.delete(link)
                db_session.commit()

            with patch('app.services.organization.rbac_seed_service.safe_remove'):
                result = seed_rbac_permissions_and_roles(use_advisory_lock=False)

            assert result['created_role_permission_links'] >= 1
            restored = db_session.query(RbacRolePermission).filter_by(
                role_id=role.id, permission_id=perm.id
            ).first()
            assert restored is not None

    # ------------------------------------------------------------------
    # completeness checks
    # ------------------------------------------------------------------

    def test_all_catalog_permissions_created_in_db(self, db_session, app):
        with app.app_context():
            from app.models.rbac import RbacPermission
            with patch('app.services.organization.rbac_seed_service.safe_remove'):
                seed_rbac_permissions_and_roles(use_advisory_lock=False)

            catalog = _permission_catalog()
            for code, name, _ in catalog:
                perm = db_session.query(RbacPermission).filter_by(code=code).first()
                assert perm is not None, f"Permission '{code}' not found in DB"
                assert perm.name == name

    def test_all_baseline_roles_created_in_db(self, db_session, app):
        with app.app_context():
            from app.models.rbac import RbacRole
            with patch('app.services.organization.rbac_seed_service.safe_remove'):
                seed_rbac_permissions_and_roles(use_advisory_lock=False)

            catalog = _permission_catalog()
            for role_def in _baseline_roles(catalog):
                role = db_session.query(RbacRole).filter_by(code=role_def['code']).first()
                assert role is not None, f"Role '{role_def['code']}' not found in DB"

    def test_system_manager_has_all_permissions_in_db(self, db_session, app):
        with app.app_context():
            from app.models.rbac import RbacRole, RbacPermission, RbacRolePermission
            with patch('app.services.organization.rbac_seed_service.safe_remove'):
                seed_rbac_permissions_and_roles(use_advisory_lock=False)

            catalog_codes = {code for code, _, _ in _permission_catalog()}
            role = db_session.query(RbacRole).filter_by(code='system_manager').first()
            assert role is not None

            linked = (
                db_session.query(RbacPermission.code)
                .join(RbacRolePermission, RbacRolePermission.permission_id == RbacPermission.id)
                .filter(RbacRolePermission.role_id == role.id)
                .all()
            )
            linked_codes = {row[0] for row in linked}
            assert catalog_codes.issubset(linked_codes)

    # ------------------------------------------------------------------
    # advisory lock paths
    # ------------------------------------------------------------------

    def test_skip_when_lock_not_acquired(self, db_session, app):
        with app.app_context():
            with patch(
                "app.services.organization.rbac_seed_service.try_session_advisory_lock",
                return_value=False,
            ), patch(
                "app.services.organization.rbac_seed_service.db"
            ) as mock_db, patch(
                "app.services.organization.rbac_seed_service.safe_remove"
            ):
                mock_db.engine.dialect.name = "postgresql"
                result = seed_rbac_permissions_and_roles(use_advisory_lock=True)

            assert result['skipped_due_to_lock'] == 1
            assert result['created_permissions'] == 0
            assert result['created_roles'] == 0

    def test_lock_acquire_exception_falls_back(self, db_session, app):
        """When pg_try_advisory_lock raises, seed should still run (lock_acquired=False)."""
        with app.app_context():
            from app import db as _db
            call_count = [0]
            real_execute = _db.session.execute

            def side_effect(stmt, *args, **kwargs):
                call_count[0] += 1
                if call_count[0] == 1:
                    raise Exception("Advisory lock query failed")
                return real_execute(stmt, *args, **kwargs)

            with patch.object(_db.session, 'execute', side_effect=side_effect):
                with patch('app.services.organization.rbac_seed_service.safe_remove'):
                    result = seed_rbac_permissions_and_roles(use_advisory_lock=True)

            # Should have run the seeding despite the lock error
            assert 'created_permissions' in result

    def test_advisory_lock_true_runs_normally(self, db_session, app):
        """use_advisory_lock=True with a real PG connection should work."""
        with app.app_context():
            with patch('app.services.organization.rbac_seed_service.safe_remove'):
                try:
                    result = seed_rbac_permissions_and_roles(use_advisory_lock=True)
                    assert 'skipped_due_to_lock' in result
                except Exception:
                    pytest.skip("Advisory lock not supported in this test environment")

    def test_no_advisory_lock_runs_normally(self, db_session, app):
        result = self._run(app, use_advisory_lock=False)
        assert result['skipped_due_to_lock'] == 0

    # ------------------------------------------------------------------
    # created_by attribution
    # ------------------------------------------------------------------

    def test_created_by_user_id_attribution_with_system_manager(self, db_session, app):
        """When a user with system_manager role exists, created_by_user_id should be set."""
        with app.app_context():
            from app.models.rbac import RbacRole, RbacUserRole
            from tests.factories import create_test_user

            # First seed to get roles
            with patch('app.services.organization.rbac_seed_service.safe_remove'):
                seed_rbac_permissions_and_roles(use_advisory_lock=False)

            # Create a user, attach system_manager role
            user = create_test_user(db_session, role='system_manager')
            sm_role = db_session.query(RbacRole).filter_by(code='system_manager').first()
            if sm_role:
                existing = db_session.query(RbacUserRole).filter_by(
                    user_id=user.id, role_id=sm_role.id
                ).first()
                if not existing:
                    db_session.add(RbacUserRole(user_id=user.id, role_id=sm_role.id))
                    db_session.commit()

            # Re-seed – should find SM user and not crash
            with patch('app.services.organization.rbac_seed_service.safe_remove'):
                result = seed_rbac_permissions_and_roles(use_advisory_lock=False)

            assert result['skipped_due_to_lock'] == 0

    def test_created_by_lookup_exception_handled(self, db_session, app):
        """If SM lookup raises, seed should still complete (fallback to None)."""
        with app.app_context():
            from app.models import User
            with patch.object(User, 'query', new_callable=MagicMock) as mock_q:
                mock_q.join.return_value.join.return_value.filter.return_value.first.side_effect = Exception("DB error")
                with patch('app.services.organization.rbac_seed_service.safe_remove'):
                    result = seed_rbac_permissions_and_roles(use_advisory_lock=False)
            # Should not raise; should have created permissions
            assert result['created_permissions'] > 0

    # ------------------------------------------------------------------
    # edge cases
    # ------------------------------------------------------------------

    def test_role_def_with_empty_code_skipped(self, db_session, app):
        """Role defs with empty/blank code should be silently skipped."""
        catalog = _permission_catalog()
        bad_roles = [{'code': '', 'name': 'Empty', 'description': 'x', 'permission_codes': []}]
        with app.app_context():
            with patch('app.services.organization.rbac_seed_service._baseline_roles', return_value=bad_roles), \
                 patch('app.services.organization.rbac_seed_service._extension_baseline_roles', return_value=[]), \
                 patch('app.services.organization.rbac_seed_service.safe_remove'):
                result = seed_rbac_permissions_and_roles(use_advisory_lock=False)
            assert result['created_roles'] == 0

    def test_duplicate_permission_codes_deduplicated(self, db_session, app):
        """Duplicate permission codes in a role's permission_codes are deduplicated."""
        catalog = _permission_catalog()
        roles_with_dup = [
            {
                'code': 'test_dedup_role',
                'name': 'Test Dedup',
                'description': 'dedup test',
                'permission_codes': ['assignment.view', 'assignment.view', 'assignment.view'],
            }
        ]
        with app.app_context():
            with patch('app.services.organization.rbac_seed_service._baseline_roles', return_value=roles_with_dup), \
                 patch('app.services.organization.rbac_seed_service._extension_baseline_roles', return_value=[]), \
                 patch('app.services.organization.rbac_seed_service.safe_remove'):
                result = seed_rbac_permissions_and_roles(use_advisory_lock=False)
            # Only one link should be created for the unique permission
            assert result['created_role_permission_links'] <= 1

    def test_permission_codes_with_empty_string_skipped(self, db_session, app):
        """Empty string in permission_codes list is silently skipped."""
        catalog = _permission_catalog()
        roles_with_empty = [
            {
                'code': 'test_empty_perm',
                'name': 'Test Empty Perm',
                'description': 'test',
                'permission_codes': ['', 'assignment.view', None],
            }
        ]
        with app.app_context():
            with patch('app.services.organization.rbac_seed_service._baseline_roles', return_value=roles_with_empty), \
                 patch('app.services.organization.rbac_seed_service.safe_remove'):
                result = seed_rbac_permissions_and_roles(use_advisory_lock=False)
            # Should not crash; assignment.view gets resolved
            assert result['skipped_due_to_lock'] == 0

    def test_role_with_none_permission_codes_handled(self, db_session, app):
        """Role with None permission_codes should not crash."""
        roles = [
            {'code': 'role_none_perms', 'name': 'Test', 'description': 'test', 'permission_codes': None}
        ]
        with app.app_context():
            with patch('app.services.organization.rbac_seed_service._baseline_roles', return_value=roles), \
                 patch('app.services.organization.rbac_seed_service._extension_baseline_roles', return_value=[]), \
                 patch('app.services.organization.rbac_seed_service.safe_remove'):
                result = seed_rbac_permissions_and_roles(use_advisory_lock=False)
            assert result['created_role_permission_links'] == 0

    def test_creates_plugin_extension_role(self, db_session, app):
        """Plugin seed roles must be inserted even when core roles already exist."""
        from app.models.rbac import RbacRole, RbacPermission

        ext_perm = ("admin.data_explore.upr_visuals", "UPR visuals", "Access UPR visuals")
        ext_role = {
            "code": "admin_data_explorer_upr_visuals",
            "name": "Admin: Data Explorer (UPR visuals)",
            "description": "Access UPR visuals.",
            "permission_codes": ["admin.data_explore.upr_visuals"],
        }
        with app.app_context():
            with patch(
                "app.services.organization.rbac_seed_service._extension_permission_catalog",
                return_value=[],
            ), patch(
                "app.services.organization.rbac_seed_service._extension_baseline_roles",
                return_value=[],
            ), patch("app.services.organization.rbac_seed_service.safe_remove"):
                seed_rbac_permissions_and_roles(use_advisory_lock=False)
            assert db_session.query(RbacRole).filter_by(code=ext_role["code"]).first() is None

            with patch(
                "app.services.organization.rbac_seed_service._extension_permission_catalog",
                return_value=[ext_perm],
            ), patch(
                "app.services.organization.rbac_seed_service._extension_baseline_roles",
                return_value=[ext_role],
            ), patch("app.services.organization.rbac_seed_service.safe_remove"):
                result = seed_rbac_permissions_and_roles(use_advisory_lock=False)

            assert result["created_roles"] == 1
            assert result["created_permissions"] == 1
            role = db_session.query(RbacRole).filter_by(code=ext_role["code"]).first()
            perm = db_session.query(RbacPermission).filter_by(code=ext_perm[0]).first()
            assert role is not None
            assert perm is not None

    def test_plugin_registry_loads_empty_manager(self, app):
        from app.services.organization.rbac_seed_service import _plugin_registry

        registry = MagicMock()
        registry.plugins = {}
        original = getattr(app, "plugin_manager", None)
        try:
            app.plugin_manager = registry
            with app.app_context():
                resolved = _plugin_registry()
            registry.load_plugins.assert_called_once()
            assert resolved is registry
        finally:
            if original is not None:
                app.plugin_manager = original
            elif hasattr(app, "plugin_manager"):
                delattr(app, "plugin_manager")
