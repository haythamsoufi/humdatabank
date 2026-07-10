"""Tests for Mapping.Unit enrichment from typeOfMeasurement."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pb_figures.data import _enrich_mapping_units  # noqa: E402


class MappingUnitEnrichmentTests(unittest.TestCase):
    def test_mapping_type_of_measurement_fills_empty_unit(self) -> None:
        mapping = pd.DataFrame(
            {
                "ID": ["644", "645"],
                "Unit": [None, "NSs"],
                "typeOfMeasurement": ["Percentage", "Number"],
            }
        )
        enriched = _enrich_mapping_units(mapping, Path("missing.xlsx"))
        self.assertEqual(enriched.loc[enriched["ID"] == "644", "Unit"].iloc[0], "Percentage")
        self.assertEqual(enriched.loc[enriched["ID"] == "645", "Unit"].iloc[0], "NSs")

    def test_indicator_bank_sheet_lookup_by_id(self) -> None:
        mapping = pd.DataFrame({"ID": ["644"], "Unit": [None]})
        excel = ROOT / "tests" / "fixtures" / "mapping_units_fixture.xlsx"
        excel.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(excel) as writer:
            mapping.to_excel(writer, sheet_name="Mapping", index=False)
            pd.DataFrame(
                {
                    "ID": ["644"],
                    "typeOfMeasurement": ["Percentage"],
                }
            ).to_excel(writer, sheet_name="Indicator bank", index=False)

        enriched = _enrich_mapping_units(mapping, excel)
        self.assertEqual(enriched.loc[0, "Unit"], "Percentage")
        excel.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
