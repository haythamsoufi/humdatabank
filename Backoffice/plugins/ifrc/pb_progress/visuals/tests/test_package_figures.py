"""Tests for figure ZIP packaging after Quarto HTML render."""

from __future__ import annotations

import importlib
import sys
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class PackageFiguresTests(unittest.TestCase):
    def test_module_imports_without_name_error(self) -> None:
        module = importlib.import_module("package_figures")
        self.assertTrue(callable(module.package_figures))
        self.assertFalse(hasattr(module, "FIGURES_DIR"))

    def test_package_figures_resolves_default_paths(self) -> None:
        import package_figures as module

        base = ROOT / "tests" / "fixtures" / "package_figures_defaults"
        figures = base / "Figures"
        output = base / "output"
        english = figures / "English"
        english.mkdir(parents=True, exist_ok=True)
        (english / "SP1.png").write_bytes(b"png")
        try:
            with patch.object(module, "resolve_figures_output", return_value=figures), patch.object(
                module, "resolve_report_output", return_value=output
            ):
                created = module.package_figures()
            self.assertTrue(any(path.name == "pb-report-figures-english.zip" for path in created))
        finally:
            for path in sorted(base.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()

    def test_package_figures_creates_language_and_all_archives(self) -> None:
        from package_figures import package_figures

        base = ROOT / "tests" / "fixtures" / "package_figures_run"
        figures = base / "Figures"
        output = base / "output"
        english = figures / "English"
        english.mkdir(parents=True, exist_ok=True)
        (english / "SP1.png").write_bytes(b"png")
        try:
            created = package_figures(figures, output, languages=("English",))
            names = {path.name for path in created}
            self.assertIn("pb-report-figures-english.zip", names)
            self.assertIn("pb-report-figures-all.zip", names)
            with zipfile.ZipFile(output / "pb-report-figures-english.zip") as zf:
                self.assertIn("English/SP1.png", zf.namelist())
        finally:
            for path in sorted(base.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()


if __name__ == "__main__":
    unittest.main()
