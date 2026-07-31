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
    generate_system_dataset,
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
    assert any("Translations" in warning for warning in summary["warnings"])
    assert any("SectionOrder" in warning for warning in summary["warnings"])
    assert "SP1" not in summary["sections_without_indicators"]
    assert len(summary["sections_without_indicators"]) >= 1


@pytest.mark.unit
def test_validate_uploaded_workbook_warns_on_section_order_gaps(tmp_path):
    path = tmp_path / "section_gap.xlsx"
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
    translations = pd.DataFrame({"id": ["report.title"], "EN": ["Title"]})
    section_order = pd.DataFrame(
        [
            {"part": "cc", "section": "CC1", "order": 1},
            {"part": "sp", "section": "SP1", "order": 2},
        ]
    )
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        empty = pd.DataFrame()
        empty.to_excel(writer, sheet_name="Mapping", index=False, startrow=3)
        mapping.to_excel(writer, sheet_name="Mapping", index=False, startrow=3)
        final.to_excel(writer, sheet_name="Final", index=False)
        total_reported.to_excel(writer, sheet_name="TotalReported", index=False)
        translations.to_excel(writer, sheet_name="Translations", index=False)
        section_order.to_excel(writer, sheet_name="SectionOrder", index=False)

    summary = validate_uploaded_workbook(path)

    assert summary["valid"] is True
    assert summary["sections_without_indicators"] == ["CC1"]
    assert any("CC1" in warning for warning in summary["warnings"])


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


@pytest.mark.unit
def test_validate_translations_config_normalizes_rows():
    from plugins.pb_progress.db_source import validate_translations_config

    rows = validate_translations_config([{"id": "report.title", "EN": " Title ", "FR": "Titre"}])
    assert rows == [{"id": "report.title", "EN": "Title", "FR": "Titre", "SP": "", "AR": ""}]


@pytest.mark.unit
def test_validate_translations_config_rejects_duplicate_ids():
    from plugins.pb_progress.db_source import validate_translations_config

    with pytest.raises(ValueError, match="Duplicate translation id"):
        validate_translations_config(
            [
                {"id": "report.title", "EN": "One"},
                {"id": "report.title", "EN": "Two"},
            ]
        )


@pytest.mark.unit
def test_validate_section_order_config_normalizes_part():
    from plugins.pb_progress.db_source import validate_section_order_config

    rows = validate_section_order_config([{"part": "SP", "section": "SP1", "order": "2"}])
    assert rows == [{"part": "sp", "section": "SP1", "order": 2}]


@pytest.mark.unit
def test_validate_section_order_config_rejects_invalid_part():
    from plugins.pb_progress.db_source import validate_section_order_config

    with pytest.raises(ValueError, match="Invalid section part"):
        validate_section_order_config([{"part": "bad", "section": "SP1", "order": 1}])


@pytest.mark.unit
def test_generate_system_dataset_uploads_without_downloading_blob(monkeypatch):
    uploaded: dict[str, object] = {}

    def fake_upload(category, rel, data):
        uploaded["category"] = category
        uploaded["rel"] = rel
        uploaded["size"] = len(data)

    monkeypatch.setattr("plugins.pb_progress.db_source.storage_service.upload", fake_upload)

    def fail_get_absolute_path(*_args, **_kwargs):
        raise AssertionError("get_absolute_path must not be used when creating a new system dataset")

    monkeypatch.setattr(
        "plugins.pb_progress.db_source.storage_service.get_absolute_path",
        fail_get_absolute_path,
    )
    monkeypatch.setattr(
        "plugins.pb_progress.db_source.export_dataset_to_excel",
        lambda _version, path: Path(path).write_bytes(b"PK fake xlsx"),
    )
    monkeypatch.setattr(
        "plugins.pb_progress.db_source.build_dataset",
        lambda _version: {
            "mapping": [{"id": "1"}],
            "final": [{"id": "1", "Year": "2027"}],
            "total_reported": [{"Year": "2027"}],
        },
    )

    summary = generate_system_dataset("2025-2026")

    assert uploaded["rel"] == "versions/2025-2026/source/system_generated.xlsx"
    assert uploaded["size"] > 0
    assert summary["mapping_rows"] == 1
    assert summary["final_rows"] == 1
    assert summary["total_reported_rows"] == 1
