"""
Regression tests for Backoffice/scripts layout and app wiring.

These tests import real script modules (no mocks) and verify admin/CLI
routes invoke subprocesses with the correct working directory.
"""

from __future__ import annotations

import importlib
import importlib.util
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

BACKOFFICE_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = BACKOFFICE_ROOT / "scripts"

# Modules the app imports via ``from scripts.<category>.<module> import …``.
APP_SCRIPT_MODULES = (
    "scripts.seeding.seed_email_templates",
    "scripts.seeding.seed_campaign_email_templates",
    "scripts.ci.check_unsafe_gettext_embedding",
)

# Importable pipeline modules (live under scripts/imports on sys.path).
IMPORTS_MODULES = (
    "import_upr_excel_data",
    "import_fdrs_form_data",
    "upr_import_versioning",
    "upr_import_warnings",
    "upr_country_reporting_excel_template",
    "fdrs_sync_constants",
)

I18N_SCRIPTS = (
    "compile_translations.py",
    "extract_update_translations.py",
    "sync_persistent_translations.py",
)

# Referenced from entrypoint.sh / Docker (must exist on disk).
OPS_WIRED_SCRIPTS = (
    ("i18n", "sync_persistent_translations.py"),
    ("seeding", "init_data.py"),
)


class TestScriptLayout:
    def test_i18n_scripts_exist(self):
        i18n_dir = SCRIPTS_ROOT / "i18n"
        for name in I18N_SCRIPTS:
            assert (i18n_dir / name).is_file(), f"missing scripts/i18n/{name}"

    def test_seeding_scripts_exist(self):
        seeding = SCRIPTS_ROOT / "seeding"
        for name in ("seed_email_templates.py", "seed_campaign_email_templates.py", "init_data.py"):
            assert (seeding / name).is_file(), f"missing scripts/seeding/{name}"

    def test_imports_scripts_exist(self):
        imports_dir = SCRIPTS_ROOT / "imports"
        for name in IMPORTS_MODULES:
            assert (imports_dir / f"{name}.py").is_file(), f"missing scripts/imports/{name}.py"

    @pytest.mark.parametrize("category,filename", OPS_WIRED_SCRIPTS)
    def test_entrypoint_wired_scripts_exist(self, category, filename):
        assert (SCRIPTS_ROOT / category / filename).is_file(), (
            f"missing scripts/{category}/{filename} (referenced from entrypoint/Docker)"
        )

    def test_dockerfile_i18n_extract_path(self):
        dockerfile = BACKOFFICE_ROOT / "Dockerfile"
        text = dockerfile.read_text(encoding="utf-8")
        assert "scripts/i18n/extract_update_translations.py" in text

    def test_bootstrap_resolves_backoffice_root(self):
        scripts_path = str(SCRIPTS_ROOT)
        if scripts_path not in sys.path:
            sys.path.insert(0, scripts_path)
        from _bootstrap import backoffice_dir

        assert backoffice_dir(__file__) == BACKOFFICE_ROOT

    @pytest.mark.parametrize("module_name", APP_SCRIPT_MODULES)
    def test_app_script_modules_import(self, module_name):
        mod = importlib.import_module(module_name)
        assert mod is not None

    def test_seed_email_templates_exports(self):
        from scripts.seeding.seed_email_templates import DEFAULT_EMAIL_TEMPLATES, seed_templates

        assert callable(seed_templates)
        assert isinstance(DEFAULT_EMAIL_TEMPLATES, dict)
        assert DEFAULT_EMAIL_TEMPLATES

    def test_imports_modules_on_sys_path(self):
        imports_dir = str(SCRIPTS_ROOT / "imports")
        if imports_dir not in sys.path:
            sys.path.insert(0, imports_dir)
        for name in IMPORTS_MODULES:
            mod = importlib.import_module(name)
            assert mod is not None


