"""Unit tests for pb_progress db_source helpers."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from plugins.pb_progress.db_source import (
    _default_source,
    _normalize_id,
    _resolve_source_for_availability,
    _section_from_area,
    copy_mapping_row,
    export_dataset_to_excel,
    resolve_build_years,
    validate_uploaded_workbook,
    WorkbookValidationError,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    "area,expected",
    [
        (None, "Cross-cutting"),
        ("", "Cross-cutting"),
        ("CC1", "Cross-cutting"),
        ("SP1", "SP1"),
        ("EF3", "EF3"),
    ],
)
def test_section_from_area(area, expected):
    assert _section_from_area(area) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "availability,expected",
    [
        ({"fdrs": True, "upr": False}, "FDRS"),
        ({"fdrs": False, "upr": True}, "UPR"),
        ({"fdrs": True, "upr": True}, None),
        ({"fdrs": False, "upr": False}, "Manual"),
    ],
)
def test_default_source(availability, expected):
    assert _default_source(availability) == expected


@pytest.mark.unit
def test_normalize_id_handles_nan():
    assert _normalize_id(float("nan")) == ""
    assert _normalize_id(" 754 ") == "754"


@pytest.mark.unit
def test_copy_mapping_row_is_deep_copy():
    row = {"id": "1", "sp_titles": {"en": "Title"}}
    copied = copy_mapping_row(row)
    copied["sp_titles"]["en"] = "Changed"
    assert row["sp_titles"]["en"] == "Title"


@pytest.mark.unit
@pytest.mark.parametrize(
    "source,availability,expected",
    [
        ("FDRS", {"fdrs": False, "upr": True}, "UPR"),
        ("UPR", {"fdrs": True, "upr": False}, "FDRS"),
        ("FDRS", {"fdrs": True, "upr": False}, "FDRS"),
        ("DREF", {"fdrs": False, "upr": True}, "UPR"),
        ("Katya", {"fdrs": False, "upr": False}, "Manual"),
    ],
)
def test_resolve_source_for_availability(source, availability, expected):
    assert _resolve_source_for_availability(source, availability) == expected


@pytest.mark.unit
def test_resolve_build_years_uses_all_when_none_selected(monkeypatch):
    monkeypatch.setattr(
        "plugins.pb_progress.db_source.list_available_years",
        lambda _version: ["2023", "2024", "2025"],
    )
    monkeypatch.setattr(
        "plugins.pb_progress.db_source.PBProgressDataStore.get_selected_years",
        lambda _version: [],
    )
    assert resolve_build_years("2025-2026") == {"2023", "2024", "2025"}


@pytest.mark.unit
def test_resolve_build_years_filters_to_selection(monkeypatch):
    monkeypatch.setattr(
        "plugins.pb_progress.db_source.list_available_years",
        lambda _version: ["2023", "2024", "2025"],
    )
    monkeypatch.setattr(
        "plugins.pb_progress.db_source.PBProgressDataStore.get_selected_years",
        lambda _version: ["2024", "2025"],
    )
    assert resolve_build_years("2025-2026") == {"2024", "2025"}


@pytest.mark.unit
def test_export_dataset_to_excel_always_writes_metadata_sheets(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "plugins.pb_progress.db_source.build_dataset",
        lambda _version: {
            "mapping": pd.DataFrame({"ID": ["1"]}),
            "final": pd.DataFrame({"ID": ["1"], "Year": ["2027"], "Value": [1]}),
            "total_reported": pd.DataFrame({"Source": ["Manual"], "Year": ["2027"], "TotalReported": [1]}),
            "translations": pd.DataFrame(),
            "sectionorder": pd.DataFrame(),
        },
    )

    output_path = tmp_path / "system_generated.xlsx"
    export_dataset_to_excel("2027-2028", output_path)

    with pd.ExcelFile(output_path) as workbook:
        assert "Translations" in workbook.sheet_names
        assert "SectionOrder" in workbook.sheet_names
        translations = pd.read_excel(workbook, sheet_name="Translations")
        section_order = pd.read_excel(workbook, sheet_name="SectionOrder")
    assert not translations.empty
    assert not section_order.empty


def _write_minimal_valid_workbook(path: Path) -> None:
    mapping = pd.DataFrame(
        {
            "Strategic Priority / Enabling Function": ["SP1"],
            "ID": ["1"],
            "Source": ["Manual"],
            "English": ["Indicator one"],
            "SP EN": ["Priority 1"],
            "Type": ["Cumulative"],
            "Unit": ["People"],
        }
    )
    final = pd.DataFrame(
        {
            "Index": [1],
            "Strategic Priority / Enabling Function": ["SP1"],
            "ID": ["1"],
            "Source": ["Manual"],
            "Year": ["2027"],
            "Value": [100],
            "Implementing": [10],
            "Count": [5],
        }
    )
    total_reported = pd.DataFrame({"Source": ["Manual"], "Year": ["2027"], "TotalReported": [10]})
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        empty = pd.DataFrame()
        empty.to_excel(writer, sheet_name="Mapping", index=False, startrow=3)
        mapping.to_excel(writer, sheet_name="Mapping", index=False, startrow=3)
        final.to_excel(writer, sheet_name="Final", index=False)
        total_reported.to_excel(writer, sheet_name="TotalReported", index=False)


@pytest.mark.unit
def test_validate_uploaded_workbook_accepts_minimal_valid_file(tmp_path):
    path = tmp_path / "SG Report.xlsx"
    _write_minimal_valid_workbook(path)

    summary = validate_uploaded_workbook(path)

    assert summary["valid"] is True
    assert summary["indicator_count"] == 1
    assert summary["row_count"] == 1
    assert summary["sections"] == ["SP1"]
    assert len(summary["warnings"]) == 2


@pytest.mark.unit
def test_validate_uploaded_workbook_rejects_missing_required_sheet(tmp_path):
    path = tmp_path / "bad.xlsx"
    mapping = pd.DataFrame({"ID": ["1"], "Strategic Priority / Enabling Function": ["SP1"]})
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        empty = pd.DataFrame()
        empty.to_excel(writer, sheet_name="Mapping", index=False, startrow=3)
        mapping.to_excel(writer, sheet_name="Mapping", index=False, startrow=3)

    with pytest.raises(WorkbookValidationError, match="Final"):
        validate_uploaded_workbook(path)


@pytest.mark.unit
def test_validate_uploaded_workbook_rejects_empty_mapping(tmp_path):
    path = tmp_path / "bad.xlsx"
    final = pd.DataFrame(
        {
            "Index": [1],
            "Strategic Priority / Enabling Function": ["SP1"],
            "ID": ["1"],
            "Source": ["Manual"],
            "Year": ["2027"],
            "Value": [100],
            "Implementing": [10],
            "Count": [5],
        }
    )
    total_reported = pd.DataFrame({"Source": ["Manual"], "Year": ["2027"], "TotalReported": [10]})
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame(
            {
                "Strategic Priority / Enabling Function": ["SP1"],
                "ID": [None],
                "Source": ["Manual"],
                "English": ["Should not count"],
            }
        ).to_excel(writer, sheet_name="Mapping", index=False, startrow=3)
        final.to_excel(writer, sheet_name="Final", index=False)
        total_reported.to_excel(writer, sheet_name="TotalReported", index=False)

    with pytest.raises(WorkbookValidationError, match="no indicator IDs"):
        validate_uploaded_workbook(path)
