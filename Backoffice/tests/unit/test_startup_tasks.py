"""
Comprehensive tests for app/startup_tasks.py — targets 100% coverage.

All external I/O (DB, threads, RBAC service) is mocked.
"""

import os
import threading
import pytest
from unittest.mock import MagicMock, patch, call


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_app(testing=False, debug=False):
    app = MagicMock()
    app.config = {"TESTING": testing, "DEBUG": debug}
    app.debug = debug
    app.logger = MagicMock()
    return app


# ===========================================================================
# deferred_startup_cleanup
# ===========================================================================

class TestDeferredStartupCleanup:
    """Tests for deferred_startup_cleanup."""

    def _import(self):
        from app.startup_tasks import deferred_startup_cleanup
        return deferred_startup_cleanup

    def _run_cleanup_task_synchronously(self, app, mock_engine=None):
        """
        Invoke deferred_startup_cleanup with a captured thread target,
        then run the target synchronously.
        """
        fn = self._import()
        captured = {}

        class CapturingThread:
            def __init__(self, target=None, daemon=None):
                captured["target"] = target

            def start(self):
                pass

        with patch("app.startup_tasks.threading.Thread", CapturingThread):
            fn(app)

        return captured.get("target")

    def test_starts_background_thread(self):
        fn = self._import()
        app = _mock_app()

        with patch("app.startup_tasks.threading.Thread") as mock_thread:
            mock_thread_instance = MagicMock()
            mock_thread.return_value = mock_thread_instance
            fn(app)

        mock_thread_instance.start.assert_called_once()
        app.logger.debug.assert_called()

    def test_cleanup_task_success_with_stale_sessions(self):
        app = _mock_app()
        task = self._run_cleanup_task_synchronously(app)
        assert task is not None

        app_ctx = MagicMock()
        app_ctx.__enter__ = MagicMock(return_value=None)
        app_ctx.__exit__ = MagicMock(return_value=False)
        app.app_context.return_value = app_ctx

        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_engine_ctx = MagicMock()
        mock_engine_ctx.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine_ctx.__exit__ = MagicMock(return_value=False)
        mock_db.engine.connect.return_value = mock_engine_ctx
        mock_db.text.return_value = "SELECT 1"

        with patch("app.startup_tasks.db", mock_db):
            with patch(
                "app.services.platform.user_analytics_service.cleanup_inactive_sessions",
                return_value=5,
            ):
                task()

        app.logger.info.assert_called()

    def test_cleanup_task_success_zero_stale_sessions(self):
        app = _mock_app()
        task = self._run_cleanup_task_synchronously(app)

        app_ctx = MagicMock()
        app_ctx.__enter__ = MagicMock(return_value=None)
        app_ctx.__exit__ = MagicMock(return_value=False)
        app.app_context.return_value = app_ctx

        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_engine_ctx = MagicMock()
        mock_engine_ctx.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine_ctx.__exit__ = MagicMock(return_value=False)
        mock_db.engine.connect.return_value = mock_engine_ctx
        mock_db.text.return_value = "SELECT 1"

        with patch("app.startup_tasks.db", mock_db):
            with patch(
                "app.services.platform.user_analytics_service.cleanup_inactive_sessions",
                return_value=0,
            ):
                task()

        # cleanup_count == 0, so info should NOT be called
        app.logger.info.assert_not_called()

    def test_cleanup_task_db_exception_logs_warning(self):
        app = _mock_app()
        task = self._run_cleanup_task_synchronously(app)

        app_ctx = MagicMock()
        app_ctx.__enter__ = MagicMock(return_value=None)
        app_ctx.__exit__ = MagicMock(return_value=False)
        app.app_context.return_value = app_ctx

        mock_db = MagicMock()
        mock_db.engine.connect.side_effect = Exception("db not ready")

        with patch("app.startup_tasks.db", mock_db):
            task()

        app.logger.warning.assert_called()


