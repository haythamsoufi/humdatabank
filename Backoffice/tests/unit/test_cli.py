"""
Comprehensive tests for app/cli.py — targets 100% coverage.

Covers:
- reset_table_sequence_verbose (verbose/non-verbose, ok/fail paths)
- reset_form_data_sequence_helper
- CLI commands: sync-indicator-embeddings, generate-api-key,
  reset-activity-sequence, reset-form-data-sequence, reset-all-sequences,
  workflows sync/list/show, rbac seed, seed-email-templates
"""

import pytest
from unittest.mock import MagicMock, patch, call


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_workflow(
    id="wf-1",
    title="My Workflow",
    category="admin",
    roles=None,
    pages=None,
    steps=None,
    description="A description",
    prerequisites=None,
    tips=None,
):
    """Return a simple namespace object that mimics a workflow document."""
    from types import SimpleNamespace

    step = SimpleNamespace(step_number=1, title="Step 1", page="page1", selector="#btn")
    return SimpleNamespace(
        id=id,
        title=title,
        category=category,
        roles=roles or ["admin"],
        pages=pages or ["/admin"],
        steps=steps or [step],
        description=description,
        prerequisites=prerequisites or [],
        tips=tips or [],
    )


# ===========================================================================
# Unit tests for module-level helpers (no CLI runner needed)
# ===========================================================================

class TestResetTableSequenceVerbose:
    """Tests for reset_table_sequence_verbose helper."""

    def test_returns_true_when_ok(self):
        from app.cli import reset_table_sequence_verbose

        with patch("app.cli.reset_table_sequence", return_value=(True, "reset")) as mock_rts:
            ok, reason = reset_table_sequence_verbose("my_table", schema="public", verbose=True)

        assert ok is True
        assert reason == "reset"
        mock_rts.assert_called_once_with("my_table", schema="public")

    def test_no_echo_when_ok(self, capsys):
        from app.cli import reset_table_sequence_verbose

        with patch("app.cli.reset_table_sequence", return_value=(True, "reset")):
            reset_table_sequence_verbose("my_table", verbose=True)

        captured = capsys.readouterr()
        assert captured.err == ""

    def test_echoes_error_when_verbose_and_not_ok(self):
        """When ok=False and verbose=True, should echo to stderr."""
        from app.cli import reset_table_sequence_verbose

        with patch("app.cli.reset_table_sequence", return_value=(False, "table not found")):
            with patch("app.cli.click.echo") as mock_echo:
                ok, reason = reset_table_sequence_verbose("bad_table", verbose=True)

        assert ok is False
        assert reason == "table not found"
        mock_echo.assert_called_once_with("  [bad_table] table not found", err=True)

    def test_no_echo_when_not_verbose_and_not_ok(self):
        """When ok=False and verbose=False, should NOT echo."""
        from app.cli import reset_table_sequence_verbose

        with patch("app.cli.reset_table_sequence", return_value=(False, "no sequence")):
            with patch("app.cli.click.echo") as mock_echo:
                ok, reason = reset_table_sequence_verbose("bad_table", verbose=False)

        assert ok is False
        mock_echo.assert_not_called()

    def test_default_schema_is_public(self):
        from app.cli import reset_table_sequence_verbose

        with patch("app.cli.reset_table_sequence", return_value=(True, "reset")) as mock_rts:
            reset_table_sequence_verbose("any_table")

        mock_rts.assert_called_once_with("any_table", schema="public")


class TestResetFormDataSequenceHelper:
    """Tests for reset_form_data_sequence_helper."""

    def test_returns_true_on_success(self):
        from app.cli import reset_form_data_sequence_helper

        with patch("app.cli.reset_table_sequence", return_value=(True, "reset")):
            result = reset_form_data_sequence_helper()

        assert result is True

    def test_returns_false_on_failure(self):
        from app.cli import reset_form_data_sequence_helper

        with patch("app.cli.reset_table_sequence", return_value=(False, "no sequence")):
            result = reset_form_data_sequence_helper()

        assert result is False

    def test_calls_reset_for_form_data(self):
        from app.cli import reset_form_data_sequence_helper

        with patch("app.cli.reset_table_sequence", return_value=(True, "reset")) as mock_rts:
            reset_form_data_sequence_helper()

        mock_rts.assert_called_once_with("form_data")


