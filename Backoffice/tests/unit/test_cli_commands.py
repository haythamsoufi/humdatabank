"""
Comprehensive tests for:
  - app/cli_commands/rbac.py
  - app/cli_commands/indicatorbank_sync.py

Targets 100% coverage for both modules.
"""

import pytest
from unittest.mock import MagicMock, patch


# ===========================================================================
# app/cli_commands/rbac.py
# ===========================================================================

class TestRbacCliCommandsModule:
    """Tests for register_rbac_commands (cli_commands/rbac.py).

    register_rbac_commands is the canonical source of the `flask rbac ...`
    group -- cli.py calls it once during normal app startup (see
    register_commands in app/cli.py) rather than defining its own inline
    `rbac` group. This test file registers it on its own minimal Flask app
    (instead of the shared `app`/`runner` fixtures) to keep these unit tests
    independent of the main app's CLI wiring.
    """

    @pytest.fixture()
    def rbac_app(self, app):
        """A separate minimal Flask app with rbac commands registered via the module."""
        from flask import Flask
        from app.cli_commands.rbac import register_rbac_commands

        mini_app = Flask(__name__ + "_rbac_test")
        mini_app.config.update(TESTING=True, SECRET_KEY="test", SQLALCHEMY_DATABASE_URI="sqlite://")
        register_rbac_commands(mini_app)
        return mini_app

    @pytest.fixture()
    def rbac_runner(self, rbac_app):
        return rbac_app.test_cli_runner()

    def test_rbac_seed_complete(self, rbac_runner):
        stats = {
            "created_permissions": 5,
            "updated_permissions": 1,
            "created_roles": 2,
            "updated_roles": 0,
            "created_role_permission_links": 10,
            "deleted_role_permission_links": 3,
        }
        with patch(
            "app.services.organization.rbac_seed_service.seed_rbac_permissions_and_roles",
            return_value=stats,
        ):
            result = rbac_runner.invoke(args=["rbac", "seed"])

        assert result.exit_code == 0
        assert "RBAC seed complete" in result.output
        assert "5 created" in result.output
        assert "2 created" in result.output
        assert "10 created" in result.output

    def test_rbac_seed_warns_when_roles_still_missing(self, rbac_runner):
        stats = {
            "created_permissions": 0,
            "updated_permissions": 0,
            "created_roles": 0,
            "updated_roles": 0,
            "created_role_permission_links": 0,
            "deleted_role_permission_links": 0,
        }
        with patch(
            "app.services.organization.rbac_seed_service.seed_rbac_permissions_and_roles",
            return_value=stats,
        ), patch(
            "app.services.organization.rbac_seed_service.get_missing_baseline_role_codes",
            return_value=["admin_data_explorer_upr_visuals"],
        ):
            result = rbac_runner.invoke(args=["rbac", "seed"])

        assert result.exit_code == 0
        assert "still missing" in result.output
        assert "admin_data_explorer_upr_visuals" in result.output

    def test_rbac_seed_skipped_due_to_lock(self, rbac_runner):
        with patch(
            "app.services.organization.rbac_seed_service.seed_rbac_permissions_and_roles",
            return_value={"skipped_due_to_lock": True},
        ):
            result = rbac_runner.invoke(args=["rbac", "seed"])

        assert result.exit_code == 0
        assert "skipped" in result.output.lower()
        assert "advisory lock" in result.output.lower()

    def test_rbac_seed_zero_stats(self, rbac_runner):
        stats = {
            "created_permissions": 0,
            "updated_permissions": 0,
            "created_roles": 0,
            "updated_roles": 0,
            "created_role_permission_links": 0,
            "deleted_role_permission_links": 0,
        }
        with patch(
            "app.services.organization.rbac_seed_service.seed_rbac_permissions_and_roles",
            return_value=stats,
        ):
            result = rbac_runner.invoke(args=["rbac", "seed"])

        assert result.exit_code == 0
        assert "RBAC seed complete" in result.output


# ===========================================================================
# app/cli_commands/indicatorbank_sync.py
# ===========================================================================

