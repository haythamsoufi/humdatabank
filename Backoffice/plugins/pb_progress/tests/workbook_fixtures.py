"""Synthetic SG Report workbooks for P&B pipeline tests."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pandas as pd

from pb_figures.defaults import default_translations_bundle
from pb_figures.translations import clear_cache


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


def section_order_env_json(section_order: dict[str, list[str]]) -> str:
    rows: list[dict[str, object]] = []
    order = 1
    for part, sections in section_order.items():
        for section in sections:
            rows.append({"part": part, "section": section, "order": order})
            order += 1
    return json.dumps(rows)


def apply_section_order_env(monkeypatch, section_order: dict[str, list[str]] | None = None) -> None:
    if section_order is None:
        section_order = {"sp": ["SP1"]}
    monkeypatch.setenv("PB_REPORT_SECTION_ORDER", section_order_env_json(section_order))


def write_test_workbook(
    path: Path,
    *,
    mapping_rows: list[dict[str, object]],
    final_rows: list[dict[str, object]] | None = None,
    total_reported_rows: list[dict[str, object]] | None = None,
) -> Path:
    """Write a minimal valid SG Report workbook for pipeline integration tests."""
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
    if total_reported_rows is None:
        total_reported_rows = [
            {"Source": "Manual", "Year": "2027", "TotalReported": 10},
            {"Source": "FDRS", "Year": "2027", "TotalReported": 84},
            {"Source": "UPR", "Year": "2027", "TotalReported": 143},
        ]
    total_reported = pd.DataFrame(total_reported_rows)

    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        empty = pd.DataFrame()
        empty.to_excel(writer, sheet_name="Mapping", index=False, startrow=3)
        mapping.to_excel(writer, sheet_name="Mapping", index=False, startrow=3)
        final.to_excel(writer, sheet_name="Final", index=False)
        total_reported.to_excel(writer, sheet_name="TotalReported", index=False)
        _translations_sheet().to_excel(writer, sheet_name="Translations", index=False)
    return path


@contextmanager
def temporary_report_excel(
    path: Path,
    *,
    mapping_rows: list[dict[str, object]] | None = None,
    total_reported_rows: list[dict[str, object]] | None = None,
    year: str | None = None,
) -> Iterator[Path]:
    """Write a synthetic workbook and point PB_REPORT_EXCEL at it for the duration."""
    write_test_workbook(
        path,
        mapping_rows=mapping_rows or [sp1_mapping_row()],
        total_reported_rows=total_reported_rows,
    )
    previous = os.environ.get("PB_REPORT_EXCEL")
    previous_year = os.environ.get("PB_REPORT_YEAR")
    os.environ["PB_REPORT_EXCEL"] = str(path)
    if year is not None:
        os.environ["PB_REPORT_YEAR"] = year
    clear_cache()
    try:
        yield path
    finally:
        if previous is None:
            os.environ.pop("PB_REPORT_EXCEL", None)
        else:
            os.environ["PB_REPORT_EXCEL"] = previous
        if year is not None:
            if previous_year is None:
                os.environ.pop("PB_REPORT_YEAR", None)
            else:
                os.environ["PB_REPORT_YEAR"] = previous_year
        clear_cache()


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
