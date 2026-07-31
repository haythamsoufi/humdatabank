"""Synthetic SG Report workbooks for P&B pipeline tests."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from pb_figures.defaults import default_translations_bundle


def _translations_sheet() -> pd.DataFrame:
    translations, _, _ = default_translations_bundle()
    rows = []
    for code, langs in translations.items():
        rows.append(
            {
                "id": code,
                "EN": langs.get("English", ""),
                "FR": langs.get("French", ""),
                "SP": langs.get("Spanish", ""),
                "AR": langs.get("Arabic", ""),
            }
        )
    return pd.DataFrame(rows)


def _section_order_sheet(section_order: dict[str, list[str]]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    order = 1
    for part, sections in section_order.items():
        for section in sections:
            rows.append({"part": part, "section": section, "order": order})
            order += 1
    return pd.DataFrame(rows)


def write_test_workbook(
    path: Path,
    *,
    mapping_rows: list[dict[str, object]],
    section_order: dict[str, list[str]] | None = None,
    final_rows: list[dict[str, object]] | None = None,
) -> Path:
    """Write a minimal valid SG Report workbook for pipeline integration tests."""
    if section_order is None:
        section_order = {
            "cc": ["CC1"],
            "sp": ["SP1"],
            "ef": ["EF1"],
        }

    mapping = pd.DataFrame(mapping_rows)
    if final_rows is None:
        final_rows = [
            {
                "Index": index + 1,
                "Strategic Priority / Enabling Function": row["Strategic Priority / Enabling Function"],
                "ID": row["ID"],
                "Source": row.get("Source", "Manual"),
                "Year": row.get("Year", "2027"),
                "Value": row.get("Value", 100),
                "Implementing": row.get("Implementing", 10),
                "Count": row.get("Count", 5),
            }
            for index, row in enumerate(mapping_rows)
        ]
    final = pd.DataFrame(final_rows)
    total_reported = pd.DataFrame(
        {
            "Source": ["Manual", "FDRS", "UPR"],
            "Year": ["2027", "2027", "2027"],
            "TotalReported": [10, 84, 143],
        }
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        empty = pd.DataFrame()
        empty.to_excel(writer, sheet_name="Mapping", index=False, startrow=3)
        mapping.to_excel(writer, sheet_name="Mapping", index=False, startrow=3)
        final.to_excel(writer, sheet_name="Final", index=False)
        total_reported.to_excel(writer, sheet_name="TotalReported", index=False)
        _translations_sheet().to_excel(writer, sheet_name="Translations", index=False)
        _section_order_sheet(section_order).to_excel(writer, sheet_name="SectionOrder", index=False)
    return path


def sp1_mapping_row(**overrides: object) -> dict[str, object]:
    row = {
        "Strategic Priority / Enabling Function": "SP1",
        "ID": "618",
        "Source": "Manual",
        "English": "Example indicator",
        "SP EN": "Strategic Priority 1",
        "Type": "Cumulative",
        "Unit": "People",
    }
    row.update(overrides)
    return row


def cumulative_docx_item() -> dict[str, object]:
    """Minimal cumulative indicator payload used by Word line-chart assets."""
    return {
        "label": "People reached",
        "values": [10.0, 20.0, 30.0, 40.0, 50.0],
        "value_labels": ["10", "20", "30", "40", "50"],
        "years": ["2023", "2024", "2025", "2026", "2027"],
        "reporting": ["8", "18", "28", "38", "48"],
        "implementing": ["5", "10", "15", "20", "25"],
        "annual_target": 45.0,
        "annual_target_label": "45",
    }