# ===========================================================================
# CLI command tests via Flask test runner
# ===========================================================================

class TestSyncIndicatorEmbeddingsCommand:
    """Tests for `flask sync-indicator-embeddings`."""

    def test_success(self, runner, app):
        mock_svc = MagicMock()
        mock_svc.sync_all.return_value = (42, 0.0123)

        with patch(
            "app.services.indicators.resolution_service.IndicatorResolutionService",
            return_value=mock_svc,
        ):
            result = runner.invoke(args=["sync-indicator-embeddings"])

        assert result.exit_code == 0
        assert "Synced 42 indicator embeddings" in result.output
        assert "0.0123" in result.output

    def test_success_with_custom_batch_size(self, runner):
        mock_svc = MagicMock()
        mock_svc.sync_all.return_value = (10, 0.0050)

        with patch(
            "app.services.indicators.resolution_service.IndicatorResolutionService",
            return_value=mock_svc,
        ):
            result = runner.invoke(args=["sync-indicator-embeddings", "--batch-size", "50"])

        assert result.exit_code == 0
        mock_svc.sync_all.assert_called_once_with(batch_size=50)

    def test_exception_raises_and_echoes(self, runner):
        with patch(
            "app.services.indicators.resolution_service.IndicatorResolutionService",
            side_effect=RuntimeError("API down"),
        ):
            result = runner.invoke(args=["sync-indicator-embeddings"])

        assert result.exit_code != 0
        assert "API down" in result.output


class TestGenerateApiKeyCommand:
    """Tests for `flask generate-api-key`."""

    def test_user_not_found(self, runner, app):
        with app.app_context():
            with patch("app.models.User") as mock_user_class:
                mock_user_class.query.filter_by.return_value.first.return_value = None
                with patch("app.cli.db"):
                    result = runner.invoke(args=["generate-api-key", "missing@example.com"])

        assert result.exit_code == 0
        assert "not found" in result.output

    def test_user_found_generates_key(self, runner, app):
        mock_user = MagicMock()
        mock_user.email = "found@example.com"

        with patch("app.cli.db") as mock_db:
            with patch("app.cli.atomic") as mock_atomic:
                mock_atomic.return_value.__enter__ = MagicMock(return_value=None)
                mock_atomic.return_value.__exit__ = MagicMock(return_value=False)
                # Patch the User import inside the command
                with patch.dict("sys.modules", {}):
                    import importlib
                    import app.cli as cli_mod
                    with patch.object(cli_mod, "__builtins__", cli_mod.__builtins__):
                        # We need to patch the User.query inside the command context
                        with app.app_context():
                            from app.models import User
                            original_query = User.query

                            class FakeQuery:
                                @staticmethod
                                def filter_by(**kwargs):
                                    return FakeQuery

                                @staticmethod
                                def first():
                                    return mock_user

                            with patch.object(User, "query", FakeQuery):
                                result = runner.invoke(args=["generate-api-key", "found@example.com"])

        assert result.exit_code == 0
        assert "API key generated for found@example.com" in result.output