class TestServiceScriptPaths:
    def test_upr_excel_import_service_resolves_imports(self, app):
        with app.app_context():
            from app.services.upr.excel_import_service import UprExcelImportService

            UprExcelImportService._upload_dir  # touch class; ensure app context
            from app.services.upr import excel_import_service as svc
            from app.services.upr import _scripts_path

            _scripts_path._SCRIPTS_DIR = None
            svc._ensure_scripts_in_path()
            import import_upr_excel_data  # noqa: F401

    def test_country_reporting_service_resolves_imports(self, app):
        with app.app_context():
            from app.services.upr import country_reporting_excel_service as svc
            from app.services.upr import _scripts_path

            _scripts_path._SCRIPTS_DIR = None
            svc._ensure_scripts_in_path()
            import upr_country_reporting_excel_template  # noqa: F401

    def test_unified_country_plan_service_resolves_imports(self, app):
        with app.app_context():
            from app.services.upr import unified_country_plan_excel_service as svc
            from app.services.upr import _scripts_path

            _scripts_path._SCRIPTS_DIR = None
            svc._ensure_scripts_in_path()
            import unified_country_plan_excel_template  # noqa: F401

    def test_scripts_path_helper_is_shared_across_services(self, app):
        """All three UPR Flask-facing services must resolve scripts/imports via the
        single shared helper (no per-module duplicate implementations)."""
        with app.app_context():
            from app.services.upr import (
                excel_import_service,
                unified_country_plan_excel_service,
                country_reporting_excel_service,
                _scripts_path,
            )

            assert excel_import_service._ensure_scripts_in_path is _scripts_path.ensure_scripts_in_path
            assert unified_country_plan_excel_service._ensure_scripts_in_path is _scripts_path.ensure_scripts_in_path
            assert country_reporting_excel_service._ensure_scripts_in_path is _scripts_path.ensure_scripts_in_path

    def test_data_sync_finds_fdrs_import_script(self, app):
        with app.app_context():
            from app.routes.admin import data_sync_imputation as dsi

            imports_dir = dsi._fdrs_imports_dir()
            assert Path(imports_dir).name == "imports"
            assert (Path(imports_dir) / "import_fdrs_form_data.py").is_file()


class TestTranslationsAdminScriptWiring:
    """Ensure compile/extract admin actions call scripts in scripts/i18n/."""

    def _post(self, client, url):
        return client.post(url, follow_redirects=False)

    def test_compile_invokes_i18n_compile_script(self, logged_in_client, app):
        i18n_dir = SCRIPTS_ROOT / "i18n"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            resp = self._post(logged_in_client, "/admin/translations/compile")
        assert resp.status_code in (302, 200)
        mock_run.assert_called_once()
        _cmd, kwargs = mock_run.call_args
        assert kwargs["cwd"] == str(i18n_dir)
        assert _cmd[0][1] == "compile_translations.py"

    def test_extract_invokes_i18n_extract_script(self, logged_in_client, app):
        i18n_dir = SCRIPTS_ROOT / "i18n"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            resp = self._post(logged_in_client, "/admin/translations/extract-update")
        assert resp.status_code in (302, 200)
        mock_run.assert_called_once()
        _cmd, kwargs = mock_run.call_args
        assert kwargs["cwd"] == str(i18n_dir)
        assert _cmd[0][1] == "extract_update_translations.py"


class TestCliSeedCommandsUseRealModulePath:
    """CLI must import seeding modules at their new path (guards against mock-only tests)."""

    def test_seed_email_templates_import_path(self):
        spec = importlib.util.find_spec("scripts.seeding.seed_email_templates")
        assert spec is not None
        assert "seeding" in (spec.origin or "")

    def test_seed_campaign_import_path(self):
        spec = importlib.util.find_spec("scripts.seeding.seed_campaign_email_templates")
        assert spec is not None
        assert "seeding" in (spec.origin or "")


class TestI18nCompileScriptRunnable:
    def test_compile_translations_exits_zero(self):
        script = SCRIPTS_ROOT / "i18n" / "compile_translations.py"
        result = subprocess.run(
            [sys.executable, str(script.name)],
            cwd=str(script.parent),
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stderr or result.stdout


class TestScriptReferenceGuard:
    def test_no_stale_flat_script_references(self):
        from scripts.ci import check_script_references

        assert check_script_references.main() == 0

    def test_no_one_level_short_bootstrap(self):
        from scripts.ci import check_script_bootstrap

        assert check_script_bootstrap.main() == 0
