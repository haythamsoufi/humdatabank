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
            ["Backoffice/plugins/upr_visuals/static/css/upr-visuals.css"],
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
            ["Backoffice/plugins/upr_visuals/raster.py"],
            BACKOFFICE_ROOT,
        )
        assert plan.mode == "selected"
        assert "plugins/upr_visuals/tests/test_raster.py" in plan.targets
        assert plan.needs_render_libs is True

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