class TestIndicatorbankSyncCommands:
    """Tests for register_indicatorbank_commands (cli_commands/indicatorbank_sync.py)."""

    def test_sync_remote_missing_api_key(self, runner):
        """Should raise ClickException when no api_key is provided."""
        result = runner.invoke(
            args=["indicatorbank", "sync-remote"],
            env={"IFRC_INDICATORBANK_API_KEY": ""},
            catch_exceptions=False,
        )
        # ClickException exits with code 1 and prints "Error: …"
        assert result.exit_code != 0
        assert "Missing API key" in result.output or "Error" in result.output

    def test_sync_remote_missing_api_key_no_env(self, runner):
        """Without env var and without --api-key flag, should fail."""
        with patch.dict("os.environ", {}, clear=False):
            # Ensure the env var is absent
            import os
            os.environ.pop("IFRC_INDICATORBANK_API_KEY", None)
            result = runner.invoke(args=["indicatorbank", "sync-remote"])

        assert result.exit_code != 0

    def test_sync_remote_dry_run(self, runner):
        """Default is dry-run (apply=False). Verifies summary output."""
        stats = {
            "sectors_created": 2,
            "subsectors_created": 3,
            "indicators_created": 10,
            "indicators_updated": 5,
            "skipped": 1,
        }
        with patch(
            "app.services.indicators.remote_sync_service.sync_remote_indicator_bank",
            return_value=stats,
        ) as mock_sync:
            result = runner.invoke(
                args=["indicatorbank", "sync-remote", "--api-key", "test-key-123"],
            )

        assert result.exit_code == 0
        assert "sectors created: 2" in result.output
        assert "indicators created: 10" in result.output
        assert "Dry-run only" in result.output
        mock_sync.assert_called_once_with(
            api_url="https://ifrc-indicatorbank.azurewebsites.net/api/indicator",
            api_key="test-key-123",
            limit=None,
            apply=False,
        )

    def test_sync_remote_apply(self, runner):
        """--apply flag should set apply=True."""
        stats = {
            "sectors_created": 0,
            "subsectors_created": 0,
            "indicators_created": 0,
            "indicators_updated": 3,
            "skipped": 0,
        }
        with patch(
            "app.services.indicators.remote_sync_service.sync_remote_indicator_bank",
            return_value=stats,
        ) as mock_sync:
            result = runner.invoke(
                args=["indicatorbank", "sync-remote", "--api-key", "key", "--apply"],
            )

        assert result.exit_code == 0
        assert "Applied changes to DB" in result.output
        mock_sync.assert_called_once_with(
            api_url="https://ifrc-indicatorbank.azurewebsites.net/api/indicator",
            api_key="key",
            limit=None,
            apply=True,
        )

    def test_sync_remote_with_limit(self, runner):
        stats = {
            "sectors_created": 0,
            "subsectors_created": 0,
            "indicators_created": 5,
            "indicators_updated": 0,
            "skipped": 0,
        }
        with patch(
            "app.services.indicators.remote_sync_service.sync_remote_indicator_bank",
            return_value=stats,
        ) as mock_sync:
            result = runner.invoke(
                args=["indicatorbank", "sync-remote", "--api-key", "key", "--limit", "5"],
            )

        assert result.exit_code == 0
        mock_sync.assert_called_once_with(
            api_url="https://ifrc-indicatorbank.azurewebsites.net/api/indicator",
            api_key="key",
            limit=5,
            apply=False,
        )

    def test_sync_remote_with_name_translations_stats(self, runner):
        """When stats include name_translations_cleared, show extra lines."""
        stats = {
            "sectors_created": 0,
            "subsectors_created": 0,
            "indicators_created": 0,
            "indicators_updated": 1,
            "skipped": 0,
            "name_translations_cleared": 4,
            "definition_translations_cleared": 2,
        }
        with patch(
            "app.services.indicators.remote_sync_service.sync_remote_indicator_bank",
            return_value=stats,
        ):
            result = runner.invoke(
                args=["indicatorbank", "sync-remote", "--api-key", "key"],
            )

        assert result.exit_code == 0
        assert "name translations cleared: 4" in result.output
        assert "definition translations cleared: 2" in result.output

    def test_sync_remote_with_name_id_mismatches_stats(self, runner):
        """When stats include name_id_mismatches, show extra line."""
        stats = {
            "sectors_created": 0,
            "subsectors_created": 0,
            "indicators_created": 0,
            "indicators_updated": 0,
            "skipped": 0,
            "name_id_mismatches": 7,
        }
        with patch(
            "app.services.indicators.remote_sync_service.sync_remote_indicator_bank",
            return_value=stats,
        ):
            result = runner.invoke(
                args=["indicatorbank", "sync-remote", "--api-key", "key"],
            )

        assert result.exit_code == 0
        assert "name/id mismatches merged by name: 7" in result.output

    def test_sync_remote_custom_api_url(self, runner):
        stats = {
            "sectors_created": 0,
            "subsectors_created": 0,
            "indicators_created": 0,
            "indicators_updated": 0,
            "skipped": 0,
        }
        custom_url = "https://custom.example.com/api/indicators"
        with patch(
            "app.services.indicators.remote_sync_service.sync_remote_indicator_bank",
            return_value=stats,
        ) as mock_sync:
            result = runner.invoke(
                args=[
                    "indicatorbank",
                    "sync-remote",
                    "--api-key",
                    "key",
                    "--api-url",
                    custom_url,
                ],
            )

        assert result.exit_code == 0
        mock_sync.assert_called_once_with(
            api_url=custom_url,
            api_key="key",
            limit=None,
            apply=False,
        )

    def test_sync_remote_api_key_from_env(self, runner):
        """API key from environment variable should work."""
        stats = {
            "sectors_created": 0,
            "subsectors_created": 0,
            "indicators_created": 0,
            "indicators_updated": 0,
            "skipped": 0,
        }
        with patch(
            "app.services.indicators.remote_sync_service.sync_remote_indicator_bank",
            return_value=stats,
        ):
            result = runner.invoke(
                args=["indicatorbank", "sync-remote"],
                env={"IFRC_INDICATORBANK_API_KEY": "env-api-key"},
            )

        assert result.exit_code == 0
