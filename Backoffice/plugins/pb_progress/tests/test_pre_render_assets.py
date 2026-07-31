"""Tests for pre_render asset generation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from pb_figures.data import load_mapping
from pre_render import _render_language_assets
from workbook_fixtures import sp1_mapping_row, write_test_workbook


@pytest.fixture
def staging_workbook(tmp_path):
    path = tmp_path / "staging_gap.xlsx"
    write_test_workbook(
        path,
        mapping_rows=[sp1_mapping_row()],
        section_order={"cc": ["CC1"], "sp": ["SP1"], "ef": ["EF1"]},
    )
    return path


@pytest.mark.pb_progress
@pytest.mark.unit
def test_pre_render_dashboard_reuses_existing_chart_assets(staging_workbook, monkeypatch) -> None:
    """Dashboard PNG step must not re-render chart PNGs already created for embed."""
    monkeypatch.setenv("PB_REPORT_EXCEL", str(staging_workbook))
    monkeypatch.setenv("PB_REPORT_YEAR", "2027")
    mapping = load_mapping(staging_workbook)

    render_calls: list[bool] = []

    def track_render_section_assets(payload, assets_dir, *, language="English"):
        render_calls.append(True)
        return {}

    def fake_render_dashboard(*_args, render_assets=True, **_kwargs):
        assert render_assets is False
        return Path("fake.png")

    with patch("pre_render.render_section_assets", side_effect=track_render_section_assets), patch(
        "pre_render.render_dashboard", side_effect=fake_render_dashboard
    ):
        _render_language_assets(staging_workbook, "English", "html", mapping)

    assert len(render_calls) == 1
