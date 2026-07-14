"""Unit tests for pb_progress db_source helpers."""

from __future__ import annotations

import pytest

from plugins.pb_progress.db_source import (
    _default_source,
    _normalize_id,
    _resolve_source_for_availability,
    _section_from_area,
    copy_mapping_row,
    resolve_build_years,
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
