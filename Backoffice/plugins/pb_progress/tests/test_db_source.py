"""Unit tests for pb_progress db_source helpers."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from plugins.pb_progress.db_source import (
    _chart_type_from_measurement,
    _default_source,
    _indicator_labels,
    _normalize_id,
    _normalize_type_of_measurement,
    _resolve_source_for_availability,
    _section_from_area,
    copy_mapping_row,
    export_dataset_to_excel,
    generate_system_dataset,
    import_config_from_excel,
    resolve_build_years,
    sync_mapping_from_indicator_bank,
    validate_uploaded_workbook,
    WorkbookValidationError,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    "area,expected",
    [
        (None, "CC1"),
        ("", "CC1"),
        ("CC1", "CC1"),
        ("Cross-cutting", "CC1"),
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


class _FakeIndicator:
    def __init__(
        self,
        *,
        aggregated_label: str | None = None,
        name: str = "Main label",
        aggregated_label_translations: dict | None = None,
        name_translations: dict | None = None,
        indicator_type: str = "number",
    ):
        self.aggregated_label = aggregated_label
        self.name = name
        self.aggregated_label_translations = aggregated_label_translations
        self.name_translations = name_translations
        self.type = indicator_type

    def get_aggregated_label_translation(self, language: str) -> str | None:
        translations = self.aggregated_label_translations or {}
        if isinstance(translations, dict) and language in translations:
            return translations[language]
        return self.aggregated_label

    def get_name_translation(self, language: str) -> str | None:
        translations = self.name_translations or {}
        if isinstance(translations, dict) and language in translations:
            return translations[language]
        return self.name


@pytest.mark.unit
def test_indicator_labels_prefer_aggregated_over_name():
    indicator = _FakeIndicator(aggregated_label="Aggregated EN", name="Main name")
    labels = _indicator_labels(indicator)
    assert labels["English"] == "Aggregated EN"
    assert "Main name" not in labels["English"]


@pytest.mark.unit
def test_indicator_labels_fall_back_to_name_when_aggregated_missing():
    indicator = _FakeIndicator(aggregated_label=None, name="Main label")
    labels = _indicator_labels(indicator)
    assert labels["English"] == "Main label"


@pytest.mark.unit
def test_indicator_labels_fall_back_to_name_translations():
    class Indicator(_FakeIndicator):
        def get_name_translation(self, language):
            return {"fr": "Libellé principal"}.get(language, self.name)

        def get_aggregated_label_translation(self, language):
            return self.aggregated_label

    indicator = Indicator(aggregated_label=None, name="Main label")
    labels = _indicator_labels(indicator)
    assert labels["English"] == "Main label"
    assert labels["French"] == "Libellé principal"


@pytest.mark.unit
def test_indicator_labels_fall_back_to_english_for_missing_translation():
    indicator = _FakeIndicator(
        aggregated_label="Aggregated EN",
        aggregated_label_translations={"fr": "Libellé FR"},
    )
    labels = _indicator_labels(indicator)
    assert labels["English"] == "Aggregated EN"
    assert labels["French"] == "Libellé FR"
    assert labels["Spanish"] == "Aggregated EN"
    assert labels["Arabic"] == "Aggregated EN"


@pytest.mark.unit
@pytest.mark.parametrize(
    "bank_type,expected",
    [
        ("yesno", "Distinct"),
        ("YesNo", "Distinct"),
        ("number", "Cumulative"),
        ("percentage", "Cumulative"),
        (None, "Cumulative"),
    ],
)
def test_chart_type_from_measurement(bank_type, expected):
    assert _chart_type_from_measurement(bank_type) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "bank_type,expected",
    [
        ("percentage", "Percentage"),
        ("percent", "Percentage"),
        ("number", "number"),
        (None, None),
    ],
)
def test_normalize_type_of_measurement(bank_type, expected):
    assert _normalize_type_of_measurement(bank_type) == expected


@pytest.mark.unit
def test_sync_mapping_derives_chart_type_from_bank(monkeypatch):
    saved: list[list[dict]] = []

    def fake_save(_version, rows):
        saved.append(rows)

    monkeypatch.setattr(
        "plugins.pb_progress.db_source.list_tagged_indicators",
        lambda _tag: [
            {
                "id": "101",
                "section": "SP1",
                "type": "Distinct",
                "unit": "NS",
                "fdrs_kpi": "KPI-1",
                "default_source": "FDRS",
                "source_availability": {"fdrs": True, "upr": False},
            }
        ],
    )
    monkeypatch.setattr("plugins.pb_progress.db_source.PBProgressDataStore.get_mapping_config", lambda _v: [])
    monkeypatch.setattr("plugins.pb_progress.db_source.PBProgressDataStore.save_mapping_config", fake_save)
    monkeypatch.setattr(
        "plugins.pb_progress.db_source.validate_mapping_config",
        lambda rows: rows,
    )

    summary = sync_mapping_from_indicator_bank("2025-2026")

    assert summary["added"] == 1
    row = saved[-1][0]
    assert row["type"] == "Distinct"
    assert row["unit"] == "NS"
    assert row["fdrs_kpi"] == "KPI-1"


@pytest.mark.unit
def test_sync_mapping_removes_untagged_rows(monkeypatch):
    saved: list[list[dict]] = []

    def fake_save(_version, rows):
        saved.append(rows)

    monkeypatch.setattr(
        "plugins.pb_progress.db_source.list_tagged_indicators",
        lambda _tag: [
            {
                "id": "101",
                "section": "SP1",
                "type": "Cumulative",
                "unit": "NS",
                "fdrs_kpi": None,
                "default_source": "FDRS",
                "source_availability": {"fdrs": True, "upr": False},
            }
        ],
    )
    monkeypatch.setattr(
        "plugins.pb_progress.db_source.PBProgressDataStore.get_mapping_config",
        lambda _v: [
            {"id": "101", "section": "SP1", "source": "FDRS", "tag_missing": True},
            {"id": "999", "section": "SP2", "source": "Manual", "tag_missing": True},
        ],
    )
    monkeypatch.setattr("plugins.pb_progress.db_source.PBProgressDataStore.save_mapping_config", fake_save)
    monkeypatch.setattr(
        "plugins.pb_progress.db_source.validate_mapping_config",
        lambda rows: rows,
    )

    summary = sync_mapping_from_indicator_bank("2025-2026")

    assert summary["removed"] == 1
    assert len(saved[-1]) == 1
    assert saved[-1][0]["id"] == "101"
    assert "tag_missing" not in saved[-1][0]


@pytest.mark.unit
def test_prune_untagged_mapping_rows(monkeypatch):
    from plugins.pb_progress.db_source import prune_untagged_mapping_rows

    monkeypatch.setattr(
        "plugins.pb_progress.db_source.list_tagged_indicators",
        lambda _tag: [{"id": "101"}, {"id": "102"}],
    )

    pruned, removed = prune_untagged_mapping_rows(
        "2025-2026",
        [
            {"id": "101", "tag_missing": True},
            {"id": "999"},
        ],
    )

    assert removed == 1
    assert [row["id"] for row in pruned] == ["101"]
    assert "tag_missing" not in pruned[0]


@pytest.mark.unit
def test_sync_mapping_refreshes_bank_metadata_for_existing_rows(monkeypatch):
    saved: list[list[dict]] = []

    def fake_save(_version, rows):
        saved.append(rows)

    monkeypatch.setattr(
        "plugins.pb_progress.db_source.list_tagged_indicators",
        lambda _tag: [
            {
                "id": "101",
                "section": "SP2",
                "type": "Distinct",
                "unit": "Platforms",
                "fdrs_kpi": "KPI-NEW",
                "default_source": "UPR",
                "source_availability": {"fdrs": False, "upr": True},
            }
        ],
    )
    monkeypatch.setattr(
        "plugins.pb_progress.db_source.PBProgressDataStore.get_mapping_config",
        lambda _v: [
            {
                "id": "101",
                "section": "SP1",
                "source": "FDRS",
                "type": "Cumulative",
                "unit": "NS",
                "fdrs_kpi": "KPI-OLD",
            }
        ],
    )
    monkeypatch.setattr("plugins.pb_progress.db_source.PBProgressDataStore.save_mapping_config", fake_save)
    monkeypatch.setattr(
        "plugins.pb_progress.db_source.validate_mapping_config",
        lambda rows: rows,
    )

    sync_mapping_from_indicator_bank("2025-2026")

    row = saved[-1][0]
    assert row["section"] == "SP2"
    assert row["type"] == "Distinct"
    assert row["unit"] == "Platforms"
    assert row["fdrs_kpi"] == "KPI-NEW"
    assert row["source"] == "UPR"


@pytest.mark.unit
def test_indicator_section_code_prefers_spef_link():
    from plugins.pb_progress.db_source import _indicator_section_code

    class Spef:
        code = "SP3"
        name = "Strategic Priority 3"

    class Indicator:
        area = None
        area_label = None
        spef_area = Spef()

    assert _indicator_section_code(Indicator()) == "SP3"


@pytest.mark.unit
def test_spef_section_titles_falls_back_to_catalog_by_area(monkeypatch):
    from plugins.pb_progress.db_source import _spef_section_titles

    class Spef:
        code = "EF3"
        name = "Resource Mobilisation"

        def get_name_translation(self, _lang: str) -> str:
            return ""

    class Indicator:
        area = "EF3"
        area_label = None
        spef_area = None

    monkeypatch.setattr(
        "plugins.pb_progress.db_source._spef_rows_by_code",
        lambda _codes: {"EF3": Spef()},
    )

    titles = _spef_section_titles(Indicator())
    assert titles["en"] == "Resource Mobilisation"


@pytest.mark.unit
def test_build_section_order_from_bank(monkeypatch):
    from plugins.pb_progress.db_source import build_section_order_from_bank

    class SpefRow:
        def __init__(self, code: str, sort_order: int):
            self.code = code
            self.sort_order = sort_order
            self.name = code
            self.is_active = True

        def get_name_translation(self, _lang: str) -> str:
            return ""

    class Indicator:
        def __init__(self, section_code: str):
            self.area = None
            self.spef_area = SpefRow(section_code, {"SP1": 1, "SP2": 2, "EF2": 3, "CC1": 0}[section_code])

    monkeypatch.setattr(
        "plugins.pb_progress.db_source._query_tagged_indicator_rows",
        lambda _tag: [
            Indicator("SP2"),
            Indicator("SP1"),
            Indicator("EF2"),
            Indicator("CC1"),
        ],
    )
    monkeypatch.setattr(
        "plugins.pb_progress.db_source._spef_rows_by_code",
        lambda codes: {
            code: SpefRow(code, {"SP1": 1, "SP2": 2, "EF2": 3, "CC1": 0}[code])
            for code in codes
        },
    )

    rows = build_section_order_from_bank("2025-2026")

    assert [row["section"] for row in rows] == ["CC1", "SP1", "SP2", "EF2"]
    assert [(row["part"], row["order"]) for row in rows] == [
        ("cc", 0),
        ("sp", 1),
        ("sp", 2),
        ("ef", 3),
    ]


@pytest.mark.unit
def test_build_mapping_dataframe_includes_type_of_measurement(monkeypatch):
    from unittest.mock import MagicMock

    from plugins.pb_progress.db_source import _build_mapping_dataframe

    class BankRow:
        id = 42
        type = "percentage"
        area = None
        area_label = None
        aggregated_label = "Agg label"
        aggregated_label_translations = None

        class _Spef:
            code = "SP1"
            name = "Strategic Priority 1"

            def get_name_translation(self, _lang: str) -> str:
                return ""

        spef_area = _Spef()

    monkeypatch.setattr(
        "plugins.pb_progress.db_source._load_indicators_by_id",
        lambda _ids: {"42": BankRow()},
    )

    df = _build_mapping_dataframe(
        [
            {
                "id": "42",
                "section": "SP1",
                "type": "Cumulative",
                "unit": "People",
                "source": "FDRS",
            }
        ]
    )

    assert df.loc[0, "typeOfMeasurement"] == "Percentage"
    assert df.loc[0, "English"] == "Agg label"
    assert df.loc[0, "Strategic Priority / Enabling Function"] == "SP1"
    assert df.loc[0, "SP EN"] == "Strategic Priority 1"


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
            "sectionorder": pd.DataFrame(
                [
                    {"part": "cc", "section": "CC1", "order": 1},
                    {"part": "sp", "section": "SP1", "order": 1},
                ]
            ),
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
def test_filter_editable_translations_drops_section_rows():
    from plugins.pb_progress.db_source import filter_editable_translations

    rows = filter_editable_translations(
        [
            {"id": "report.title", "EN": "Title"},
            {"id": "section.SP1", "EN": "Response"},
            {"id": "section.EF2", "EN": "EF title"},
            {"id": "ui.part.sp", "EN": "Strategic Priorities"},
        ]
    )
    assert [row["id"] for row in rows] == ["report.title", "ui.part.sp"]


@pytest.mark.unit
def test_get_editable_translations_config_prunes_section_rows(monkeypatch):
    from plugins.pb_progress.db_source import get_editable_translations_config

    stored = [
        {"id": "report.title", "EN": "Title"},
        {"id": "section.SP2", "EN": "Old manual title"},
    ]
    saved: list[list[dict]] = []

    monkeypatch.setattr(
        "plugins.pb_progress.db_source.PBProgressDataStore.get_translations_config",
        lambda _version: stored,
    )
    monkeypatch.setattr(
        "plugins.pb_progress.db_source.PBProgressDataStore.save_translations_config",
        lambda _version, rows: saved.append(rows) or True,
    )

    rows = get_editable_translations_config("2025-2026")
    assert [row["id"] for row in rows] == ["report.title"]
    assert saved == [[{"id": "report.title", "EN": "Title"}]]


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


def _write_workbook_with_section_order(path: Path, *, part: str = "sp") -> None:
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
    section_order = pd.DataFrame({"part": [part], "section": ["SP1"], "order": [1]})
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        empty = pd.DataFrame()
        empty.to_excel(writer, sheet_name="Mapping", index=False, startrow=3)
        mapping.to_excel(writer, sheet_name="Mapping", index=False, startrow=3)
        final.to_excel(writer, sheet_name="Final", index=False)
        total_reported.to_excel(writer, sheet_name="TotalReported", index=False)
        section_order.to_excel(writer, sheet_name="SectionOrder", index=False)


@pytest.mark.unit
def test_import_config_from_excel_validates_translations(tmp_path, monkeypatch):
    path = tmp_path / "SG Report.xlsx"
    _write_workbook_with_section_order(path)
    translations = pd.DataFrame({"id": ["report.title", "report.title"], "EN": ["One", "Two"]})
    with pd.ExcelWriter(path, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
        translations.to_excel(writer, sheet_name="Translations", index=False)
    monkeypatch.setattr(
        "plugins.pb_progress.db_source._excel_path_for_version",
        lambda _version: path,
    )
    monkeypatch.setattr(
        "plugins.pb_progress.db_source.validate_mapping_config",
        lambda rows: rows,
    )

    with pytest.raises(ValueError, match="Duplicate translation id"):
        import_config_from_excel("2025-2026")
