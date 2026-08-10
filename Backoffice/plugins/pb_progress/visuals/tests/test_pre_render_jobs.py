"""Tests for pre_render section-level parallel job planning."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pb_figures.config import build_workers
from pb_figures.data import load_mapping
from pre_render import SectionJob, _clean_build_workspace, _generate_assets, _section_jobs
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


@pytest.mark.unit
def test_clean_build_workspace_removes_stale_section_pngs(tmp_path, monkeypatch) -> None:
    figures = tmp_path / "Figures"
    english = figures / "English"
    english.mkdir(parents=True)
    (english / "CC1.png").write_bytes(b"current")
    stale = english / "Cross-cutting.png"
    stale.write_bytes(b"stale")

    monkeypatch.setattr("pre_render.resolve_figures_output", lambda: figures)
    monkeypatch.setattr("pre_render.resolve_report_output", lambda: tmp_path / "output")

    _clean_build_workspace(("English",), keep_sections={"CC1"})

    assert (english / "CC1.png").is_file()
    assert not stale.exists()


@pytest.mark.unit
def test_section_jobs_one_per_indicator_section(staging_workbook, monkeypatch) -> None:
    monkeypatch.setenv("PB_REPORT_EXCEL", str(staging_workbook))
    mapping = load_mapping(staging_workbook)
    jobs = _section_jobs(staging_workbook, ("English",), mapping, "html")
    assert jobs == [("English", "SP1", "html")]


@pytest.mark.unit
def test_generate_assets_uses_section_count_for_workers(staging_workbook, monkeypatch) -> None:
    """Single-language builds should parallelize across sections when capped > 1."""
    monkeypatch.setenv("PB_REPORT_EXCEL", str(staging_workbook))
    monkeypatch.setenv("PB_BUILD_WORKERS", "4")
    mapping = load_mapping(staging_workbook)
    languages = ("English",)

    with patch("pre_render.build_workers", wraps=build_workers) as mock_build_workers, patch(
        "pre_render._render_section_job",
        side_effect=lambda _excel, _lang, section, _renderer, _mapping, **_kw: (
            "English", section, 0, 1, [f"    {section}/ (text-only)"],
        ),
    ):
        charts, dashboards = _generate_assets(staging_workbook, languages, mapping)

    mock_build_workers.assert_called_once_with(1)
    assert charts == 0
    assert dashboards == 1


@pytest.mark.unit
def test_generate_assets_parallelizes_multiple_sections(tmp_path, monkeypatch) -> None:
    path = tmp_path / "multi_section.xlsx"
    write_test_workbook(
        path,
        mapping_rows=[
            sp1_mapping_row(**{"Strategic Priority / Enabling Function": "CC1", "ID": "101"}),
            sp1_mapping_row(**{"Strategic Priority / Enabling Function": "SP1", "ID": "618"}),
            sp1_mapping_row(**{"Strategic Priority / Enabling Function": "EF1", "ID": "901"}),
        ],
    )
    monkeypatch.setenv("PB_REPORT_EXCEL", str(path))
    monkeypatch.setenv("PB_BUILD_WORKERS", "4")
    mapping = load_mapping(path)
    jobs = _section_jobs(path, ("English",), mapping, "html")

    def fake_result(job: SectionJob):
        language, section, _renderer = job
        return language, section, 0, 1, [f"    {section}/ (text-only)"]

    job_to_future = {}
    for job in jobs:
        future = MagicMock()
        future.result.return_value = fake_result(job)
        job_to_future[job] = future

    mock_executor = MagicMock()
    mock_executor.__enter__.return_value = mock_executor
    mock_executor.submit.side_effect = lambda _fn, job: job_to_future[job]

    with patch("pre_render.build_workers", wraps=build_workers) as mock_build_workers, patch(
        "pre_render.ProcessPoolExecutor", return_value=mock_executor
    ) as mock_executor_cls, patch(
        "pre_render.as_completed", side_effect=lambda futures: list(futures)
    ):
        charts, dashboards = _generate_assets(path, ("English",), mapping)

    mock_build_workers.assert_called_once_with(3)
    mock_executor_cls.assert_called_once()
    assert charts == 0
    assert dashboards == 3
