"""Integration tests for workbook → pre_render body generation."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from pb_figures.data import build_model, load_mapping  # noqa: E402
from pb_figures.layouts import section_has_indicators  # noqa: E402
from pb_figures.payload import build_payload  # noqa: E402
from pb_figures.report_meta import report_parts  # noqa: E402
from pb_figures.workbook_validation import sections_without_indicators  # noqa: E402
from pre_render import _generate_body  # noqa: E402
from workbook_fixtures import sp1_mapping_row, write_test_workbook  # noqa: E402


class WorkbookPipelineIntegrationTests(unittest.TestCase):
    def test_sections_without_indicators_detects_cc1_gap(self) -> None:
        workbook = ROOT / "tests" / "fixtures" / "cc1_no_mapping.xlsx"
        write_test_workbook(
            workbook,
            mapping_rows=[sp1_mapping_row()],
            section_order={"cc": ["CC1"], "sp": ["SP1"], "ef": ["EF1"]},
        )
        try:
            missing = sections_without_indicators(workbook)
            self.assertIn("CC1", missing)
            self.assertNotIn("SP1", missing)
        finally:
            workbook.unlink(missing_ok=True)

    def test_generate_body_skips_cc1_when_mapping_empty(self) -> None:
        workbook = ROOT / "tests" / "fixtures" / "body_cc1_skip.xlsx"
        write_test_workbook(
            workbook,
            mapping_rows=[sp1_mapping_row()],
            section_order={"cc": ["CC1"], "sp": ["SP1"], "ef": ["EF1"]},
        )
        body_path = ROOT / "tests" / "fixtures" / "_body_test.qmd"
        os.environ["PB_REPORT_EXCEL"] = str(workbook)
        try:
            model = build_model(workbook)
            mapping = load_mapping(workbook)
            _generate_body(body_path, model, ("English",), workbook, mapping)
            body = body_path.read_text(encoding="utf-8")
            self.assertIn("Strategic Priorities", body)
            self.assertIn("report-figure", body)
            self.assertNotIn("section-cc1", body)
        finally:
            os.environ.pop("PB_REPORT_EXCEL", None)
            workbook.unlink(missing_ok=True)
            body_path.unlink(missing_ok=True)

    def test_build_payload_raises_for_unmapped_section(self) -> None:
        """Document guardrail: callers must skip sections without Mapping rows."""
        workbook = ROOT / "tests" / "fixtures" / "payload_cc1.xlsx"
        write_test_workbook(workbook, mapping_rows=[sp1_mapping_row()])
        try:
            model = build_model(workbook)
            mapping = load_mapping(workbook)
            with self.assertRaisesRegex(ValueError, "No indicators configured for CC1"):
                build_payload(model, "CC1", "English", mapping=mapping)
        finally:
            workbook.unlink(missing_ok=True)


class SGReportWorkbookScanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workbooks: list[tuple[str, Path]] = []
        local = ROOT / "SG Report.xlsx"
        if local.is_file():
            cls.workbooks.append(("bundled", local))
        uploaded = (
            ROOT.parents[1]
            / "instance"
            / "uploads"
            / "pb_progress"
            / "source"
            / "SG_Report.xlsx"
        )
        if uploaded.is_file():
            cls.workbooks.append(("uploaded", uploaded))

    def test_mapped_sections_build_payload_without_error(self) -> None:
        if not self.workbooks:
            self.skipTest("No SG Report workbook available locally")
        failures: list[str] = []
        for label, workbook in self.workbooks:
            os.environ["PB_REPORT_EXCEL"] = str(workbook)
            try:
                model = build_model(workbook)
                mapping = load_mapping(workbook)
                for part in report_parts(workbook):
                    for section in part["sections"]:
                        if not section_has_indicators(mapping, section):
                            continue
                        try:
                            build_payload(model, section, "English", mapping=mapping)
                        except Exception as exc:
                            failures.append(f"{label}:{section}: {exc}")
            finally:
                os.environ.pop("PB_REPORT_EXCEL", None)
        if failures:
            self.fail("build_payload failed for mapped sections:\n" + "\n".join(failures))

    def test_report_sections_without_indicators_are_reported(self) -> None:
        if not self.workbooks:
            self.skipTest("No SG Report workbook available locally")
        for label, workbook in self.workbooks:
            missing = sections_without_indicators(workbook)
            with self.subTest(workbook=label):
                # Informational: empty CC1-style gaps must not crash body generation.
                for section in missing:
                    self.assertRegex(section, r"^(CC|SP|EF)\d+$")


if __name__ == "__main__":
    unittest.main()