class TestResetActivitySequenceCommand:
    """Tests for `flask reset-activity-sequence`."""

    def test_success_path(self, runner):
        with patch("app.cli.reset_table_sequence_verbose", return_value=(True, "reset")):
            result = runner.invoke(args=["reset-activity-sequence"])

        assert result.exit_code == 0
        assert "Reset sequence for user_activity_log successfully" in result.output

    def test_skip_path(self, runner):
        with patch("app.cli.reset_table_sequence_verbose", return_value=(False, "no sequence")):
            result = runner.invoke(args=["reset-activity-sequence"])

        assert result.exit_code == 0
        assert "Skipped user_activity_log" in result.output

    def test_exception_path(self, runner):
        with patch(
            "app.cli.reset_table_sequence_verbose",
            side_effect=RuntimeError("DB error"),
        ):
            result = runner.invoke(args=["reset-activity-sequence"])

        assert result.exit_code != 0
        assert "Failed to reset sequence" in result.output


class TestResetFormDataSequenceCommand:
    """Tests for `flask reset-form-data-sequence`."""

    def test_success_path(self, runner):
        with patch("app.cli.reset_table_sequence_verbose", return_value=(True, "reset")):
            result = runner.invoke(args=["reset-form-data-sequence"])

        assert result.exit_code == 0
        assert "Reset sequence for form_data successfully" in result.output

    def test_skip_path(self, runner):
        with patch("app.cli.reset_table_sequence_verbose", return_value=(False, "no id col")):
            result = runner.invoke(args=["reset-form-data-sequence"])

        assert result.exit_code == 0
        assert "Skipped form_data" in result.output

    def test_exception_path(self, runner):
        with patch(
            "app.cli.reset_table_sequence_verbose",
            side_effect=Exception("boom"),
        ):
            result = runner.invoke(args=["reset-form-data-sequence"])

        assert result.exit_code != 0
        assert "Failed to reset sequence" in result.output


class TestResetAllSequencesCommand:
    """Tests for `flask reset-all-sequences`."""

    def test_list_tables_success(self, runner):
        with patch(
            "app.cli.get_tables_with_id_column",
            return_value=["user", "country"],
        ):
            result = runner.invoke(args=["reset-all-sequences", "--list-tables"])

        assert result.exit_code == 0
        assert "user" in result.output
        assert "country" in result.output

    def test_list_tables_empty(self, runner):
        with patch("app.cli.get_tables_with_id_column", return_value=[]):
            result = runner.invoke(args=["reset-all-sequences", "--list-tables"])

        assert result.exit_code == 0
        assert "(none)" in result.output

    def test_list_tables_exception(self, runner):
        with patch(
            "app.cli.get_tables_with_id_column",
            side_effect=Exception("cannot query"),
        ):
            result = runner.invoke(args=["reset-all-sequences", "--list-tables"])

        assert result.exit_code == 0
        assert "Could not list tables" in result.output

    def test_reset_all_success(self, runner):
        with patch("app.cli.get_tables_with_id_column", return_value=["user", "country"]):
            with patch(
                "app.cli.reset_table_sequence_verbose",
                return_value=(True, "reset"),
            ):
                result = runner.invoke(args=["reset-all-sequences"])

        assert result.exit_code == 0
        assert "Reset sequences for 2 tables" in result.output

    def test_reset_all_with_skip(self, runner):
        with patch("app.cli.get_tables_with_id_column", return_value=["user"]):
            with patch(
                "app.cli.reset_table_sequence_verbose",
                return_value=(False, "no sequence"),
            ):
                result = runner.invoke(args=["reset-all-sequences"])

        assert result.exit_code == 0
        assert "[SKIP]" in result.output
        assert "Reset sequences for 0 tables" in result.output

    def test_reset_all_with_table_exception(self, runner):
        with patch("app.cli.get_tables_with_id_column", return_value=["bad_table"]):
            with patch(
                "app.cli.reset_table_sequence_verbose",
                side_effect=Exception("db error"),
            ):
                result = runner.invoke(args=["reset-all-sequences"])

        assert result.exit_code == 0
        assert "[FAIL]" in result.output

    def test_reset_all_zero_tables_warning(self, runner):
        with patch("app.cli.get_tables_with_id_column", return_value=[]):
            with patch("app.cli.reset_table_sequence_verbose"):
                result = runner.invoke(args=["reset-all-sequences"])

        assert result.exit_code == 0
        assert "Reset sequences for 0 tables" in result.output
        assert "No tables were reset" in result.output

    def test_verbose_flag_passed_through(self, runner):
        with patch("app.cli.get_tables_with_id_column", return_value=["user"]):
            with patch(
                "app.cli.reset_table_sequence_verbose",
                return_value=(True, "reset"),
            ) as mock_rtv:
                runner.invoke(args=["reset-all-sequences", "--verbose"])

        mock_rtv.assert_called_once_with("user", schema="public", verbose=True)

    def test_custom_schema(self, runner):
        with patch("app.cli.get_tables_with_id_column", return_value=[]) as mock_gtc:
            with patch("app.cli.reset_table_sequence_verbose"):
                runner.invoke(args=["reset-all-sequences", "--schema", "myschema"])

        mock_gtc.assert_called_once_with(schema="myschema")


