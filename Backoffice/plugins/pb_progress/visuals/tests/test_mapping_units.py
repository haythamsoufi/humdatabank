"""Tests for Mapping enrichment from Indicator bank."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pb_figures.data import (  # noqa: E402
    _enrich_mapping_from_bank,
    chart_type_from_measurement,
)


class ChartTypeMappingTests(unittest.TestCase):
    def test_yesno_maps_to_distinct(self) -> None:
        self.assertEqual(chart_type_from_measurement("YesNo"), "Distinct")

    def test_number_maps_to_cumulative(self) -> None:
        self.assertEqual(chart_type_from_measurement("Number"), "Cumulative")

    def test_percentage_defaults_to_cumulative(self) -> None:
        self.assertEqual(chart_type_from_measurement("Percentage"), "Cumulative")


class MappingBankEnrichmentTests(unittest.TestCase):
    def test_bank_enriches_type_unit_and_type_of_measurement(self) -> None:
        mapping = pd.DataFrame(
            {
                "ID": ["620", "644"],
                "Type": ["Distinct", "Cumulative"],
                "Unit": ["NSs", "Platforms"],
            }
        )
        excel = ROOT / "tests" / "fixtures" / "mapping_bank_fixture.xlsx"
        excel.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(excel) as writer:
            mapping.to_excel(writer, sheet_name="Mapping", index=False)
            pd.DataFrame(
                {
                    "indicatorId": ["620", "644"],
                    "typeOfMeasurement": ["Percentage", "YesNo"],
                    "unitOfMeasurement": ["Funds", "NS"],
                }
            ).to_excel(writer, sheet_name="Indicator bank", index=False)

        enriched = _enrich_mapping_from_bank(mapping, excel)
        row_620 = enriched.loc[enriched["ID"] == "620"].iloc[0]
        row_644 = enriched.loc[enriched["ID"] == "644"].iloc[0]
        self.assertEqual(row_620["Type"], "Cumulative")
        self.assertEqual(row_620["typeOfMeasurement"], "Percentage")
        self.assertEqual(row_620["Unit"], "Funds")
        self.assertEqual(row_644["Type"], "Distinct")
        self.assertEqual(row_644["typeOfMeasurement"], "YesNo")
        self.assertEqual(row_644["Unit"], "NS")
        excel.unlink(missing_ok=True)

    def test_missing_bank_sheet_leaves_mapping_values(self) -> None:
        mapping = pd.DataFrame(
            {
                "ID": ["644"],
                "Type": ["Distinct"],
                "Unit": ["NSs"],
            }
        )
        enriched = _enrich_mapping_from_bank(mapping, Path("missing.xlsx"))
        self.assertEqual(enriched.loc[0, "Type"], "Distinct")
        self.assertEqual(enriched.loc[0, "Unit"], "NSs")


if __name__ == "__main__":
    unittest.main()