# ===========================================================================
# deferred_rbac_seed
# ===========================================================================

class TestDeferredRbacSeed:
    """Tests for deferred_rbac_seed."""

    def _import(self):
        from app.startup_tasks import deferred_rbac_seed
        return deferred_rbac_seed

    def test_returns_early_when_auto_seed_false(self):
        fn = self._import()
        app = _mock_app()

        with patch.dict(os.environ, {"AUTO_SEED_RBAC_ON_STARTUP": "false"}):
            with patch("app.startup_tasks.threading.Thread") as mock_thread:
                fn(app, "development", is_reloader=False)

        mock_thread.assert_not_called()

    def test_auto_seeds_when_env_unset_including_development(self):
        fn = self._import()
        app = _mock_app()

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AUTO_SEED_RBAC_ON_STARTUP", None)
            os.environ.pop("RUNNING_MIGRATION", None)
            os.environ.pop("FLASK_RUN_FROM_CLI", None)
            with patch("app.startup_tasks.threading.Thread") as mock_thread:
                mock_instance = MagicMock()
                mock_thread.return_value = mock_instance
                fn(app, "development", is_reloader=False)

        mock_instance.start.assert_called_once()

    def test_auto_seeds_for_production_config(self):
        fn = self._import()
        app = _mock_app()

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AUTO_SEED_RBAC_ON_STARTUP", None)
            with patch("app.startup_tasks.threading.Thread") as mock_thread:
                mock_instance = MagicMock()
                mock_thread.return_value = mock_instance
                fn(app, "production", is_reloader=False)

        mock_instance.start.assert_called_once()

    def test_auto_seeds_for_staging_config(self):
        fn = self._import()
        app = _mock_app()

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AUTO_SEED_RBAC_ON_STARTUP", None)
            with patch("app.startup_tasks.threading.Thread") as mock_thread:
                mock_instance = MagicMock()
                mock_thread.return_value = mock_instance
                fn(app, "staging", is_reloader=False)

        mock_instance.start.assert_called_once()

    def test_returns_early_when_testing(self):
        fn = self._import()
        app = _mock_app(testing=True)

        with patch.dict(os.environ, {"AUTO_SEED_RBAC_ON_STARTUP": "true"}):
            with patch("app.startup_tasks.threading.Thread") as mock_thread:
                fn(app, "production", is_reloader=False)

        mock_thread.assert_not_called()

    def test_returns_early_when_running_migration(self):
        fn = self._import()
        app = _mock_app()

        with patch.dict(os.environ, {
            "AUTO_SEED_RBAC_ON_STARTUP": "true",
            "RUNNING_MIGRATION": "1",
        }):
            with patch("app.startup_tasks.threading.Thread") as mock_thread:
                fn(app, "production", is_reloader=False)

        mock_thread.assert_not_called()

    def test_flask_run_from_cli_env_var_does_not_prevent_seeding(self):
        """Regression guard: FLASK_RUN_FROM_CLI is set by Flask for *every*
        `flask` subcommand, including plain `flask run` in local dev -- not
        just one-off commands like `flask rbac seed`. A previous fix bailed
        out of auto-seeding whenever this env var was set, which silently
        disabled the local-dev auto-seed safety net entirely. The CLI/auto-seed
        race this was meant to solve is now handled at the advisory-lock layer
        (RbacSeedLockMode.WAIT for CLI/entrypoint callers) instead.
        """
        fn = self._import()
        app = _mock_app()

        with patch.dict(os.environ, {
            "AUTO_SEED_RBAC_ON_STARTUP": "true",
            "FLASK_RUN_FROM_CLI": "true",
        }):
            os.environ.pop("RUNNING_MIGRATION", None)
            with patch("app.startup_tasks.threading.Thread") as mock_thread:
                mock_instance = MagicMock()
                mock_thread.return_value = mock_instance
                fn(app, "production", is_reloader=False)

        mock_instance.start.assert_called_once()

    def test_returns_early_when_debug_without_reloader(self):
        fn = self._import()
        app = _mock_app(debug=True)

        with patch.dict(os.environ, {"AUTO_SEED_RBAC_ON_STARTUP": "true"}):
            os.environ.pop("RUNNING_MIGRATION", None)
            with patch("app.startup_tasks.threading.Thread") as mock_thread:
                fn(app, "production", is_reloader=False)

        mock_thread.assert_not_called()

    def test_debug_with_reloader_does_seed(self):
        fn = self._import()
        app = _mock_app(debug=True)

        with patch.dict(os.environ, {"AUTO_SEED_RBAC_ON_STARTUP": "true"}):
            os.environ.pop("RUNNING_MIGRATION", None)
            with patch("app.startup_tasks.threading.Thread") as mock_thread:
                mock_instance = MagicMock()
                mock_thread.return_value = mock_instance
                fn(app, "production", is_reloader=True)

        mock_instance.start.assert_called_once()

    def _run_seed_task_synchronously(self, app, config_name="production"):
        fn = self._import()
        captured = {}

        class CapturingThread:
            def __init__(self, target=None, daemon=None):
                captured["target"] = target

            def start(self):
                pass

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AUTO_SEED_RBAC_ON_STARTUP", None)
            os.environ.pop("RUNNING_MIGRATION", None)
            with patch("app.startup_tasks.threading.Thread", CapturingThread):
                fn(app, config_name, is_reloader=False)

        return captured.get("target")

    def test_seed_task_success(self):
        app = _mock_app()
        app_ctx = MagicMock()
        app_ctx.__enter__ = MagicMock(return_value=None)
        app_ctx.__exit__ = MagicMock(return_value=False)
        app.app_context.return_value = app_ctx

        task = self._run_seed_task_synchronously(app, "production")
        assert task is not None

        mock_conn = MagicMock()
        mock_engine_ctx = MagicMock()
        mock_engine_ctx.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine_ctx.__exit__ = MagicMock(return_value=False)

        mock_db = MagicMock()
        mock_db.engine.connect.return_value = mock_engine_ctx
        mock_db.text.return_value = "SELECT 1"

        stats = {
            "created_permissions": 5,
            "updated_permissions": 1,
            "created_roles": 2,
            "updated_roles": 0,
            "created_role_permission_links": 10,
            "deleted_role_permission_links": 3,
        }

        with patch("app.startup_tasks.db", mock_db):
            with patch(
                "app.services.organization.rbac_seed_service.seed_rbac_permissions_and_roles",
                return_value=stats,
            ):
                task()

        app.logger.info.assert_called()

    def test_seed_task_skipped_due_to_lock(self):
        app = _mock_app()
        app_ctx = MagicMock()
        app_ctx.__enter__ = MagicMock(return_value=None)
        app_ctx.__exit__ = MagicMock(return_value=False)
        app.app_context.return_value = app_ctx

        task = self._run_seed_task_synchronously(app, "production")

        mock_conn = MagicMock()
        mock_engine_ctx = MagicMock()
        mock_engine_ctx.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine_ctx.__exit__ = MagicMock(return_value=False)
        mock_db = MagicMock()
        mock_db.engine.connect.return_value = mock_engine_ctx
        mock_db.text.return_value = "SELECT 1"

        with patch("app.startup_tasks.db", mock_db):
            with patch(
                "app.services.organization.rbac_seed_service.seed_rbac_permissions_and_roles",
                return_value={"skipped_due_to_lock": True},
            ):
                task()

        info_calls = " ".join(str(c) for c in app.logger.info.call_args_list)
        assert "skipped" in info_calls.lower()

    def test_seed_task_db_retry_then_success(self):
        """DB fails on first attempt, succeeds on second; seed runs."""
        app = _mock_app()
        app_ctx = MagicMock()
        app_ctx.__enter__ = MagicMock(return_value=None)
        app_ctx.__exit__ = MagicMock(return_value=False)
        app.app_context.return_value = app_ctx

        task = self._run_seed_task_synchronously(app, "production")

        mock_db = MagicMock()
        call_count = {"n": 0}

        def engine_connect():
            call_count["n"] += 1
            if call_count["n"] < 2:
                raise Exception("connection refused")
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=MagicMock())
            ctx.__exit__ = MagicMock(return_value=False)
            return ctx

        mock_db.engine.connect.side_effect = engine_connect
        mock_db.text.return_value = "SELECT 1"

        with patch("app.startup_tasks.db", mock_db):
            with patch("app.startup_tasks._time.sleep"):
                with patch(
                    "app.services.organization.rbac_seed_service.seed_rbac_permissions_and_roles",
                    return_value={},
                ):
                    task()

        assert app.logger.info.called

    def test_seed_task_all_db_retries_fail_logs_warning(self):
        """When all 5 DB retries fail, log a warning."""
        app = _mock_app()
        app_ctx = MagicMock()
        app_ctx.__enter__ = MagicMock(return_value=None)
        app_ctx.__exit__ = MagicMock(return_value=False)
        app.app_context.return_value = app_ctx

        task = self._run_seed_task_synchronously(app, "production")

        mock_db = MagicMock()
        mock_db.engine.connect.side_effect = Exception("connection refused")
        mock_db.text.return_value = "SELECT 1"

        with patch("app.startup_tasks.db", mock_db):
            with patch("app.startup_tasks._time.sleep"):
                task()

        app.logger.warning.assert_called()

    def test_auto_seed_env_true_string(self):
        fn = self._import()
        app = _mock_app()

        with patch.dict(os.environ, {"AUTO_SEED_RBAC_ON_STARTUP": "true"}):
            os.environ.pop("RUNNING_MIGRATION", None)
            with patch("app.startup_tasks.threading.Thread") as mock_thread:
                mock_instance = MagicMock()
                mock_thread.return_value = mock_instance
                fn(app, "development", is_reloader=False)

        mock_instance.start.assert_called_once()

    def test_auto_seed_env_false_string(self):
        fn = self._import()
        app = _mock_app()

        with patch.dict(os.environ, {"AUTO_SEED_RBAC_ON_STARTUP": "false"}):
            with patch("app.startup_tasks.threading.Thread") as mock_thread:
                fn(app, "production", is_reloader=False)

        mock_thread.assert_not_called()


