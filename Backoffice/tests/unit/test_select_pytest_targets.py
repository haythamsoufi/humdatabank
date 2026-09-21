"""Unit tests for CI pytest target selection (no database)."""

from __future__ import annotations

from pathlib import Path

from scripts.ci.select_pytest_targets import (
    WORKFLOW_PATH,
    PytestPlan,
    plan_pytest_run,
)

BACKOFFICE_ROOT = Path(__file__).resolve().parents[2]


class TestPlanPytestRun:
    def test_css_only_skips(self):
        plan = plan_pytest_run(
            ["Backoffice/plugins/upr/static/css/upr.css"],
            BACKOFFICE_ROOT,
        )
        assert plan == PytestPlan(
            "skip",
            (),
            "Diff is non-Python (templates/static/docs)",
            False,
        )

    def test_template_only_skips(self):
        plan = plan_pytest_run(
            ["Backoffice/app/templates/admin/users.html"],
            BACKOFFICE_ROOT,
        )
        assert plan.mode == "skip"

    def test_conftest_alone_does_not_run_the_suite(self):
        plan = plan_pytest_run(["Backoffice/tests/conftest.py"], BACKOFFICE_ROOT)
        assert plan.mode == "skip"
        assert plan.targets == ()

    def test_workflow_maps_to_selector_tests_only(self):
        plan = plan_pytest_run([WORKFLOW_PATH], BACKOFFICE_ROOT)
        assert plan.mode == "selected"
        assert plan.targets == ("tests/unit/test_select_pytest_targets.py",)
        assert plan.needs_render_libs is False

    def test_requirements_alone_skips(self):
        plan = plan_pytest_run(["Backoffice/requirements.txt"], BACKOFFICE_ROOT)
        assert plan.mode == "skip"

    def test_migrations_alone_do_not_run_the_suite(self):
        plan = plan_pytest_run(
            ["Backoffice/migrations/versions/abc123_example.py"],
            BACKOFFICE_ROOT,
        )
        assert plan.mode == "skip"

    def test_changed_test_file_is_selected(self):
        rel = "tests/unit/test_select_pytest_targets.py"
        plan = plan_pytest_run([f"Backoffice/{rel}"], BACKOFFICE_ROOT)
        assert plan.mode == "selected"
        assert plan.targets == (rel,)
        assert plan.needs_render_libs is False

    def test_maps_audit_service_to_matching_unit_test(self):
        plan = plan_pytest_run(
            ["Backoffice/app/services/audit/trail_session_query.py"],
            BACKOFFICE_ROOT,
        )
        assert plan.mode == "selected"
        assert "tests/unit/test_services/test_audit_trail_session_query.py" in plan.targets

    def test_maps_plugin_module_to_plugin_test_file(self):
        plan = plan_pytest_run(
            ["Backoffice/plugins/upr/raster.py"],
            BACKOFFICE_ROOT,
        )
        assert plan.mode == "selected"
        assert "plugins/upr/tests/test_raster.py" in plan.targets
        assert plan.needs_render_libs is True

    def test_plugin_py_does_not_select_visuals_or_excel_suites(self):
        plan = plan_pytest_run(
            ["Backoffice/plugins/pb_progress/plugin.py"],
            BACKOFFICE_ROOT,
        )
        assert plan.mode == "selected"
        assert "tests/unit/test_plugins/test_plugin_metadata.py" in plan.targets
        assert "plugins/pb_progress/visuals/tests" not in plan.targets
        assert "plugins/pb_progress/tests" not in plan.targets
        assert plan.needs_render_libs is False

    def test_upr_plugin_py_maps_to_plugin_unit_tests_not_excel_suite(self):
        plan = plan_pytest_run(
            ["Backoffice/plugins/upr/plugin.py"],
            BACKOFFICE_ROOT,
        )
        assert "tests/unit/test_plugins/test_plugin_metadata.py" in plan.targets
        assert "tests/unit/test_plugins/test_upr_plugin.py" in plan.targets
        assert "tests/unit/test_plugins/test_upr_bulk_job.py" not in plan.targets
        assert "plugins/upr/tests" not in plan.targets
        assert plan.needs_render_libs is False

    def test_routes_py_maps_to_route_unit_tests_not_visuals(self):
        plan = plan_pytest_run(
            ["Backoffice/plugins/pb_progress/routes.py"],
            BACKOFFICE_ROOT,
        )
        assert "tests/unit/test_routes/test_pb_progress_routes.py" in plan.targets
        assert "tests/unit/test_plugins/test_plugin_metadata.py" in plan.targets
        assert "plugins/pb_progress/visuals/tests" not in plan.targets
        assert "plugins/upr/tests/test_routes.py" not in plan.targets
        assert plan.needs_render_libs is False

    def test_fdrs_routes_do_not_select_upr_test_routes(self):
        plan = plan_pytest_run(
            ["Backoffice/plugins/fdrs/routes.py"],
            BACKOFFICE_ROOT,
        )
        assert "tests/unit/test_plugins/test_fdrs_routes.py" in plan.targets
        assert "plugins/upr/tests/test_routes.py" not in plan.targets
        assert "tests/unit/test_plugins/test_fdrs_compliance_doc_matching.py" not in plan.targets

    def test_shared_metadata_module_maps_to_metadata_tests(self):
        plan = plan_pytest_run(
            ["Backoffice/plugins/metadata.py"],
            BACKOFFICE_ROOT,
        )
        assert plan == PytestPlan(
            "selected",
            ("tests/unit/test_plugins/test_plugin_metadata.py",),
            "Mapped changed files to tests",
            False,
        )

    def test_unmapped_python_skips_rather_than_full_suite(self, tmp_path: Path):
        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "no_tests_here.py").write_text("# dummy\n", encoding="utf-8")
        (tmp_path / "tests" / "unit").mkdir(parents=True)
        plan = plan_pytest_run(["Backoffice/app/no_tests_here.py"], tmp_path)
        assert plan.mode == "skip"
        assert "no matching tests" in plan.reason

    def test_non_backoffice_paths_are_ignored(self):
        plan = plan_pytest_run(["Website/app/page.tsx"], BACKOFFICE_ROOT)
        assert plan.mode == "skip"
        assert plan.reason == "No Backoffice files in the diff"

    def test_fake_tree_maps_stem_and_ignores_missing(self, tmp_path: Path):
        tests = tmp_path / "tests" / "unit" / "test_services"
        tests.mkdir(parents=True)
        match = tests / "test_foo.py"
        match.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
        (tmp_path / "app" / "services").mkdir(parents=True)
        (tmp_path / "app" / "services" / "foo.py").write_text("x = 1\n", encoding="utf-8")
        plan = plan_pytest_run(
            [
                "Backoffice/app/services/foo.py",
                "Backoffice/tests/unit/test_services/test_missing.py",
            ],
            tmp_path,
        )
        assert plan.mode == "selected"
        assert plan.targets == ("tests/unit/test_services/test_foo.py",)