# ===========================================================================
# Workflow commands
# ===========================================================================

class TestWorkflowsSyncCommand:
    """Tests for `flask workflows sync`."""

    def test_sync_success_with_workflows_and_cost(self, runner):
        mock_svc = MagicMock()
        mock_svc.get_all_workflows.return_value = [_make_workflow()]
        mock_svc.sync_to_vector_store.return_value = {
            "synced": 1,
            "updated": 0,
            "errors": [],
            "total_cost": 0.005,
        }

        with patch(
            "app.services.documentation.workflow_docs_service.WorkflowDocsService",
            return_value=mock_svc,
        ):
            result = runner.invoke(args=["workflows", "sync"])

        assert result.exit_code == 0
        assert "Synced: 1 new workflows" in result.output
        assert "Embedding cost:" in result.output

    def test_sync_success_with_errors(self, runner):
        mock_svc = MagicMock()
        mock_svc.get_all_workflows.return_value = [_make_workflow()]
        mock_svc.sync_to_vector_store.return_value = {
            "synced": 0,
            "updated": 1,
            "errors": ["embed failed for wf-1"],
            "total_cost": 0,
        }

        with patch(
            "app.services.documentation.workflow_docs_service.WorkflowDocsService",
            return_value=mock_svc,
        ):
            result = runner.invoke(args=["workflows", "sync"])

        assert result.exit_code == 0
        assert "Errors" in result.output
        assert "embed failed for wf-1" in result.output

    def test_sync_no_workflows(self, runner):
        mock_svc = MagicMock()
        mock_svc.get_all_workflows.return_value = []

        with patch(
            "app.services.documentation.workflow_docs_service.WorkflowDocsService",
            return_value=mock_svc,
        ):
            result = runner.invoke(args=["workflows", "sync"])

        assert result.exit_code == 0
        assert "No workflows found" in result.output

    def test_sync_import_error(self, runner):
        with patch.dict("sys.modules", {"app.services.documentation.workflow_docs_service": None}):
            result = runner.invoke(args=["workflows", "sync"])

        assert result.exit_code != 0

    def test_sync_general_exception(self, runner):
        with patch(
            "app.services.documentation.workflow_docs_service.WorkflowDocsService",
            side_effect=RuntimeError("vector store down"),
        ):
            result = runner.invoke(args=["workflows", "sync"])

        assert result.exit_code != 0
        assert "vector store down" in result.output

    def test_sync_no_cost_when_zero(self, runner):
        mock_svc = MagicMock()
        mock_svc.get_all_workflows.return_value = [_make_workflow()]
        mock_svc.sync_to_vector_store.return_value = {
            "synced": 1,
            "updated": 0,
            "errors": [],
            "total_cost": 0,
        }

        with patch(
            "app.services.documentation.workflow_docs_service.WorkflowDocsService",
            return_value=mock_svc,
        ):
            result = runner.invoke(args=["workflows", "sync"])

        assert result.exit_code == 0
        assert "Embedding cost" not in result.output