# ===========================================================================
# audit_admin_route_guards
# ===========================================================================

class TestAuditAdminRouteGuards:
    """Tests for audit_admin_route_guards."""

    def _import(self):
        from app.startup_tasks import audit_admin_route_guards
        return audit_admin_route_guards

    def _make_app_with_rules(self, rules):
        """Build a mock Flask app with the given list of rule specs."""
        app = MagicMock()
        app.logger = MagicMock()
        app.debug = False

        mock_rules = []
        for spec in rules:
            rule = MagicMock()
            rule.rule = spec["path"]
            rule.endpoint = spec["endpoint"]
            view = MagicMock()
            view._rbac_guard_audit_exempt = spec.get("exempt", False)
            view._rbac_admin_required = spec.get("admin_required", False)
            view._rbac_system_manager_required = spec.get("sm_required", False)
            view._rbac_permissions_required = spec.get("perms", None)
            view._rbac_permissions_any_required = spec.get("perms_any", None)
            mock_rules.append(rule)
            app.view_functions.__getitem__ = MagicMock(return_value=view)
            app.view_functions.get = MagicMock(return_value=view)

        app.url_map.iter_rules.return_value = iter(mock_rules)
        return app

    def test_mode_off_returns_early(self):
        fn = self._import()
        app = MagicMock()
        app.logger = MagicMock()

        with patch.dict(os.environ, {"RBAC_ADMIN_ROUTE_GUARD_MODE": "off"}):
            fn(app)

        app.url_map.iter_rules.assert_not_called()

    def test_mode_disabled_returns_early(self):
        fn = self._import()
        app = MagicMock()
        app.logger = MagicMock()

        with patch.dict(os.environ, {"RBAC_ADMIN_ROUTE_GUARD_MODE": "disabled"}):
            fn(app)

        app.url_map.iter_rules.assert_not_called()

    def test_mode_false_returns_early(self):
        fn = self._import()
        app = MagicMock()
        app.logger = MagicMock()

        for val in ("0", "false", "no"):
            with patch.dict(os.environ, {"RBAC_ADMIN_ROUTE_GUARD_MODE": val}):
                fn(app)

            app.url_map.iter_rules.assert_not_called()

    def test_no_problems_returns_silently(self, app):
        """Routes that ARE protected produce no warnings."""
        fn = self._import()

        # Use the real app fixture since it has actual rules
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RBAC_ADMIN_ROUTE_GUARD_MODE", None)
            # Should not raise regardless
            fn(app)

    def test_unprotected_admin_route_logs_warning(self):
        fn = self._import()

        mock_view = MagicMock()
        mock_view._rbac_guard_audit_exempt = False
        mock_view._rbac_admin_required = False
        mock_view._rbac_system_manager_required = False
        mock_view._rbac_permissions_required = None
        mock_view._rbac_permissions_any_required = None

        mock_rule = MagicMock()
        mock_rule.rule = "/admin/some-unprotected-route"
        mock_rule.endpoint = "admin.unprotected"

        mock_app = MagicMock()
        mock_app.logger = MagicMock()
        mock_app.url_map.iter_rules.return_value = iter([mock_rule])
        mock_app.view_functions.get.return_value = mock_view

        with patch.dict(os.environ, {"RBAC_ADMIN_ROUTE_GUARD_MODE": "warn"}):
            fn(mock_app)

        mock_app.logger.warning.assert_called()

    def test_error_mode_logs_debug_when_runtime_error_raised(self):
        """In 'error' mode with unprotected routes, RuntimeError is caught by outer handler.

        The outer try/except in audit_admin_route_guards catches the RuntimeError and
        logs it at debug level instead of propagating it.
        """
        fn = self._import()

        mock_view = MagicMock()
        mock_view._rbac_guard_audit_exempt = False
        mock_view._rbac_admin_required = False
        mock_view._rbac_system_manager_required = False
        mock_view._rbac_permissions_required = None
        mock_view._rbac_permissions_any_required = None

        mock_rule = MagicMock()
        mock_rule.rule = "/admin/bad-route"
        mock_rule.endpoint = "admin.bad"

        mock_app = MagicMock()
        mock_app.logger = MagicMock()
        mock_app.url_map.iter_rules.return_value = iter([mock_rule])
        mock_app.view_functions.get.return_value = mock_view

        with patch.dict(os.environ, {"RBAC_ADMIN_ROUTE_GUARD_MODE": "error"}):
            fn(mock_app)  # should NOT raise — outer except catches RuntimeError

        mock_app.logger.debug.assert_called()

    def test_strict_mode_logs_debug_when_runtime_error_raised(self):
        """In 'strict' mode with unprotected routes, RuntimeError is caught by outer handler."""
        fn = self._import()

        mock_view = MagicMock()
        mock_view._rbac_guard_audit_exempt = False
        mock_view._rbac_admin_required = False
        mock_view._rbac_system_manager_required = False
        mock_view._rbac_permissions_required = None
        mock_view._rbac_permissions_any_required = None

        mock_rule = MagicMock()
        mock_rule.rule = "/admin/bad-route"
        mock_rule.endpoint = "admin.bad"

        mock_app = MagicMock()
        mock_app.logger = MagicMock()
        mock_app.url_map.iter_rules.return_value = iter([mock_rule])
        mock_app.view_functions.get.return_value = mock_view

        with patch.dict(os.environ, {"RBAC_ADMIN_ROUTE_GUARD_MODE": "strict"}):
            fn(mock_app)  # should NOT raise

        mock_app.logger.debug.assert_called()

    def test_exempt_view_is_skipped(self):
        fn = self._import()

        mock_view = MagicMock()
        mock_view._rbac_guard_audit_exempt = True  # exempt
        mock_view._rbac_admin_required = False
        mock_view._rbac_system_manager_required = False
        mock_view._rbac_permissions_required = None
        mock_view._rbac_permissions_any_required = None

        mock_rule = MagicMock()
        mock_rule.rule = "/admin/exempt-route"
        mock_rule.endpoint = "admin.exempt"

        mock_app = MagicMock()
        mock_app.logger = MagicMock()
        mock_app.url_map.iter_rules.return_value = iter([mock_rule])
        mock_app.view_functions.get.return_value = mock_view

        with patch.dict(os.environ, {"RBAC_ADMIN_ROUTE_GUARD_MODE": "warn"}):
            fn(mock_app)

        mock_app.logger.warning.assert_not_called()

    def test_non_admin_route_is_skipped(self):
        fn = self._import()

        mock_view = MagicMock()
        mock_rule = MagicMock()
        mock_rule.rule = "/public/some-route"
        mock_rule.endpoint = "public.route"

        mock_app = MagicMock()
        mock_app.logger = MagicMock()
        mock_app.url_map.iter_rules.return_value = iter([mock_rule])
        mock_app.view_functions.get.return_value = mock_view

        with patch.dict(os.environ, {"RBAC_ADMIN_ROUTE_GUARD_MODE": "warn"}):
            fn(mock_app)

        mock_app.logger.warning.assert_not_called()

    def test_none_view_is_skipped(self):
        fn = self._import()

        mock_rule = MagicMock()
        mock_rule.rule = "/admin/route-with-no-view"
        mock_rule.endpoint = "admin.ghost"

        mock_app = MagicMock()
        mock_app.logger = MagicMock()
        mock_app.url_map.iter_rules.return_value = iter([mock_rule])
        mock_app.view_functions.get.return_value = None  # view not found

        with patch.dict(os.environ, {"RBAC_ADMIN_ROUTE_GUARD_MODE": "warn"}):
            fn(mock_app)

        mock_app.logger.warning.assert_not_called()

    def test_rule_iteration_exception_is_skipped(self):
        fn = self._import()

        bad_rule = MagicMock()
        bad_rule.rule = "/admin/broken"
        bad_rule.endpoint = "admin.broken"

        mock_app = MagicMock()
        mock_app.logger = MagicMock()
        mock_app.url_map.iter_rules.return_value = iter([bad_rule])
        # view_functions.get raises
        mock_app.view_functions.get.side_effect = Exception("attr error")

        with patch.dict(os.environ, {"RBAC_ADMIN_ROUTE_GUARD_MODE": "warn"}):
            fn(mock_app)  # should not raise

        mock_app.logger.debug.assert_called()

    def test_outer_exception_is_silently_swallowed(self):
        fn = self._import()

        mock_app = MagicMock()
        mock_app.logger = MagicMock()
        mock_app.url_map.iter_rules.side_effect = Exception("url_map broken")

        with patch.dict(os.environ, {"RBAC_ADMIN_ROUTE_GUARD_MODE": "warn"}):
            fn(mock_app)  # should not raise

    def test_view_with_rbac_admin_required_is_protected(self):
        fn = self._import()

        mock_view = MagicMock()
        mock_view._rbac_guard_audit_exempt = False
        mock_view._rbac_admin_required = True
        mock_view._rbac_system_manager_required = False
        mock_view._rbac_permissions_required = None
        mock_view._rbac_permissions_any_required = None

        mock_rule = MagicMock()
        mock_rule.rule = "/admin/protected"
        mock_rule.endpoint = "admin.protected"

        mock_app = MagicMock()
        mock_app.logger = MagicMock()
        mock_app.url_map.iter_rules.return_value = iter([mock_rule])
        mock_app.view_functions.get.return_value = mock_view

        with patch.dict(os.environ, {"RBAC_ADMIN_ROUTE_GUARD_MODE": "warn"}):
            fn(mock_app)

        mock_app.logger.warning.assert_not_called()

    def test_view_with_perms_required_is_protected(self):
        fn = self._import()

        mock_view = MagicMock()
        mock_view._rbac_guard_audit_exempt = False
        mock_view._rbac_admin_required = False
        mock_view._rbac_system_manager_required = False
        mock_view._rbac_permissions_required = ["some_permission"]
        mock_view._rbac_permissions_any_required = None

        mock_rule = MagicMock()
        mock_rule.rule = "/admin/guarded"
        mock_rule.endpoint = "admin.guarded"

        mock_app = MagicMock()
        mock_app.logger = MagicMock()
        mock_app.url_map.iter_rules.return_value = iter([mock_rule])
        mock_app.view_functions.get.return_value = mock_view

        with patch.dict(os.environ, {"RBAC_ADMIN_ROUTE_GUARD_MODE": "warn"}):
            fn(mock_app)

        mock_app.logger.warning.assert_not_called()

    def test_default_mode_is_warn_when_env_missing(self):
        fn = self._import()

        mock_view = MagicMock()
        mock_view._rbac_guard_audit_exempt = False
        mock_view._rbac_admin_required = False
        mock_view._rbac_system_manager_required = False
        mock_view._rbac_permissions_required = None
        mock_view._rbac_permissions_any_required = None

        mock_rule = MagicMock()
        mock_rule.rule = "/admin/unguarded"
        mock_rule.endpoint = "admin.unguarded"

        mock_app = MagicMock()
        mock_app.debug = False
        mock_app.logger = MagicMock()
        mock_app.url_map.iter_rules.return_value = iter([mock_rule])
        mock_app.view_functions.get.return_value = mock_view

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RBAC_ADMIN_ROUTE_GUARD_MODE", None)
            fn(mock_app)

        mock_app.logger.warning.assert_called()


