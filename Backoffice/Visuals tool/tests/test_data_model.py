"""Integration checks against SG Report.xlsx when present."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from gb_figures.config import resolve_excel  # noqa: E402
from gb_figures.data import build_model  # noqa: E402


class DataModelIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        excel = ROOT / "SG Report.xlsx"
        cls.excel_available = excel.exists()
        cls.excel_path = excel

    def test_build_model_joins(self) -> None:
        if not self.excel_available:
            self.skipTest("SG Report.xlsx not present in workspace")
        model = build_model(self.excel_path)
        self.assertGreater(len(model), 0)
        self.assertIn("section", model.columns)
        self.assertIn("ID", model.columns)

    def test_resolve_excel_finds_workbook(self) -> None:
        if not self.excel_available:
            self.skipTest("SG Report.xlsx not present in workspace")
        resolved = resolve_excel(self.excel_path)
        self.assertTrue(resolved.exists())


if __name__ == "__main__":
    unittest.main()