class TestWorkflowsListCommand:
    """Tests for `flask workflows list`."""

    def test_list_with_workflows(self, runner):
        wf1 = _make_workflow(id="wf-1", title="Add User", category="admin")
        wf2 = _make_workflow(id="wf-2", title="View Data", category="data", roles=["viewer"])

        mock_svc = MagicMock()
        mock_svc.get_all_workflows.return_value = [wf1, wf2]

        with patch(
            "app.services.documentation.workflow_docs_service.WorkflowDocsService",
            return_value=mock_svc,
        ):
            result = runner.invoke(args=["workflows", "list"])

        assert result.exit_code == 0
        assert "ADMIN:" in result.output
        assert "wf-1" in result.output
        assert "DATA:" in result.output

    def test_list_workflow_with_no_category(self, runner):
        wf = _make_workflow(id="wf-x", category=None)
        mock_svc = MagicMock()
        mock_svc.get_all_workflows.return_value = [wf]

        with patch(
            "app.services.documentation.workflow_docs_service.WorkflowDocsService",
            return_value=mock_svc,
        ):
            result = runner.invoke(args=["workflows", "list"])

        assert result.exit_code == 0
        assert "UNCATEGORIZED:" in result.output

    def test_list_no_workflows(self, runner):
        mock_svc = MagicMock()
        mock_svc.get_all_workflows.return_value = []

        with patch(
            "app.services.documentation.workflow_docs_service.WorkflowDocsService",
            return_value=mock_svc,
        ):
            result = runner.invoke(args=["workflows", "list"])

        assert result.exit_code == 0
        assert "No workflows found" in result.output

    def test_list_exception(self, runner):
        with patch(
            "app.services.documentation.workflow_docs_service.WorkflowDocsService",
            side_effect=Exception("fs error"),
        ):
            result = runner.invoke(args=["workflows", "list"])

        assert result.exit_code != 0
        assert "fs error" in result.output


class TestWorkflowsShowCommand:
    """Tests for `flask workflows show`."""

    def test_show_found_with_prerequisites_and_tips(self, runner):
        from types import SimpleNamespace

        step = SimpleNamespace(step_number=1, title="Open form", page="/admin", selector="#form")
        wf = _make_workflow(
            id="add-user",
            title="Add a User",
            category="admin",
            prerequisites=["Must be system manager"],
            tips=["Use Chrome"],
            steps=[step],
        )
        mock_svc = MagicMock()
        mock_svc.get_workflow_by_id.return_value = wf

        with patch(
            "app.services.documentation.workflow_docs_service.WorkflowDocsService",
            return_value=mock_svc,
        ):
            result = runner.invoke(args=["workflows", "show", "add-user"])

        assert result.exit_code == 0
        assert "Add a User" in result.output
        assert "Prerequisites:" in result.output
        assert "Must be system manager" in result.output
        assert "Tips:" in result.output
        assert "Use Chrome" in result.output
        assert "Open form" in result.output

    def test_show_found_without_prerequisites_or_tips(self, runner):
        wf = _make_workflow(id="simple-wf", prerequisites=[], tips=[])
        mock_svc = MagicMock()
        mock_svc.get_workflow_by_id.return_value = wf

        with patch(
            "app.services.documentation.workflow_docs_service.WorkflowDocsService",
            return_value=mock_svc,
        ):
            result = runner.invoke(args=["workflows", "show", "simple-wf"])

        assert result.exit_code == 0
        assert "Prerequisites:" not in result.output
        assert "Tips:" not in result.output

    def test_show_not_found(self, runner):
        mock_svc = MagicMock()
        mock_svc.get_workflow_by_id.return_value = None

        with patch(
            "app.services.documentation.workflow_docs_service.WorkflowDocsService",
            return_value=mock_svc,
        ):
            result = runner.invoke(args=["workflows", "show", "missing-id"])

        assert result.exit_code == 0
        assert 'not found' in result.output

    def test_show_exception(self, runner):
        with patch(
            "app.services.documentation.workflow_docs_service.WorkflowDocsService",
            side_effect=Exception("svc crashed"),
        ):
            result = runner.invoke(args=["workflows", "show", "any"])

        assert result.exit_code != 0
        assert "svc crashed" in result.output