# ===========================================================================
# run_startup_tasks
# ===========================================================================

class TestRunStartupTasks:
    """Tests for run_startup_tasks."""

    def _import(self):
        from app.startup_tasks import run_startup_tasks
        return run_startup_tasks

    def test_calls_both_deferred_functions(self, app):
        fn = self._import()

        with patch("app.startup_tasks.deferred_startup_cleanup") as mock_cleanup:
            with patch("app.startup_tasks.deferred_rbac_seed") as mock_seed:
                fn(app, "testing", is_reloader=False)

        mock_cleanup.assert_called_once_with(app)
        mock_seed.assert_called_once_with(app, "testing", False)

    def test_cleanup_exception_is_caught_and_logged(self):
        fn = self._import()
        app = _mock_app()

        with patch(
            "app.startup_tasks.deferred_startup_cleanup",
            side_effect=Exception("cleanup failed"),
        ):
            with patch("app.startup_tasks.deferred_rbac_seed") as mock_seed:
                fn(app, "production", is_reloader=False)

        app.logger.warning.assert_called()
        mock_seed.assert_called_once()

    def test_rbac_seed_exception_is_caught_and_logged(self):
        fn = self._import()
        app = _mock_app()

        with patch("app.startup_tasks.deferred_startup_cleanup"):
            with patch(
                "app.startup_tasks.deferred_rbac_seed",
                side_effect=Exception("seed failed"),
            ):
                fn(app, "production", is_reloader=False)

        app.logger.warning.assert_called()