class TestWorkflowsGenerateStaticCommand:
    """Tests for `flask workflows generate-static`."""

    def _mock_service(self, workflows=None, tours_by_lang=None, languages=("en", "fr")):
        """Build a mock WorkflowDocsService for the generate-static command.

        tours_by_lang: dict[str, dict|None] mapping language -> tour config
        returned for every workflow (None means "no steps, skip").
        """
        mock_svc = MagicMock()
        mock_svc.reload.return_value = None
        mock_svc.get_all_workflows.return_value = workflows if workflows is not None else [_make_workflow()]
        mock_svc.SUPPORTED_LANGUAGES = set(languages)

        tours_by_lang = tours_by_lang or {"en": {"name": "My Workflow", "steps": [{"page": "/admin"}], "language": "en"}}

        def _get_tour(workflow_id, language):
            return tours_by_lang.get(language)

        mock_svc.get_workflow_for_tour.side_effect = _get_tour
        return mock_svc

    def test_generate_static_writes_files(self, runner, app, tmp_path, monkeypatch):
        monkeypatch.setattr(app, "root_path", str(tmp_path))
        mock_svc = self._mock_service(
            tours_by_lang={
                "en": {"name": "My Workflow", "steps": [{"page": "/admin"}], "language": "en"},
                "fr": None,  # no French translation -> skipped
            }
        )

        with patch("app.services.documentation.workflow_docs_service.WorkflowDocsService", return_value=mock_svc):
            result = runner.invoke(args=["workflows", "generate-static"])

        assert result.exit_code == 0
        assert "Wrote 1 tour file(s)" in result.output
        assert "Skipped 1 workflow/language" in result.output

        written = tmp_path / "static" / "generated" / "tours" / "wf-1.en.json"
        assert written.exists()

        import json
        data = json.loads(written.read_text(encoding="utf-8"))
        assert data["steps"] == [{"page": "/admin"}]

        not_written = tmp_path / "static" / "generated" / "tours" / "wf-1.fr.json"
        assert not not_written.exists()

    def test_generate_static_no_workflows(self, runner, app, tmp_path, monkeypatch):
        monkeypatch.setattr(app, "root_path", str(tmp_path))
        mock_svc = self._mock_service(workflows=[])

        with patch("app.services.documentation.workflow_docs_service.WorkflowDocsService", return_value=mock_svc):
            result = runner.invoke(args=["workflows", "generate-static"])

        assert result.exit_code == 0
        assert "nothing to generate" in result.output

    def test_generate_static_mirrors_to_cdn_when_enabled(self, runner, app, tmp_path, monkeypatch):
        monkeypatch.setattr(app, "root_path", str(tmp_path))
        mock_svc = self._mock_service(languages=("en",))

        mock_storage = MagicMock()
        mock_storage.public_cdn_enabled.return_value = True

        with patch("app.services.documentation.workflow_docs_service.WorkflowDocsService", return_value=mock_svc), \
             patch("app.services.platform.storage_service", mock_storage):
            result = runner.invoke(args=["workflows", "generate-static"])

        assert result.exit_code == 0
        assert "Mirrored 1 file(s)" in result.output
        mock_storage.publish_to_static_cdn.assert_called_once()
        blob_name = mock_storage.publish_to_static_cdn.call_args[0][0]
        assert blob_name == "generated/tours/wf-1.en.json"

    def test_generate_static_cdn_disabled_message(self, runner, app, tmp_path, monkeypatch):
        monkeypatch.setattr(app, "root_path", str(tmp_path))
        mock_svc = self._mock_service(languages=("en",))

        mock_storage = MagicMock()
        mock_storage.public_cdn_enabled.return_value = False

        with patch("app.services.documentation.workflow_docs_service.WorkflowDocsService", return_value=mock_svc), \
             patch("app.services.platform.storage_service", mock_storage):
            result = runner.invoke(args=["workflows", "generate-static"])

        assert result.exit_code == 0
        assert "STATIC_CDN_URL not configured" in result.output
        mock_storage.publish_to_static_cdn.assert_not_called()

    def test_generate_static_cdn_mirror_failure_is_non_fatal(self, runner, app, tmp_path, monkeypatch):
        monkeypatch.setattr(app, "root_path", str(tmp_path))
        mock_svc = self._mock_service(languages=("en",))

        mock_storage = MagicMock()
        mock_storage.public_cdn_enabled.return_value = True
        mock_storage.publish_to_static_cdn.side_effect = RuntimeError("blob unreachable")

        with patch("app.services.documentation.workflow_docs_service.WorkflowDocsService", return_value=mock_svc), \
             patch("app.services.platform.storage_service", mock_storage):
            result = runner.invoke(args=["workflows", "generate-static"])

        assert result.exit_code == 0
        assert "CDN mirror failed" in result.output
        # Local file is still written even if the CDN mirror fails.
        assert (tmp_path / "static" / "generated" / "tours" / "wf-1.en.json").exists()

    def test_generate_static_general_exception(self, runner):
        with patch(
            "app.services.documentation.workflow_docs_service.WorkflowDocsService",
            side_effect=RuntimeError("svc crashed"),
        ):
            result = runner.invoke(args=["workflows", "generate-static"])

        assert result.exit_code != 0
        assert "svc crashed" in result.output


class TestRbacSeedCommand:
    """Tests for `flask rbac seed`."""

    def test_seed_success(self, runner):
        stats = {
            "created_permissions": 10,
            "updated_permissions": 2,
            "created_roles": 3,
            "updated_roles": 1,
            "created_role_permission_links": 20,
            "deleted_role_permission_links": 5,
        }
        with patch(
            "app.services.organization.rbac_seed_service.seed_rbac_permissions_and_roles",
            return_value=stats,
        ):
            result = runner.invoke(args=["rbac", "seed"])

        assert result.exit_code == 0
        assert "RBAC seed complete" in result.output
        assert "10 created" in result.output
        assert "3 created" in result.output
        assert "20 created" in result.output


class TestSeedEmailTemplatesCommand:
    """Tests for `flask seed-email-templates`."""

    def test_seed_without_force(self, runner):
        stats = {
            "email": {"seeded": 5, "skipped": 2},
            "metadata": {"seeded": 3, "skipped": 1},
        }
        with patch("scripts.seeding.seed_email_templates.seed_templates", return_value=stats):
            result = runner.invoke(args=["seed-email-templates"])

        assert result.exit_code == 0
        assert "5 seeded" in result.output
        assert "2 skipped" in result.output

    def test_seed_with_force(self, runner):
        stats = {
            "email": {"seeded": 7, "skipped": 0},
            "metadata": {"seeded": 4, "skipped": 0},
        }
        with patch("scripts.seeding.seed_email_templates.seed_templates", return_value=stats) as mock_seed:
            result = runner.invoke(args=["seed-email-templates", "--force"])

        assert result.exit_code == 0
        mock_seed.assert_called_once_with(force=True)


class TestSeedCampaignEmailTemplatesCommand:
    def test_seed_campaign_without_force(self, runner):
        stats = {"email": {"seeded": 2, "skipped": 1}}
        with patch("scripts.seeding.seed_campaign_email_templates.seed_campaign_templates", return_value=stats):
            result = runner.invoke(args=["seed-campaign-email-templates"])
        assert result.exit_code == 0
        assert "2 seeded" in result.output
